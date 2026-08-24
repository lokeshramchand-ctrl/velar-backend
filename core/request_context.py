import logging
from fastapi import Request

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request, accounting for proxies.

    Checks X-Forwarded-For, X-Real-IP, and Falls back to direct connection.
    """
    if x_forwarded_for := request.headers.get("x-forwarded-for"):
        return x_forwarded_for.split(",")[0].strip()

    if x_real_ip := request.headers.get("x-real-ip"):
        return x_real_ip

    if request.client:
        return request.client.host

    return "unknown"


def get_user_agent(request: Request) -> str | None:
    """Extract user agent from request headers."""
    return request.headers.get("user-agent")


def get_device_fingerprint(request: Request) -> str | None:
    """Generate a device fingerprint from request headers.

    Creates a hash of user agent, accept-language, and accept-encoding
    to identify likely device/browser combinations.
    """
    try:
        components = [
            request.headers.get("user-agent", ""),
            request.headers.get("accept-language", ""),
            request.headers.get("accept-encoding", ""),
        ]
        fingerprint_str = "|".join(components)

        import hashlib
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]
    except Exception as e:
        logger.warning(f"Failed to generate device fingerprint: {str(e)}")
        return None


class RequestContextData:
    """Encapsulates security-relevant request context."""

    def __init__(self, request: Request):
        self.ip_address = get_client_ip(request)
        self.user_agent = get_user_agent(request)
        self.device_fingerprint = get_device_fingerprint(request)
        self.request_id = request.scope.get("state", {}).get("request_id", "unknown")

    def to_dict(self) -> dict:
        """Convert to dictionary for logging."""
        return {
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "device_fingerprint": self.device_fingerprint,
            "request_id": self.request_id,
        }
