from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import uuid

from app.database.connection import db_manager
from app.game.director.director_models import (
    Opportunity,
    OpportunityType,
    OpportunityUrgency,
    OpportunityStatus,
)
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class OpportunityEngine:
    """
    Manages the generation, presentation, tracking, and expiration of contextual opportunities.
    Ensures the player is never trapped in an empty sandbox while never being forced into a single linear path.
    """

    def __init__(self):
        self.collection_name = "director_opportunities"

    @property
    def collection(self):
        return db_manager.db[self.collection_name]

    async def list_active_opportunities(
        self,
        character_id: str,
        location_id: Optional[str] = None,
        include_rumors: bool = True
    ) -> List[Opportunity]:
        """Returns non-expired, non-completed opportunities for the player."""
        query: Dict[str, Any] = {
            "character_id": character_id,
            "status": OpportunityStatus.ACTIVE.value,
        }
        if location_id:
            query["$or"] = [{"location_id": location_id}, {"location_id": "all"}]

        cursor = self.collection.find(query).sort("urgency", -1)
        docs = await cursor.to_list(length=50)

        results: List[Opportunity] = []
        now = datetime.now(timezone.utc)

        for d in docs:
            opp = Opportunity(**d)
            # Check for expiration on the fly
            if opp.expires_at:
                exp = opp.expires_at if opp.expires_at.tzinfo else opp.expires_at.replace(tzinfo=timezone.utc)
                if exp < now:
                    await self._expire_opportunity(opp)
                    continue
            if not include_rumors and opp.opportunity_type == OpportunityType.RUMOR:
                continue
            results.append(opp)

        return results

    async def get_opportunity_by_id(self, character_id: str, opportunity_id: str) -> Optional[Opportunity]:
        doc = await self.collection.find_one({"_id": opportunity_id, "character_id": character_id})
        if doc:
            return Opportunity(**doc)
        return None

    async def create_opportunity(
        self,
        character_id: str,
        title: str,
        description: str,
        opp_type: OpportunityType = OpportunityType.NPC_REQUEST,
        urgency: OpportunityUrgency = OpportunityUrgency.MODERATE,
        location_id: str = "port_azure",
        related_npc_name: Optional[str] = None,
        duration_minutes: Optional[int] = None,
        consequence_summary: Optional[str] = None,
        suggested_actions: Optional[List[str]] = None,
        reward_preview: Optional[str] = None
    ) -> Opportunity:
        """Registers a living opportunity into the persistent world."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=duration_minutes) if duration_minutes else None

        opp = Opportunity(
            opportunity_id=f"opp_{uuid.uuid4().hex[:10]}",
            character_id=character_id,
            title=title,
            description=description,
            opportunity_type=opp_type,
            urgency=urgency,
            location_id=location_id,
            related_npc_name=related_npc_name,
            suggested_actions=suggested_actions or [],
            consequence_summary=consequence_summary or "The moment passes, and the city adjusts without you.",
            status=OpportunityStatus.ACTIVE,
            reward_preview=reward_preview,
            created_at=now,
            expires_at=expires_at
        )

        await self.collection.update_one(
            {"_id": opp.opportunity_id},
            {"$set": opp.to_mongo()},
            upsert=True
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.OPPORTUNITY_GENERATED,
            timestamp=now,
            actor_id=character_id,
            visibility=EventVisibility.PRIVATE,
            metadata={
                "opportunity_id": opp.opportunity_id,
                "title": opp.title,
                "urgency": opp.urgency.value,
                "opportunity_type": opp.opportunity_type.value,
                "npc": opp.related_npc_name
            }
        ))

        logger.info(f"[OPPORTUNITY GENERATED] '{opp.title}' for {character_id} (Type: {opp.opportunity_type.value})")
        return opp

    async def complete_opportunity(
        self,
        character_id: str,
        opportunity_id: str,
        resolution_notes: str = ""
    ) -> bool:
        """Marks an opportunity as resolved."""
        now = datetime.now(timezone.utc)
        res = await self.collection.update_one(
            {"_id": opportunity_id, "character_id": character_id, "status": OpportunityStatus.ACTIVE.value},
            {"$set": {
                "status": OpportunityStatus.RESOLVED.value,
                "resolved_at": now,
                "consequence_summary": resolution_notes
            }}
        )
        if res.modified_count > 0:
            await event_bus.publish(WorldEvent(
                event_type=EventType.OPPORTUNITY_COMPLETED,
                timestamp=now,
                actor_id=character_id,
                visibility=EventVisibility.PRIVATE,
                metadata={"opportunity_id": opportunity_id, "resolution": resolution_notes}
            ))
            return True
        return False

    async def _expire_opportunity(self, opp: Opportunity) -> None:
        """Updates status to expired/ignored and publishes missed event."""
        now = datetime.now(timezone.utc)
        await self.collection.update_one(
            {"_id": opp.opportunity_id},
            {"$set": {
                "status": OpportunityStatus.EXPIRED.value,
                "resolved_at": now
            }}
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.OPPORTUNITY_EXPIRED,
            timestamp=now,
            actor_id=opp.character_id,
            visibility=EventVisibility.PRIVATE,
            metadata={
                "opportunity_id": opp.opportunity_id,
                "title": opp.title,
                "consequence": opp.consequence_summary,
                "npc": opp.related_npc_name
            }
        ))
        logger.info(f"[OPPORTUNITY EXPIRED] '{opp.title}' for {opp.character_id}. Consequence: {opp.consequence_summary}")

    async def check_expirations_and_missed_opportunities(self, character_id: str) -> List[str]:
        """Scans for expired opportunities and triggers world advancement consequences."""
        now = datetime.now(timezone.utc)
        cursor = self.collection.find({
            "character_id": character_id,
            "status": OpportunityStatus.ACTIVE.value,
            "expires_at": {"$ne": None}
        })
        docs = await cursor.to_list(length=50)
        consequences: List[str] = []

        for d in docs:
            opp = Opportunity(**d)
            if opp.expires_at:
                exp = opp.expires_at if opp.expires_at.tzinfo else opp.expires_at.replace(tzinfo=timezone.utc)
                if exp <= now:
                    await self._expire_opportunity(opp)
                    consequences.append(f"{opp.title}: {opp.consequence_summary}")

        return consequences

    async def ensure_starter_opportunities(
        self,
        character_id: str,
        location_id: str = "port_azure",
        faction: str = "Independent"
    ) -> List[Opportunity]:
        """
        Seeds initial contextual opportunities (urgent requests, crime clues, and rumors)
        to make the port feel instantly alive.
        """
        existing = await self.list_active_opportunities(character_id, location_id=location_id)
        if len(existing) >= 3:
            return existing

        created: List[Opportunity] = []

        # 1. IMMEDIATE NPC REQUEST: Mara's Stolen Herbs
        mara_opp = await self.create_opportunity(
            character_id=character_id,
            title="The Distressed Apothecary",
            description="Mara stands outside her shop on Harbor Row, arguing quietly with a dockworker about a broken crate of silverleaf herbs.",
            opp_type=OpportunityType.NPC_REQUEST,
            urgency=OpportunityUrgency.URGENT,
            location_id=location_id,
            related_npc_name="Mara",
            duration_minutes=180,
            consequence_summary="Mara is forced to buy tainted herbs from Marcus Vale. Medicine prices in Port Azure double.",
            suggested_actions=["talk_mara", "inspect_herb_crate", "offer_apothecary_help"],
            reward_preview="Restorative medicines and medical favors"
        )
        created.append(mara_opp)

        # 2. IMMEDIATE / CRIME DISCOVERY: Marine Patrol on the Docks
        vance_opp = await self.create_opportunity(
            character_id=character_id,
            title="Inspector Vance's Inquisition",
            description="Inspector Vance is personally interrogating crew arrivals near Pier 4 following last night's dockworker murder.",
            opp_type=OpportunityType.CRIME_DISCOVERY,
            urgency=OpportunityUrgency.MODERATE,
            location_id=location_id,
            related_npc_name="Inspector Vance",
            duration_minutes=240,
            consequence_summary="Vance arrests an innocent deckhand and locks down the docks with strict curfews.",
            suggested_actions=["speak_to_vance", "slip_past_patrol", "observe_interrogation"],
            reward_preview="Marine faction standing and confidential case files"
        )
        created.append(vance_opp)

        # 3. MYSTERY: Scratched Cipher on Warehouse 7
        dock_mystery = await self.create_opportunity(
            character_id=character_id,
            title="Odd Chalk Marks on Warehouse 7",
            description="A strange symbol — three slashed waves over an inverted anchor — is freshly chalked behind the cargo crane.",
            opp_type=OpportunityType.MYSTERY,
            urgency=OpportunityUrgency.LEISURELY,
            location_id=location_id,
            consequence_summary="The smugglers finish moving the contraband crate unhindered.",
            suggested_actions=["investigate_chalk_mark", "stake_out_warehouse", "ask_bartender_about_symbol"],
            reward_preview="Smuggling route map and Black Tide intelligence"
        )
        created.append(dock_mystery)

        # 4. RUMOR: High-Stakes Dice in The Golden Anchor Backroom
        rumor = await self.create_opportunity(
            character_id=character_id,
            title="Whispers of Marcus Vale's Private Table",
            description="Sailors whisper that Madame Corbeau is taking high-stakes wagers in the backroom of The Golden Anchor tonight.",
            opp_type=OpportunityType.RUMOR,
            urgency=OpportunityUrgency.LEISURELY,
            location_id=location_id,
            related_npc_name="Madame Corbeau",
            consequence_summary="The private table disperses for the night.",
            suggested_actions=["visit_golden_anchor", "bribe_barkeep_for_pass", "challenge_corbeau"],
            reward_preview="High-roller gold stakes and VIP den access"
        )
        created.append(rumor)

        return await self.list_active_opportunities(character_id, location_id=location_id)


opportunity_engine = OpportunityEngine()
