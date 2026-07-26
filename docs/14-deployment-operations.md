# 14 · Deployment & Operations

## 14.1 Python dependencies

`requirements.txt` (used by `Dockerfile`) and `requirements-linux.txt` (a superset used for a full Linux/Ubuntu system) both list packages such as `attrs`, `Automat`, `Twisted`, `PyGObject`, `python-apt`, `ubuntu-pro-client`, `cloud-init` — these are **Ubuntu/`apt`-managed system Python packages**, not application dependencies. Neither file lists `fastapi`, `uvicorn`, `pydantic`, `motor`, `pymilvus`, `slowapi`, `prometheus-fastapi-instrumentator`, `httpx`, `scikit-learn`, `umap-learn`, `hdbscan` (or scikit-learn's bundled `HDBSCAN`), `networkx`, `pandas`, `numpy`, `lightgbm`, `xgboost`, `shap`, `torch`, `transformers`, `peft`, or `datasets` — every third-party package actually imported by the application code in this repository.

**Practical consequence**: running `pip install -r requirements.txt` (exactly what `Dockerfile` line 6 does) will **not** install anything the application needs to run, and `docker build` will produce an image that fails immediately on `CMD ["uvicorn", "app:app", ...]` with `ModuleNotFoundError: No module named 'fastapi'`. This is the top infrastructure-level finding in [16 · Known Issues](./16-known-issues-tech-debt.md#requirementstxt-is-not-the-apps-dependency-list). Until corrected, anyone deploying from this repo as-is needs to manually `pip install` the actual runtime dependencies (cross-reference the `import` statements across `app.py`, every `routers/*.py`, `core/*.py`, `database/*.py`, `engines/*.py`, `services/*.py`, `analytics/*.py`, `features/*.py`, `behaviour/*.py`, `memory/*.py`, `repositories/*.py`, `embeddings/*.py`, `milvus/*.py`, `clustering/*.py`, `graphs/*.py`, `rag/*.py`, `feedback/*.py`, `training/*.py`, and `evaluation/*.py` to build a correct list — this documentation set's other pages cite the exact import lines module-by-module).

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
      - MONGO_URI=mongodb://lokesh:Lokesh%401234@123156456323:27017/?authSource=admin
      - MONGO_DB_NAME=velar
      - MILVUS_HOST=10.10.10.130
      - MILVUS_PORT=19530
    networks: [coolify]   # external network, implies deployment via Coolify PaaS
```
⚠ **This file contains what appears to be a live-looking credential** (a MongoDB username/password embedded directly in the connection string) committed in plaintext to version control. Even if this specific value is a placeholder or has since been rotated, treat any committed connection string with embedded credentials as compromised and rotate it — see [Known Issues](./16-known-issues-tech-debt.md#plaintext-credential-in-compose-file). Also note the env var names here (`MONGO_URI`, `MONGO_DB_NAME`, `MILVUS_HOST`, `MILVUS_PORT`) **do not match** what `core/config.py` actually reads (`MONGODB_URI`, `MONGODB_DB_NAME`, `MILVUS_URI`) — running the app with only these environment variables set would fail Pydantic settings validation (missing required `MONGODB_URI`, `MILVUS_URI`, `EMBED_MODEL`, `LLM_MODEL`, `VELAR_API_KEY`). This compose file predates or was never updated alongside the current `Settings` schema.

## 14.4 Required environment variables (authoritative — from `core/config.py`)

```env
MONGODB_URI=mongodb://<host>:27017
MONGODB_DB_NAME=velar
MILVUS_URI=http://<host>:19530
OLLAMA_URI=http://<host>:11434        # OR use OLLAMA_HOSTS below
OLLAMA_HOSTS=http://host1:11434,http://host2:11434
EMBED_MODEL=<ollama embedding model name>
LLM_MODEL=<ollama generation model name>
VELAR_API_KEY=<currently ignored at runtime — see Known Issues>
```
Place this file at the repo root as `.env` for local development (loaded via `pydantic_settings`'s `env_file=".env"`); for containerized deployment, either mount/inject it or set each variable directly in the container environment (aligning names exactly — see the mismatch warning above for `docker-compose_production.yaml`).

## 14.5 Bootstrapping data (manual, out-of-band steps)

None of these run automatically on startup — they must be triggered manually, in this order, for the full feature set to produce meaningful results:

1. `python scripts/seed.py` — seeds canonical `merchants` (Swiggy, Zomato, Netflix + aliases) so `/v1/resolve` can find matches beyond `"Unknown"`.
2. `python scripts/mock_seeder.py` (and `python scripts/mock_seeder.py cleanup` to remove it) — injects 100 synthetic `is_mock: True` transactions for `user_id: "user_123"` so the Analytics Engine has data to aggregate. Used by `scripts/test_pipeline.sh`.
3. Manually invoke `behaviour.behavior_engine.behavior_engine.profile_merchant_behavior(merchant_name)` per merchant (no CLI wrapper exists) to populate `behavior_patterns` — required before `/v1/analytics/subscriptions` or `/v1/analytics/anomaly/check` return anything non-trivial.
4. Embedding generation and Milvus insertion (`embeddings/vectorizer.py` → `embeddings/generate_embeddings.py` → `milvus/insert_vectors.py::insert_behavior_vector`) has no orchestrating script at all today — must be scripted ad hoc before `/v1/explain` can retrieve any grounded context.
5. `python clustering/cluster_engine.py`-style invocation of `ClusterEngine.run_discovery_pipeline()` is currently **non-functional** due to the `davies_bouldin_index` import bug — see [07 · Embeddings, Vector Search & Clustering §7.4](./07-embeddings-vectorsearch-clustering.md#74-phase-8-clustering-pipeline--clusteringpy).

## 14.6 `scripts/test_pipeline.sh` — manual E2E smoke test

A bash script exercising the API end-to-end against a running server at `http://localhost:8080` (note: this differs from the Dockerfile's default port `8000` and compose's exposed port `9850` — adjust `BASE_URL` to match whichever way you've started the server). It parses `VELAR_API_KEY` out of a local `.env` if present, falling back to the hardcoded `velar_test_key_123` (which is the only value `core/security.py` actually accepts regardless). Exercises: merchant resolution, memory state promotion (3 calls to force `EPHEMERAL → TEMPORARY`), the confidence wall, mock data seeding, top-merchant/category analytics, then cleans up the mock data it created.

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
