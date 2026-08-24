import logging
from datetime import UTC, datetime
from typing import Any

from database.mongo import db

logger = logging.getLogger(__name__)

class RefreshTokenRepository:
    """Stores only a SHA-256 hash of each refresh token, never the token
    itself - a leaked database dump alone can't be replayed as a valid
    session. Unlike password hashing, this deliberately uses a fast hash: the
    token is already 384 bits of `secrets.token_urlsafe` entropy (see
    core/jwt_auth.py::generate_refresh_token), so it needs no per-value salt
    or deliberately slow KDF, and it must support a plain equality lookup by
    hash on every refresh call."""

    async def store(
        self, user_id: str, token_hash: str, expires_at: datetime,
        device_id: str | None = None, device_name: str = "Unknown Device",
        user_agent: str | None = None, ip_address: str | None = None
    ) -> None:
        await db.refresh_tokens.insert_one({
            "user_id": user_id,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "created_at": datetime.now(UTC),
            "revoked_at": None,
            "device_id": device_id,
            "device_name": device_name,
            "user_agent": user_agent,
            "ip_address": ip_address,
            "last_used_at": datetime.now(UTC),
        })

    async def get_by_hash(self, token_hash: str) -> dict[str, Any] | None:
        return await db.refresh_tokens.find_one({"token_hash": token_hash})

    async def revoke(self, token_hash: str) -> None:
        """Idempotent: revoking an already-revoked or unknown token hash is a
        silent no-op, so callers (e.g. logout) never need to branch on
        whether the token existed."""
        await db.refresh_tokens.update_one(
            {"token_hash": token_hash, "revoked_at": None},
            {"$set": {"revoked_at": datetime.now(UTC)}},
        )

    async def revoke_all_for_user(self, user_id: str) -> None:
        """Used on refresh-token-reuse detection (see routers/auth.py) to
        burn every active session for a user, not just the replayed one."""
        await db.refresh_tokens.update_many(
            {"user_id": user_id, "revoked_at": None},
            {"$set": {"revoked_at": datetime.now(UTC)}},
        )

    async def revoke_by_device(self, user_id: str, device_id: str) -> None:
        """Revoke all tokens for a specific device."""
        await db.refresh_tokens.update_many(
            {"user_id": user_id, "device_id": device_id, "revoked_at": None},
            {"$set": {"revoked_at": datetime.now(UTC)}},
        )

    async def mark_used(self, token_hash: str) -> None:
        """Update last_used_at timestamp on token use."""
        await db.refresh_tokens.update_one(
            {"token_hash": token_hash},
            {"$set": {"last_used_at": datetime.now(UTC)}},
        )

    async def get_active_sessions_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """Retrieve all active (non-revoked) sessions for a user."""
        return await db.refresh_tokens.find(
            {"user_id": user_id, "revoked_at": None}
        ).to_list(None)

    async def revoke_old_token_on_refresh(self, old_token_hash: str) -> None:
        """Revoke the old refresh token when issuing a new one (rotation).
        This prevents accidental token reuse and limits session windows."""
        await db.refresh_tokens.update_one(
            {"token_hash": old_token_hash},
            {"$set": {"revoked_at": datetime.now(UTC)}},
        )

refresh_token_repo = RefreshTokenRepository()
