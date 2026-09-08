from typing import Dict, Any, Optional
from app.database.connection import db_manager
from app.game.models.character import Character
from app.ai.providers.gemini_provider import gemini_provider
from app.ai.schemas.npc_schemas import NPCReaction
from app.config.settings import settings
from app.game.director.relationship_service import relationship_service
from app.services.logger import logger


NPC_PERSONAS: Dict[str, Dict[str, Any]] = {
    "Captain Redhook": {
        "title": "Captain of The Black Tide",
        "personality": "Gruff, fiercely protective of his gold, highly suspicious of Marines and disloyal deckhands.",
        "secrets": ["Owns The Golden Anchor gambling den under the forged alias Marcus Vale.", "Smuggles illegal weapons through Port Azure."],
        "faction": "Pirate"
    },
    "Old Salty Bill": {
        "title": "Navigator of The Black Tide",
        "personality": "Superstitious, talkative when offered spiced rum, loyal to Redhook but cowardly under Marine threat.",
        "secrets": ["Knows the sea route to Dead Man's Cove."],
        "faction": "Pirate"
    },
    "Tavern Bartender": {
        "title": "Barkeep at The Golden Anchor",
        "personality": "Neutral civilian, observes everything, fears pirates and respects Marine authority.",
        "secrets": ["Notices Marcus Vale visits the rear storage crates late at night."],
        "faction": "Civilian"
    },
    "Mara": {
        "title": "Herbalist & Proprietor of Azure Remedies",
        "personality": "Quiet, observant, fiercely independent. Deeply compassionate toward dockworkers, suspicious of corrupt officials and extortionists like Marcus Vale.",
        "secrets": ["Knows the rare moon-lily needed for antitoxin grows near Dead Man's Cove.", "Refuses to pay protection gold to Marcus Vale's enforcers."],
        "faction": "Civilian"
    },
    "Thomas": {
        "title": "Dockside Provisioner & Ex-Smuggler",
        "personality": "Calculating, pragmatic, values coin and reliable couriers over ideological causes.",
        "secrets": ["Supplies counterfeit Marine passage seals to pirate captains."],
        "faction": "Merchant"
    },
    "Inspector Vance": {
        "title": "Marine Investigative Officer",
        "personality": "Relentless, cynical, smells deceit easily. Considers Port Azure a nest of vipers requiring iron discipline.",
        "secrets": ["Suspects the dockmaster is taking bribes from Marcus Vale.", "Carries a personal vendetta against Captain Redhook."],
        "faction": "Marine"
    },
    "Madame Corbeau": {
        "title": "High-Stakes Gambler & Information Broker",
        "personality": "Enigmatic, theatrical, thrives on calculated risk and juicy gossip. Never forgets a wager or a slight.",
        "secrets": ["Holds blackmail letters on three prominent Marine commanders.", "Runs an illegal betting ring from The Golden Anchor cellar."],
        "faction": "Independent"
    }
}


class NPCEngine:
    """
    Simulates autonomous NPC dialogue, emotional shifts, secret knowledge protection,
    and deep memory recall based on past player interactions.
    """

    async def converse_with_npc(
        self,
        character_id: str,
        npc_name: str,
        player_speech: str
    ) -> NPCReaction:
        db = db_manager.db

        char_doc = await db.characters.find_one({"_id": character_id})
        player_name = char_doc.get("name", "Traveler") if char_doc else "Traveler"
        player_faction = char_doc.get("faction", "Independent") if char_doc else "Independent"

        persona = NPC_PERSONAS.get(npc_name, {
            "title": "Local Citizen",
            "personality": "Guarded, ordinary resident of the port.",
            "secrets": [],
            "faction": "Civilian"
        })

        # Fetch living memory and relationship history
        memory_context = await relationship_service.get_npc_memory_context(character_id, npc_name)

        system_instruction = (
            f"You are roleplaying as {npc_name} ({persona['title']}) in Pirate Wars.\n"
            f"Personality: {persona['personality']}\n"
            f"Private Secrets: {', '.join(persona['secrets']) if persona['secrets'] else 'None'}\n\n"
            f"YOUR PAST MEMORY & RELATIONSHIP WITH THIS TRAVELER:\n{memory_context}\n\n"
            f"RULES:\n"
            f"1. Stay strictly in character.\n"
            f"2. Let your tone reflect your standing (trust, fear, respect, affection) with {player_name}.\n"
            f"3. Never voluntarily confess secret criminal ties unless high trust or cornered.\n"
            f"4. If favors are owed or past promises were made, reference them naturally.\n"
            f"5. Generate an NPCReaction JSON with dialogue, internal_thought, and body language."
        )

        prompt = (
            f"=== CONVERSATION SCENE ===\n"
            f"Interlocutor: {player_name} (Faction: {player_faction})\n"
            f"What {player_name} says:\n"
            f"<player_dialogue>\n{player_speech.strip()}\n</player_dialogue>\n\n"
            f"Respond in character as {npc_name}."
        )

        reaction: NPCReaction = await gemini_provider.structured_output(
            prompt=prompt,
            schema=NPCReaction,
            system_instruction=system_instruction,
            model=settings.GEMINI_MODEL_FAST
        )

        # Log memory of this conversation
        await relationship_service.adjust_relationship(
            character_id=character_id,
            npc_name=npc_name,
            memory_event=f"Spoke to player: \"{player_speech[:60]}...\""
        )

        logger.info(f"[NPC DIALOGUE] {npc_name} replied to {player_name}: \"{reaction.dialogue}\"")
        return reaction


npc_engine = NPCEngine()
