import uuid
import logging
from contextvars import ContextVar

from fastapi import HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Bound per-request so log records can include the request id without threading
# it through every function signature.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDMiddleware:
    """
    Pure ASGI middleware: assigns a request id (reusing an inbound X-Request-ID
    if the caller/proxy already set one), exposes it via request.state and a
    contextvar for logging, and echoes it back as a response header so a client
    or on-call engineer can correlate a specific failure with server-side logs.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        request_id = headers.get(b"x-request-id", b"").decode() or str(uuid.uuid4())
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id
        token = request_id_ctx.set(request_id)

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_ctx.reset(token)


class SecurityHeadersMiddleware:
    """
    Adds defensive response headers for API security. Includes:
    - X-Content-Type-Options: nosniff (prevent MIME sniffing)
    - X-Frame-Options: DENY (prevent clickjacking)
    - Referrer-Policy: no-referrer (privacy)
    - Permissions-Policy: restrict dangerous APIs
    - Cross-Origin-Resource-Policy: same-origin (CORP)
    - Strict-Transport-Security: HSTS for HTTPS enforcement
    - X-XSS-Protection: deprecated but included for defense-in-depth
    - Cache-Control: no-store for sensitive responses

    Additional HSTS/CSP at TLS-terminating proxy level is recommended.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"geolocation=(), microphone=(), camera=(), payment=()"),
                    (b"cross-origin-resource-policy", b"same-origin"),
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains; preload"),
                    (b"cache-control", b"no-store, no-cache, must-revalidate, private"),
                ])
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """
    Rejects oversized request bodies before they're ever fully read into memory
    (CWE-400 uncontrolled resource consumption). Two layers, since Content-Length
    can be omitted entirely (chunked transfer-encoding):
      1. Immediate rejection if a declared Content-Length exceeds the limit.
      2. A running byte counter on the actual ASGI receive channel that aborts
         the request the moment more than max_bytes has actually been streamed,
         even if no Content-Length header was sent at all.
    """

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    response = JSONResponse(
                        status_code=413,
                        content={"error": "payload_too_large", "detail": "Request body exceeds the maximum allowed size."},
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                pass

        total_received = 0

        async def limited_receive():
            nonlocal total_received
            message = await receive()
            if message["type"] == "http.request":
                total_received += len(message.get("body", b""))
                if total_received > self.max_bytes:
                    raise HTTPException(status_code=413, detail="Request body exceeds the maximum allowed size.")
            return message

        await self.app(scope, limited_receive, send)


class HTTPSEnforcementMiddleware:
    """
    Enforces HTTPS in production environments by:
    1. Rejecting non-HTTPS requests (except health checks and metrics)
    2. Verifying X-Forwarded-Proto header on reverse-proxy setups
    3. Allowing HTTP for local development (localhost/127.0.0.1)
    """

    def __init__(self, app, enabled_for_environment: str = "production"):
        self.app = app
        self.enabled_for_environment = enabled_for_environment

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        scheme = scope.get("scheme", "http")
        client = scope.get("client", ("unknown", 0))
        client_host = client[0] if client else "unknown"

        path = scope.get("path", "")
        is_health_check = path in ["/live", "/ready", "/health", "/metrics"]

        x_forwarded_proto = headers.get(b"x-forwarded-proto", b"").decode().lower()
        is_https = scheme == "https" or x_forwarded_proto == "https"
        is_localhost = client_host in ["127.0.0.1", "localhost", "::1"]

        if not is_https and not is_localhost and not is_health_check:
            logger.warning(f"HTTPS enforcement: rejecting {scheme.upper()} request to {path} from {client_host}")
            response = JSONResponse(
                status_code=400,
                content={
                    "error": "https_required",
                    "detail": "This API requires HTTPS. Use https:// instead of http://",
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
