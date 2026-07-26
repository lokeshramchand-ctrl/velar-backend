# 03 · Data Model

All Pydantic schemas live in `models/schemas.py`. Every model extends `CoreModel`, which sets `populate_by_name=True` and `arbitrary_types_allowed=True`, allowing both the Python field name and its Mongo `_id` alias to populate a field.

## 3.1 Schema reference

### `Merchant`
| Field | Type | Notes |
|---|---|---|
| `id` | `str` (alias `_id`) | Mongo document id |
| `name` | `str` | |
| `aliases` | `list[str]` | default `[]` |
| `created_at` | `datetime` | default now (UTC) |

Note: the actual `merchants` collection documents written by `scripts/seed.py` use `canonical_name` + `aliases`, not `name` — this `Merchant` model does not match what's actually stored/queried against the `merchants` collection anywhere in the code (`services/merchant_resolver.py` queries `aliases` and reads back `canonical_name`, never validating against this model). `Merchant` appears to be unused/vestigial.

### `Category`
| Field | Type | Notes |
|---|---|---|
| `id` | `str` (alias `_id`) | |
| `name` | `str` | |
| `description` | `Optional[str]` | |

Not referenced anywhere outside this file — the `categories` Mongo collection is created (`database/mongo.py`) but never read or written by any module.

### `Transaction`
| Field | Type | Notes |
|---|---|---|
| `id` | `Optional[str]` (alias `_id`) | |
| `raw_text` | `str` | |
| `merchant` | `Optional[str]` | |
| `amount` | `float` | |
| `category` | `Optional[str]` | |
| `source` | `str` | |
| `timestamp` | `datetime` | default now (UTC) |

Documents actually inserted into `db.transactions` (by `scripts/mock_seeder.py`, and intended by `routers/v1.py`) use fields `user_id`, `merchant`, `category`, `amount`, `timestamp`, `is_mock` — `user_id` and `is_mock` are not part of this schema, and `source`/`raw_text` are not populated by the seeder. This model is not actually validated against inserted documents anywhere (Motor writes raw dicts).

### `Feedback`
| Field | Type | Notes |
|---|---|---|
| `id` | `Optional[str]` (alias `_id`) | |
| `transaction_id` | `str` | |
| `prediction` | `str` | |
| `corrected_category` | `str` | |
| `confidence` | `float` | |
| `timestamp` | `datetime` | default now (UTC) |

Matches the shape written by `feedback/feedback_service.py`'s `feedback_doc`, plus that doc also stores `is_correction` and `user_id`, which are not in this schema.

### `CategorizeRequest` / `CategorizeResponse`
Request: `{ text: str }`. Response: `{ merchant: str, category: str, confidence: float }`. Used by `POST /v1/categorize`.

### `ResolutionResult`
`{ raw_text, cleaned_text, canonical_merchant, confidence, is_resolved, resolution_method }`. `resolution_method` is a free-text field documented (not enum-enforced) as one of `exact_alias | substring | rule_engine | none` — note `services/merchant_resolver.py` never actually emits `"rule_engine"` as a value; only `exact_alias`, `substring`, and `none` are produced.

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

No indexes are created programmatically anywhere in this codebase (no `create_index` calls) — all queries above run against unindexed collections by default.

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

The collection is created lazily on first `VectorStoreManager()` instantiation (module import time, in `milvus/insert_vectors.py`) if it doesn't already exist, then immediately `load_collection`'d into memory. The dimension `768` must exactly match the output size of whatever model `EMBED_MODEL` points to on the Ollama server — there is no runtime validation of this; a mismatch will surface as a Milvus insertion/search error at call time.

## 3.4 Field/vocabulary inconsistencies worth knowing before writing new code

- `TransactionCategory` enum vs. actual category strings in use (`merchant_aliases.json`, mock seeder) diverge — see §3.1 above and [Known Issues](./16-known-issues-tech-debt.md#category-vocabulary-mismatch).
- `features/amount_features.py::extract_statistical_metrics` returns keys `avg`, `median`, `variance`, `std_dev`, `entropy` in its empty-input (`n == 0`) branch, but `avg_amount`, `median_amount`, `variance`, `std_dev`, `entropy_score` in its normal branch — callers (`behaviour/behavior_engine.py`) always index with the normal-branch key names, so an empty-amounts call would `KeyError`. In practice `behavior_engine` already guards against empty transaction sets before calling this, so the bug is latent rather than triggered on the current call path.
- `features/temporal_features.py::extract_temporal_metrics` has the same shape: its empty-input branch returns `time_buckets`/`weekday_dist`, while the normal branch returns `time_bucket_distribution`/`weekday_distribution`. Same latent-bug caveat applies.
