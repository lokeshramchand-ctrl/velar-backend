from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGODB_URI: str
    MONGODB_DB_NAME: str = "velar"
    MILVUS_URI: str
    OLLAMA_URI: str | None = None  # optional single host
    OLLAMA_HOSTS: str | None = None  # comma-separated list
    EMBED_MODEL: str
    LLM_MODEL: str
    VELAR_API_KEY: str

    # Gates routers/pipelines.py (behavior profiling, embedding sync, decay
    # sweep, clustering, graph rebuild) - deliberately separate from and
    # never falls back to VELAR_API_KEY, which ships inside every client app
    # binary and is trivially extractable, so it can't be trusted to gate
    # expensive, system-wide batch jobs that aren't scoped to any one user.
    # Unset by default: those endpoints 503 until an operator explicitly
    # configures this for their own cron/ops use.
    ADMIN_API_KEY: str | None = None

    # JWT user authentication (core/jwt_auth.py, routers/auth.py). Distinct
    # from VELAR_API_KEY above: the API key authenticates the calling
    # application, JWT_SECRET_KEY signs per-user access tokens issued after
    # login - see docs/01-architecture.md §1.8.
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Operational settings (all have safe production-appropriate defaults)
    ENVIRONMENT: str = "production"  # "production" | "development"
    LOG_LEVEL: str = "INFO"  # DEBUG is opt-in, never the default - DEBUG logs full DB command payloads
    # Raised from the original 1 MB (fine when every request was a JSON body)
    # to accommodate multipart PDF statement uploads - see POST /statements/upload -
    # and, since routers/app_updates.py, Android release APK uploads (also
    # admin-key gated, but the outer backstop still has to fit them).
    # MAX_STATEMENT_PDF_BYTES/MAX_APK_UPLOAD_BYTES below are the tighter,
    # upload-specific ceilings checked in each router for a clearer,
    # route-specific error message; this middleware-level limit is the outer
    # backstop for every request body regardless of route.
    MAX_REQUEST_BODY_BYTES: int = 80_000_000  # 80 MB
    MAX_STATEMENT_PDF_BYTES: int = 10_000_000  # 10 MB
    MAX_APK_UPLOAD_BYTES: int = 80_000_000  # 80 MB - a Flutter release APK is typically 20-50 MB
    PDF_RETENTION_DAYS: int = 90  # Auto-delete PDFs after 90 days
    MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = 5000
    MONGODB_CONNECT_TIMEOUT_MS: int = 5000
    # Security: Input validation and request constraints
    MAX_STRING_FIELD_LENGTH: int = 500
    MAX_USERNAME_LENGTH: int = 128
    MAX_PASSWORD_LENGTH: int = 128
    MIN_PASSWORD_LENGTH: int = 8
    RATE_LIMIT_LOGIN_ATTEMPTS: str = "5/minute"
    RATE_LIMIT_API_CALLS: str = "100/minute"
    ENABLE_REQUEST_VALIDATION: bool = True
    ENABLE_AUDIT_LOGGING: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _require_strong_jwt_secret(cls, v: str) -> str:
        # Fails app startup immediately rather than letting a short/weak
        # secret (e.g. a copy-pasted placeholder) silently sign real tokens -
        # same "fail fast on a bad mandatory secret" posture as every other
        # required setting above, extended to also cover *weak* values since
        # a present-but-trivial signing key is just as dangerous as a missing
        # one. 32 bytes matches common guidance for HS256 signing keys.
        if len(v) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters long "
                "(generate one with: openssl rand -hex 32)"
            )
        return v

    @property
    def ollama_hosts_list(self) -> list[str]:
        """Convert comma-separated hosts into a list."""
        if self.OLLAMA_HOSTS:
            return [h.strip() for h in self.OLLAMA_HOSTS.split(",")]
        return []

settings = Settings()
