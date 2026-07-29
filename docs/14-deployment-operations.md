# 14 · Deployment & Operations

## 14.1 Python dependencies

✅ **FIXED.** `requirements.txt` and `requirements-linux.txt` previously listed Ubuntu/`apt`-managed system packages (`attrs`, `Automat`, `Twisted`, `PyGObject`, `python-apt`, `ubuntu-pro-client`, `cloud-init`, etc.) instead of application dependencies. Both files now list the actual runtime dependencies (`fastapi`, `uvicorn`, `pydantic`/`pydantic-settings`, `motor`, `pymilvus`, `slowapi`, `prometheus-fastapi-instrumentator`, `httpx`, `scikit-learn`, `umap-learn`, `networkx`, `pandas`, `numpy`, `lightgbm`, `xgboost`, `shap`, `tabulate`, `torch`, `transformers`, `peft`, `datasets`), pinned to specific versions. `pip install -r requirements.txt` (what `Dockerfile` runs) now installs everything `app.py`'s import graph needs — verified by a clean `import app` and a full `pytest` pass in a fresh virtualenv built solely from this file. See [Known Issues §16.1](./16-known-issues-tech-debt.md#161-critical-previously-broke-the-application-or-a-whole-feature--all-fixed).

## 14.2 Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```
Single-stage build. No multi-stage optimization, no non-root user, no `HEALTHCHECK` directive. Base image is `python:3.12-slim` — worth noting `README.md` states "Python 3.10+" and `.dockerignore`/tooling elsewhere imply a range of supported versions; the container specifically pins `3.12`.

`.dockerignore` excludes `.venv`, `__pycache__/`, `*.log`, `.git`, `.gitignore` — notably `.env` is **not** in `.dockerignore`, meaning if a `.env` file exists in the build context when `COPY . .` runs, secrets would be baked into the image layer. In this repo's current `docker-compose_production.yaml` (see §14.3), secrets are instead passed via the `environment:` block, not a `.env` file, which avoids this — but if you switch to `env_file:` in production (as `docker-compose_local.yaml` does), be sure `.env` is excluded from the Docker build context or only mounted at runtime, not baked in.

## 14.3 Docker Compose environments

### `docker-compose_local.yaml`
```yaml
services:
  mongodb:            # mongo:6.0, port 27017, named volume mongo_data
  velar-backend:       # builds from local Dockerfile, port 9850:8000
                       # env_file: .env
                       # depends_on: mongodb
```
This is the intended local dev stack — but it only stands up **MongoDB**, not Milvus or Ollama. `README.md`'s own setup instructions describe a *different*, more complete compose file (with `milvus-standalone` on ports `19530`/`9091`) that is not actually checked into the repo as `docker-compose_local.yaml` — the committed compose file and the README's documented compose file have diverged. If you follow `README.md` literally, you'll need to author that Milvus service yourself; if you run the checked-in `docker-compose_local.yaml` as-is, the app will start with `milvus: disconnected` on `/health` (per `database/milvus.py`'s retry-then-`None` behavior) unless Milvus is running separately.

### `docker-compose_production.yaml`
```yaml
services:
  velar-backend:
    build: .
    environment:
      - MONGODB_URI=${MONGODB_URI:?MONGODB_URI must be set}
      - MONGODB_DB_NAME=${MONGODB_DB_NAME:-velar}
      - MILVUS_URI=${MILVUS_URI:?MILVUS_URI must be set}
      - OLLAMA_URI=${OLLAMA_URI:-}
      - OLLAMA_HOSTS=${OLLAMA_HOSTS:-}
      - EMBED_MODEL=${EMBED_MODEL:?EMBED_MODEL must be set}
      - LLM_MODEL=${LLM_MODEL:?LLM_MODEL must be set}
      - VELAR_API_KEY=${VELAR_API_KEY:?VELAR_API_KEY must be set}
    networks: [coolify]   # external network, implies deployment via Coolify PaaS
```
✅ **FIXED — both issues.** This file previously committed a plaintext MongoDB username/password directly in the connection string, and used env var names (`MONGO_URI`, `MONGO_DB_NAME`, `MILVUS_HOST`, `MILVUS_PORT`) that didn't match what `core/config.py` reads. It now sources every value via `${VAR:?required}`/`${VAR:-default}` substitution from a compose `.env` file or the host/CI secret store, with names matching `Settings` exactly. See [Known Issues §16.2–16.3](./16-known-issues-tech-debt.md).

**Action still required from whoever operates this deployment** (not something fixable from inside the repo): the credential previously committed here is in git history and must be treated as compromised — rotate it on the actual MongoDB server. Removing it from the tracked file does not undo its prior exposure.

## 14.4 Required environment variables (authoritative — from `core/config.py`)

```env
MONGODB_URI=mongodb://<host>:27017
MONGODB_DB_NAME=velar
MILVUS_URI=http://<host>:19530
OLLAMA_URI=http://<host>:11434        # OR use OLLAMA_HOSTS below
OLLAMA_HOSTS=http://host1:11434,http://host2:11434
EMBED_MODEL=<ollama embedding model name>
LLM_MODEL=<ollama generation model name>
VELAR_API_KEY=<enforced on every non-public route via X-Velar-API-Key>
```
Place this file at the repo root as `.env` for local development (loaded via `pydantic_settings`'s `env_file=".env"`); for containerized deployment, either mount/inject it or set each variable directly in the container environment (aligning names exactly — see the mismatch warning above for `docker-compose_production.yaml`).

## 14.5 Bootstrapping data (manual, out-of-band steps)

None of these run automatically on startup (no scheduler exists), but all are now reachable via HTTP instead of requiring direct script/REPL invocation:

1. `python scripts/seed.py` — seeds canonical `merchants` (Swiggy, Zomato, Netflix + aliases) so `/v1/resolve` can find matches beyond `"Unknown"`.
2. `python scripts/mock_seeder.py` (and `python scripts/mock_seeder.py cleanup` to remove it) — injects 100 synthetic `is_mock: True` transactions for `user_id: "user_123"` so the Analytics Engine has data to aggregate. Used by `scripts/test_pipeline.sh`.
3. `POST /v1/pipelines/behavior/run-all` — profiles every distinct merchant seen in `transactions` and populates `behavior_patterns`, required before `/v1/analytics/subscriptions` or `/v1/analytics/anomaly/check` return anything non-trivial.
4. `POST /v1/pipelines/embeddings/sync` — generates embeddings for every stored `behavior_pattern` and inserts them into Milvus, required before `/v1/explain` can retrieve any grounded context.
5. `POST /v1/pipelines/clustering/run` — runs `ClusterEngine.run_discovery_pipeline()` (the `davies_bouldin_index` import bug is fixed — see [07 · Embeddings, Vector Search & Clustering §7.4](./07-embeddings-vectorsearch-clustering.md#74-phase-8-clustering-pipeline--clusteringpy)).
6. `POST /v1/pipelines/decay/sweep` and `POST /v1/pipelines/graph/build` — the Phase 4 archival sweep and Phase 13 knowledge graph rebuild, both previously fully orphaned with zero callers.

Full request/response details for all of these are in [02 · API Reference §2.9](./02-api-reference.md#29-batch-pipelines-routerspipelinespy-prefix-v1pipelines).

## 14.6 `scripts/test_pipeline.sh` — manual E2E smoke test

A bash script exercising the API end-to-end against a running server at `http://localhost:8080` (note: this differs from the Dockerfile's default port `8000` and compose's exposed port `9850` — adjust `BASE_URL` to match whichever way you've started the server). It parses `VELAR_API_KEY` out of a local `.env` if present, falling back to the hardcoded `velar_test_key_123` — make sure this matches your actual configured `VELAR_API_KEY`, since `core/security.py` now enforces the real configured value rather than accepting that literal unconditionally. Exercises: merchant resolution, memory state promotion (3 calls to force `EPHEMERAL → TEMPORARY`), the confidence wall, mock data seeding, top-merchant/category analytics, then cleans up the mock data it created.

## 14.7 Running locally without Docker

```bash
python -m venv .venv
source .venv/bin/activate
# Manually install actual runtime deps (see 14.1) — requirements.txt is insufficient
pip install fastapi uvicorn "pydantic-settings" motor pymilvus slowapi \
    prometheus-fastapi-instrumentator httpx scikit-learn umap-learn networkx \
    pandas numpy lightgbm xgboost shap
# create .env per §14.4
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```
(This list is derived from cross-referencing every module's imports as documented in this suite; verify versions before pinning, since none are specified in this repository.)
