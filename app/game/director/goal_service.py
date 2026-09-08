from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.database.connection import db_manager
from app.game.models.character import Faction
from app.game.director.director_models import PlayerGoal, GoalTier, GoalStatus
from app.services.logger import logger


class GoalService:
    """Manages multi-tier player goal states (Short-Term, Medium-Term, Long-Term Ambitions)."""

    async def seed_initial_player_goals(self, character_id: str, faction: Any) -> List[PlayerGoal]:
        if isinstance(faction, str):
            try:
                faction = Faction(faction.upper())
            except ValueError:
                faction = Faction.INDEPENDENT
        db = db_manager.db
        existing = await db.goals.count_documents({"character_id": character_id})
        if existing > 0:
            return await self.list_goals(character_id)

        goals: List[PlayerGoal] = []

        # Short-Term
        goals.append(PlayerGoal(
            character_id=character_id,
            tier=GoalTier.SHORT_TERM,
            title="Explore the Harbor & Inquire About Work",
            description="Visit the local markets, talk to merchants or dockmasters, and gather initial coin.",
            reward_notes="Earn honest wages or find lucrative illicit opportunities."
        ))
        goals.append(PlayerGoal(
            character_id=character_id,
            tier=GoalTier.SHORT_TERM,
            title="Investigate Port Rumors at The Golden Anchor",
            description="Have a drink at the tavern and listen to whispers regarding murders and missing shipments.",
            reward_notes="Gain confidential intelligence and discover living story threads."
        ))

        # Medium-Term
        if faction == Faction.PIRATE:
            goals.append(PlayerGoal(
                character_id=character_id,
                tier=GoalTier.MEDIUM_TERM,
                title="Commission a Seaworthy Sloop or Join a Crew",
                description="Accumulate 500 Gold to acquire your own ship or earn a role aboard The Black Tide.",
                reward_notes="Unlocks high-seas navigation and island raiding."
            ))
        elif faction == Faction.MARINE:
            goals.append(PlayerGoal(
                character_id=character_id,
                tier=GoalTier.MEDIUM_TERM,
                title="Solve Your First Port Criminal Case",
                description="Collect physical and testimonial evidence, secure a warrant, and apprehend an outlaw.",
                reward_notes="Promotion to Lieutenant and naval command clearance."
            ))
        else:
            goals.append(PlayerGoal(
                character_id=character_id,
                tier=GoalTier.MEDIUM_TERM,
                title="Establish a Maritime Trade Route or Storefront",
                description="Secure a trade license or purchase a share in a harbor warehouse.",
                reward_notes="Generates passive revenue and commercial influence."
            ))

        # Long-Term Ambition
        ambition_title = "Become a Feared Pirate Lord of the High Seas" if faction == Faction.PIRATE else (
            "Rise to Marine Fleet Admiral and Purge Colonial Corruption" if faction == Faction.MARINE else (
                "Monopolize the Archipelago Trade Syndicate" if faction == Faction.MERCHANT else
                "Become a Renowned Legend Operating in the Gray Shadows"
            )
        )
        goals.append(PlayerGoal(
            character_id=character_id,
            tier=GoalTier.LONG_TERM,
            title=ambition_title,
            description="A grand vision emerging as you navigate relationships, battles, and faction loyalties.",
            reward_notes="Immortalized in the colonial history chronicles."
        ))

        for g in goals:
            await db.goals.insert_one(g.to_mongo())

        logger.info(f"Seeded 3-tier initial goals for character #{character_id}.")
        return goals

    async def add_goal(
        self,
        character_id: str,
        tier: GoalTier,
        title: str,
        description: str,
        reward_notes: Optional[str] = None
    ) -> PlayerGoal:
        db = db_manager.db
        goal = PlayerGoal(
            character_id=character_id,
            tier=tier,
            title=title,
            description=description,
            reward_notes=reward_notes
        )
        await db.goals.insert_one(goal.to_mongo())
        return goal

    async def complete_goal(self, goal_id: str) -> Optional[PlayerGoal]:
        db = db_manager.db
        now = datetime.now(timezone.utc)
        await db.goals.update_one(
            {"_id": goal_id},
            {"$set": {"status": GoalStatus.COMPLETED.value, "completed_at": now}}
        )
        doc = await db.goals.find_one({"_id": goal_id})
        return PlayerGoal(**doc) if doc else None

    async def list_goals(self, character_id: str, status: Optional[GoalStatus] = None) -> List[PlayerGoal]:
        db = db_manager.db
        query: Dict[str, Any] = {"character_id": character_id}
        if status:
            query["status"] = status.value
        cursor = db.goals.find(query)
        goals = []
        async for doc in cursor:
            goals.append(PlayerGoal(**doc))
        return goals


goal_service = GoalService()
