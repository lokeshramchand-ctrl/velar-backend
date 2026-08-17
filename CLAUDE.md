# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Velar is a single async FastAPI service (`app.py`) that turns noisy financial transaction text (UPI references, bank SMS, POS narrations) or an uploaded Google Pay PDF statement into canonical merchant identity, spend category, behavioral fingerprints, anomaly signals, and grounded natural-language explanations. It is **one process**, not a microservice mesh: every router, ML engine, and pipeline module documented below runs in the same container, sharing one MongoDB client and one Milvus client via process-wide singletons (`database/mongo.py::db`, `database/milvus.py::vector_db`), imported directly (`from database.mongo import db`) rather than through FastAPI DI. There is no Celery/task queue/scheduler anywhere in this codebase, despite some code comments referencing one.

Full documentation portal: [`docs/README.md`](docs/README.md) (23 numbered docs + per-folder/per-file/per-endpoint deep dives + a 204-question interview bank). **`docs/16-known-issues-tech-debt.md`** is a historical fix log — where it conflicts with the current code, trust the code; it says so itself. The root `README.md`'s "no linter/CI" claim is now stale — see Tooling below.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt                       # runtime deps for the live API
pip install -r requirements-training.txt               # only if running training/finetune.py or evaluation/metrics.py

# Run the API (needs MongoDB + Milvus reachable, and a valid .env — see below)
python scripts/seed.py                                 # optional: seed canonical merchant data first
uvicorn app:app --reload --host 0.0.0.0 --port 8000
docker compose -f docker-compose_local.yaml up --build  # provisions MongoDB only; bring your own Milvus/Ollama

# Tests — the full suite needs a REAL, reachable MongoDB and Milvus (FastAPI TestClient
# triggers the real lifespan; nothing is mocked). VELAR_API_KEY in .env must literally
# equal "velar_test_key_123" — test_api.py hardcodes that value in its request headers.
pytest test_api.py -v
pytest test_api.py::test_categorize_valid_payload -v    # single test
pytest test_api.py -v -k "auth"                          # by keyword
bash scripts/test_pipeline.sh                             # manual, narrated E2E smoke test against a running server

# Lint / format (ruff config lives in pyproject.toml; frontend/ is excluded — it's a separate Flutter app)
ruff check .
ruff check --fix .
ruff format .
pre-commit install          # one-time; hooks: ruff --fix, trailing-whitespace, gitleaks, etc.
pre-commit run --all-files
```

### Required `.env` (app fails fast at startup if any of these are missing)

`MONGODB_URI`, `MILVUS_URI`, `EMBED_MODEL`, `LLM_MODEL`, `VELAR_API_KEY`, `JWT_SECRET_KEY` (rejected at startup if under 32 chars — `openssl rand -hex 32`). Optional with defaults/behavior worth knowing: `ADMIN_API_KEY` (unset → every admin-gated endpoint 503s rather than falling back to anything permissive — see Auth below), `MONGODB_DB_NAME` (`velar`), `OLLAMA_URI` / `OLLAMA_HOSTS` (comma-separated failover list; `OLLAMA_URI` wins if both set), `ENVIRONMENT` (`production`), `LOG_LEVEL` (`INFO` — DEBUG logs full Mongo command payloads including raw transaction data, so it's opt-in only). Full list: `core/config.py`.

## Architecture

### The "Phase" model

The codebase organizes itself into numbered Phases — this is literally how source comments label it (`# Phase 3 Endpoint`, `PHASE 0 & 15: ...`), not a doc invention. Each phase's folder is only reachable end-to-end if the phases before it have already run:

| Phase | Folder(s) | Reachable via |
|---|---|---|
| 1–3 Rules + noisy-text resolution | `engines/rule_engine.py`, `services/merchant_resolver.py` | `POST /v1/categorize`, `POST /v1/resolve` |
| 4 Memory / trust state machine | `memory/`, `repositories/profile_repository.py` | `POST /memory/update` |
| 5 Confidence wall | `engines/confidence_engine.py` | `POST /v1/confidence/evaluate` |
| 6 Behavioral features | `features/`, `behaviour/behavior_engine.py` | `POST /v1/pipelines/behavior/run(-all)` |
| 7 Embeddings + vector search | `embeddings/`, `milvus/` | `POST /v1/pipelines/embeddings/sync` |
| 8 UMAP + HDBSCAN clustering | `clustering/` | `POST /v1/pipelines/clustering/run` (lazily imported — a missing `umap-learn`/`scikit-learn` install only breaks this one endpoint) |
| 9, 11 Baseline ML + LoRA fine-tuning | `training/` | **Script-only** (`python training/train.py`), deliberately not wired to an endpoint — see Non-obvious facts |
| 10 Feedback / active learning | `feedback/` | `POST /v1/feedback/` |
| 12 Grounded RAG | `rag/` | `POST /v1/explain` |
| 13 Analytics | `analytics/`, `graphs/` | `GET /v1/analytics/*`, `/v1/pipelines/graph/*` |
| 14 Observability | `routers/observability.py` | Stub — no Evidently/MLflow wired up |
| 15 Auth | `core/security.py`, `core/jwt_auth.py` | Every router |

Since `docs/01-architecture.md` was written, a full product surface (`statements/`, `routers/statements.py` + `routers/jobs.py`) was added on top of this: **Statement PDF upload → async background-task pipeline → Transactions → Analytics → AI Insights**. `POST /statements/upload` validates/decrypts synchronously (fails fast, 422), returns `202` immediately, and does the actual parse → categorize → persist → profile → embed → analyze → insights work via `fastapi.BackgroundTasks` (in-process — same "no real task queue" caveat as everything else, but the `GET /jobs/{id}` polling contract wouldn't need to change if one were added later). See `docs/23-statements-pipeline.md`.

### Auth — three independent layers, composed per-route

1. **`X-Velar-API-Key`** (`core/security.py::validate_api_key`) — mounted via `dependencies=[Depends(...)]` on nearly every router in `app.py`. Authenticates the *calling application*, not an end user. Enforced before any handler runs, regardless of what else that handler requires.
2. **`Authorization: Bearer <JWT>`** (`core/jwt_auth.py::get_current_user`) — bound as a handler parameter (`current_user: User = Depends(...)`) only where a specific end user matters: `/auth/me`, `/v1/categorize`, every `GET /v1/analytics/*`, `/v1/feedback/`, statement endpoints. Endpoints operating on non-user-scoped data (`/v1/resolve`, `/memory/*`, `/v1/pipelines/*`, `/v1/observability/*`) stay API-key-only.
3. **`X-Velar-Admin-Key`** (`ADMIN_API_KEY`, `core/security.py::validate_admin_key`) — gates `routers/pipelines.py` (mounted with this as a *router-level* dependency, not per-handler) and `POST /app/releases`. Deliberately separate from `VELAR_API_KEY`, which ships inside every client app binary and is trivially extractable — not a safe gate for expensive, system-wide batch jobs. If `ADMIN_API_KEY` is unset, these routes 503 rather than silently allowing access.

### Non-obvious facts that will cost you time if you miss them

- **`/v1/explain` is architecturally forbidden from hallucinating.** If Milvus returns zero hits, `rag/context_builder.py` emits the literal string `"NO_CONTEXT_AVAILABLE"` and `rag/generator.py` short-circuits with an error response **without calling Ollama at all**. This is the core design guarantee of the RAG layer — don't "fix" it into always generating something.
- **`training/train.py` and `training/finetune.py` are intentionally not wired to any endpoint.** Both train on synthetic/mock data (their docstrings describe the intended real MongoDB queries, but that data-assembly pipeline doesn't exist yet), and `BaselineTrainer.run_benchmarks()` is a long-running synchronous CPU job that would block the event loop if called from a request handler. Don't expose them as routes without first solving both problems.
- **`feedback/retraining_queue.py::trigger_retraining_if_needed`** flips queued corrections to `"processing"` and stops — there is no executor. Wiring one up needs a real task queue, not a request-handler call to the trainer above (same blocking-event-loop problem).
- **Trust state machine thresholds** (`memory/state_machine.py`): `frequency >= 10` → `PERMANENT`, `>= 3` → `TEMPORARY`, else `EPHEMERAL`. `PERMANENT`/`ARCHIVED` don't demote through `evaluate_promotion`, but `memory/memory_manager.py::process_encounter` explicitly overrides an `ARCHIVED` profile back to `TEMPORARY` on any new encounter, bypassing the state machine for that one transition.
- **External connections resolve lazily, not at import time — this is a deliberate, repeated pattern.** `database/milvus.py`/`milvus/insert_vectors.py` and `core/ollama_client.py` both used to make blocking network calls at module-import time (crashing the whole app if Milvus/Ollama was briefly unreachable at startup, not just the feature that needed them); both now defer connection to `lifespan` (Milvus) or first actual use (Ollama, via `get_ollama_host()`). Preserve this pattern in any new external-service client.
- **Batch pipelines under `/v1/pipelines/*` are manually triggered only** — nothing schedules them. In a fresh environment, run `behavior/run-all` before expecting real data from `/v1/analytics/subscriptions` or the anomaly endpoint, and follow it with `embeddings/sync` before expecting `/v1/explain` to retrieve real context.
- **`requirements.txt`** is the live API's actual dependency list (what the Dockerfile installs); **`requirements-training.txt`** is only for the offline `training/*.py` + `evaluation/metrics.py` scripts, which are never imported by the running app. Don't merge them.
- **Tooling exists even though `README.md` says otherwise**: `pyproject.toml` has a real `[tool.ruff]` config (line-length 120, py312, `frontend/` excluded) and `.pre-commit-config.yaml` runs ruff + gitleaks + standard hygiene hooks. Use them.
