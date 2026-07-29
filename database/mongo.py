import logging

from motor.motor_asyncio import AsyncIOMotorClient

from core.config import settings

logger = logging.getLogger(__name__)

class MongoDB:
    client: AsyncIOMotorClient = None
    db = None

    @classmethod
    async def connect(cls, uri: str = None, db_name: str = None):
        logger.info("Connecting to MongoDB...")

        # Use provided values or fallback to settings
        uri = uri or settings.MONGODB_URI
        db_name = db_name or settings.MONGODB_DB_NAME

        cls.client = AsyncIOMotorClient(
            uri,
            serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
            connectTimeoutMS=settings.MONGODB_CONNECT_TIMEOUT_MS,
        )
        cls.db = cls.client[db_name]

        # Collections
        cls.transactions = cls.db.get_collection("transactions")
        cls.feedback = cls.db.get_collection("feedback")
        cls.categories = cls.db.get_collection("categories")
        cls.merchants = cls.db.get_collection("merchants")
        cls.merchant_profiles = cls.db.get_collection("merchant_profiles")
        cls.behavior_patterns = cls.db.get_collection("behavior_patterns")
        cls.retraining_queue = cls.db.get_collection("retraining_queue")

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
