import random
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

from app.database.connection import db_manager
from app.game.npcs.npc_models import WorldNPC, NPCFaction, NPCArchetype
from app.game.director.relationship_service import relationship_service
from app.game.director.director_models import RelationshipLevel
from app.ai.providers.gemini_provider import gemini_provider
from app.config.settings import settings
from app.services.logger import logger


class NPCInteractionResult(BaseModel):
    npc_id: str
    npc_name: str
    npc_role: str
    dialogue: str
    relationship_standing: str
    trust_delta: int = 0
    respect_delta: int = 0
    memory_logged: Optional[str] = None
    rewards_granted: List[str] = []


class NPCInteractionService:
    """Handles deep, persistent, in-character dialogue, bribery, trading, and recruitment."""

    async def interact(
        self,
        character_id: str,
        npc_id: str,
        action_type: str,
        player_speech: Optional[str] = None
    ) -> NPCInteractionResult:
        """Resolves an interaction with a persistent NPC and updates memory and relationship."""
        db = db_manager.db
        npc_doc = await db.npcs.find_one({"_id": npc_id})
        if not npc_doc:
            raise ValueError(f"NPC {npc_id} not found in world registry.")

        npc = WorldNPC(**npc_doc)
        char_doc = await db.characters.find_one({"_id": character_id})
        char_name = char_doc.get("name", "Traveler") if char_doc else "Traveler"
        char_faction = char_doc.get("faction", "Independent") if char_doc else "Independent"

        # 1. Fetch persistent relationship
        rel = await relationship_service.get_or_create_relationship(character_id, npc.name)

        # 2. Process specific interaction type deterministically
        trust_delta = 0
        respect_delta = 0
        fear_delta = 0
        memory_summary = None
        rewards = []

        action_clean = action_type.upper()

        if action_clean in ["BRIBE", "BRIBE_50"]:
            if "Easily bribed" in npc.personality or "Corrupt" in npc.personality:
                dialogue = f"\"{npc.name} slides the purse into a concealed pocket with a knowing nod. 'Consider your business in this harbor overlooked, {char_name}. Just stay clear of the senior guard.'\""
                trust_delta = 10
                fear_delta = -5
                memory_summary = f"{char_name} bribed {npc.name} to look the other way."
                rewards.append("Dock Inspection Pass")
            elif "Incorruptible" in npc.personality or "Strict" in npc.personality:
                dialogue = f"\"{npc.name} knocks your purse aside in disgust. 'Attempting to bribe an officer of the realm? You're treading on razor-thin ice, {char_name}. Draw back before I lock you in irons!'\""
                trust_delta = -20
                respect_delta = -15
                fear_delta = 10
                memory_summary = f"{char_name} attempted to bribe {npc.name} and was sharply rebuked."
            else:
                dialogue = f"\"{npc.name} eyes the gold coin pensively before shaking their head. 'Keep your coin, traveler. I don't risk my skin for pocket change.'\""
                trust_delta = -5
                memory_summary = f"{char_name} offered an unsolicited bribe to {npc.name}."

        elif action_clean in ["RECRUIT", "HIRE"]:
            if npc.role in [NPCArchetype.SAILOR, NPCArchetype.DOCKWORKER, NPCArchetype.ROOKIE_PIRATE, NPCArchetype.DRIFTER]:
                dialogue = f"\"{npc.name} squares their shoulders and smiles with crooked teeth. 'A berth on a real ship? You've got yourself a deal, Captain {char_name}. What's our first port of call?'\""
                trust_delta = 15
                respect_delta = 10
                memory_summary = f"{char_name} offered {npc.name} a position on their crew."
                rewards.append(f"Recruited {npc.name} as crew member")
            else:
                dialogue = f"\"{npc.name} laughs heartily. 'I command my own destiny, {char_name}. I'm no swab to take orders from another captain.'\""
                respect_delta = 5
                memory_summary = f"{char_name} attempted to recruit {npc.name}, who politely declined."

        elif action_clean in ["ASK_RUMORS", "INTEL"]:
            rumor = npc.known_information[0] if npc.known_information else f"Word has it that patrols are doubling near the trade lanes."
            dialogue = f"\"{npc.name} leans in and whispers: '{rumor}'\""
            trust_delta = 2
            memory_summary = f"{npc.name} shared harbor intelligence with {char_name}."

        else:
            # General conversation - dynamic AI generation or rule-based fallback
            prompt = (
                f"NPC Name: {npc.name}\n"
                f"Role: {npc.role_title}\n"
                f"Faction: {npc.faction.value}\n"
                f"Personality Traits: {', '.join(npc.personality)}\n"
                f"Current Activity: {npc.current_activity}\n"
                f"Relationship with Player: Trust {rel.trust}, Respect {rel.respect}, Standing {rel.level.value}\n"
                f"Player Name: {char_name} (Faction: {char_faction})\n"
                f"Player said/acted: {player_speech or 'Greeted warmly'}\n\n"
                f"Write 1-2 sentences of spoken in-character dialogue from {npc.name} responding to {char_name}."
            )
            try:
                ai_resp = await gemini_provider.generate_content(
                    prompt=prompt,
                    model=settings.GEMINI_MODEL_BASIC,
                    system_instruction="You are roleplaying a gritty, living NPC in a high seas pirate world. Respond with authentic maritime flavor.",
                    temperature=0.7
                )
                dialogue = f"\"{ai_resp.strip()}\""
            except Exception as e:
                logger.warning(f"NPC AI dialogue fallback triggered: {e}")
                dialogue = f"\"{npc.name} nods curtly. 'Fair winds, {char_name}. Keep your wits sharp in this district.'\""

            trust_delta = 2
            respect_delta = 1
            memory_summary = f"{char_name} spoke with {npc.name} about local happenings."

        # 3. Apply persistent relationship update
        updated_rel = await relationship_service.adjust_relationship(
            character_id=character_id,
            npc_name=npc.name,
            trust_delta=trust_delta,
            respect_delta=respect_delta,
            fear_delta=fear_delta,
            memory_summary=memory_summary
        )

        return NPCInteractionResult(
            npc_id=npc.npc_id,
            npc_name=npc.name,
            npc_role=npc.role_title,
            dialogue=dialogue,
            relationship_standing=updated_rel.level.value,
            trust_delta=trust_delta,
            respect_delta=respect_delta,
            memory_logged=memory_summary,
            rewards_granted=rewards
        )


npc_interaction_service = NPCInteractionService()
