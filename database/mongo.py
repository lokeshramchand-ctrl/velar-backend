from motor.motor_asyncio import AsyncIOMotorClient
import logging
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

        cls.client = AsyncIOMotorClient(uri)
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
    async def disconnect(cls):
        if cls.client:
            logger.info("Closing MongoDB connection...")
            cls.client.close()
            logger.info("MongoDB disconnected.")

db = MongoDB()
