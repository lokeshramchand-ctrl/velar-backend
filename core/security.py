import logging
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

from core.config import settings

logger = logging.getLogger(__name__)

API_KEY_NAME = "X-Velar-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

ADMIN_KEY_NAME = "X-Velar-Admin-Key"
admin_key_header = APIKeyHeader(name=ADMIN_KEY_NAME, auto_error=False)

# Argon2id (the library's default variant) with its built-in, OWASP-aligned
# default cost parameters - the current recommended password hashing
# algorithm, ahead of bcrypt/PBKDF2. Salting and constant-time verification
# are handled internally by the library, not hand-rolled here.
_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Constant-time-verified against the stored hash. Returns False for any
    mismatch or malformed/foreign hash rather than raising, so callers never
    need to special-case a corrupt stored value vs. a genuinely wrong password."""
    try:
        return _password_hasher.verify(hashed_password, password)
    except (VerifyMismatchError, InvalidHashError):
        return False

async def validate_api_key(api_key_header: str = Security(api_key_header)) -> str:
    """
    Validates the incoming API key.
    In production, this routes through Redis for sub-millisecond validation.
    """
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Velar-API-Key header"
        )

    if not secrets.compare_digest(api_key_header, settings.VELAR_API_KEY):
        logger.warning("Rejected invalid API key attempt.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or revoked API Key"
        )

    return "developer_id_789" # Returns the authenticated entity


async def validate_admin_key(admin_key_header: str = Security(admin_key_header)) -> str:
    """Gates routers/pipelines.py's operational/batch endpoints. These run
    expensive, system-wide jobs (full clustering passes, embedding syncs)
    with no per-user scope, so VELAR_API_KEY - shipped inside every client
    app binary and trivially extractable from the compiled app - isn't a
    safe gate for them on its own. Unset ADMIN_API_KEY means these
    endpoints are unreachable (503) rather than falling back to anything
    permissive."""
    if not settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin operations are not enabled on this deployment.",
        )

    if not admin_key_header or not secrets.compare_digest(admin_key_header, settings.ADMIN_API_KEY):
        logger.warning("Rejected invalid or missing admin key attempt.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing admin key",
        )

    return "admin"
