# 04 · Core Infrastructure

Everything in this document lives under `core/` and `database/`, plus the composition root in `app.py`.

## 4.1 Configuration — `core/config.py`

Configuration is a single Pydantic `Settings` object (`BaseSettings`), instantiated once at import time as the module-level singleton `settings`. It loads from a `.env` file in the working directory (`SettingsConfigDict(env_file=".env")`).

| Env var | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `MONGODB_URI` | `str` | Yes | — | Mongo connection string |
| `MONGODB_DB_NAME` | `str` | No | `"velar"` | Mongo database name |
| `MILVUS_URI` | `str` | Yes | — | Milvus endpoint |
| `OLLAMA_URI` | `str \| None` | No | `None` | Single Ollama host; takes precedence over `OLLAMA_HOSTS` |
| `OLLAMA_HOSTS` | `str \| None` | No | `None` | Comma-separated list of Ollama hosts for failover resolution |
| `EMBED_MODEL` | `str` | Yes | — | Ollama model name for embeddings |
| `LLM_MODEL` | `str` | Yes | — | Ollama model name for generation |
| `VELAR_API_KEY` | `str` | Yes | — | **Declared but never read by `core/security.py`** — see [Known Issues](./16-known-issues-tech-debt.md#hardcoded-api-key) |

Because these are all required (no default) except where noted, **the process will fail to start** (Pydantic validation error at `settings = Settings()`) if `.env` is missing any of `MONGODB_URI`, `MILVUS_URI`, `EMBED_MODEL`, `LLM_MODEL`, or `VELAR_API_KEY`.

`ollama_hosts_list` is a computed property that splits `OLLAMA_HOSTS` on commas and strips whitespace; returns `[]` if unset.

## 4.2 Ollama host resolution — `core/ollama_client.py`

This module does real work **at import time** (not lazily): it computes `OLLAMA_HOST`, `EMBED_MODEL`, `LLM_MODEL` as module-level constants the first time anything imports `core.ollama_client`.

```mermaid
flowchart TD
    A[Module import] --> B{settings.OLLAMA_URI set?}
    B -- yes --> C[OLLAMA_HOST = OLLAMA_URI]
    B -- no --> D[resolve_ollama_host(ollama_hosts_list)]
    D --> E{hosts list empty?}
    E -- yes --> F[raise RuntimeError]
    E -- no --> G[for each host: GET host, 2s timeout]
    G --> H{status_code == 200?}
    H -- yes --> I[return this host]
    H -- no, more hosts --> G
    H -- no, exhausted --> J[raise RuntimeError: all hosts failed]
```

Consumers: `rag/generator.py` and `embeddings/generate_embeddings.py` both import `OLLAMA_HOST`, `EMBED_MODEL`/`LLM_MODEL` from this module and build their API URLs by string concatenation (`f"{OLLAMA_HOST}/api/generate"`, `f"{OLLAMA_HOST}/api/embeddings"`). Because resolution happens at import time and raises on total failure, **any request touching the RAG or embedding pipeline will crash the whole process at import** if no configured Ollama host is reachable when that module is first imported (which, given Python's import caching, is typically at app startup via the router import chain: `app.py` → `routers.rag` → `rag.generator` → `core.ollama_client`).

## 4.3 Security — `core/security.py`

```python
async def validate_api_key(api_key_header: str = Security(api_key_header)) -> str:
    if not api_key_header:
        raise HTTPException(401, "Missing X-Velar-API-Key header")
    if api_key_header != "velar_test_key_123":
        raise HTTPException(403, "Invalid or revoked API Key")
    return "developer_id_789"
```

- The header name is `X-Velar-API-Key` (`API_KEY_NAME`), implemented via `fastapi.security.api_key.APIKeyHeader(auto_error=False)` so that a missing header is handled explicitly (401) rather than FastAPI's default 403.
- The comparison value is a **hardcoded literal**, not `settings.VELAR_API_KEY`. Every deployment of this code accepts exactly one key: `velar_test_key_123`, regardless of what is configured in `.env`. This is flagged as a critical finding in [Known Issues](./16-known-issues-tech-debt.md#hardcoded-api-key).
- On success, the function returns a **hardcoded identity string** `"developer_id_789"` — there is no real multi-tenant identity resolution; this return value is unused by any caller today (FastAPI dependency return values are discarded when used only in `dependencies=[...]`, not `Depends()` bound to a parameter).
- The docstring claims "In production, this routes through Redis for sub-millisecond validation" — no Redis client, dependency, or configuration exists anywhere in this repository.

## 4.4 Rate limiting — `core/rate_limiter.py`

Uses **SlowAPI** (`slowapi.Limiter`), keyed by `get_remote_address` (client IP). Global defaults: `1000/day`, `100/minute`. `setup_rate_limiting(app)` attaches the limiter to `app.state.limiter` and registers `RateLimitExceeded` → `_rate_limit_exceeded_handler`.

The only per-route override in the codebase is on the inline (unreachable — see [02 · API Reference](./02-api-reference.md#22-system-endpoints)) `public_categorize` stub: `@limiter.limit("50/minute")`. Since that route is shadowed by the router-mounted `/v1/categorize`, **no endpoint in the live routing table currently has a tighter-than-default rate limit** — everything effectively runs at 100/minute per IP.

`test_api.py::test_rate_limiter_defense` is marked `xfail` with the reason "TestClient bypasses actual ASGI network layer, preventing IP-based rate limiting in some configurations" — rate limiting is acknowledged by the team as untested in CI.

## 4.5 Database clients

### MongoDB — `database/mongo.py`
- `MongoDB` is a class used purely as a namespace (all methods are `@classmethod`, attributes are class-level) — instantiated once as `db = MongoDB()`, but since everything is class-level, any import of `database.mongo.db` sees the same shared state as `MongoDB` itself.
- `connect(uri, db_name)` creates one `AsyncIOMotorClient` and binds seven named collection accessors as class attributes (`transactions`, `feedback`, `categories`, `merchants`, `merchant_profiles`, `behavior_patterns`, `retraining_queue`).
- `disconnect()` closes the client if present.
- No connection pooling configuration, no TLS options, no retryWrites configuration — whatever Motor/PyMongo defaults apply given the URI.

### Milvus — `database/milvus.py`
- `VectorDB.connect(uri, retries=5, delay=3)` retries up to 5 times with a blocking `time.sleep(delay)` between attempts (this is a **synchronous** sleep inside code called from the async `lifespan`, so it blocks the event loop for up to 15 seconds during startup if Milvus is slow to come up).
- On success it calls `client.list_collections()` purely to confirm connectivity (result is logged at DEBUG, not otherwise used).
- On exhausting all retries, `cls.client` is set to `None` rather than raising — the app will start in a degraded state and `/health` will report `milvus: disconnected`.
- **This `vector_db` singleton is not used anywhere else in the codebase.** All actual Milvus reads/writes go through the separate `milvus.insert_vectors.VectorStoreManager` (`vector_store`) and `milvus.search_vectors.VectorSearchEngine` (`vector_search`), which each construct their own `MilvusClient` directly from `os.getenv("MILVUS_URI", "http://localhost:19530")` — bypassing `core.config.settings` entirely. See [01 · Architecture §1.2](./01-architecture.md#12-process-topology) and [Known Issues](./16-known-issues-tech-debt.md#duplicate-milvus-clients).

## 4.6 Application composition — `app.py`

- Logging is configured globally at `DEBUG` level via `logging.basicConfig` — this applies to the root logger, so every module's `logging.getLogger(__name__)` calls inherit `DEBUG` verbosity in any environment unless overridden. There is no environment-based log-level switch (no `LOG_LEVEL` env var is read).
- `FastAPI(title="Velar", version="1.0.0", lifespan=lifespan)` — OpenAPI docs are available at the default `/docs` and `/redoc` paths (not disabled).
- Router mount order: `v1` → `memory` → `analytics` → `rag` → `observability`, each with `dependencies=[Depends(validate_api_key)]` applied at the `include_router` call (this wraps every route in that router with the auth dependency, in addition to any dependencies declared on the router or individual routes directly — there are none of the latter here).
- The local dev entry point (`if __name__ == "__main__": uvicorn.run(...)`) hardcodes `reload=True`, `host="0.0.0.0"`, `port=8000` — this path is bypassed entirely in Docker, where the `CMD`/`command` directly invokes `uvicorn app:app` without `--reload`.
