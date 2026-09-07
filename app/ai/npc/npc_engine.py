from typing import Dict, Any, Optional
from app.database.connection import db_manager
from app.game.models.character import Character
from app.ai.providers.gemini_provider import gemini_provider
from app.ai.schemas.npc_schemas import NPCReaction
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
    }
}


class NPCEngine:
    """Simulates autonomous NPC dialogue, emotional shifts, and secret knowledge protection."""

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

        system_instruction = (
            f"You are roleplaying as {npc_name} ({persona['title']}) in Pirate Wars.\n"
            f"Personality: {persona['personality']}\n"
            f"Private Secrets: {', '.join(persona['secrets']) if persona['secrets'] else 'None'}\n\n"
            f"RULES:\n"
            f"1. Stay strictly in character.\n"
            f"2. Never voluntarily confess secret criminal ties to Marines unless heavily cornered with proof.\n"
            f"3. Generate an NPCReaction JSON with dialogue, internal_thought, and body language."
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
            model="gemini-3-flash-preview"
        )

        logger.info(f"[NPC DIALOGUE] {npc_name} replied to {player_name}: \"{reaction.dialogue}\"")
        return reaction


npc_engine = NPCEngine()
