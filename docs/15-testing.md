# 15 · Testing

## 15.1 Automated suite — `test_api.py`

Single pytest file, 183 lines, using FastAPI's `TestClient` against the real `app` object (imported directly from `app.py`), so the module-scoped `client` fixture genuinely triggers the `lifespan` context manager — real MongoDB/Milvus connection attempts happen during test setup, meaning **this suite requires live MongoDB and Milvus reachable at whatever `.env` currently points to; nothing is mocked.**

| Test | Covers | Notes |
|---|---|---|
| `test_health_check` | `GET /health` | Asserts status is `healthy` or `degraded` — never fails purely on service unavailability |
| `test_security_missing_key` | Auth rejection | Asserts `401`/`403` on `POST /v1/categorize` with no key — will currently fail differently than expected if the `/v1/categorize` handler itself throws before auth is even relevant (auth is a router-level dependency, evaluated before the handler body, so this specific test should still pass even given the `/v1/categorize` bug) |
| `test_rate_limiter_defense` | SlowAPI 429 | Marked `@pytest.mark.xfail` — team-acknowledged as unreliable under `TestClient` |
| `test_resolution_regex_engine` | `POST /v1/resolve`, parametrized over 4 raw UPI/NEFT/IMPS/POS strings | Only asserts `cleaned_text` key presence, not its actual value — a weak assertion that would pass even if the cleaning logic regressed to producing wrong (but present) output |
| `test_categorize_valid_payload` | `POST /v1/categorize` | Asserts response has `merchant`/`category`/`confidence` keys — **this test should currently fail** given the `AttributeError` bug described in [02 · API Reference](./02-api-reference.md#23-transaction-intelligence-routersv1py-prefix-v1) and [16 · Known Issues](./16-known-issues-tech-debt.md#v1-categorize-is-broken), unless something in the actual deployed environment differs from what's committed |
| `test_memory_engine_lifecycle` | `/memory/update` state promotion | Drives a unique merchant through 3 encounters, asserting `EPHEMERAL` then `TEMPORARY` — this test **cannot pass while `repositories/profile_repository.py` has its missing-`Optional`-import bug**, since that would prevent the module (and thus the whole `/memory` router and app startup) from importing at all — see [16 · Known Issues](./16-known-issues-tech-debt.md#profile-repository-missing-import) |
| `test_confidence_evaluator_blocks_hallucinations` | Confidence wall | Straightforward, matches implementation |
| `test_analytics_categories_negative_days` | Boundary handling | Accepts either `200` or `422` — deliberately loose |
| `test_analytics_anomaly_check` | Z-score anomaly | Only checks `200` + key presence, not the actual anomaly verdict |
| `test_feedback_triggers_retraining_queue` | `POST /v1/feedback/` | Assertion is inside `if response.status_code == 200:` — since the feedback router is **not mounted** (§9), this request will 404 and the test will pass trivially without exercising anything, silently masking the fact that the feature is unreachable |
| `test_rag_explanation_safety` | `POST /v1/explain` | Accepts `200`, `404`, or `500` — a smoke test confirming the route exists and doesn't hard-crash, not a correctness test |
| `test_observability_endpoints` | Drift stubs | Matches the stub implementation exactly |

### Practical implication
Given the `repositories/profile_repository.py` `NameError` bug (see [16 · Known Issues](./16-known-issues-tech-debt.md#profile-repository-missing-import)), **the entire test module likely cannot even collect/run today**, because `app.py` imports `routers.memory` at module load time, which imports `memory.memory_manager`, which imports `repositories.profile_repository` — a chain that fails at import before any test executes. If tests are passing in your environment, either the bug has since been patched locally, or `pytest`'s collection is somehow not exercising this import chain (unlikely, since `test_api.py` imports `app` directly on line 7). This should be the first thing verified when picking up this codebase.

## 15.2 Manual E2E script — `scripts/test_pipeline.sh`

See [14 · Deployment & Operations §14.6](./14-deployment-operations.md#146-scriptstest_pipelinesh-manual-e2e-smoke-test). This is a curl-driven smoke test intended to be run against a live, already-started server — it is not invoked by CI (no CI configuration files exist anywhere in this repository; there is no `.github/workflows`, `.gitlab-ci.yml`, or equivalent).

## 15.3 What is not tested at all

- Rule engine (`engines/rule_engine.py`) has no direct unit test — only indirectly exercised via `/v1/categorize`, which is broken.
- Feature extractors (`features/*.py`) have no unit tests despite containing the most mathematically dense logic in the codebase (entropy, coefficient of variation, periodicity scoring).
- `behaviour/behavior_engine.py`, `clustering/*`, `embeddings/*`, `milvus/*`, `graphs/graph_builder.py`, `training/*`, `evaluation/metrics.py` have zero test coverage — consistent with them being disconnected from the live HTTP surface (§1.9 in [01 · Architecture](./01-architecture.md)).
- No test verifies the actual *content* of resolved merchant names, confidence values, or category outputs beyond key presence in several places (noted per-test above) — meaning a logic regression that still returns the right JSON shape would not be caught.
