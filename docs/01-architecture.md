# 01 · Architecture

## 1.1 Overview

Velar is a single FastAPI service (`app.py`) that fronts two datastores (MongoDB, Milvus) and one external inference server (Ollama). It is **not** a microservice mesh — every router, engine, and ML component documented here runs in the same Python process, in the same container. There is no message queue, no Celery worker, and no separate training service actually wired up in this codebase, despite comments referencing them (see [16 · Known Issues](./16-known-issues-tech-debt.md)).

The codebase is organized as a linear sequence of "Phases," visible directly in source comments. Each phase builds on data produced by the previous one:

```mermaid
flowchart TD
    P0["Phase 0<br/>Health & Bootstrap"] --> P1
    P1["Phases 1-3<br/>Ingestion, Rules, Resolution"] --> P4
    P4["Phase 4<br/>Memory State Machine"] --> P5
    P5["Phase 5<br/>Confidence Wall"] --> P6
    P6["Phase 6<br/>Behavioral Feature Extraction"] --> P7
    P7["Phase 7<br/>Embeddings + Vector Search"] --> P8
    P8["Phase 8<br/>UMAP + HDBSCAN Clustering"] --> P9
    P9["Phase 9<br/>Baseline ML Training"] --> P10
    P10["Phase 10<br/>Feedback + Active Learning"] --> P11
    P11["Phase 11<br/>LoRA Fine-Tuning"] --> P12
    P12["Phase 12<br/>RAG Explainability"] --> P13
    P13["Phase 13<br/>Analytics Engine"] --> P14
    P14["Phase 14<br/>Observability / MLOps"] --> P15
    P15["Phase 15<br/>API Key Security"]
```

Only a subset of these phases are reachable over HTTP today. The rest exist as importable Python modules intended to be invoked by scripts, cron jobs, or a future orchestrator (Celery is referenced in comments but is not a dependency of this codebase, and no scheduler is wired up).

## 1.2 Process topology

```mermaid
flowchart LR
    subgraph Container["velar-backend container (Dockerfile)"]
        APP["Uvicorn / FastAPI app.py"]
    end
    subgraph Data["Datastores"]
        Mongo[("MongoDB 6.0<br/>(docker-compose_local.yaml)")]
        Milvus[("Milvus<br/>external, MILVUS_URI")]
    end
    subgraph Inference["Inference"]
        Ollama[["Ollama server(s)<br/>OLLAMA_URI / OLLAMA_HOSTS"]]
    end

    Client(["API Consumer"]) -- "HTTPS + X-Velar-API-Key" --> APP
    APP -- "Motor (async)" --> Mongo
    APP -- "MilvusClient" --> Milvus
    APP -- "httpx (async)" --> Ollama
    Prometheus(["Prometheus scraper"]) -- "GET /metrics" --> APP
```

`app.py`'s `lifespan` context manager is the composition root: on startup it calls `db.connect(...)` (`database/mongo.py`) and `vector_db.connect(...)` (`database/milvus.py`); on shutdown it calls the corresponding `disconnect()` methods. Both `db` and `vector_db` are process-wide singletons (class-level attributes on `MongoDB` and `VectorDB`), so there is exactly one Mongo client and one Milvus client per process, shared by every request via plain module import (`from database.mongo import db`), not FastAPI dependency injection.

Note: `milvus/insert_vectors.py` constructs its **own** independent `MilvusClient` at import time (`vector_store = VectorStoreManager()`), reading `MILVUS_URI` directly from `os.getenv` rather than from `core.config.settings` or the `database.milvus.vector_db` singleton. This means the application can end up with **two separate Milvus client connections** — one managed by the app lifespan (`vector_db`, currently unused by any router) and one created eagerly at import time by `VectorStoreManager` (actually used by clustering and vector search). See [16 · Known Issues](./16-known-issues-tech-debt.md#duplicate-milvus-clients).

## 1.3 Request flow — application startup

```mermaid
sequenceDiagram
    participant OS as Process Start
    participant App as FastAPI (app.py)
    participant Mongo as database.mongo.db
    participant Milvus as database.milvus.vector_db
    participant Prom as Instrumentator

    OS->>App: import app.py
    App->>App: configure logging (DEBUG level)
    App->>App: setup_rate_limiting(app)
    App->>Prom: Instrumentator().instrument(app).expose(app, "/metrics")
    App->>App: include_router(v1, memory, analytics, rag, observability)
    Note over App: lifespan() begins
    App->>Mongo: db.connect(MONGODB_URI, MONGODB_DB_NAME)
    Mongo-->>App: collections bound (transactions, feedback, categories, merchants, merchant_profiles, behavior_patterns, retraining_queue)
    App->>Milvus: vector_db.connect(MILVUS_URI)
    Milvus-->>App: MilvusClient created (retries up to 5x, 3s delay)
    App->>App: yield (ready to serve)
```

## 1.4 Request flow — `/v1/categorize` (rule-based categorization)

This is the primary ingestion endpoint. **It currently contains a fatal implementation bug** (documented below and in [16 · Known Issues](./16-known-issues-tech-debt.md#v1-categorize-is-broken)) that will raise an exception before returning a response; the flow below reflects the code as written.

```mermaid
sequenceDiagram
    participant C as Client
    participant R as routers/v1.py
    participant RE as engines.rule_engine
    participant Mongo as database.mongo.db

    C->>R: POST /v1/categorize {"text": "..."}
    R->>R: start_time = time.time()
    R->>RE: rule_engine.categorize(request.text)
    RE-->>R: {merchant, category, confidence}
    R->>R: text_content = request.get("text", "")  ⚠ CategorizeRequest has no .get()
    Note over R: AttributeError raised here in practice
    R->>Mongo: db.transactions.insert_one({... "merchant": merchant_resolver ...})
    Note over R: Fields assign module objects, not resolved values (see Known Issues)
    R-->>C: result (never reached today)
```

`RuleEngine.categorize` itself (`engines/rule_engine.py`) is a clean, deterministic implementation:

1. On startup, loads `merchant_aliases.json` into memory and pre-compiles a `\b<alias>\b` case-insensitive regex per alias.
2. `categorize(text)` scans compiled patterns in dict-insertion order and returns the **first** alias match with `confidence: 0.95`.
3. No match → `{"merchant": "Unknown", "category": "Uncategorized", "confidence": 0.0}`.

## 1.5 Request flow — `/v1/resolve` (merchant resolution)

This is the working, well-formed counterpart to `/v1/categorize` for noisy bank/UPI text.

```mermaid
sequenceDiagram
    participant C as Client
    participant R as routers/v1.py
    participant MR as services.merchant_resolver
    participant Mongo as MongoDB (merchants collection)

    C->>R: POST /v1/resolve {"text": "UPI/CR/.../BUNDL TECHNOLOGIES/HDFC"}
    R->>MR: merchant_resolver.resolve(text)
    MR->>MR: clean_text(): strip UPI/IMPS/NEFT/RTGS/INB noise, 12-digit ref#s, UPI handles, special chars
    MR->>Mongo: find_one({aliases: cleaned_text})  (exact match)
    alt exact alias hit
        Mongo-->>MR: {canonical_name: "Swiggy", ...}
        MR-->>R: ResolutionResult(confidence=0.99, method="exact_alias")
    else no exact hit
        loop each word (len >= 4) in cleaned text
            MR->>Mongo: find_one({aliases: {$regex: "^WORD", $options: "i"}})
        end
        alt substring hit
            MR-->>R: ResolutionResult(confidence=0.75, method="substring")
        else no hit
            MR-->>R: ResolutionResult(canonical_merchant="Unknown", confidence=0.0, method="none")
        end
    end
    R-->>C: ResolutionResult JSON
```

## 1.6 Request flow — `/v1/explain` (RAG explainability)

```mermaid
sequenceDiagram
    participant C as Client
    participant R as routers/rag.py
    participant Retr as rag.retriever
    participant VS as milvus.search_vectors
    participant Emb as embeddings.generate_embeddings
    participant Mongo as MongoDB
    participant CB as rag.context_builder
    participant Gen as rag.generator
    participant Ollama as Ollama /api/generate

    C->>R: POST /v1/explain {transaction_text, target_question}
    R->>Retr: fetch_grounded_context(transaction_text)
    Retr->>Emb: generate(transaction_text) -> query_vector
    Emb->>Ollama: POST /api/embeddings {model: EMBED_MODEL, prompt}
    Ollama-->>Emb: embedding vector
    Retr->>VS: find_similar_behaviors(transaction_text, top_k=3)
    VS-->>Retr: [{merchant_name, similarity_score, id}, ...]
    loop each matched merchant
        Retr->>Mongo: merchant_profiles.find_one(canonical_name)
        Retr->>Mongo: behavior_patterns.find_one(merchant_name)
        Retr->>Mongo: feedback.find({prediction: name}).sort(-1).limit(3)
    end
    Retr-->>R: context_payloads[]
    R->>CB: build_prompt_string(context_payloads)
    CB-->>R: XML-tagged <MERCHANT_DATA> prompt block
    R->>Gen: generate_explanation(query, context_string)
    Gen->>Ollama: POST /api/generate {system, prompt, format:"json"}
    Ollama-->>Gen: {"response": "<json string>"}
    Gen-->>R: parsed JSON {explanation, confidence_in_explanation, primary_data_source}
    R-->>C: {query, retrieved_documents, result}
```

If Milvus returns zero hits, `fetch_grounded_context` returns `[]`, `build_prompt_string` returns the literal string `"NO_CONTEXT_AVAILABLE"`, and `generate_explanation` short-circuits with `{"error": "No historical behavior found to explain this transaction."}` **without calling Ollama** — this is the system's core hallucination-prevention guarantee.

## 1.7 Request flow — `/memory/update` (state machine)

```mermaid
sequenceDiagram
    participant C as Client
    participant R as routers/memory.py
    participant MM as memory.memory_manager
    participant Repo as repositories.profile_repository
    participant SM as memory.state_machine
    participant Mongo as MongoDB (merchant_profiles)

    C->>R: POST /memory/update {canonical_name, raw_text}
    R->>MM: process_encounter(canonical_name, raw_text)
    MM->>Repo: get_profile(canonical_name)
    alt profile not found
        MM->>MM: new MerchantProfile(frequency=1, state=EPHEMERAL)
        MM->>Repo: create_profile(profile)
        Repo->>Mongo: insert_one(profile)
    else profile found
        MM->>MM: frequency += 1, last_seen = now, append alias if new
        MM->>SM: evaluate_promotion(profile)
        SM-->>MM: new_state (EPHEMERAL/TEMPORARY/PERMANENT, sticky at PERMANENT/ARCHIVED)
        MM->>MM: if was ARCHIVED -> wake to TEMPORARY, else apply new_state
        MM->>Repo: update_profile(profile)
        Repo->>Mongo: update_one({canonical_name}, {$set: ...})
    end
    MM-->>R: MerchantProfile
    R-->>C: MerchantProfile JSON
```

State thresholds (`memory/state_machine.py`): `frequency >= 10` → `PERMANENT`; `frequency >= 3` → `TEMPORARY`; otherwise `EPHEMERAL`. `PERMANENT` and `ARCHIVED` are treated as non-demotable by `evaluate_promotion`, but `MemoryManager.process_encounter` explicitly overrides an `ARCHIVED` profile back to `TEMPORARY` on any new encounter (bypassing `evaluate_promotion`'s own state machine for that one transition).

## 1.8 Security & rate limiting

- **Auth**: every router except `/health` and `/metrics` is mounted with `dependencies=[Depends(validate_api_key)]` in `app.py`. `validate_api_key` (`core/security.py`) checks the `X-Velar-API-Key` header against a single **hardcoded** string, `"velar_test_key_123"` — it does not read `settings.VELAR_API_KEY` from config at all, despite that setting existing in `core/config.py` and being required in `.env`. See [16 · Known Issues](./16-known-issues-tech-debt.md#hardcoded-api-key).
- **Rate limiting**: SlowAPI (`core/rate_limiter.py`) applies a global default of `1000/day` and `100/minute` per client IP (`get_remote_address`). `POST /v1/categorize` (the top-level public route registered directly on `app`, not the router-mounted one) additionally declares `@limiter.limit("50/minute")`.
- **Metrics**: `prometheus_fastapi_instrumentator` auto-instruments every route and exposes `GET /metrics` with no auth dependency.

## 1.9 What is *not* wired into the HTTP surface

The following modules are fully implemented Python classes with module-level singletons, but **no router calls them**. They are reachable only by importing them directly (e.g., from a script, notebook, or future endpoint):

| Module | Singleton | Would be invoked by |
|---|---|---|
| `behaviour/behavior_engine.py` | `behavior_engine` | Phase 6 batch job to populate `behavior_patterns` |
| `clustering/cluster_engine.py` | `cluster_engine` | Phase 8 discovery pipeline |
| `memory/decay_engine.py` | `decay_engine` | A scheduled sweep (no scheduler exists in this repo) |
| `training/train.py` | `BaselineTrainer` (script entry point only) | Manual `python training/train.py` |
| `training/finetune.py` | `FinetuneEngine` (script entry point only) | Manual `python training/finetune.py` |
| `graphs/graph_builder.py` | `graph_engine` | No caller found anywhere in the repo |
| `feedback/api_router.py` | mounted `router`, but **never `include_router`'d in `app.py`** | Not reachable over HTTP at all today |

This matters operationally: analytics endpoints (`/v1/analytics/subscriptions`, `/v1/analytics/anomaly/check`) read from the `behavior_patterns` collection, but nothing in the live HTTP path ever populates it — only the disconnected `behavior_engine.profile_merchant_behavior()` does. In a fresh environment, these analytics endpoints will return empty/degenerate results until someone runs the behavior engine out-of-band.
