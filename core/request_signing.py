import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status

from database.mongo import db

logger = logging.getLogger(__name__)


class RequestSigningVerifier:
    """Verify HMAC-SHA256 signed requests and detect replay attacks using
    a nonce cache. Clients sign each request with a per-device signing key;
    the backend verifies the signature and rejects if the nonce was seen before."""

    NONCE_TTL_SECONDS = 300  # Nonces expire after 5 minutes

    @staticmethod
    def compute_signature(
        method: str,
        path: str,
        timestamp: str,
        nonce: str,
        body_hash: str,
        signing_secret: str
    ) -> str:
        """Compute HMAC-SHA256 signature over method, path, timestamp, nonce,
        and body hash, concatenated in that order."""
        message = f"{method}|{path}|{timestamp}|{nonce}|{body_hash}"
        signature = hmac.new(
            signing_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature

    async def verify_request_signature(
        self,
        method: str,
        path: str,
        timestamp: str,
        nonce: str,
        body_hash: str,
        provided_signature: str,
        signing_secret: str,
        max_age_seconds: int = 60
    ) -> tuple[bool, str | None]:
        """Verify request signature and check for replay.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path
            timestamp: ISO8601 timestamp from request header
            nonce: Unique nonce from request header
            body_hash: SHA-256 hash of request body (hex)
            provided_signature: X-Signature header value
            signing_secret: Device-specific signing secret
            max_age_seconds: Maximum age of timestamp (60 seconds default)

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Verify signature
        expected_signature = self.compute_signature(
            method, path, timestamp, nonce, body_hash, signing_secret
        )

        if not hmac.compare_digest(provided_signature, expected_signature):
            logger.warning(f"Signature mismatch for {method} {path}")
            return False, "Invalid signature"

        # Check timestamp freshness
        try:
            request_time = datetime.fromisoformat(timestamp)
            if request_time.tzinfo is None:
                request_time = request_time.replace(tzinfo=UTC)

            age = datetime.now(UTC) - request_time
            if age.total_seconds() > max_age_seconds:
                logger.warning(f"Stale request timestamp: {age.total_seconds()}s old")
                return False, "Request timestamp too old"
        except Exception as e:
            logger.warning(f"Invalid timestamp format: {e}")
            return False, "Invalid timestamp"

        # Check nonce for replay
        nonce_record = await db.request_nonces.find_one({"nonce": nonce})
        if nonce_record is not None:
            logger.warning(f"Replay detected: nonce {nonce} reused")
            return False, "Nonce reused (replay detected)"

        # Store nonce with expiration
        await db.request_nonces.insert_one({
            "nonce": nonce,
            "timestamp": datetime.now(UTC),
            "expires_at": datetime.now(UTC) + timedelta(seconds=self.NONCE_TTL_SECONDS)
        })

        # Set TTL index for automatic cleanup (if not already set)
        await db.request_nonces.create_index(
            "expires_at",
            expireAfterSeconds=0
        )

        return True, None


request_signing_verifier = RequestSigningVerifier()


async def validate_request_signature(request: Request) -> None:
    """FastAPI dependency to validate request signature. Can be applied to
    routes that require signed requests.

    Expects headers:
    - X-Signature: HMAC-SHA256 signature
    - X-Timestamp: ISO8601 timestamp
    - X-Nonce: Unique nonce for replay protection

    Raises HTTPException if signature invalid or replay detected.
    """
    from core.config import settings
    from core.jwt_auth import get_current_user

    if not settings.REQUEST_SIGNING_REQUIRED:
        return  # Request signing not enforced

    # Get current user to look up device signing secret
    # This assumes the request already has a valid JWT (via get_current_user dependency)
    # For this to work, apply validate_request_signature AFTER get_current_user in
    # the dependency chain.

    signature = request.headers.get("X-Signature")
    timestamp = request.headers.get("X-Timestamp")
    nonce = request.headers.get("X-Nonce")

    if not all([signature, timestamp, nonce]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required signature headers (X-Signature, X-Timestamp, X-Nonce)"
        )

    # Read and hash request body
    body = await request.body()
    body_hash = hashlib.sha256(body).hexdigest()

    # For now, use a placeholder signing secret (in production, look this up
    # from the device's signing key stored in the database).
    # TODO: Retrieve device-specific signing secret from database
    signing_secret = "placeholder-device-signing-secret"

    is_valid, error = await request_signing_verifier.verify_request_signature(
        method=request.method,
        path=request.url.path,
        timestamp=timestamp,
        nonce=nonce,
        body_hash=body_hash,
        provided_signature=signature,
        signing_secret=signing_secret,
        max_age_seconds=settings.REQUEST_SIGNATURE_MAX_AGE_SECONDS
    )

    if not is_valid:
        logger.warning(f"Request signature validation failed: {error}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Request signature validation failed: {error}"
        )
