from typing import Optional, Dict, Any, List
from app.database.connection import db_manager
from app.game.models.character import Character, CharacterStatus, Faction
from app.game.world.location import Location, location_service
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


FACTION_STARTER_KITS: Dict[Faction, Dict[str, Any]] = {
    Faction.PIRATE: {
        "rank": "Deckhand",
        "wealth": 100,
        "items": [
            {"item_id": "rusty_cutlass", "name": "Rusty Cutlass", "type": "weapon", "damage": 12, "desc": "A chipped blade smelling of brine."},
            {"item_id": "crude_lockpick", "name": "Crude Lockpick", "type": "tool", "desc": "A bent wire handy for picking simple locks."},
            {"item_id": "spiced_rum", "name": "Bottle of Spiced Rum", "type": "consumable", "desc": "Fiery local brew."}
        ]
    },
    Faction.MARINE: {
        "rank": "Recruit",
        "wealth": 150,
        "items": [
            {"item_id": "marine_sabre", "name": "Standard-Issue Sabre", "type": "weapon", "damage": 14, "desc": "Polished steel stamped with the Marine insignia."},
            {"item_id": "marine_badge", "name": "Marine Warrant Badge", "type": "authority", "desc": "Authorizes low-level questioning and patrol duty."},
            {"item_id": "iron_manacles", "name": "Iron Manacles", "type": "restraint", "desc": "Heavy cuffs for securing detained suspects."}
        ]
    },
    Faction.MERCHANT: {
        "rank": "Apprentice Trader",
        "wealth": 350,
        "items": [
            {"item_id": "trade_ledger", "name": "Merchant's Trade Ledger", "type": "document", "desc": "Records debits, credits, and port tariffs."},
            {"item_id": "brass_scales", "name": "Brass Weighing Scales", "type": "tool", "desc": "Used to verify purity of coin and cargo weights."},
            {"item_id": "trade_permit", "name": "Port Azure Trade Permit", "type": "permit", "desc": "Official stamp allowing market stall operations."}
        ]
    },
    Faction.INDEPENDENT: {
        "rank": "Drifter",
        "wealth": 120,
        "items": [
            {"item_id": "concealed_dagger", "name": "Concealed Dagger", "type": "weapon", "damage": 10, "desc": "A short, sharp blade hidden inside the boot."},
            {"item_id": "silver_watch", "name": "Silver Pocket Watch", "type": "trinket", "desc": "Ticking brass mechanism engraved with faded initials."}
        ]
    }
}


class CharacterService:
    """Service governing character creation, inventory, and authoritative movement."""

    async def get_active_character_by_user(self, user_id: str) -> Optional[Character]:
        db = db_manager.db
        user = await db.users.find_one({"_id": user_id})
        if not user or not user.get("active_character_id"):
            return None

        char_doc = await db.characters.find_one({"_id": user["active_character_id"]})
        if not char_doc:
            return None

        # Verify character is alive
        if char_doc.get("status") != CharacterStatus.ALIVE.value:
            return None

        return Character(**char_doc)

    async def create_character(
        self,
        user_id: str,
        name: str,
        faction: Faction,
        starting_location_id: str = "port_azure_docks"
    ) -> Character:
        db = db_manager.db

        # 1. Enforce One-Life Rule: Cannot create character if already living
        existing = await self.get_active_character_by_user(user_id)
        if existing:
            raise ValueError(
                f"You already have an active living character: {existing.name} (Status: {existing.status.value}). "
                f"Under the One-Life system, you cannot create another character while alive."
            )

        # 2. Check Name Uniqueness among living characters
        name_clean = name.strip()
        if len(name_clean) < 2 or len(name_clean) > 32:
            raise ValueError("Character name must be between 2 and 32 characters.")

        duplicate = await db.characters.find_one({
            "name": {"$regex": f"^{name_clean}$", "$options": "i"},
            "status": CharacterStatus.ALIVE.value
        })
        if duplicate:
            raise ValueError(f"A living character with the name '{name_clean}' already exists.")

        # 3. Apply Faction Starter Kit
        kit = FACTION_STARTER_KITS.get(faction, FACTION_STARTER_KITS[Faction.PIRATE])

        char = Character(
            user_id=user_id,
            name=name_clean,
            is_ai=False,
            status=CharacterStatus.ALIVE,
            faction=faction,
            rank=kit["rank"],
            wealth=kit["wealth"],
            inventory=kit["items"],
            location_id=starting_location_id,
            health=100,
            max_health=100
        )

        # 4. Insert into database
        await db.characters.insert_one(char.to_mongo())

        # 5. Link to user record
        await db.users.update_one(
            {"_id": user_id},
            {
                "$set": {"active_character_id": char.character_id},
                "$setOnInsert": {"deceased_character_ids": []}
            },
            upsert=True
        )

        # 6. Publish World Event
        await event_bus.publish(WorldEvent(
            event_type=EventType.PLAYER_CREATED,
            actor_id=char.character_id,
            location_id=starting_location_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={
                "name": char.name,
                "faction": char.faction.value,
                "rank": char.rank,
                "wealth": char.wealth
            },
            metadata={"user_id": user_id}
        ))

        logger.info(f"Created new player character '{char.name}' (Faction: {char.faction.value}) for user {user_id}.")
        return char

    async def move_character(self, character_id: str, target_location_id: str) -> Location:
        """Validates graph connectivity and deterministically moves character."""
        db = db_manager.db

        char_doc = await db.characters.find_one({"_id": character_id})
        if not char_doc:
            raise ValueError(f"Character {character_id} not found.")

        if char_doc.get("status") != CharacterStatus.ALIVE.value:
            raise ValueError("Deceased or imprisoned characters cannot travel.")

        current_location_id = char_doc.get("location_id", "port_azure_docks")
        if current_location_id == target_location_id:
            raise ValueError("You are already at this location.")

        # Validate Movement Graph
        if not location_service.can_move(current_location_id, target_location_id):
            target_loc = location_service.get_location(target_location_id)
            target_name = target_loc.name if target_loc else target_location_id
            raise ValueError(f"Cannot travel directly to {target_name}. It is not connected to your current location.")

        # Atomic State Mutation
        await db.characters.update_one(
            {"_id": character_id},
            {"$set": {"location_id": target_location_id}}
        )

        destination = location_service.get_location(target_location_id)

        # Record movement event
        await event_bus.publish(WorldEvent(
            event_type=EventType.CHARACTER_SPAWNED,
            actor_id=character_id,
            location_id=target_location_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={
                "from_location": current_location_id,
                "to_location": target_location_id
            }
        ))

        return destination

    async def add_item(self, character_id: str, item: Dict[str, Any]):
        db = db_manager.db
        await db.characters.update_one(
            {"_id": character_id},
            {"$push": {"inventory": item}}
        )

    async def remove_item(self, character_id: str, item_id: str) -> bool:
        db = db_manager.db
        res = await db.characters.update_one(
            {"_id": character_id},
            {"$pull": {"inventory": {"item_id": item_id}}}
        )
        return res.modified_count > 0


character_service = CharacterService()
