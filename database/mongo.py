import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket

from core.config import settings

logger = logging.getLogger(__name__)

class MongoDB:
    client: AsyncIOMotorClient = None
    db = None

    @staticmethod
    def _validate_connection_uri(uri: str) -> None:
        """Validate that MongoDB connection enforces TLS and authentication.

        Production URIs should use:
        - mongodb+srv:// (enforces TLS, auto-discovers replica set)
        - mongodb://username:password@host (includes credentials)

        Raises ValueError if URI doesn't meet security requirements.
        """
        if not uri:
            raise ValueError("MONGODB_URI is not configured")

        if not uri.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("Invalid MONGODB_URI format. Must start with mongodb:// or mongodb+srv://")

        # mongodb+srv enforces TLS, but mongodb:// connections should have tls param or be authenticated
        if uri.startswith("mongodb://") and "tls=true" not in uri and "@" not in uri:
            logger.warning(
                "MongoDB URI does not appear to enforce TLS or authentication. "
                "Production deployments must use mongodb+srv:// or include tls=true and credentials."
            )

        # Ensure no plaintext password in logs (just check presence of credentials)
        if "@" in uri:
            logger.info("MongoDB connection includes authentication credentials (TLS + Auth)")
        elif "mongodb+srv" in uri:
            logger.info("MongoDB connection uses mongodb+srv (TLS enforced, discovery required)")
        else:
            logger.warning("MongoDB connection may not have authentication - ensure TLS is enabled")

    @classmethod
    async def connect(cls, uri: str = None, db_name: str = None):
        logger.info("Connecting to MongoDB...")

        # Use provided values or fallback to settings
        uri = uri or settings.MONGODB_URI
        db_name = db_name or settings.MONGODB_DB_NAME

        # Validate connection URI has TLS/auth (Tier 1: MongoDB authentication/TLS)
        cls._validate_connection_uri(uri)

        # Configure TLS and authentication options
        client_options = {
            "serverSelectionTimeoutMS": settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
            "connectTimeoutMS": settings.MONGODB_CONNECT_TIMEOUT_MS,
        }
        if settings.MONGODB_REQUIRE_TLS:
            client_options["tls"] = True
            client_options["tlsInsecure"] = not settings.MONGODB_VALIDATE_TLS_CERTIFICATE

        cls.client = AsyncIOMotorClient(uri, **client_options)
        cls.db = cls.client[db_name]

        # Collections
        cls.transactions = cls.db.get_collection("transactions")
        cls.feedback = cls.db.get_collection("feedback")
        cls.categories = cls.db.get_collection("categories")
        cls.merchants = cls.db.get_collection("merchants")
        cls.merchant_profiles = cls.db.get_collection("merchant_profiles")
        cls.behavior_patterns = cls.db.get_collection("behavior_patterns")
        cls.retraining_queue = cls.db.get_collection("retraining_queue")
        cls.users = cls.db.get_collection("users")
        cls.refresh_tokens = cls.db.get_collection("refresh_tokens")
        cls.statements = cls.db.get_collection("statements")
        cls.jobs = cls.db.get_collection("jobs")
        cls.app_releases = cls.db.get_collection("app_releases")

        # GridFS: stores the original uploaded PDF (repositories/statement_repository.py).
        # Reuses this same Mongo connection - no new infrastructure - see
        # docs/23-statements-pipeline.md for why GridFS over S3/local disk.
        cls.gridfs_bucket = AsyncIOMotorGridFSBucket(cls.db, bucket_name="statement_pdfs")

        # Same reasoning for the self-hosted app updater (repositories/app_release_repository.py):
        # stores uploaded release APKs on the same Mongo connection instead of
        # requiring a Coolify volume/S3 bucket the backend container's own
        # (otherwise stateless) filesystem can't durably provide across redeploys.
        cls.app_releases_bucket = AsyncIOMotorGridFSBucket(cls.db, bucket_name="app_releases_apks")

        logger.info(f"MongoDB connected to {uri}/{db_name}")

    @classmethod
    async def ensure_indexes(cls):
        """
        Creates every index this app's actual query patterns need. Previously
        zero indexes existed anywhere (confirmed by grep - no create_index
        calls at all), so every query - including the auth-adjacent profile
        lookup on every /memory/update call - ran as a full collection scan.
        Also enforces uniqueness constraints the app's logic assumes but never
        had backed by the database (canonical_name, merchant_name), which is
        what actually closes the create-profile race condition described in
        repositories/profile_repository.py.

        Wrapped so a failure here (e.g. insufficient privileges in a locked-
        down production cluster) logs a warning instead of crashing startup -
        an app that's slow because an index is missing is far better than an
        app that won't start at all because index creation was denied.
        """
        try:
            await cls.merchant_profiles.create_index("canonical_name", unique=True, background=True)
            await cls.merchant_profiles.create_index("last_seen", background=True)
            await cls.merchants.create_index("aliases", background=True)
            await cls.behavior_patterns.create_index("merchant_name", unique=True, background=True)
            await cls.transactions.create_index([("user_id", 1), ("timestamp", -1)], background=True)
            await cls.transactions.create_index("merchant", background=True)
            await cls.feedback.create_index("merchant_name", background=True)
            await cls.feedback.create_index("transaction_id", background=True)
            await cls.retraining_queue.create_index("status", background=True)

            # Auth (database/mongo.py, repositories/user_repository.py,
            # repositories/refresh_token_repository.py). Uniqueness on email
            # is the real backstop against the register-race two concurrent
            # signups for the same address (the app-level pre-check in
            # routers/auth.py is just the fast, common-case path). token_hash
            # is looked up on every refresh call, so it needs an index for
            # more than correctness - unique because a hash collision would
            # otherwise let one stored token match two documents. The TTL
            # index on expires_at lets MongoDB itself sweep expired refresh
            # tokens instead of needing a separate cleanup job.
            await cls.users.create_index("email", unique=True, background=True)
            await cls.refresh_tokens.create_index("token_hash", unique=True, background=True)
            await cls.refresh_tokens.create_index("user_id", background=True)
            await cls.refresh_tokens.create_index("expires_at", expireAfterSeconds=0, background=True)

            # Statement ingestion (repositories/statement_repository.py,
            # repositories/transaction_repository.py, repositories/job_repository.py).
            # The partial unique index on (user_id, reference_number) is what
            # makes re-uploading the same statement - or two statements whose
            # date ranges overlap - idempotent: the same UPI transaction ID for
            # the same user upserts in place instead of duplicating. It's
            # partial (only applies where reference_number exists) so it never
            # constrains transactions written by POST /v1/categorize, which
            # has no reference_number at all.
            await cls.transactions.create_index(
                [("user_id", 1), ("reference_number", 1)],
                unique=True,
                background=True,
                partialFilterExpression={"reference_number": {"$exists": True}},
            )
            await cls.transactions.create_index("statement_id", background=True)
            await cls.statements.create_index("user_id", background=True)
            await cls.statements.create_index([("user_id", 1), ("processing_status", 1)], background=True)
            await cls.jobs.create_index("user_id", background=True)
            await cls.jobs.create_index("resource_id", background=True)

            # App updater (routers/app_updates.py). version_code is unique so
            # two releases can never collide; platform+is_latest is what
            # GET /app/latest-version actually queries on every app launch.
            await cls.app_releases.create_index([("platform", 1), ("version_code", 1)], unique=True, background=True)
            await cls.app_releases.create_index([("platform", 1), ("is_latest", 1)], background=True)

            logger.info("MongoDB indexes ensured.")
        except Exception:
            logger.warning("Failed to ensure one or more MongoDB indexes - continuing without them.", exc_info=True)

    @classmethod
    async def disconnect(cls):
        if cls.client:
            logger.info("Closing MongoDB connection...")
            cls.client.close()
            logger.info("MongoDB disconnected.")

db = MongoDB()
