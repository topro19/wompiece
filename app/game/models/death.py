import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from app.game.models.character import CharacterStatus
from app.database.connection import db_manager
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class CauseOfDeath(str, Enum):
    COMBAT = "COMBAT"
    EXECUTION = "EXECUTION"
    ASSASSINATION = "ASSASSINATION"
    MUTINY = "MUTINY"
    NAVAL_SINKING = "NAVAL_SINKING"


class DeathRecord(BaseModel):
    """Immutable memorial of a permanently fallen character."""
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str
    character_name: str
    cause: CauseOfDeath
    killer_id: Optional[str] = None
    killer_name: Optional[str] = None
    location_id: str
    bounty_at_death: int = 0
    final_wealth: int = 0
    related_case_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    legacy_notes: List[str] = Field(default_factory=list)

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.record_id
        return data


class PermadeathService:
    """Authoritative handler for permanent character death and world consequence cascades."""

    async def execute_permadeath(
        self,
        character_id: str,
        cause: CauseOfDeath,
        location_id: str,
        killer_id: Optional[str] = None,
        killer_name: Optional[str] = None,
        related_case_id: Optional[str] = None,
    ) -> DeathRecord:
        db = db_manager.db

        character_doc = await db.characters.find_one({"_id": character_id})
        if not character_doc:
            raise ValueError(f"Character {character_id} not found.")

        if character_doc.get("status") == CharacterStatus.DEAD.value:
            raise ValueError(f"Character {character_id} is already permanently dead.")

        now = datetime.now(timezone.utc)

        # 1. Update Character Status to permanently DEAD
        await db.characters.update_one(
            {"_id": character_id},
            {
                "$set": {
                    "status": CharacterStatus.DEAD.value,
                    "health": 0,
                    "died_at": now
                }
            }
        )

        # 2. If owned by a real user, archive active character link
        user_id = character_doc.get("user_id")
        if user_id:
            await db.users.update_one(
                {"_id": user_id},
                {
                    "$set": {"active_character_id": None},
                    "$push": {"deceased_character_ids": character_id}
                }
            )

        # 3. Create Immutable Death Record
        death_rec = DeathRecord(
            character_id=character_id,
            character_name=character_doc.get("name", "Unknown"),
            cause=cause,
            killer_id=killer_id,
            killer_name=killer_name,
            location_id=location_id,
            bounty_at_death=character_doc.get("bounty", 0),
            final_wealth=character_doc.get("wealth", 0),
            related_case_id=related_case_id,
            timestamp=now,
            legacy_notes=[f"Fell in {location_id} via {cause.value}."]
        )
        await db.death_records.insert_one(death_rec.to_mongo())

        # 4. Publish Public DEATH_EVENT
        await event_bus.publish(WorldEvent(
            event_type=EventType.DEATH_EVENT,
            actor_id=killer_id,
            target_ids=[character_id],
            location_id=location_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={
                "victim_id": character_id,
                "victim_name": death_rec.character_name,
                "cause": cause.value,
                "bounty": death_rec.bounty_at_death
            },
            related_case_id=related_case_id,
            metadata={"permanent_death": True}
        ))

        logger.warning(
            f"[PERMADEATH] Character '{death_rec.character_name}' ({character_id}) has permanently died. Cause: {cause.value}."
        )

        return death_rec


permadeath_service = PermadeathService()
