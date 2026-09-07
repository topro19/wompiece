import uuid
import random
from typing import Dict, Any, Optional, List
from app.database.connection import db_manager
from app.game.models.character import Character, CharacterStatus
from app.game.world.location import location_service
from app.game.crews.crew_service import crew_service
from app.game.crews.crew_models import CrewRole
from app.game.economy.ledger import ledger
from app.ai.context.builder import context_builder
from app.ai.providers.gemini_provider import gemini_provider
from app.ai.schemas.action_schemas import ActionProposal
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class ActionEngine:
    """
    Authoritative resolution engine for contextual and freeform player actions.
    Translates untrusted player natural language into verified, deterministic state changes.
    """

    async def resolve_freeform_action(
        self,
        character_id: str,
        untrusted_action_text: str,
        target_entity_id: Optional[str] = None
    ) -> Dict[str, Any]:
        db = db_manager.db

        char_doc = await db.characters.find_one({"_id": character_id})
        if not char_doc:
            raise ValueError(f"Character {character_id} not found.")

        if char_doc.get("status") != CharacterStatus.ALIVE.value:
            return {
                "success": False,
                "outcome": "IMPOSSIBLE",
                "narrative": "A dead soul cannot act in the realm of the living."
            }

        character = Character(**char_doc)

        # 1. Build sandboxed prompt-injection safe context
        ctx = await context_builder.build_action_context(
            character=character,
            untrusted_player_text=untrusted_action_text
        )

        # 2. AI Reasoning & Proposal (Google Gemini)
        proposal: ActionProposal = await gemini_provider.structured_output(
            prompt=ctx["prompt"],
            schema=ActionProposal,
            system_instruction=ctx["system_instruction"]
        )

        # 3. Deterministic Validation Gate
        if not proposal.feasible:
            return {
                "success": False,
                "outcome": "INFEASIBLE",
                "intent": proposal.intent,
                "difficulty_level": proposal.difficulty_level,
                "success_chance_percent": proposal.success_chance_percent,
                "dice_roll": 0,
                "reward_gold": 0,
                "narrative": proposal.rejection_reason or "That action cannot be physically performed right now.",
                "state_deltas": {}
            }

        # 4. Deterministic Dice Roll & Probability Mechanics
        chance = max(5, min(95, proposal.success_chance_percent))
        dice_roll = random.randint(1, 100)
        action_type = proposal.action_type.upper()

        if dice_roll <= max(1, int(chance * 0.10)):
            outcome = "CRITICAL_SUCCESS"
        elif dice_roll <= chance:
            outcome = "SUCCESS"
        elif dice_roll <= min(98, chance + 15):
            outcome = "PARTIAL_SUCCESS"
        elif dice_roll >= 95 or "STEAL" in action_type or "CRIME" in action_type:
            outcome = "DETECTED" if ("STEAL" in action_type or "CRIME" in action_type) else "CRITICAL_FAILURE"
        else:
            outcome = "FAILURE"

        is_success = outcome in ["SUCCESS", "PARTIAL_SUCCESS", "CRITICAL_SUCCESS"]
        state_deltas: Dict[str, Any] = {}

        # 5. Authoritative Rewards Disbursement
        earned_gold = 0
        if is_success and proposal.reward_gold > 0:
            multiplier = 1.5 if outcome == "CRITICAL_SUCCESS" else (0.5 if outcome == "PARTIAL_SUCCESS" else 1.0)
            earned_gold = max(1, int(proposal.reward_gold * multiplier))
            earned_gold = min(500, earned_gold)  # Strict authoritative cap

            await ledger.transfer(
                sender_id=None,
                receiver_id=character.character_id,
                amount=earned_gold,
                reason=f"Action Reward: {proposal.intent[:45]}",
                idempotency_key=f"act_reward_{character.character_id}_{uuid.uuid4().hex[:8]}"
            )
            state_deltas["gold_earned"] = f"+{earned_gold} Gold"

            updated_char = await db.characters.find_one({"_id": character.character_id})
            if updated_char:
                state_deltas["new_balance"] = f"{updated_char.get('wealth', character.wealth + earned_gold)} Gold"

        # 6. Failure Consequences (Health Loss, Bounty, Wanted Level)
        if not is_success:
            if proposal.health_change < 0 or outcome == "CRITICAL_FAILURE":
                damage = abs(proposal.health_change) if proposal.health_change < 0 else 15
                new_health = max(1, character.health - damage)
                await db.characters.update_one(
                    {"_id": character.character_id},
                    {"$set": {"health": new_health}}
                )
                state_deltas["health_loss"] = f"-{damage} HP ({new_health}/{character.max_health})"

            if proposal.wanted_level_change > 0 or outcome == "DETECTED":
                wanted_inc = max(1, proposal.wanted_level_change)
                await db.characters.update_one(
                    {"_id": character.character_id},
                    {"$inc": {"wanted_level": wanted_inc, "bounty": wanted_inc * 100}}
                )
                state_deltas["wanted_level"] = f"+{wanted_inc} (Wanted Level {character.wanted_level + wanted_inc})"

        # 7. Reputation Delta
        if proposal.reputation_faction and proposal.reputation_change != 0:
            valid_factions = ["marine", "pirate", "merchant", "independent"]
            f_clean = proposal.reputation_faction.lower().strip()
            if f_clean in valid_factions:
                field_name = f"reputation_{f_clean}"
                await db.characters.update_one(
                    {"_id": character.character_id},
                    {"$inc": {field_name: proposal.reputation_change}}
                )
                prefix = "+" if proposal.reputation_change > 0 else ""
                state_deltas["reputation"] = f"{prefix}{proposal.reputation_change} {f_clean.title()}"

        # 8. Items summary
        if is_success and proposal.reward_items_summary:
            state_deltas["items_found"] = proposal.reward_items_summary

        # 9. Handle Crew Betrayals
        if ("BETRAY" in action_type or "STEAL" in action_type or "SABOTAGE" in action_type) and character.crew_id:
            resolution = await self._resolve_crew_betrayal(
                character=character,
                proposal=proposal
            )
            state_deltas.update(resolution)

        return {
            "success": is_success,
            "outcome": outcome,
            "intent": proposal.intent,
            "difficulty_level": proposal.difficulty_level,
            "success_chance_percent": chance,
            "dice_roll": dice_roll,
            "reward_gold": earned_gold,
            "narrative": proposal.narrative,
            "state_deltas": state_deltas
        }

    async def _resolve_crew_betrayal(
        self,
        character: Character,
        proposal: ActionProposal
    ) -> Dict[str, Any]:
        """
        Calculates contextual betrayal feasibility and consequences:
        Detects if crew catches the player in the act, adjusts loyalty, emits events.
        """
        db = db_manager.db
        if not character.crew_id:
            return {"note": "No crew to betray; acting independently."}

        crew = await crew_service.get_crew(character.crew_id)
        if not crew:
            return {}

        member = crew.members.get(character.character_id)
        if not member:
            return {}

        # Base detection risk depends on captain authority and player influence
        detection_chance = (crew.captain_authority * 0.4) + 20 - (member.influence * 0.2)
        roll = random.uniform(0, 100)

        is_detected = roll < detection_chance

        if is_detected:
            # Betrayal detected!
            new_loyalty = 0
            new_dissatisfaction = 100
            await db.crews.update_one(
                {"_id": crew.crew_id},
                {
                    "$set": {
                        f"members.{character.character_id}.loyalty": new_loyalty,
                        f"members.{character.character_id}.dissatisfaction": new_dissatisfaction
                    }
                }
            )

            await event_bus.publish(WorldEvent(
                event_type=EventType.CREW_BETRAYAL_ATTEMPTED,
                actor_id=character.character_id,
                target_ids=[crew.captain_id],
                location_id=character.location_id,
                visibility=EventVisibility.CREW_ONLY,
                state_delta={
                    "crew_id": crew.crew_id,
                    "crew_name": crew.name,
                    "betrayer_name": character.name,
                    "detected": True,
                    "action_intent": proposal.intent
                }
            ))

            logger.warning(f"[BETRAYAL DETECTED] {character.name} was caught attempting betrayal against {crew.name}!")
            return {"betrayal_detected": True, "crew_alert": "Officers have witnessed your treason!"}
        else:
            # Subtle betrayal succeeded without immediate discovery
            await event_bus.publish(WorldEvent(
                event_type=EventType.CREW_BETRAYAL_ATTEMPTED,
                actor_id=character.character_id,
                target_ids=[crew.captain_id],
                location_id=character.location_id,
                visibility=EventVisibility.SECRET,
                state_delta={
                    "crew_id": crew.crew_id,
                    "crew_name": crew.name,
                    "detected": False,
                    "action_intent": proposal.intent
                }
            ))
            return {"betrayal_detected": False, "crew_alert": "The deed was done unseen in the dark."}


action_engine = ActionEngine()
