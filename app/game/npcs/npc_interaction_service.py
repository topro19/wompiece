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
    """Handles deep, persistent, constructive in-character dialogue, work offers, bribery, and recruitment."""

    async def interact(
        self,
        character_id: str,
        npc_id: str,
        action_type: str,
        player_speech: Optional[str] = None
    ) -> NPCInteractionResult:
        """Resolves a constructive multi-turn interaction with a persistent NPC and updates memory and relationship."""
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

        trust_delta = 0
        respect_delta = 0
        fear_delta = 0
        memory_summary = None
        rewards = []

        action_clean = action_type.upper()
        effective_speech = player_speech or ""

        # 2. Build structured prompt for AI dialogue
        is_custom = action_clean == "CUSTOM_SPEECH"
        is_bribe = "BRIBE" in action_clean
        is_recruit = action_clean in ["RECRUIT", "HIRE"]
        is_rumor = action_clean in ["ASK_RUMORS", "INTEL", "RUMORS"]
        is_work = action_clean in ["ASK_WORK", "JOB", "WORK"]

        if is_bribe:
            if "Easily bribed" in npc.personality or "Corrupt" in npc.personality:
                dialogue = (
                    f"\"{npc.name} slides the gold purse into a concealed pocket with a knowing smirk. "
                    f"'You understand how the world turns, {char_name}. Consider your affairs in this sector unmonitored. "
                    f"If anyone asks, I was inspecting cargo at the far pier.'\""
                )
                trust_delta = 10
                fear_delta = -5
                memory_summary = f"{char_name} bribed {npc.name} to overlook harbor activities."
                rewards.append("Dock Clearance / Guard Blind Eye")
            elif "Incorruptible" in npc.personality or "Strict" in npc.personality:
                dialogue = (
                    f"\"{npc.name} knocks the coins aside with a harsh clatter. "
                    f"'You dare try to grease my palms, {char_name}? I took an oath to the admiralty. "
                    f"Take your dirty gold and walk before I haul you before the magistrate in irons!'\""
                )
                trust_delta = -20
                respect_delta = -15
                fear_delta = 10
                memory_summary = f"{char_name} attempted to bribe {npc.name} and was sharply rebuked."
            else:
                dialogue = (
                    f"\"{npc.name} eyes the gold coin thoughtfully before gently pushing your hand away. "
                    f"'I don't risk my neck for loose pocket change, {char_name}. "
                    f"If you want my favor, prove yourself with actions, not scraps.'\""
                )
                trust_delta = -3
                memory_summary = f"{char_name} offered an unsolicited bribe to {npc.name}."

        elif is_recruit:
            if npc.role in [NPCArchetype.SAILOR, NPCArchetype.DOCKWORKER, NPCArchetype.ROOKIE_PIRATE, NPCArchetype.DRIFTER]:
                if rel.trust >= 10 or rel.respect >= 5:
                    dialogue = (
                        f"\"{npc.name} wipes calloused hands on their trousers and grins. "
                        f"'A berth under your flag, Captain {char_name}? I'm sick of breaking my back for copper wages on these wharves. "
                        f"Count me in. When the tide turns, my cutlass is yours!'\""
                    )
                    trust_delta = 15
                    respect_delta = 10
                    memory_summary = f"{char_name} recruited {npc.name} into their crew."
                    rewards.append(f"Recruited {npc.name} ({npc.role_title}) as Crew Hand")
                else:
                    dialogue = (
                        f"\"{npc.name} crosses their arms, sizing you up carefully. "
                        f"'You look like a capable captain, {char_name}, but I don't sign articles with strangers on a whim. "
                        f"Show me you can keep a crew afloat and rich, and then we'll talk shares.'\""
                    )
                    respect_delta = 3
                    memory_summary = f"{char_name} made an initial crew pitch to {npc.name}."
            else:
                dialogue = (
                    f"\"{npc.name} chuckles with genuine amusement. "
                    f"'Me? Swabbing decks for another captain? I lead my own ventures, {char_name}. "
                    f"I'll gladly trade with you or drink to your fortune, but I take orders from no one.'\""
                )
                respect_delta = 5
                memory_summary = f"{char_name} proposed recruitment to {npc.name}, who declined with mutual respect."

        else:
            # AI Generation for Custom Speech, Rumors, Work inquiries, and Dialogue
            intent_context = ""
            if is_rumor:
                intent_context = "The player is asking about local rumors, confidential gossip, and movements around the island."
            elif is_work:
                intent_context = "The player is asking about available work, odd jobs, contracts, or money-making opportunities."
            elif is_custom:
                intent_context = f"The player directly spoke/acted: \"{effective_speech}\""
            else:
                intent_context = "The player approached warmly to start a conversation."

            traits_str = ", ".join(npc.personality) if npc.personality else "Pragmatic, Observant"
            prompt = (
                f"=== NPC PROFILE ===\n"
                f"Name: {npc.name}\n"
                f"Role / Archetype: {npc.role_title}\n"
                f"Faction: {npc.faction.value}\n"
                f"Personality Traits: {traits_str}\n"
                f"Current District Activity: {npc.current_activity}\n"
                f"Personal Goals: {[g.description for g in npc.goals]}\n"
                f"Known Secrets & Intel: {npc.secrets + npc.known_information}\n"
                f"Current Location: {npc.location_id} on {npc.island_id}\n\n"
                f"=== PLAYER PROFILE ===\n"
                f"Name: {char_name}\n"
                f"Faction: {char_faction}\n"
                f"Relationship Standing: {rel.level.value} (Trust: {rel.trust}, Respect: {rel.respect})\n\n"
                f"=== INTERACTION CONTEXT ===\n"
                f"{intent_context}\n\n"
                f"=== INSTRUCTIONS ===\n"
                f"Write 2 to 4 sentences of constructive, in-character spoken dialogue from {npc.name} to {char_name}.\n"
                f"RULES:\n"
                f"1. Be constructive and engaging! Give actionable information, mention concrete details of the port, or propose a next step.\n"
                f"2. Never give a dead-end brush off unless the relationship is fiercely hostile.\n"
                f"3. Speak with rich nautical/gritty pirate-era dialect fitting the character's role ({npc.role_title}).\n"
                f"4. If asking for work: suggest a concrete task or tell who is hiring.\n"
                f"5. If asking for rumors: share a secret regarding patrols, cargo, or pirates.\n"
                f"6. Return ONLY the spoken dialogue in quotation marks."
            )

            try:
                ai_text = await gemini_provider.generate_prose(
                    prompt=prompt,
                    system_instruction="You are the dialogue engine of Pirate Wars. Write immersive, constructive character dialogue.",
                    model=settings.GEMINI_MODEL_BASIC
                )
                dialogue = ai_text.strip()
                if not dialogue.startswith("\""):
                    dialogue = f"\"{dialogue}\""
            except Exception as e:
                logger.warning(f"AI dialogue generation fallback triggered: {e}")
                if is_work:
                    dialogue = (
                        f"\"{npc.name} scratches their stubble thoughtfully. "
                        f"'If your coinpurse is feeling light, {char_name}, head down to berth three. "
                        f"The harbor master has two crates of iron ballast that need hauling before high tide. "
                        f"Pays forty gold for an honest hour of sweat.'\""
                    )
                elif is_rumor:
                    dialogue = (
                        f"\"{npc.name} leans in and drops their voice to a whisper. "
                        f"'Word around the docks is that a Marine cutter intercepted a smuggler's schooner off the western shoals. "
                        f"Half the contraband went missing before it reached headquarters. Someone on the inside got very rich.'\""
                    )
                else:
                    dialogue = (
                        f"\"{npc.name} adjusts their coat and nods warmly. "
                        f"'Good to meet someone with their boots firmly on the planks, {char_name}. "
                        f"Things have been tense around the harbor lately with Marine patrols doubling their watches. "
                        f"What brings you to our side of the island?'\""
                    )

            trust_delta = 2
            respect_delta = 1
            memory_summary = f"{char_name} spoke with {npc.name} about local matters ({action_clean.lower()})."

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
