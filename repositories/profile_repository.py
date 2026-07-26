import logging
from database.mongo import db
from models.schemas import MerchantProfile, MemoryState

logger = logging.getLogger(__name__)

class ProfileRepository:
    async def get_profile(self, canonical_name: str) -> Optional[MerchantProfile]:
        data = await db.merchant_profiles.find_one({"canonical_name": canonical_name}, {"_id": 0})      
        if data:
            return MerchantProfile(**data)
        return None

    async def create_profile(self, profile: MerchantProfile):
        profile_dict = profile.model_dump(by_alias=True, exclude={"id"})
        await db.merchant_profiles.insert_one(profile_dict)
        return profile

    async def update_profile(self, profile: MerchantProfile):
        # Update everything except first_seen
        update_data = profile.model_dump(by_alias=True, exclude={"id", "first_seen", "canonical_name"})
        await db.merchant_profiles.update_one(
            {"canonical_name": profile.canonical_name},
            {"$set": update_data}
        )
        return profile

    async def get_stale_profiles(self, cutoff_date) -> list[MerchantProfile]:
        # Find profiles that haven't been seen since the cutoff date and aren't already archived
        cursor = db.merchant_profiles.find({
            "last_seen": {"$lt": cutoff_date},
            "memory_state": {"$ne": MemoryState.ARCHIVED.value}
        })
        return [MerchantProfile(**doc) async for doc in cursor]

profile_repo = ProfileRepository()