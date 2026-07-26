# 16 · Known Issues & Tech Debt

This document consolidates every concrete defect, inconsistency, and gap identified while reading the implementation, ranked roughly by severity/blast radius. Each entry cites the exact file and reasoning so it can be verified independently. Nothing here is speculative — each was confirmed by reading the actual source.

## 16.1 Critical (breaks the application or a whole feature)

### `profile_repository.py` missing import
**File**: `repositories/profile_repository.py`
```python
class ProfileRepository:
    async def get_profile(self, canonical_name: str) -> Optional[MerchantProfile]:
```
`Optional` is used in a type annotation but `from typing import Optional` is never imported anywhere in this file, and the file has no `from __future__ import annotations`. Python evaluates function annotations eagerly at `def`-execution time, so this raises `NameError: name 'Optional' is not defined` the instant the module is imported. Import chain impact: `app.py` → `routers.memory` → `memory.memory_manager` → `repositories.profile_repository` → **crash**. This likely prevents `app.py` from importing at all, i.e. **the application may not start** in its current committed state. Fix: add `from typing import Optional` at the top of the file.

### `requirements.txt` is not the app's dependency list
**Files**: `requirements.txt`, `requirements-linux.txt`, `Dockerfile`
Both requirements files list OS-level/`apt`-adjacent Python packages (`Automat`, `Twisted`, `PyGObject`, `python-apt`, `cloud-init`, `ubuntu-pro-client`, etc.) and omit every actual application dependency (`fastapi`, `uvicorn`, `motor`, `pymilvus`, `slowapi`, `httpx`, `pydantic-settings`, `prometheus-fastapi-instrumentator`, `scikit-learn`, `umap-learn`, `networkx`, `pandas`, `numpy`, `lightgbm`, `xgboost`, `shap`, and — for the fine-tuning path — `torch`, `transformers`, `peft`, `datasets`). `Dockerfile` installs exactly `requirements.txt`, so a fresh `docker build && docker run` will fail with `ModuleNotFoundError` on the very first import in `app.py`. See [14 · Deployment §14.1](./14-deployment-operations.md#141-python-dependencies).

### `/v1/categorize` is broken
**File**: `routers/v1.py`
```python
text_content = request.get("text", "")  # request is a CategorizeRequest (Pydantic model) — no .get()
...
"merchant": merchant_resolver,           # the resolver *object*, not a resolved name
"category": categorize_transaction,      # the handler *function*, not a category string
"confidence": confidence_engine,         # the engine *object*, not a confidence float
```
`request.get(...)` raises `AttributeError` immediately (Pydantic v2 `BaseModel` has no `.get`). Even past that, the Mongo insert assigns module/function objects into document fields meant to hold resolved values — placeholder code left mid-edit (the comments `# CHANGE THIS to...` confirm this was never finished). This is the primary public ingestion endpoint and it cannot currently complete a request successfully. See [02 · API Reference §2.3](./02-api-reference.md#23-transaction-intelligence-routersv1py-prefix-v1).

### `davies_bouldin_index` does not exist in scikit-learn
**File**: `clustering/cluster_engine.py`
```python
from sklearn.metrics import silhouette_score, davies_bouldin_index
```
The correct scikit-learn export is `davies_bouldin_score`. This `ImportError`s the moment `clustering/cluster_engine.py` is imported, making the entire Phase 8 clustering pipeline non-importable/non-runnable as committed. Fix: rename to `davies_bouldin_score` (and update the corresponding call site in `_calculate_metrics`). See [07 · Embeddings, Vector Search & Clustering §7.4](./07-embeddings-vectorsearch-clustering.md#74-phase-8-clustering-pipeline--clusteringpy).

## 16.2 High (security / correctness with real user impact)

### Hardcoded API key, config setting unused
**File**: `core/security.py`
```python
if api_key_header != "velar_test_key_123":
```
`core/config.py` declares a required `VELAR_API_KEY` setting, which is present in `.env`, but `validate_api_key` never reads `settings.VELAR_API_KEY` — it compares against a hardcoded literal instead. Every deployment of this exact code, regardless of environment or configured key, accepts only `"velar_test_key_123"`. This means the "test" key is functionally the production key for every environment running this code, and rotating `VELAR_API_KEY` in `.env` has zero effect. Fix: `if api_key_header != settings.VELAR_API_KEY:`.

### Plaintext credential committed in `docker-compose_production.yaml`
**File**: `docker-compose_production.yaml`
```yaml
- MONGO_URI=mongodb://lokesh:Lokesh%401234@123156456323:27017/?authSource=admin
```
A MongoDB username and password are embedded directly in a connection string committed to version control. Regardless of whether this specific credential is still live, treat it as compromised: rotate the credential and switch to a secrets manager or `.env`/CI secret injection instead of inline `environment:` values in a tracked file.

### Category vocabulary mismatch
**Files**: `models/schemas.py` (`TransactionCategory`), `merchant_aliases.json`, `scripts/mock_seeder.py`
`TransactionCategory` only contains `Food, Travel, Entertainment, Bills, Friends, Education, Healthcare, Unknown`. But `merchant_aliases.json` produces `"Subscription"` and `"Shopping"`, and the mock seeder additionally produces `"Utility"` — none of which are valid enum members. If any of these ever reach `ConfidenceEngine.evaluate()`, they'd be force-rejected to `Unknown` as an "invalid category," silently discarding a correct rule-engine categorization. Fix: reconcile the enum with the actual category vocabulary in use, or route rule-engine output through a separate validation path that doesn't assume the ML-prediction enum.

### Month-over-month trend is mocked
**File**: `analytics/trends.py`
```python
prev_total = 15000.0 # Replace with actual DB query
```
`GET /v1/analytics/trends/mom` compares real current-month spend against a hardcoded ₹15,000 "previous month," not an actual queried value. Any consumer of this endpoint is looking at a fabricated comparison. See [11 · Analytics Engine §11.5](./11-analytics-engine.md#115-month-over-month-trend--analyticstrendspycalculate_mom_growth).

## 16.3 Medium (disconnected features, dead code, silent no-ops)

### Feedback router not mounted
**Files**: `feedback/api_router.py`, `app.py`
`feedback.router` (prefix `/v1/feedback`) is fully implemented but never passed to `app.include_router(...)` in `app.py`, and `feedback` is never even imported there. `POST /v1/feedback/` is unreachable — a 404 for every caller. `test_api.py::test_feedback_triggers_retraining_queue` only asserts inside `if response.status_code == 200:`, so this gap doesn't surface as a test failure — it silently no-ops. See [09 · Feedback & Active Learning](./09-feedback-active-learning.md).

### Duplicate `/v1/categorize` route
**File**: `app.py`
A second, static-response `POST /v1/categorize` handler (`public_categorize`) is registered directly on `app` (line 73), duplicating the path already claimed by `routers/v1.py`'s router (included at line 65). Because the router is included first, its handler wins the route match and the inline stub is dead code — but two operations for the same path in the OpenAPI schema is confusing and should be removed. See [02 · API Reference](./02-api-reference.md#21-endpoint-index).

### Duplicate/inconsistent Milvus clients
**Files**: `database/milvus.py` (`vector_db`), `milvus/insert_vectors.py` (`vector_store`)
Two independent `MilvusClient` instances can exist in the same process: one owned by the app `lifespan` (`vector_db`, connected/disconnected with the app, reads `MILVUS_URI` from `core.config.settings`, but is **never used by any router or engine**) and one created eagerly at import time by `VectorStoreManager` (`vector_store`, reads `MILVUS_URI` via `os.getenv` directly, bypassing `core.config.settings` — meaning if `.env` sets `MILVUS_URI` but the process environment variable of the same name isn't separately exported, `VectorStoreManager` silently falls back to its own hardcoded default `http://localhost:19530`, which may differ from what `/health` reports). See [01 · Architecture §1.2](./01-architecture.md#12-process-topology).

### Behavior pipeline never runs automatically
**File**: `behaviour/behavior_engine.py`
`behavior_engine.profile_merchant_behavior()` is the sole writer of `behavior_patterns`, which both `/v1/analytics/subscriptions` and `/v1/analytics/anomaly/check` depend on — but nothing calls it. In a fresh deployment both endpoints will report "insufficient data" / zero subscriptions indefinitely until someone manually invokes this per merchant. See [06 · Confidence & Behavioral Intelligence §6.3](./06-confidence-behavioral-intelligence.md#63-phase-6-behavior-engine--behaviourbehavior_enginepy).

### Embedding-write pipeline has no caller
**Files**: `embeddings/vectorizer.py`, `embeddings/generate_embeddings.py`, `milvus/insert_vectors.py`
The building blocks to turn a `MerchantProfile`/`BehaviorPattern` into a stored Milvus vector all exist, but no code path connects them — nothing ever calls `vectorizer.stringify_*` → `embedding_generator.generate` → `vector_store.insert_behavior_vector`. Consequently the query-time path used by `/v1/explain` (`vector_search.find_similar_behaviors`) will find nothing in a fresh environment. See [07 · Embeddings, Vector Search & Clustering §7.5](./07-embeddings-vectorsearch-clustering.md#75-why-this-matters-for-rag-and-analytics).

### Decay engine never scheduled
**File**: `memory/decay_engine.py`
`DecayEngine.run_archive_sweep()` (Phase 4's 180-day inactivity archival) has no caller anywhere — no cron, no scheduled task, no endpoint. Stale merchant profiles will never actually transition to `ARCHIVED` unless this is invoked manually or wired into a scheduler.

### Knowledge graph fully orphaned
**File**: `graphs/graph_builder.py`
`graph_engine` (build + neighborhood query) has zero callers anywhere in the repository — not even from other disconnected batch modules. See [13 · Knowledge Graph](./13-knowledge-graph.md).

### Retraining queue trigger is a dead end
**File**: `feedback/retraining_queue.py`
`trigger_retraining_if_needed()` flips queued records from `"pending"` to `"processing"` once the 100-item threshold is met, then stops — the `# TODO: Launch BaselineTrainer().run_benchmarks() via Celery` marks unfinished work. Records will sit in `"processing"` forever with no code path that ever completes or trains against them. See [09 · Feedback & Active Learning §9.3](./09-feedback-active-learning.md#93-feedbackretraining_queuepy).

### Training pipelines use synthetic data, not real feedback
**Files**: `training/train.py`, `training/finetune.py`
Both `load_data()`/`load_training_data()` generate random/hardcoded mock datasets, despite docstrings describing intended MongoDB queries against `transactions`/`behavior_patterns`/`feedback`. These are benchmark/pipeline templates, not production training jobs yet. See [08 · ML Training & Evaluation](./08-ml-training-evaluation.md).

### Observability endpoints are pure stubs
**File**: `routers/observability.py`
`POST /v1/observability/drift/analyze` always returns a canned success message with no actual drift computation; `GET /v1/observability/reports/latest` always returns 404. No Evidently AI, MLflow, or Celery integration exists anywhere despite being named in `README.md`'s tech stack and in code comments. See [12 · Observability & MLOps](./12-observability-mlops.md).

## 16.4 Low (latent bugs, unused/mismatched code, cosmetic)

### Feature-extractor empty-input key mismatch
**Files**: `features/amount_features.py`, `features/temporal_features.py`
Each extractor's `n == 0` / empty-input branch returns differently-named dict keys than its normal-path branch (e.g. `avg` vs `avg_amount`; `time_buckets`/`weekday_dist` vs `time_bucket_distribution`/`weekday_distribution`). Currently latent because `behaviour/behavior_engine.py` already guards against empty transaction sets before calling these — but any new caller that doesn't guard the same way will hit a `KeyError`. See [03 · Data Model §3.4](./03-data-model.md#34-fieldvocabulary-inconsistencies-worth-knowing-before-writing-new-code).

### `Merchant`, `Category`, `Transaction`, `Feedback` schemas don't match stored documents
**File**: `models/schemas.py`
`Merchant` uses `name`, but the actual `merchants` collection (per `scripts/seed.py` and `services/merchant_resolver.py`) uses `canonical_name`/`aliases` with no `name` field — `Merchant` appears unused/vestigial. `Transaction` and `Feedback` are missing fields that are actually written (`user_id`, `is_mock`, `is_correction`). `Category` has zero readers or writers anywhere despite the `categories` collection being created on connect. None of these models are validated against Mongo documents at insert/read time (Motor writes/reads raw dicts throughout), so these mismatches don't currently cause runtime errors — they're a documentation/type-safety gap, not a functional bug. See [03 · Data Model §3.1](./03-data-model.md#31-schema-reference).

### `resolution_method: "rule_engine"` documented but never produced
**File**: `models/schemas.py` (`ResolutionResult.resolution_method` docstring) vs. `services/merchant_resolver.py`
The field description lists `rule_engine` as a possible value, but the resolver only ever emits `exact_alias`, `substring`, or `none`. The two resolution mechanisms (`engines/rule_engine.py` and `services/merchant_resolver.py`) are entirely separate code paths that never call each other.

### `XGBClassifier(use_label_encoder=False)` may be incompatible with modern XGBoost
**File**: `training/train.py`
This constructor argument was deprecated and removed in newer XGBoost releases; whether this raises depends on the installed version (unpinned in this repo — see §16.1). Worth verifying before relying on this script.

### `to_markdown()` requires `tabulate`, not in dependency list
**File**: `training/train.py`
`results_df.to_markdown(index=False)` depends on the optional `tabulate` package being installed; it is not present in either requirements file (which, per §16.1, don't list the real dependencies at all anyway).

### Rate limit override is unreachable
**File**: `app.py`
The `@limiter.limit("50/minute")` decorator only exists on the dead-code inline `/v1/categorize` stub (see §16.3 duplicate route entry), so no live endpoint currently has a tighter-than-default (100/minute) rate limit.

### `README.md` documents infrastructure that diverges from what's committed
**Files**: `README.md`, `docker-compose_local.yaml`
The README's setup instructions describe authoring a compose file with a `milvus-standalone` service; the actually-committed `docker-compose_local.yaml` only defines `mongodb` and `velar-backend`. Someone following the README exactly will end up with a different file than what's in source control. See [14 · Deployment §14.3](./14-deployment-operations.md#143-docker-compose-environments).

### `docker-compose_production.yaml` env var names don't match `core/config.py`
**Files**: `docker-compose_production.yaml`, `core/config.py`
Compose sets `MONGO_URI`/`MONGO_DB_NAME`/`MILVUS_HOST`/`MILVUS_PORT`; `Settings` requires `MONGODB_URI`/`MONGODB_DB_NAME`/`MILVUS_URI` (plus `OLLAMA_*`, `EMBED_MODEL`, `LLM_MODEL`, `VELAR_API_KEY`, none of which appear in this compose file at all). Running the production compose file as committed would fail Pydantic settings validation on startup. See [14 · Deployment §14.3](./14-deployment-operations.md#143-docker-compose-environments).

## 16.5 Suggested triage order

1. Fix the `Optional` import in `repositories/profile_repository.py` (likely blocks the app from starting at all).
2. Replace `requirements.txt`/`requirements-linux.txt` with the actual runtime dependency list.
3. Rotate the credential in `docker-compose_production.yaml` and stop committing secrets inline.
4. Fix `core/security.py` to read `settings.VELAR_API_KEY` instead of the hardcoded literal.
5. Fix `routers/v1.py::categorize_transaction` (the `.get()` call and the placeholder field assignments).
6. Fix `clustering/cluster_engine.py`'s `davies_bouldin_index` → `davies_bouldin_score` import.
7. Decide whether to mount `feedback.router` in `app.py`, or remove it if the feature is intentionally on hold.
8. Reconcile `docker-compose_production.yaml` env var names with `core/config.py`, and reconcile `README.md`'s local-dev instructions with the committed `docker-compose_local.yaml`.
9. Everything else in §16.3/§16.4 as time and priority allow.
