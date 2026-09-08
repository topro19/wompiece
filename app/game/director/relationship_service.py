from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.database.connection import db_manager
from app.game.director.director_models import (
    NPCRelationship,
    NPCMemory,
    RelationshipLevel,
    RewardGrant,
    RewardType
)
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class RelationshipService:
    """Authoritative living NPC relationship, friendship, memory, and favor engine."""

    async def get_or_create_relationship(self, character_id: str, npc_name: str) -> NPCRelationship:
        """Retrieves an existing relationship or instantiates a fresh acquaintance record."""
        db = db_manager.db
        clean_name = npc_name.strip()
        doc = await db.relationships.find_one({
            "character_id": character_id,
            "npc_name": {"$regex": f"^{clean_name}$", "$options": "i"}
        })
        if doc:
            return NPCRelationship(**doc)

        rel = NPCRelationship(
            character_id=character_id,
            npc_name=clean_name,
            level=RelationshipLevel.STRANGER,
            trust=0,
            respect=0
        )
        await db.relationships.insert_one(rel.to_mongo())
        return rel

    async def adjust_relationship(
        self,
        character_id: str,
        npc_name: str,
        trust_delta: int = 0,
        respect_delta: int = 0,
        fear_delta: int = 0,
        affection_delta: int = 0,
        memory_summary: Optional[str] = None,
        emotional_value: str = "MEDIUM",
        favor_earned: bool = False,
        related_event_id: Optional[str] = None,
        memory_event: Optional[str] = None
    ) -> NPCRelationship:
        """Modifies relationship dimensions, logs persistent memory, and re-evaluates relationship standing."""
        memory_summary = memory_summary or memory_event
        db = db_manager.db
        rel = await self.get_or_create_relationship(character_id, npc_name)

        new_trust = max(-100, min(100, rel.trust + trust_delta))
        new_respect = max(-100, min(100, rel.respect + respect_delta))
        new_fear = max(-100, min(100, rel.fear + fear_delta))
        new_affection = max(-100, min(100, rel.affection + affection_delta))
        favors_owed = rel.favors_owed_to_player + (1 if favor_earned else 0)

        # Dynamic level thresholding
        if new_trust >= 80 and new_respect >= 60:
            new_level = RelationshipLevel.LOYAL_ALLY
        elif new_trust >= 60:
            new_level = RelationshipLevel.CLOSE_FRIEND
        elif new_trust >= 35:
            new_level = RelationshipLevel.FRIEND
        elif new_trust >= 15:
            new_level = RelationshipLevel.TRUSTED
        elif new_trust >= 5:
            new_level = RelationshipLevel.FRIENDLY
        elif new_trust <= -60:
            new_level = RelationshipLevel.BITTER_ENEMY
        elif new_trust <= -35:
            new_level = RelationshipLevel.HOSTILE
        elif new_trust <= -15:
            new_level = RelationshipLevel.RIVAL
        elif new_trust > 0 or new_respect > 0:
            new_level = RelationshipLevel.ACQUAINTANCE
        else:
            new_level = RelationshipLevel.STRANGER

        memories = list(rel.memories)
        if memory_summary:
            mem = NPCMemory(
                summary=memory_summary,
                emotional_value=emotional_value,
                trust_change=trust_delta,
                favor_owed=favor_earned,
                related_event_id=related_event_id
            )
            memories.append(mem)

        now = datetime.now(timezone.utc)
        await db.relationships.update_one(
            {"_id": rel.relationship_id},
            {
                "$set": {
                    "trust": new_trust,
                    "respect": new_respect,
                    "fear": new_fear,
                    "affection": new_affection,
                    "level": new_level.value,
                    "favors_owed_to_player": favors_owed,
                    "memories": [m.model_dump() for m in memories],
                    "last_interaction_at": now
                }
            }
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.RELATIONSHIP_CHANGED,
            actor_id=character_id,
            location_id="relationship_hub",
            visibility=EventVisibility.PRIVATE,
            state_delta={
                "character_id": character_id,
                "npc_name": rel.npc_name,
                "new_level": new_level.value,
                "trust": new_trust,
                "favors_owed": favors_owed
            }
        ))

        rel.trust = new_trust
        rel.respect = new_respect
        rel.fear = new_fear
        rel.affection = new_affection
        rel.level = new_level
        rel.favors_owed_to_player = favors_owed
        rel.memories = memories
        rel.last_interaction_at = now
        return rel

    async def add_favor(self, character_id: str, npc_name: str, favors: int = 1, reason: str = "") -> None:
        """Increments favors owed to player."""
        db = db_manager.db
        rel = await self.get_or_create_relationship(character_id, npc_name)
        new_favors = rel.favors_owed_to_player + favors
        await db.relationships.update_one(
            {"_id": rel.relationship_id},
            {"$set": {"favors_owed_to_player": new_favors}}
        )
        await event_bus.publish(WorldEvent(
            event_type=EventType.FAVOR_EARNED,
            actor_id=character_id,
            location_id="relationship_hub",
            visibility=EventVisibility.PRIVATE,
            state_delta={"character_id": character_id, "npc_name": npc_name, "favors": new_favors, "reason": reason}
        ))

    async def call_in_favor(self, character_id: str, npc_name: str, favor_type: str = "INFORMATION") -> Dict[str, Any]:
        """Exchanges an owed favor for concrete assistance."""
        db = db_manager.db
        rel = await self.get_or_create_relationship(character_id, npc_name)
        if rel.favors_owed_to_player <= 0:
            raise ValueError(f"{npc_name} does not owe you any favors.")

        from app.game.director.reward_service import reward_service
        new_favors = rel.favors_owed_to_player - 1
        await db.relationships.update_one(
            {"_id": rel.relationship_id},
            {"$set": {"favors_owed_to_player": new_favors}}
        )

        outcome_desc = ""
        ftype = favor_type.upper()
        if "MEDICINE" in ftype or "POTION" in ftype:
            await reward_service.grant(
                character_id=character_id,
                rewards=[RewardGrant(
                    reward_type=RewardType.MEDICINE,
                    item_id="potent_salve",
                    item_name="Potent Restorative Salve",
                    quantity=2,
                    description="Restores 35 HP on use."
                )],
                reason=f"Favor called in with {npc_name}",
                actor_npc_name=npc_name
            )
            outcome_desc = f"{npc_name} handed you 2x Potent Restorative Salve from their personal stash."
        elif "SAFEHOUSE" in ftype or "HIDING" in ftype:
            await reward_service.grant(
                character_id=character_id,
                rewards=[RewardGrant(
                    reward_type=RewardType.SAFEHOUSE,
                    description="Key to the Harbor Cellar Hideout",
                    metadata={"safehouse_id": "port_azure_cellar"}
                )],
                reason=f"Favor called in with {npc_name}",
                actor_npc_name=npc_name
            )
            outcome_desc = f"{npc_name} slipped you the brass key to a hidden cellar safehouse."
        elif "INTRODUCTION" in ftype:
            contact = "Thomas the Maritime Merchant" if npc_name == "Mara" else "Captain Redhook"
            await reward_service.grant(
                character_id=character_id,
                rewards=[RewardGrant(
                    reward_type=RewardType.INTRODUCTION,
                    description=contact,
                    metadata={"contact_name": contact}
                )],
                reason=f"Introduction by {npc_name}",
                actor_npc_name=npc_name
            )
            outcome_desc = f"{npc_name} wrote a signed wax-sealed introduction to {contact}."
        else:  # Default: INFORMATION / INTEL
            await reward_service.grant(
                character_id=character_id,
                rewards=[RewardGrant(
                    reward_type=RewardType.INFORMATION,
                    item_name="Marine Patrol Route",
                    description="Confidential patrol timings for Port Azure Harbor waters."
                )],
                reason=f"Favor called in with {npc_name}",
                actor_npc_name=npc_name
            )
            outcome_desc = f"{npc_name} leaned in and whispered the patrol timings of the local naval guard."

        await event_bus.publish(WorldEvent(
            event_type=EventType.FAVOR_EXCHANGED,
            actor_id=character_id,
            location_id="relationship_hub",
            visibility=EventVisibility.PRIVATE,
            state_delta={"character_id": character_id, "npc_name": npc_name, "favor_type": favor_type, "outcome": outcome_desc}
        ))

        return {
            "success": True,
            "npc_name": npc_name,
            "favors_remaining": new_favors,
            "outcome": outcome_desc
        }

    async def send_npc_gift(
        self,
        character_id: str,
        npc_name: str,
        item_name: str,
        item_id: str,
        quantity: int = 1,
        reason: str = "A token of appreciation."
    ) -> Dict[str, Any]:
        """Triggers an unsolicited gift delivered from an NPC to the player."""
        from app.game.director.reward_service import reward_service
        rel = await self.get_or_create_relationship(character_id, npc_name)

        await reward_service.grant(
            character_id=character_id,
            rewards=[RewardGrant(
                reward_type=RewardType.ITEM,
                item_id=item_id,
                item_name=item_name,
                quantity=quantity,
                description=reason
            )],
            reason=f"Gift from {npc_name}",
            actor_npc_name=npc_name
        )

        await self.adjust_relationship(
            character_id=character_id,
            npc_name=npc_name,
            trust_delta=3,
            memory_summary=f"Sent player a gift: {quantity}x {item_name} ({reason}).",
            emotional_value="HIGH"
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.NPC_GIFT_RECEIVED,
            actor_id=character_id,
            location_id="port_azure",
            visibility=EventVisibility.PRIVATE,
            state_delta={"npc_name": npc_name, "gift": f"{quantity}x {item_name}", "reason": reason}
        ))

        return {
            "success": True,
            "npc_name": npc_name,
            "gift": f"{quantity}x {item_name}",
            "reason": reason
        }

    async def list_relationships(self, character_id: str) -> List[NPCRelationship]:
        """Lists all known NPC relationships for a player."""
        db = db_manager.db
        cursor = db.relationships.find({"character_id": character_id})
        rels = []
        async for doc in cursor:
            rels.append(NPCRelationship(**doc))
        return rels

    async def get_npc_memory_context(
        self,
        character_id_or_relationship: Any,
        npc_name: Optional[str] = None
    ) -> str:
        """Formats memory block for AI prompt injection."""
        if isinstance(character_id_or_relationship, str) and npc_name:
            relationship = await self.get_or_create_relationship(character_id_or_relationship, npc_name)
        elif isinstance(character_id_or_relationship, NPCRelationship):
            relationship = character_id_or_relationship
        else:
            relationship = None

        if not relationship or not relationship.memories:
            return "No previous interactions on record."
        lines = []
        for m in relationship.memories[-4:]:
            lines.append(f"• {m.summary}")
        lines.append(f"Relationship Level: {relationship.level.value} (Trust: {relationship.trust}, Favors Owed: {relationship.favors_owed_to_player})")
        return "\n".join(lines)


relationship_service = RelationshipService()
