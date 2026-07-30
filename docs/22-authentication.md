# 22 · Authentication

## 22.1 Two independent layers

This system authenticates two different things, checked independently:

| Layer | Proves | Mechanism | Where enforced |
|---|---|---|---|
| API key | Which **application** is calling | `X-Velar-API-Key` header, compared against `settings.VELAR_API_KEY` via `secrets.compare_digest` (`core/security.py::validate_api_key`) | `dependencies=[Depends(validate_api_key)]` on every `include_router(...)` call in `app.py` — unchanged from before this feature existed |
| JWT | Which **end user** is calling, within that application | `Authorization: Bearer <access token>` header, verified against `settings.JWT_SECRET_KEY` (`core/jwt_auth.py::get_current_user`) | `current_user: User = Depends(get_current_user)` bound explicitly as a handler parameter, only where the resolved identity is actually used |

These compose, not substitute for each other. A router-mounted API-key dependency runs for *every* request to that router regardless of what an individual handler additionally declares — so a genuine, unexpired JWT presented without the API key is rejected before any handler body runs, and a valid API key alone is never sufficient on a handler that also requires `get_current_user`. See `test_categorize_and_analytics_reject_jwt_without_api_key` and `test_security_valid_key_missing_jwt` in `test_api.py`.

The API-key dependency is attached via `dependencies=[...]` (its return value is discarded — see [16 · Known Issues](./16-known-issues-tech-debt.md) for why that's fine for a single shared key with no distinct identity to carry). The JWT dependency is deliberately *not* attached that way: it's bound to a `current_user` parameter precisely because handlers need the resolved identity (to scope a Mongo query by `user_id`, for instance), not just a pass/fail check.

## 22.2 Endpoint protection matrix

| Endpoint | API key | JWT | Why |
|---|---|---|---|
| `GET /health`, `/live`, `/ready`, `/metrics` | — | — | Infrastructure/orchestrator endpoints; unauthenticated by convention (unchanged) |
| `POST /auth/register` | ✅ | — | Onboards a new user on behalf of the calling application; no JWT exists yet |
| `POST /auth/login` | ✅ | — | Same — issues the first JWT for this user |
| `POST /auth/refresh` | ✅ | — | Authenticates via the presented refresh token itself, not an access token |
| `POST /auth/logout` | ✅ | — | Revokes a refresh token by value; deliberately works even if the access token already expired |
| `GET /auth/me` | ✅ | ✅ | Returns the calling user's own profile |
| `POST /v1/categorize` | ✅ | ✅ | Persists a transaction attributed to `current_user.id` |
| `GET /v1/analytics/patterns/categories`, `/patterns/merchants`, `/subscriptions`, `/trends/mom` | ✅ | ✅ | All query transactions scoped to `current_user.id` (previously a hardcoded `TEST_USER = "user_123"` — see [16 · Known Issues](./16-known-issues-tech-debt.md)) |
| `POST /v1/feedback/` | ✅ | ✅ | Attributes feedback to `current_user.id` instead of the previous default `"system_user"` |
| `POST /v1/resolve`, `POST /v1/confidence/evaluate`, `POST /v1/explain` | ✅ | — | Stateless utilities / RAG over the shared merchant knowledge base — not scoped to one user's data |
| `POST /v1/analytics/anomaly/check` | ✅ | — | Evaluates a merchant/amount pair against that merchant's global behavioral profile, not any one user's history |
| `/memory/*` | ✅ | — | Merchant profiles are a shared knowledge base, not per-user data |
| `/v1/pipelines/*`, `/v1/observability/*` | ✅ | — | Batch/admin operations with no per-user semantics |

## 22.3 Token design

**Access tokens** (`core/jwt_auth.py::create_access_token`) are JWTs, HS256-signed with `settings.JWT_SECRET_KEY`, default lifetime 15 minutes (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`). Claims: `sub` (user id), `type: "access"`, `iat`, `exp`, `jti`. The `type` claim is checked on every decode so a refresh token (even if it were somehow HS256-decodable) can never be used where an access token is expected — see `test_auth_me_wrong_token_type`.

**Refresh tokens** (`core/jwt_auth.py::generate_refresh_token`) are deliberately *not* JWTs — `secrets.token_urlsafe(48)` opaque random values, default lifetime 30 days (`JWT_REFRESH_TOKEN_EXPIRE_DAYS`). Only a SHA-256 hash is ever persisted (`repositories/refresh_token_repository.py`), so a database dump alone can't be replayed as a valid session. A self-contained JWT refresh token can't be individually revoked before its own expiry without a separate blocklist anyway — an opaque, server-stored token gets that for free from the storage model itself.

**Rotation and reuse detection** (`routers/auth.py::refresh`): every `POST /auth/refresh` call revokes the presented token and issues a brand-new pair — a refresh token is single-use. If an already-revoked token is presented again (a strong signal it was stolen and both the legitimate client and an attacker are racing to use it), every other active session for that user is revoked too (`refresh_token_repo.revoke_all_for_user`), not just the replayed token.

## 22.4 Password storage

`core/security.py::hash_password` / `verify_password` use Argon2id (`argon2-cffi`, the library's default variant) with its built-in OWASP-aligned cost parameters — salting and constant-time verification are handled internally, not hand-rolled. `POST /auth/login` runs `verify_password` even when no user was found for the given email (against a throwaway hash), so response timing doesn't reveal whether an email is registered.

## 22.5 Configuration

| Setting | Default | Notes |
|---|---|---|
| `JWT_SECRET_KEY` | *(required)* | No default — `core/config.py` fails app startup if missing **or** shorter than 32 characters, the same "fail fast on a bad mandatory secret" posture as `VELAR_API_KEY`/`MONGODB_URI`, extended to also reject a present-but-weak value |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `30` | |

## 22.6 Rate limiting

`POST /auth/register`: `5/minute`. `POST /auth/login`: `10/minute`. `POST /auth/refresh`, `POST /auth/logout`: `20/minute`. All per-IP via the same SlowAPI `limiter` (`core/rate_limiter.py`) every other rate-limited endpoint uses — deliberately tighter than the `100/minute` global default, since these are the endpoints a credential-stuffing or account-enumeration attempt would actually hit.

## 22.7 Data model

See [03 · Data Model §3.1](./03-data-model.md#31-schema-reference) for the `User` schema and `users`/`refresh_tokens` collection document shapes, and [§3.2](./03-data-model.md#32-mongodb-collections) for the Mongo indexes backing them (`users.email` unique, `refresh_tokens.token_hash` unique, `refresh_tokens.user_id`, and a TTL index on `refresh_tokens.expires_at` so MongoDB itself sweeps expired tokens without a separate cleanup job).

## 22.8 OpenAPI / Swagger

Both schemes are registered automatically (FastAPI introspects the `Security()`-based dependencies used across the app) and appear together in Swagger's "Authorize" dialog at `/docs`: `APIKeyHeader` (`X-Velar-API-Key`) and `JWT` (HTTP Bearer). Authorizing with both lets `/docs` exercise every endpoint, including the ones that require both layers.
