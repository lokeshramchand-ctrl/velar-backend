from datetime import datetime, timezone
from repositories.profile_repository import profile_repo
from memory.state_machine import state_machine
from models.schemas import MerchantProfile, MemoryState

class MemoryManager:
    async def process_encounter(self, canonical_name: str, raw_text: str) -> MerchantProfile:
        """
        Called every time a transaction is processed.
        Updates frequency, checks state transitions, and saves to DB.
        """
        profile = await profile_repo.get_profile(canonical_name)

        if not profile:
            # First time seeing this entity. It starts as Ephemeral.
            profile = MerchantProfile(
                canonical_name=canonical_name,
                aliases=[raw_text],
                frequency=1,
                memory_state=MemoryState.EPHEMERAL
            )
            await profile_repo.create_profile(profile)
            return profile

        # Entity exists. Update tracking metrics.
        profile.frequency += 1
        profile.last_seen = datetime.now(timezone.utc)
        
        # Append alias if it's a new variation of the canonical name
        if raw_text not in profile.aliases:
            profile.aliases.append(raw_text)

        # Evaluate if it has earned a state promotion
        new_state = state_machine.evaluate_promotion(profile)
        
        # If it was archived but we just saw it again, wake it up as Temporary
        if profile.memory_state == MemoryState.ARCHIVED:
            profile.memory_state = MemoryState.TEMPORARY
        else:
            profile.memory_state = new_state

        # Persist changes
        await profile_repo.update_profile(profile)
        return profile

memory_manager = MemoryManager()