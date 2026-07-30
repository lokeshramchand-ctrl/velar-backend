# 03 · Data Model

All Pydantic schemas live in `models/schemas.py`. Every model extends `CoreModel`, which sets `populate_by_name=True` and `arbitrary_types_allowed=True`, allowing both the Python field name and its Mongo `_id` alias to populate a field.

## 3.1 Schema reference

> ✅ **FIXED** — this section previously described `Merchant`/`Category` schema classes that were entirely unused (zero readers/writers) and matched neither the `merchants` collection's real shape nor anything else in the codebase. Both were removed. `Transaction` and `Feedback` are updated to match what's actually written. See [16 · Known Issues §16.4](./16-known-issues-tech-debt.md#164-low-previously-latent-bugs-unusedmismatched-code-cosmetic--fixed).

### `Transaction`
| Field | Type | Notes |
|---|---|---|
| `id` | `Optional[str]` (alias `_id`) | |
| `raw_text` | `str` | |
| `merchant` | `Optional[str]` | |
| `amount` | `float` | |
| `category` | `Optional[str]` | |
| `user_id` | `str` | default `"system_user"` — matches what `routers/v1.py` and `scripts/mock_seeder.py` actually write |
| `is_mock` | `bool` | default `False` — matches `scripts/mock_seeder.py`'s flag |
| `timestamp` | `datetime` | default now (UTC) |

Previously had a required `source: str` field that nothing ever wrote, and was missing `user_id`/`is_mock`, which everything actually writes. This model still isn't validated against inserted documents anywhere (Motor writes raw dicts) — that's an intentional simplicity trade-off in this codebase, not a bug.

### `Feedback`
| Field | Type | Notes |
|---|---|---|
| `id` | `Optional[str]` (alias `_id`) | |
| `transaction_id` | `str` | |
| `merchant_name` | `Optional[str]` | ✅ Added — resolved from `transaction_id` at write time; this is the join key `rag/retriever.py` and `graphs/graph_builder.py` now use instead of `prediction` |
| `prediction` | `str` | holds a category value, e.g. `"Unknown"`, `"Travel"` |
| `corrected_category` | `str` | |
| `confidence` | `float` | |
| `is_correction` | `bool` | default `False` |
| `user_id` | `str` | default `"system_user"` |
| `timestamp` | `datetime` | default now (UTC) |

### `CategorizeRequest` / `CategorizeResponse`
Request: `{ text: str }`. Response: `{ merchant: str, category: str, confidence: float, transaction_id: Optional[str] }`. Used by `POST /v1/categorize`. `transaction_id` (the inserted Mongo document's stringified `_id`) was added so `POST /v1/feedback/` has something real to resolve a merchant from.

### `ResolutionResult`
`{ raw_text, cleaned_text, canonical_merchant, confidence, is_resolved, resolution_method }`. `resolution_method`'s docstring now reads `exact_alias | substring | none` (previously incorrectly listed `rule_engine` as a possible value, which `services/merchant_resolver.py` never actually emits).

### `MemoryState` (enum)
`EPHEMERAL`, `TEMPORARY`, `PERMANENT`, `ARCHIVED` — see [05 · Ingestion, Resolution & Memory](./05-ingestion-resolution-memory.md) for the transition rules.

### `MerchantProfile`
| Field | Type | Default |
|---|---|---|
| `id` | `Optional[str]` (alias `_id`) | `None` |
| `canonical_name` | `str` | required |
| `display_name` | `Optional[str]` | `None` |
| `aliases` | `List[str]` | `[]` |
| `entity_type` | `str` | `"Unknown"` |
| `memory_state` | `MemoryState` | `EPHEMERAL` |
| `frequency` | `int` | `1` |
| `first_seen` | `datetime` | now (UTC) |
| `last_seen` | `datetime` | now (UTC) |
| `notes` | `Optional[str]` | `None` |
| `confidence` | `float` | `0.0` |
| `category` | `Optional[str]` | `None` |
| `subcategory` | `Optional[str]` | `None` |

Backing collection: `merchant_profiles`. Written/read exclusively through `repositories/profile_repository.py`.

### `TransactionCategory` (enum)
`Food`, `Travel`, `Entertainment`, `Bills`, `Friends`, `Education`, `Healthcare`, `Unknown`. This is the closed vocabulary enforced by the confidence engine — note `merchant_aliases.json` and the analytics mock seeder both use category values (`"Subscription"`, `"Shopping"`, `"Utility"`, `"Income"`) that **are not members of this enum**, meaning `ConfidenceEngine.evaluate()` would reject them as invalid categories and force `Unknown` if ever passed through it. See [Known Issues](./16-known-issues-tech-debt.md#category-vocabulary-mismatch).

### `ConfidenceEvaluation`
`{ raw_category, final_category: TransactionCategory, confidence, is_hallucination_risk, calibration_applied }`. Output of `engines/confidence_engine.py`.

### `BehaviorPattern`
| Field | Type | Meaning |
|---|---|---|
| `id` | `Optional[str]` (alias `_id`) | |
| `merchant_name` | `str` | Resolved name or unresolved raw string |
| `avg_amount`, `median_amount`, `variance`, `std_dev` | `float` | From `features/amount_features.py` |
| `preferred_hour` | `int` | Mode of transaction hour, from `features/temporal_features.py` |
| `time_bucket_distribution` | `Dict[str, float]` | `{morning, afternoon, evening, night}` normalized frequencies |
| `weekday_distribution` | `List[float]` | Length-7 normalized frequency array (Mon=0 per Python `.weekday()`) |
| `daily_frequency`, `weekly_frequency` | `float` | From `features/frequency_features.py` |
| `periodicity_score` | `float` | 0.0 (random) – 1.0 (perfectly regular), from `features/periodicity.py` |
| `entropy_score` | `float` | Shannon entropy of rounded amount buckets, from `features/amount_features.py` |
| `last_updated` | `datetime` | default now (UTC) |

Backing collection: `behavior_patterns`. Written only by `behaviour/behavior_engine.py` (not wired to any HTTP endpoint — see [01 · Architecture §1.9](./01-architecture.md#19-what-is-not-wired-into-the-http-surface)). Also gains a non-schema field `discovered_cluster` when written by `clustering/cluster_engine.py::_persist_clusters` (Mongo is schemaless at the driver level, so this is a silent extension not reflected in the Pydantic model).

### `User`
| Field | Type | Notes |
|---|---|---|
| `id` | `Optional[str]` (alias `_id`) | Mongo's own ObjectId, stringified — this is the value encoded as the JWT `sub` claim |
| `email` | `EmailStr` | Lowercased before storage (see `RegisterRequest`/`LoginRequest`); unique index, see §3.2 |
| `hashed_password` | `str` | Argon2id hash (`core/security.py::hash_password`) — never serialized in any API response |
| `is_active` | `bool` | default `True` |
| `created_at`, `updated_at` | `datetime` | default now (UTC) |

`UserPublic` is the response-safe counterpart — a deliberately separate model (not `User` with a field excluded) so a future field added to `User` can never leak into a response by accident: `{ id, email, is_active, created_at }`.

Backing collection: `users`. Written/read exclusively through `repositories/user_repository.py`.

### Refresh token documents
Not a Pydantic model — `repositories/refresh_token_repository.py` writes/reads plain dicts directly, since nothing outside that repository ever needs to construct or validate one.

| Field | Type | Notes |
|---|---|---|
| `user_id` | `str` | References `User.id` |
| `token_hash` | `str` | SHA-256 hex digest of the opaque refresh token; the raw token itself is never persisted |
| `expires_at` | `datetime` | Backs the TTL index, see §3.2 |
| `created_at` | `datetime` | |
| `revoked_at` | `Optional[datetime]` | `None` while active; set on rotation, logout, or reuse-detection mass-revocation |

Backing collection: `refresh_tokens`.

## 3.2 MongoDB collections

Declared in `database/mongo.py::MongoDB.connect`:

| Collection | Written by | Read by |
|---|---|---|
| `transactions` | `routers/v1.py` (categorize, buggy), `scripts/mock_seeder.py` | `analytics/*.py`, `behaviour/behavior_engine.py` |
| `feedback` | `feedback/feedback_service.py` | `rag/retriever.py`, `graphs/graph_builder.py` |
| `categories` | *(nothing)* | *(nothing)* |
| `merchants` | `scripts/seed.py` | `services/merchant_resolver.py` |
| `merchant_profiles` | `repositories/profile_repository.py` | `repositories/profile_repository.py`, `rag/retriever.py`, `graphs/graph_builder.py` |
| `behavior_patterns` | `behaviour/behavior_engine.py`, `clustering/cluster_engine.py` (adds `discovered_cluster`) | `analytics/anomaly_detection.py`, `analytics/subscriptions.py`, `rag/retriever.py`, `graphs/graph_builder.py` |
| `retraining_queue` | `feedback/retraining_queue.py` (via `feedback_service`) | `feedback/retraining_queue.py::check_retraining_status` |
| `users` | `repositories/user_repository.py` | `repositories/user_repository.py`, `core/jwt_auth.py::get_current_user` |
| `refresh_tokens` | `repositories/refresh_token_repository.py` | `repositories/refresh_token_repository.py` |

`database/mongo.py::ensure_indexes()` (called once from `app.py`'s `lifespan`) creates indexes for every query pattern that actually needs one, including the auth collections added here:
- `users.email` — unique (backs the register-time uniqueness guarantee; also what every login/`/auth/me` lookup queries on)
- `refresh_tokens.token_hash` — unique (looked up on every `/auth/refresh` call)
- `refresh_tokens.user_id` — supports the mass-revocation query used on logout-all/reuse-detection
- `refresh_tokens.expires_at` — TTL index (`expireAfterSeconds=0`), so MongoDB itself sweeps expired refresh token documents without a separate cleanup job

See [22 · Authentication §22.7](./22-authentication.md#227-data-model) for how these back the auth flows.

## 3.3 Milvus vector schema

Defined in `milvus/insert_vectors.py::VectorStoreManager._ensure_collections`:

| Property | Value |
|---|---|
| Collection name | `behavior_vectors` |
| Field `id` | `VARCHAR(255)`, primary key |
| Field `merchant_name` | `VARCHAR(255)` |
| Field `embedding` | `FLOAT_VECTOR`, dim `768` |
| Index | HNSW, `metric_type=COSINE`, `M=8`, `efConstruction=200` |
| Search params | `{"metric_type": "COSINE", "params": {"ef": 64}}` |

The collection is created lazily via `vector_store.ensure_collections()`, called once from `app.py`'s `lifespan` right after `vector_db.connect()` succeeds — previously this happened at module-import time inside `VectorStoreManager.__init__`, which meant a briefly-unreachable Milvus could crash the whole app at import rather than just failing gracefully during startup (fixed, see [16 · Known Issues §16.3](./16-known-issues-tech-debt.md#163-medium-previously-disconnected-features-dead-code-silent-no-ops--fixed)). The dimension `768` must exactly match the output size of whatever model `EMBED_MODEL` points to on the Ollama server — there is no runtime validation of this; a mismatch will surface as a Milvus insertion/search error at call time.

## 3.4 Field/vocabulary inconsistencies worth knowing before writing new code

- ✅ **FIXED** — `TransactionCategory` enum now includes `Subscription`, `Shopping`, and `Utility` alongside the original members, matching what `merchant_aliases.json` and `scripts/mock_seeder.py` actually produce (previously these were force-rejected to `Unknown` by `ConfidenceEngine.evaluate()`).
- ✅ **FIXED** — `features/amount_features.py::extract_statistical_metrics`'s empty-input (`n == 0`) branch now returns the same key names as its normal branch (`avg_amount`, `median_amount`, `variance`, `std_dev`, `entropy_score`) instead of a differently-named set (`avg`, `median`, `entropy`) that would have `KeyError`'d if a caller without `behaviour/behavior_engine.py`'s empty-set guard ever hit this path.
- ✅ **FIXED** — `features/temporal_features.py::extract_temporal_metrics` had the same shape mismatch; its empty-input branch now returns `time_bucket_distribution`/`weekday_distribution`, matching the normal branch (previously `time_buckets`/`weekday_dist`).
