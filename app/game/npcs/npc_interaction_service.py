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

        # 2. Deterministic mechanical evaluation
        trust_delta = 0
        respect_delta = 0
        fear_delta = 0
        memory_summary = None
        rewards = []

        action_clean = action_type.upper()
        effective_speech = player_speech or ""

        is_custom = action_clean == "CUSTOM_SPEECH"
        is_bribe = "BRIBE" in action_clean
        is_recruit = action_clean in ["RECRUIT", "HIRE"]
        is_rumor = action_clean in ["ASK_RUMORS", "INTEL", "RUMORS"]
        is_work = action_clean in ["ASK_WORK", "JOB", "WORK"]

        traits_str = ", ".join(npc.personality) if npc.personality else "Pragmatic, Observant"

        # Determine outcome directives and stat deltas deterministically
        if is_bribe:
            if "Easily bribed" in npc.personality or "Corrupt" in npc.personality or npc.role in [NPCArchetype.SMUGGLER, NPCArchetype.THIEF, NPCArchetype.INFORMANT, NPCArchetype.PIRATE_INFORMANT, NPCArchetype.GAMBLER]:
                trust_delta = 8
                respect_delta = -2
                fear_delta = -5
                rewards.append("Dock Clearance / Guard Blind Eye")
                memory_summary = f"{char_name} bribed {npc.name} to overlook harbor activities."
                outcome_directive = (
                    f"The bribe IS ACCEPTED! {npc.name} is corrupt or open to bribes. "
                    f"They pocket the gold with discreet, sly satisfaction and promise to overlook {char_name}'s dock activities or provide quiet access."
                )
            elif "Incorruptible" in npc.personality or "Strict" in npc.personality or (npc.is_marine and "Honorable" in npc.personality):
                trust_delta = -15
                respect_delta = -10
                fear_delta = 10
                memory_summary = f"{char_name} attempted to bribe {npc.name} and was sharply rebuked."
                outcome_directive = (
                    f"The bribe IS HARSHLY REJECTED! {npc.name} is an incorruptible, dutiful {npc.role_title} ({npc.faction.value}). "
                    f"They react with fierce indignation and disgust, warning {char_name} that another attempt will result in iron shackles, arrest, or drawn steel."
                )
            else:
                trust_delta = -2
                memory_summary = f"{char_name} offered an unsolicited bribe to {npc.name}."
                outcome_directive = (
                    f"The bribe is CAUTIOUSLY DECLINED. {npc.name} tells {char_name} they don't take dirty gold from strangers without trust. "
                    f"They push the coins back and tell {char_name} to prove their reputation first."
                )

        elif is_recruit:
            if npc.is_marine or npc.faction == NPCFaction.MARINE:
                trust_delta = -10
                respect_delta = -5
                fear_delta = 5
                memory_summary = f"{char_name} audaciously proposed recruitment to Marine {npc.name}."
                outcome_directive = (
                    f"The recruitment offer is OUTRAGEOUSLY REJECTED! {npc.name} is a proud, disciplined Marine ({npc.role_title}) loyal to naval justice and the World Government! "
                    f"Asking a Marine commander/officer to join a pirate/civilian crew is insolent bravado. "
                    f"They rebuff {char_name} with harsh naval authority, reminding them of gallows, iron cells, or marine cannons."
                )
            elif npc.role in [NPCArchetype.SAILOR, NPCArchetype.DOCKWORKER, NPCArchetype.ROOKIE_PIRATE, NPCArchetype.DRIFTER, NPCArchetype.MERCENARY, NPCArchetype.FISHERMAN]:
                if rel.trust >= 10 or rel.respect >= 5:
                    trust_delta = 15
                    respect_delta = 10
                    rewards.append(f"Recruited {npc.name} ({npc.role_title}) to Crew")
                    memory_summary = f"{char_name} recruited {npc.name} into their crew."
                    outcome_directive = (
                        f"The recruitment offer is ACCEPTED WITH EXCITEMENT! {npc.name} is sick of shorebound wages and eagerly accepts {char_name}'s flag. "
                        f"They pledge their loyalty, weapon, and seamanship to the crew."
                    )
                else:
                    respect_delta = 3
                    memory_summary = f"{char_name} made an initial crew pitch to {npc.name}."
                    outcome_directive = (
                        f"The recruitment offer is HESITANTLY DECLINED FOR NOW. {npc.name} acknowledges {char_name} respectfully, "
                        f"but explains they don't sign articles with unfamiliar captains without proof of reliable plunder, steady coin, or higher reputation."
                    )
            else:
                respect_delta = 2
                memory_summary = f"{char_name} invited {npc.name} to join their crew."
                outcome_directive = (
                    f"The recruitment offer is AMUSEDLY DECLINED. {npc.name} is an established {npc.role_title} ({npc.occupation}) on {npc.island_id} with their own enterprise. "
                    f"They have no interest in swabbing decks or leaving their trade for sea voyages, but gladly offer to continue trading, drinking, or doing business."
                )

        elif is_work:
            trust_delta = 2
            respect_delta = 1
            memory_summary = f"{char_name} asked {npc.name} for work in the district."
            outcome_directive = (
                f"The player is asking about available work, jobs, or contracts. "
                f"{npc.name} describes a concrete, localized job or task fitting their role ({npc.role_title}) and district ({npc.location_id} on {npc.island_id})—such as cargo hauling, courier errands, escorting cargo, or bounties."
            )

        elif is_rumor:
            trust_delta = 2
            respect_delta = 1
            memory_summary = f"{char_name} gathered local rumors from {npc.name}."
            outcome_directive = (
                f"The player is asking about local rumors, secrets, and movements around {npc.island_id}. "
                f"{npc.name} shares authentic, concrete intel drawn from their known secrets and current district activity."
            )

        elif is_custom:
            trust_delta = 2
            respect_delta = 1
            memory_summary = f"{char_name} said: \"{effective_speech[:40]}\" to {npc.name}."
            outcome_directive = (
                f"The player directly spoke or acted: \"{effective_speech}\". "
                f"{npc.name} responds directly to the player's exact words and tone in authentic character."
            )

        else:
            trust_delta = 1
            respect_delta = 1
            memory_summary = f"{char_name} approached {npc.name} to converse."
            outcome_directive = f"The player approached {npc.name} to converse. {npc.name} greets them in authentic character."

        # 3. Dynamic AI Dialogue Generation for ALL actions
        prompt = (
            f"=== NPC PROFILE ===\n"
            f"Name: {npc.name}\n"
            f"Role / Archetype: {npc.role_title} ({npc.role.value})\n"
            f"Faction: {npc.faction.value}\n"
            f"Occupation: {npc.occupation}\n"
            f"Personality Traits: {traits_str}\n"
            f"Current District Activity: {npc.current_activity}\n"
            f"District Location: {npc.location_id} on {npc.island_id}\n"
            f"Wealth / Purse: {npc.wealth} Gold\n"
            f"Known Secrets / Intel: {npc.secrets + npc.known_information}\n\n"
            f"=== PLAYER INTERACTING ===\n"
            f"Player Name: {char_name}\n"
            f"Player Faction: {char_faction}\n"
            f"Standing with NPC: {rel.level.value} (Trust: {rel.trust}, Respect: {rel.respect}, Fear: {rel.fear})\n\n"
            f"=== ACTION & OUTCOME DIRECTIVE ===\n"
            f"Action Taken: {action_clean}\n"
            f"Player Words/Action: \"{effective_speech}\"\n"
            f"Directive: {outcome_directive}\n\n"
            f"=== INSTRUCTIONS ===\n"
            f"Write 2 to 4 sentences of spoken, immersive in-character dialogue from {npc.name} to {char_name}.\n"
            f"RULES:\n"
            f"1. Stay 100% in character for {npc.name}'s specific role ({npc.role_title}) and faction ({npc.faction.value}). "
            f"If {npc.name} is a Marine, speak with Marine authority and discipline—NEVER use pirate slang! If civilian, speak like an island resident.\n"
            f"2. Follow the outcome directive precisely.\n"
            f"3. Make dialogue vivid, constructive, and responsive to the player.\n"
            f"4. Wrap the spoken dialogue in quotation marks: \"...\" and return ONLY the dialogue."
        )

        try:
            ai_text = await gemini_provider.generate_prose(
                prompt=prompt,
                system_instruction="You are the dialogue engine of Pirate Wars. Write authentic, immersive character dialogue matching role and faction.",
                model=settings.GEMINI_MODEL_BASIC
            )
            dialogue = ai_text.strip()
            if not dialogue.startswith("\""):
                dialogue = f"\"{dialogue}\""
        except Exception as e:
            logger.warning(f"AI dialogue generation fallback triggered: {e}")
            dialogue = self._generate_role_aware_fallback(npc, char_name, action_clean, outcome_directive)

        # 4. Apply persistent relationship update
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

    def _generate_role_aware_fallback(
        self,
        npc: WorldNPC,
        char_name: str,
        action_clean: str,
        outcome_directive: str
    ) -> str:
        """Dynamic, role-aware and faction-aware fallback when AI generation is temporarily unreachable."""
        if npc.is_marine or npc.faction == NPCFaction.MARINE:
            if "RECRUIT" in action_clean:
                return (
                    f"\"{npc.name} rests a hand firmly on the hilt of their naval blade, scowling with cold disdain. "
                    f"'You have nerve asking a commissioned officer of the Marines to sail under your dubious colors, {char_name}. "
                    f"Take your leave before I have my squad throw you in the garrison stockade.'\""
                )
            elif "BRIBE" in action_clean:
                return (
                    f"\"{npc.name} glares at the gold coins and draws their shoulders back. "
                    f"'You insult the uniform and the law, {char_name}. "
                    f"Take your dirty gold out of my sight before I charge you with attempted bribery of the admiralty!'\""
                )
            else:
                return (
                    f"\"{npc.name} adjusts their Marine greatcoat and inspects you with a disciplined eye. "
                    f"'State your business in this district, {char_name}. "
                    f"The garrison maintains strict order here, and we keep close watch over every vessel docking in this harbor.'\""
                )
        elif npc.faction == NPCFaction.MERCHANT or npc.role in [NPCArchetype.MERCHANT, NPCArchetype.BARTENDER, NPCArchetype.APOTHECARY]:
            if "RECRUIT" in action_clean:
                return (
                    f"\"{npc.name} laughs heartily and gestures around at their goods and ledger. "
                    f"'Me, leave my counter to sleep on wet hammocks, {char_name}? Not a chance. "
                    f"My fortune is made right here on dry timber. But I'll gladly sell your crew provisions whenever you drop anchor.'\""
                )
            elif "WORK" in action_clean:
                return (
                    f"\"{npc.name} taps a finger against their ledger thoughtfully. "
                    f"'If you have strong arms and honest intent, {char_name}, I need three barrels of salt-cured provisions carried to the storehouse before dusk. "
                    f"Thirty gold coins when the manifest is signed.'\""
                )
            else:
                return (
                    f"\"{npc.name} smiles warmly across the counter. "
                    f"'Welcome, {char_name}. The cargo schooners brought fresh goods this morning, and coin is always welcome here. "
                    f"What can I help you find today?'\""
                )
        else:
            # Pirate or dockworker or civilian
            if "RECRUIT" in action_clean:
                return (
                    f"\"{npc.name} sizes you up with a weathered squint. "
                    f"'You look like you know how to hold a cutlass, {char_name}, but a sailor needs to know a captain can keep them paid and afloat. "
                    f"Make a greater name for yourself on these waters, and we'll talk shares.'\""
                )
            elif "RUMORS" in action_clean:
                return (
                    f"\"{npc.name} leans in and drops their voice to a low murmur. "
                    f"'Keep your ears open around the eastern pier, {char_name}. "
                    f"Word is a Marine frigate sighted a smuggler's sloop off the shoals, and several locked crates never made it to the manifest.'\""
                )
            else:
                return (
                    f"\"{npc.name} nods as they finish coiling a heavy mooring line. "
                    f"'Aye, {char_name}. Salt air and hard tides today. What brings you wandering down this section of the district?'\""
                )


npc_interaction_service = NPCInteractionService()
