from typing import Dict, Any, List, Optional
from app.database.connection import db_manager
from app.services.logger import logger


class ReputationService:
    """Manages multi-dimensional faction standings and emergent behavioral traits."""

    async def adjust_reputation(
        self,
        character_id: str,
        faction_deltas: Dict[str, int]
    ) -> Dict[str, int]:
        """Adjusts multi-dimensional faction reputations (-100 to +100)."""
        db = db_manager.db
        valid_factions = ["marine", "pirate", "merchant", "independent", "civilian", "criminal"]

        inc_fields = {}
        for f, delta in faction_deltas.items():
            clean_f = f.lower().strip()
            if clean_f in valid_factions and delta != 0:
                inc_fields[f"reputation_{clean_f}"] = delta

        if inc_fields:
            await db.characters.update_one(
                {"_id": character_id},
                {"$inc": inc_fields}
            )

        char = await db.characters.find_one({"_id": character_id})
        if not char:
            return {}

        return {
            "marine": char.get("reputation_marine", 0),
            "pirate": char.get("reputation_pirate", 0),
            "merchant": char.get("reputation_merchant", 0),
            "independent": char.get("reputation_independent", 0),
            "civilian": char.get("reputation_civilian", 0),
            "criminal": char.get("reputation_criminal", 0)
        }

    async def record_action_traits(
        self,
        character_id: str,
        trait_deltas: Dict[str, int]
    ) -> Dict[str, int]:
        """Infers and accumulates behavioral personality tendencies (generous, violent, diplomatic, etc.)."""
        db = db_manager.db
        inc_fields = {f"behavioral_traits.{k.lower()}": v for k, v in trait_deltas.items() if v != 0}
        if inc_fields:
            await db.characters.update_one(
                {"_id": character_id},
                {"$inc": inc_fields}
            )
        char = await db.characters.find_one({"_id": character_id})
        return char.get("behavioral_traits", {}) if char else {}

    async def get_reputation_standing(self, character_id: str) -> Dict[str, str]:
        """Translates raw integers into descriptive social standing titles."""
        db = db_manager.db
        char = await db.characters.find_one({"_id": character_id})
        if not char:
            return {}

        def to_title(val: int) -> str:
            if val >= 75: return "Revered Icon"
            if val >= 45: return "Trusted Ally"
            if val >= 20: return "Favorable Standing"
            if val >= 5: return "Mildly Respected"
            if val <= -75: return "Public Enemy No. 1"
            if val <= -45: return "Hated Outlaw"
            if val <= -20: return "Distrusted Person"
            if val <= -5: return "Suspicious"
            return "Neutral / Unknown"

        return {
            "Marines": to_title(char.get("reputation_marine", 0)),
            "Pirates": to_title(char.get("reputation_pirate", 0)),
            "Merchants": to_title(char.get("reputation_merchant", 0)),
            "Civilians": to_title(char.get("reputation_civilian", 0)),
            "Underworld": to_title(char.get("reputation_criminal", 0))
        }


reputation_service = ReputationService()
