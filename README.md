<div align="center">

![Profile Picture](/assets/banner.png)

# Velar

**Transaction Intelligence Engine — turning noisy financial text into explainable, structured insight.**

Velar ingests raw, messy transaction strings (UPI references, bank SMS, POS narrations) and turns them into canonical merchant identity, spend category, behavioral fingerprints, anomaly signals, and natural-language explanations — grounded in retrieved data, not guesswork.

[![Python](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-async%20API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Motor%20async-47A248?logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![Milvus](https://img.shields.io/badge/Milvus-vector%20search-00A1EA)](https://milvus.io/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Status](https://img.shields.io/badge/status-pre--production-orange)](./docs/16-known-issues-tech-debt.md)

[Documentation](./docs/README.md) · [API Reference](./docs/api/README.md) · [Architecture](./docs/01-architecture.md) · [Known Issues](./docs/16-known-issues-tech-debt.md)

</div>

---

## Project Status

> **Pre-production / actively stabilizing.** Velar's architecture is genuinely ambitious — a 15-phase pipeline from ingestion through explainability — but several phases are disconnected from the live API surface, and a small number of endpoints have known, tracked defects. This README describes the project honestly: what works today, what's mocked, and what's planned. See [`docs/16-known-issues-tech-debt.md`](./docs/16-known-issues-tech-debt.md) for the complete, current defect list before deploying this anywhere important.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Folder Structure](#folder-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Variables](#environment-variables)
  - [Running Locally](#running-locally)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Deployment](#deployment)
- [API Overview](#api-overview)
- [Screenshots / API Preview](#screenshots--api-preview)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

Most transaction-categorization systems either rely on brittle string matching or hand the whole problem to a single opaque LLM call. Velar takes a different approach: a layered pipeline where each stage has a single, well-defined responsibility —

- **Deterministic rules** handle the obvious cases fast and cheaply.
- **A trust/memory state machine** means a merchant isn't treated as reliable the first time it's seen — trust is earned over repeated encounters.
- **A confidence wall** actively rejects low-confidence or out-of-vocabulary predictions rather than letting a bad guess pollute analytics — *"Unknown" is treated as a valid, honest answer.*
- **A grounded RAG layer** explains categorizations in natural language, but is architecturally forbidden from answering unless it has real retrieved data to point to.

Velar is built as a single async FastAPI service backed by MongoDB (system of record) and Milvus (semantic vector search), with Ollama providing local/self-hosted embeddings and generation.

## Architecture

```mermaid
flowchart LR
    Client([API Client]) -->|X-Velar-API-Key| API[FastAPI App]
    API --> V1[/v1 — categorize, resolve, confidence/]
    API --> MEM[/memory — trust state machine/]
    API --> ANA[/v1/analytics — spend intelligence/]
    API --> RAG[/v1/explain — grounded RAG/]
    V1 --> Mongo[(MongoDB)]
    MEM --> Mongo
    ANA --> Mongo
    RAG --> Mongo
    RAG --> Milvus[(Milvus)]
    RAG --> Ollama[[Ollama LLM]]
    API --> Prom[/metrics — Prometheus/]
```

Velar's own code comments describe the system as a sequence of numbered **phases** — this isn't a documentation invention, it's how the codebase actually labels itself:

| Phase | Capability | Status |
|---|---|---|
| 1–3 | Rule-based categorization + noisy-text merchant resolution | Resolution works; categorize has a known bug |
| 4 | Memory / trust state machine (`EPHEMERAL → TEMPORARY → PERMANENT`) | Working |
| 5 | Confidence wall (reject low-confidence predictions) | Working |
| 6 | Behavioral feature extraction (amount, timing, frequency, periodicity) | Implemented, not auto-triggered |
| 7 | Embeddings + Milvus vector search | Search path live; write/index path not wired up |
| 8 | UMAP + HDBSCAN clustering | Two known bugs, currently non-functional |
| 9 | Baseline ML model benchmarking | Script-only, synthetic data |
| 10 | Human feedback + active learning queue | Implemented, but not mounted to the API |
| 11 | LoRA fine-tuning (FinBERT) | Script-only, synthetic data |
| 12 | Grounded RAG explainability | Working end-to-end |
| 13 | Spend analytics (patterns, subscriptions, trends, anomalies) | Working |
| 14 | Observability / drift monitoring | Stubbed, not implemented |
| 15 | API key authentication + rate limiting | Working (single shared key model) |

**Full architecture deep-dive, sequence diagrams, and per-folder/per-file references live in [`/docs`](./docs/README.md).**

## Features

| Feature | Endpoint(s) | Status |
|---|---|---|
| Deterministic merchant/category rule matching | `POST /v1/categorize` | Known bug — see [Known Limitations](#known-limitations) |
| Noisy UPI/bank text → canonical merchant resolution | `POST /v1/resolve` | Stable |
| Confidence-wall prediction gating | `POST /v1/confidence/evaluate` | Stable |
| Merchant trust/memory state tracking | `POST /memory/update`, `GET /memory/profile/{name}`, `GET /memory/state/{name}` | Stable |
| Spend breakdown by category & top merchants | `GET /v1/analytics/patterns/*` | Stable |
| Subscription detection | `GET /v1/analytics/subscriptions` | Needs behavioral backfill |
| Real-time anomaly detection (z-score) | `POST /v1/analytics/anomaly/check` | Needs behavioral backfill |
| Month-over-month trend | `GET /v1/analytics/trends/mom` | Partially mocked |
| Grounded, hallucination-resistant explanations | `POST /v1/explain` | Stable |
| Health check & Prometheus metrics | `GET /health`, `GET /metrics` | Stable |

Legend: **Stable** — working correctly and verified · **Needs backfill** — works, but depends on a manual step · **Partially mocked / Script-only** — experimental or not yet connected to real data · **Known bug** — tracked defect (see Known Limitations)

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) |
| Primary Database | [MongoDB](https://www.mongodb.com/) via [Motor](https://motor.readthedocs.io/) (async) |
| Vector Database | [Milvus](https://milvus.io/) via `pymilvus` |
| LLM / Embeddings | [Ollama](https://ollama.com/) (self-hosted inference) |
| Rate Limiting | [SlowAPI](https://github.com/laurentS/slowapi) |
| Metrics | [prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator) |
| Classical ML | scikit-learn, LightGBM, XGBoost, SHAP |
| Deep Learning | PyTorch, HuggingFace Transformers, PEFT (LoRA) |
| Dimensionality Reduction / Clustering | UMAP, HDBSCAN |
| Graph Modeling | NetworkX |
| Configuration | Pydantic Settings (`.env`-driven) |
| Containerization | Docker, Docker Compose |
| Testing | pytest, FastAPI `TestClient` |

## Folder Structure

```
backend/
├── app.py                    # FastAPI entry point, lifespan, router mounting
├── core/                     # Config, security (auth), rate limiting, Ollama client
├── database/                 # MongoDB + Milvus connection singletons
├── models/                   # Shared Pydantic schemas & enums
├── routers/                  # HTTP controllers (v1, memory, analytics, rag, observability)
├── engines/                  # Rule engine (Phase 1-2) + confidence wall (Phase 5)
├── services/                 # Noisy-text merchant resolver (Phase 3)
├── memory/                   # Trust state machine + decay engine (Phase 4)
├── repositories/             # Data-access layer for merchant profiles
├── features/                 # Statistical feature extractors (Phase 6)
├── behaviour/                # Behavior-profiling orchestrator (Phase 6)
├── embeddings/                # Text → vector generation (Phase 7)
├── milvus/                   # Vector store insert/search (Phase 7)
├── clustering/                # UMAP + HDBSCAN discovery pipeline (Phase 8)
├── training/                  # Baseline ML + LoRA fine-tuning pipelines (Phase 9, 11)
├── evaluation/                 # Shared ML metrics (accuracy, F1, ECE, SHAP)
├── feedback/                   # Human feedback + retraining queue (Phase 10)
├── rag/                        # Grounded explainability pipeline (Phase 12)
├── analytics/                  # Spend patterns, subscriptions, trends, anomalies (Phase 13)
├── graphs/                     # Cross-collection knowledge graph (NetworkX)
├── scripts/                    # Seed data, mock data, manual E2E smoke test
├── docs/                       # Full documentation portal (architecture, API, per-file/folder deep dives)
├── test_api.py                 # pytest suite
├── merchant_aliases.json       # Static rule-engine lookup table
├── Dockerfile
├── docker-compose_local.yaml
└── docker-compose_production.yaml
```

**For a deep dive into any single folder or file** — purpose, classes, dependency graphs, interview questions, and what breaks if it's removed — see [`docs/folders/`](./docs/folders/README.md) and [`docs/files/`](./docs/files/README.md).

## Getting Started

### Prerequisites

- Python **3.12** (the `Dockerfile` is pinned to `python:3.12-slim`)
- [Docker](https://www.docker.com/) & Docker Compose (recommended path)
- A running **MongoDB** instance
- A running **Milvus** instance ([standalone Docker image](https://milvus.io/docs/install_standalone-docker.md) is sufficient for local dev)
- A reachable **Ollama** server with an embedding model and a generation model pulled

> **Note:** The committed `docker-compose_local.yaml` only provisions MongoDB — you'll need to run Milvus and Ollama separately (or add them to your own compose override) for the full feature set to work locally.

### Installation

```bash
git clone https://github.com/lokeshramchand-ctrl/backend.git velar
cd velar

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

> **Important: do not rely on `pip install -r requirements.txt` alone.** The committed `requirements.txt` does not list this project's actual runtime dependencies (see [Known Limitations](#known-limitations)). Until it's corrected, install the real dependency set manually:

```bash
pip install fastapi uvicorn "pydantic-settings" motor pymilvus slowapi \
    prometheus-fastapi-instrumentator httpx scikit-learn umap-learn networkx \
    pandas numpy lightgbm xgboost shap
# Optional — only needed for the training/ scripts:
pip install torch transformers peft datasets
```

### Environment Variables

Create a `.env` file in the project root:

```env
# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=velar

# Milvus
MILVUS_URI=http://localhost:19530

# Ollama — set ONE of the following
OLLAMA_URI=http://localhost:11434
# OLLAMA_HOSTS=http://host1:11434,http://host2:11434   # comma-separated failover list

# Ollama models — replace with whatever models you've pulled in your own Ollama instance
EMBED_MODEL=nomic-embed-text   # example only
LLM_MODEL=llama3               # example only

# API authentication
VELAR_API_KEY=your-secret-key-here
```

| Variable | Required | Default | Notes |
|---|---|---|---|
| `MONGODB_URI` | Yes | — | Full MongoDB connection string |
| `MONGODB_DB_NAME` | No | `velar` | |
| `MILVUS_URI` | Yes | — | |
| `OLLAMA_URI` | No | — | Takes precedence over `OLLAMA_HOSTS` if both are set |
| `OLLAMA_HOSTS` | No | — | Comma-separated failover list, tried in order at startup |
| `EMBED_MODEL` | Yes | — | Ollama embedding model name |
| `LLM_MODEL` | Yes | — | Ollama generation model name |
| `VELAR_API_KEY` | Yes | — | Currently **not actually enforced** by the running app — see [Known Limitations](#known-limitations) |

The app **fails fast at startup** if any required variable is missing — this is deliberate, not a bug.

### Running Locally

**Option A — Docker Compose (MongoDB only; bring your own Milvus/Ollama):**
```bash
docker compose -f docker-compose_local.yaml up --build
```

**Option B — Manual:**
```bash
# 1. Seed canonical merchant data (optional but recommended)
python scripts/seed.py

# 2. Start the server
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

**Verify it's up:**
```bash
curl http://localhost:8000/health
```

**Explore the interactive API docs** (auto-generated by FastAPI) at **http://localhost:8000/docs**.

## Development Workflow

This repository doesn't currently ship a linter config, formatter config, or CI pipeline — the recommendations below are conventional best practice for a project at this stage, not enforced tooling:

1. **Branch from `main`** — `git checkout -b feature/your-change`.
2. **Make focused commits** — one logical change per commit, with a message describing *why*, not just *what*.
3. **Run the test suite** before opening a PR (see [Testing](#testing)) — note the suite currently requires live MongoDB and Milvus connections.
4. **Cross-check `docs/16-known-issues-tech-debt.md`** before touching a file — several modules have documented, non-obvious defects; fixing one is a great first contribution.
5. **Open a pull request** against `main` with a clear description of the change and its motivation.

Consider adding `ruff`/`black` + a pre-commit hook and a CI workflow (`.github/workflows/`) as immediate, high-value process improvements — see [Roadmap](#roadmap).

## Testing

```bash
# Full suite (requires live MongoDB + Milvus)
pytest test_api.py -v

# Manual, narrated end-to-end smoke test against a running server
bash scripts/test_pipeline.sh
```

The `pytest` suite uses FastAPI's `TestClient` against the real app object, so it genuinely exercises the app's `lifespan` (real database connections) rather than mocking them — see [`docs/15-testing.md`](./docs/15-testing.md) for a full breakdown of what each test covers and its current pass/fail status.

## Deployment

**Build and run with Docker:**
```bash
docker build -t velar-backend .
docker run -p 8000:8000 --env-file .env velar-backend
```

**Or via Compose** (`docker-compose_production.yaml` targets an external Coolify network — adapt for your own infrastructure):
```bash
docker compose -f docker-compose_production.yaml up -d --build
```

> **Important:** before deploying anywhere beyond local development, read [`docs/14-deployment-operations.md`](./docs/14-deployment-operations.md) in full — it documents several real gaps (the `requirements.txt` issue above, an env-var naming mismatch in the production compose file, and a credential-hygiene issue) that matter for a real deployment.

## API Overview

All endpoints except `/health` and `/metrics` require the header `X-Velar-API-Key`.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness + dependency status |
| `GET` | `/metrics` | Prometheus metrics |
| `POST` | `/v1/categorize` | Rule-based categorization |
| `POST` | `/v1/resolve` | Noisy-text → canonical merchant |
| `POST` | `/v1/confidence/evaluate` | Confidence-wall evaluation |
| `POST` | `/memory/update` | Record a merchant encounter |
| `GET` | `/memory/profile/{name}` | Fetch a merchant's full trust profile |
| `GET` | `/memory/state/{name}` | Fetch just trust state + frequency |
| `GET` | `/v1/analytics/patterns/categories` | Spend by category |
| `GET` | `/v1/analytics/patterns/merchants` | Top merchants by visits |
| `GET` | `/v1/analytics/subscriptions` | Detected recurring subscriptions |
| `GET` | `/v1/analytics/trends/mom` | Month-over-month spend trend |
| `POST` | `/v1/analytics/anomaly/check` | Real-time anomaly check |
| `POST` | `/v1/explain` | Grounded RAG explanation |
| `POST` | `/v1/observability/drift/analyze` | Drift analysis (stub) |
| `GET` | `/v1/observability/reports/latest` | Latest drift report (stub) |

**Full per-endpoint documentation** — headers, validation rules, exact database queries, sequence diagrams, and example requests/responses — lives in [`docs/api/`](./docs/api/README.md).

## Screenshots / API Preview

Velar is a headless JSON API with no bundled frontend, so there's no UI to screenshot. The closest equivalent:

**Interactive API docs** — every endpoint is explorable and testable live at `/docs` (Swagger UI) and `/redoc` once the server is running:
```
http://localhost:8000/docs
```

**Example interaction:**
```bash
$ curl -s -X POST http://localhost:8000/v1/resolve \
    -H "X-Velar-API-Key: your-secret-key-here" \
    -H "Content-Type: application/json" \
    -d '{"text": "UPI/CR/3152671239/BUNDL TECHNOLOGIES/HDFC"}'
```
```json
{
  "raw_text": "UPI/CR/3152671239/BUNDL TECHNOLOGIES/HDFC",
  "cleaned_text": "BUNDL TECHNOLOGIES",
  "canonical_merchant": "Swiggy",
  "confidence": 0.99,
  "is_resolved": true,
  "resolution_method": "exact_alias"
}
```

## Known Limitations

Velar is transparent about its own maturity. The full, continuously-maintained list — with file/line-level detail and suggested fixes — lives in [`docs/16-known-issues-tech-debt.md`](./docs/16-known-issues-tech-debt.md). Headlines:

- **`POST /v1/categorize` currently returns a 500 on every call** — a bug in the request-handling code, not a configuration issue.
- **`requirements.txt` does not list this project's actual dependencies** — see [Installation](#installation) for the correct package list until this is fixed.
- **`VELAR_API_KEY` is not actually enforced** — the auth check currently compares against a hardcoded value, not your configured key.
- **Several pipeline phases are implemented but not wired to a scheduler or the live API**, including behavior profiling, clustering, decay sweeps, and the feedback/active-learning loop — meaning subscription/anomaly detection needs a manual backfill step, and `POST /v1/feedback/` isn't reachable yet.
- **No caching layer and no database indexes exist yet** — fine for development, a real constraint before any production load.

## Roadmap

- [ ] Fix `POST /v1/categorize` and correct `requirements.txt`
- [ ] Wire real authentication (`VELAR_API_KEY`) and add per-caller authorization
- [ ] Add MongoDB indexes on every actively-queried field
- [ ] Mount the feedback/active-learning router and connect it to a real retraining trigger
- [ ] Automate the behavior-profiling and embedding-generation pipelines (currently manual/never-run)
- [ ] Fix the Phase 8 clustering pipeline (two known bugs)
- [ ] Add a CI pipeline (lint, type-check, test) and a LICENSE
- [ ] Replace the mocked month-over-month trend calculation with a real query
- [ ] Introduce a caching layer for repeated embedding/analytics queries
- [ ] Real multi-tenancy: per-user data scoping instead of a hardcoded test user

## Contributing

Contributions are welcome. Since this project doesn't yet have a formal `CONTRIBUTING.md` or CI gate:

1. Fork the repository and create a feature branch off `main`.
2. Cross-reference [`docs/16-known-issues-tech-debt.md`](./docs/16-known-issues-tech-debt.md) — many great first contributions are already identified and scoped there.
3. Add or update tests in `test_api.py` for any behavioral change.
4. Open a pull request with a clear description of the problem and the fix.
5. Be explicit in your PR description about what you tested and how, given the current lack of CI.

## License

**No license file is currently present in this repository.** Until one is added, all rights are reserved by default under standard copyright law — this code should not be assumed to be open-source-licensed for reuse, modification, or redistribution. If open-source distribution is intended, adding a `LICENSE` file (e.g., MIT, Apache 2.0) is a recommended near-term action — see [Roadmap](#roadmap).

---

<div align="center">

Built as a demonstration of layered, explainable financial ML architecture.
For the complete technical documentation set, start at [`docs/README.md`](./docs/README.md).

</div>
