import logging
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import settings
from models.schemas import User
from repositories.user_repository import user_repo

logger = logging.getLogger(__name__)

# auto_error=False mirrors core/security.py::api_key_header - lets this
# function distinguish "no token at all" from "token present but invalid"
# with its own specific detail message instead of a generic framework 403.
bearer_scheme = HTTPBearer(
    scheme_name="JWT",
    description="Access token obtained from POST /auth/login or POST /auth/refresh.",
    auto_error=False,
)

ACCESS_TOKEN_TYPE = "access"  # noqa: S105 - a JWT "type" claim value, not a credential


def create_access_token(user_id: str, scopes: list[str] | None = None) -> tuple[str, int]:
    """Returns (token, expires_in_seconds).

    Args:
        user_id: The subject (user ID) for the token
        scopes: Optional list of authorization scopes (e.g., ["statements:read", "admin"])
    """
    now = datetime.now(UTC)
    lifetime = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + lifetime,
        "jti": secrets.token_hex(16),
    }
    if scopes:
        payload["scopes"] = scopes
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, int(lifetime.total_seconds())


def generate_refresh_token(device_id: str | None = None) -> tuple[str, datetime]:
    """Opaque, high-entropy token with optional device tracking. Returns
    (raw_token, expires_at); only the raw token is ever returned to the
    client, never persisted in plaintext.

    Args:
        device_id: Optional device identifier for per-device authorization
    """
    raw_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    return raw_token, expires_at


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except jwt.InvalidTokenError as e:
        # Covers bad signature, malformed token, wrong algorithm, etc. - PyJWT
        # collapses these into subclasses of InvalidTokenError; the client
        # doesn't need to know which one, and detailing it would be a minor
        # oracle for token-forgery attempts.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    """The JWT half of this app's two-layer auth (see core/security.py for
    the API-key half). Bind this via `Depends(get_current_user)` on a
    handler parameter - not `dependencies=[...]` - wherever the resolved
    identity is actually needed, e.g. to scope a query by user id.

    Returns the decoded JWT payload dict with 'sub', 'scopes', 'jti', etc.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    user = await user_repo.get_by_id(user_id) if user_id else None

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        # 403, not 401: the token itself is genuine and correctly identifies
        # a real user (authentication succeeded) - the account is just
        # disabled (an authorization decision), matching this codebase's
        # 401-vs-403 convention in core/security.py.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    return payload


def require_scope(required_scopes: str | list[str]):
    """FastAPI dependency factory that checks for required authorization scopes.

    Usage:
        @router.get("/admin/users")
        async def admin_endpoint(payload = Depends(require_scope("admin"))):
            ...

    Args:
        required_scopes: Single scope or list of scopes (at least one must be present)

    Returns:
        FastAPI dependency function
    """
    if isinstance(required_scopes, str):
        required_scopes = [required_scopes]

    async def check_scopes(
        payload = Depends(get_current_user),
    ) -> dict:
        token_scopes = payload.get("scopes", [])

        # Check if any required scope is present
        if not any(scope in token_scopes for scope in required_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required scope not present. Need one of: {', '.join(required_scopes)}"
            )

        return payload

    return check_scopes
