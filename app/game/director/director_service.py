from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.database.connection import db_manager
from app.game.director.goal_service import goal_service
from app.game.director.thread_service import thread_service
from app.game.director.opportunity_service import opportunity_engine
from app.game.director.relationship_service import relationship_service
from app.game.director.reputation_service import reputation_service
from app.game.director.director_models import (
    PlayerGoal,
    StoryThread,
    Opportunity,
    NPCRelationship,
    GoalTier,
    OpportunityUrgency,
    OpportunityType
)
from app.game.notifications.notification_models import OfflineRecap
from app.game.notifications.notification_service import notification_service
from app.services.logger import logger


class PlayerBriefing(BaseModel):
    """Living World overview presented on the Player Home Screen."""
    character_id: str
    character_name: str
    location_name: str
    faction: str
    reputation_summary: Dict[str, str]
    behavioral_traits: Dict[str, Any] = Field(default_factory=dict)
    active_goals: Dict[str, List[PlayerGoal]] = Field(default_factory=dict)
    active_threads: List[StoryThread] = Field(default_factory=list)
    immediate_opportunities: List[Opportunity] = Field(default_factory=list)
    discoverable_opportunities: List[Opportunity] = Field(default_factory=list)
    rumors: List[Opportunity] = Field(default_factory=list)
    known_people: List[NPCRelationship] = Field(default_factory=list)
    world_updates: List[str] = Field(default_factory=list)
    unread_messages_count: int = 0
    offline_recap: Optional[OfflineRecap] = None


class GameDirector:
    """
    The Master Conductor of Pirate Wars.
    Eliminates the empty sandbox feel by providing immediate, living direction,
    tracking persistent goals, relationships, threads, and dynamic opportunities.
    """

    async def initialize_player_world(
        self,
        character_id: str,
        location_id: str = "port_azure",
        faction: str = "Independent"
    ) -> None:
        """Seeds the living world for a new or transitioning player."""
        logger.info(f"[GAME DIRECTOR] Initializing living world for {character_id} at {location_id} ({faction})")

        # 1. Starter Goals
        await goal_service.seed_initial_player_goals(character_id, faction)

        # 2. Starter Threads
        await thread_service.ensure_starter_story_threads()

        # 3. Starter Opportunities
        await opportunity_engine.ensure_starter_opportunities(character_id, location_id, faction)

        # 4. Seed Known Characters
        await relationship_service.get_or_create_relationship(character_id, "Mara")
        await relationship_service.get_or_create_relationship(character_id, "Old Salty Bill")
        await relationship_service.get_or_create_relationship(character_id, "Inspector Vance")
        await relationship_service.get_or_create_relationship(character_id, "Captain Redhook")

    async def get_player_briefing(
        self,
        character_id: str,
        location_id: str = "port_azure"
    ) -> PlayerBriefing:
        """
        Gathers complete context for the Player Home Screen:
        Current Threads, Opportunities, Known People, Goals, Rumors, and Expirations.
        """
        # Process any expired opportunities first to capture consequences
        missed_consequences = await opportunity_engine.check_expirations_and_missed_opportunities(character_id)

        # Ensure world is initialized
        await self.initialize_player_world(character_id, location_id)

        # Fetch character details
        char_doc = await db_manager.db.characters.find_one({"_id": character_id})
        char_name = char_doc.get("name", "Traveler") if char_doc else "Traveler"
        char_faction = char_doc.get("faction", "Independent") if char_doc else "Independent"
        traits = char_doc.get("behavioral_traits", {}) if char_doc else {}

        # Fetch reputation standings
        rep_summary = await reputation_service.get_reputation_standing(character_id)

        # Fetch Goals
        goals = await goal_service.list_goals(character_id)
        grouped_goals: Dict[str, List[PlayerGoal]] = {
            "Short-Term": [g for g in goals if g.tier == GoalTier.SHORT_TERM],
            "Medium-Term": [g for g in goals if g.tier == GoalTier.MEDIUM_TERM],
            "Long-Term": [g for g in goals if g.tier == GoalTier.LONG_TERM],
        }

        # Fetch Threads
        threads = await thread_service.list_active_threads()

        # Fetch Opportunities
        opps = await opportunity_engine.list_active_opportunities(character_id, location_id)
        immediate = [o for o in opps if o.urgency in [OpportunityUrgency.URGENT, OpportunityUrgency.TIMED]]
        rumors = [o for o in opps if o.opportunity_type == OpportunityType.RUMOR]
        discoverable = [o for o in opps if o not in immediate and o not in rumors]

        # Fetch People
        people = await relationship_service.list_relationships(character_id)

        # Notification & Offline Recap
        recap = await notification_service.get_offline_recap(character_id, char_name)

        # Location name mapping
        loc_name = "Port Azure" if location_id == "port_azure" else location_id.replace("_", " ").title()

        return PlayerBriefing(
            character_id=character_id,
            character_name=char_name,
            location_name=loc_name,
            faction=char_faction,
            reputation_summary=rep_summary,
            behavioral_traits=traits if isinstance(traits, dict) else {},
            active_goals=grouped_goals,
            active_threads=threads,
            immediate_opportunities=immediate,
            discoverable_opportunities=discoverable,
            rumors=rumors,
            known_people=people,
            world_updates=missed_consequences,
            unread_messages_count=recap.unread_messages_count,
            offline_recap=recap,
        )


game_director = GameDirector()
