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

        # 2. AI Reasoning & Proposal (Gemini 3 Flash)
        proposal: ActionProposal = await gemini_provider.structured_output(
            prompt=ctx["prompt"],
            schema=ActionProposal,
            system_instruction=ctx["system_instruction"],
            model="gemini-3-flash-preview"
        )

        # 3. Deterministic Validation Gate
        if not proposal.feasible:
            return {
                "success": False,
                "outcome": "INFEASIBLE",
                "narrative": proposal.rejection_reason or "That action cannot be physically performed right now.",
                "proposal": proposal.model_dump()
            }

        # 4. Process Specific Action Archetypes
        action_type = proposal.action_type.upper()
        state_deltas = {}

        # Handle Betrayal / Thefts against own crew
        if "BETRAY" in action_type or "STEAL" in action_type or "SABOTAGE" in action_type:
            resolution = await self._resolve_crew_betrayal(
                character=character,
                proposal=proposal
            )
            state_deltas.update(resolution)

        # Narrative prose synthesis
        return {
            "success": proposal.proposed_outcome in ["SUCCESS", "PARTIAL_SUCCESS", "CRITICAL_SUCCESS"],
            "outcome": proposal.proposed_outcome,
            "intent": proposal.intent,
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
