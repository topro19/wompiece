from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.database.connection import db_manager
from app.game.director.director_models import StoryThread, StoryThreadStatus
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class StoryThreadService:
    """Authoritative persistent story thread engine for evolving narrative arcs and mystery merges."""

    async def create_thread(
        self,
        title: str,
        summary: str,
        known_facts: Optional[List[str]] = None,
        unknown_questions: Optional[List[str]] = None,
        related_npc_names: Optional[List[str]] = None,
        player_involvement: str = "Observer"
    ) -> StoryThread:
        db = db_manager.db
        thread = StoryThread(
            title=title,
            summary=summary,
            known_facts=known_facts or [],
            unknown_questions=unknown_questions or [],
            related_npc_names=related_npc_names or [],
            player_involvement=player_involvement,
            history=[f"Thread established: {title}"]
        )
        await db.story_threads.insert_one(thread.to_mongo())
        await event_bus.publish(WorldEvent(
            event_type=EventType.STORY_THREAD_CREATED,
            visibility=EventVisibility.PUBLIC,
            state_delta={"thread_id": thread.thread_id, "title": thread.title}
        ))
        logger.info(f"Created living story thread: '{thread.title}' (#{thread.thread_id}).")
        return thread

    async def get_thread(self, thread_id: str) -> Optional[StoryThread]:
        db = db_manager.db
        doc = await db.story_threads.find_one({"_id": thread_id})
        return StoryThread(**doc) if doc else None

    async def get_thread_by_title(self, title: str) -> Optional[StoryThread]:
        db = db_manager.db
        doc = await db.story_threads.find_one({"title": {"$regex": f"^{title.strip()}$", "$options": "i"}})
        return StoryThread(**doc) if doc else None

    async def update_thread(
        self,
        thread_id: str,
        new_fact: Optional[str] = None,
        new_status: Optional[StoryThreadStatus] = None,
        new_npc: Optional[str] = None,
        log_entry: Optional[str] = None
    ) -> Optional[StoryThread]:
        db = db_manager.db
        thread = await self.get_thread(thread_id)
        if not thread:
            return None

        update_fields: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        push_fields: Dict[str, Any] = {}

        if new_status:
            update_fields["status"] = new_status.value
        if new_fact:
            push_fields["known_facts"] = new_fact
        if new_npc and new_npc not in thread.related_npc_names:
            push_fields["related_npc_names"] = new_npc
        if log_entry:
            push_fields["history"] = log_entry

        update_doc: Dict[str, Any] = {"$set": update_fields}
        if push_fields:
            update_doc["$push"] = push_fields

        await db.story_threads.update_one({"_id": thread_id}, update_doc)
        updated = await self.get_thread(thread_id)

        await event_bus.publish(WorldEvent(
            event_type=EventType.STORY_THREAD_UPDATED,
            visibility=EventVisibility.PUBLIC,
            state_delta={"thread_id": thread_id, "status": updated.status.value if updated else None}
        ))
        return updated

    async def merge_threads(
        self,
        source_thread_id: str,
        target_thread_id: str,
        merge_reason: str
    ) -> Optional[StoryThread]:
        """Merges two narrative threads when evidence reveals they are part of the same conspiracy."""
        db = db_manager.db
        source = await self.get_thread(source_thread_id)
        target = await self.get_thread(target_thread_id)
        if not source or not target:
            return None

        now = datetime.now(timezone.utc)
        # Mark source thread as MERGED
        await db.story_threads.update_one(
            {"_id": source_thread_id},
            {
                "$set": {
                    "status": StoryThreadStatus.MERGED.value,
                    "merged_into_thread_id": target_thread_id,
                    "updated_at": now
                },
                "$push": {"history": f"Merged into '{target.title}' (#{target_thread_id}): {merge_reason}"}
            }
        )

        # Merge facts and NPCs into target
        combined_facts = list(set(target.known_facts + source.known_facts + [f"Merged Clue: {merge_reason}"]))
        combined_npcs = list(set(target.related_npc_names + source.related_npc_names))
        history_entry = f"Merged with thread '{source.title}': {merge_reason}"

        await db.story_threads.update_one(
            {"_id": target_thread_id},
            {
                "$set": {
                    "known_facts": combined_facts,
                    "related_npc_names": combined_npcs,
                    "updated_at": now
                },
                "$push": {"history": history_entry}
            }
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.STORY_THREAD_MERGED,
            visibility=EventVisibility.PUBLIC,
            state_delta={
                "source_thread_id": source_thread_id,
                "target_thread_id": target_thread_id,
                "reason": merge_reason
            }
        ))

        logger.info(f"Merged thread '{source.title}' into '{target.title}': {merge_reason}")
        return await self.get_thread(target_thread_id)

    async def list_active_threads(self) -> List[StoryThread]:
        db = db_manager.db
        cursor = db.story_threads.find({"status": {"$in": [StoryThreadStatus.ACTIVE.value, StoryThreadStatus.ESCALATED.value]}})
        threads = []
        async for doc in cursor:
            threads.append(StoryThread(**doc))
        return threads

    async def ensure_starter_story_threads(self) -> List[StoryThread]:
        """Seeds initial persistent narrative threads for a living port."""
        existing = await self.list_active_threads()
        if existing:
            return existing

        t1 = await self.create_thread(
            title="The Port Azure Murders",
            summary="A string of mysterious nighttime homicides near the eastern wharf has left dockhands terrified and Marines on edge.",
            known_facts=["3 bodies recovered near warehouse alleyways.", "Victims suffered precision blade wounds."],
            unknown_questions=["Who is the killer?", "Why are victims found without their boots?"],
            related_npc_names=["Mara", "Inspector Vance", "Tavern Bartender"],
            player_involvement="Witness & Investigator"
        )
        t2 = await self.create_thread(
            title="The Apothecary's Missing Shipment",
            summary="Mara the apothecary ordered rare mountain herbs from the mainland, but the shipping sloop never unloaded at Port Azure.",
            known_facts=["Cargo was marked with green wax seals.", "Ship arrived with slashed tarps."],
            unknown_questions=["Did pirates raid the sloop?", "Was it dockworker theft?"],
            related_npc_names=["Mara", "Thomas"],
            player_involvement="Allied Helper"
        )
        t3 = await self.create_thread(
            title="The Black Tide Armory Whispers",
            summary="Rumors circulate that Captain Redhook is stockpiling colonial naval muskets at Skull Rock Anchorage.",
            known_facts=["Black Tide deckhands have been buying gunpowder in bulk."],
            unknown_questions=["Is a full raid on Port Azure imminent?"],
            related_npc_names=["Captain Redhook", "Old Salty Bill"],
            player_involvement="Observer"
        )
        return [t1, t2, t3]


thread_service = StoryThreadService()
