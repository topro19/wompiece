import random
from typing import Optional, List, Dict, Any
from app.database.connection import db_manager
from app.game.salvage.salvage_models import SalvageSite, SalvageType
from app.game.economy.ledger import ledger
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


DEFAULT_SALVAGE_TEMPLATES = [
    ("Wreck of the Golden Siren", SalvageType.SUNKEN_SHIPWRECK, "Azure Merchant Consortium", 450, [{"item_id": "fine_silk", "name": "Waterlogged Fine Silk", "type": "cargo", "quantity": 3}]),
    ("Drifting Cannonball Casks", SalvageType.DRIFTING_FLOTSAM, "Marine 16th Division", 180, [{"item_id": "gunpowder", "name": "Dry Gunpowder Cask", "type": "cargo", "quantity": 2}]),
    ("Buried Smuggler Cache", SalvageType.BURIED_CHEST, "Dead Man's Syndicate", 320, [{"item_id": "vintage_rum", "name": "Rare Aged Rum", "type": "cargo", "quantity": 4}])
]


class SalvageService:
    """Authoritative exploration, shipwreck diving, and salvage moral dilemma engine."""

    async def explore_for_salvage(
        self,
        character_id: str,
        location_id: str
    ) -> Optional[SalvageSite]:
        """Searches current waters/coves for salvage sites or spawns procedural flotsam."""
        db = db_manager.db

        # Check existing unclaimed site at this location
        existing = await db.salvage_sites.find_one({"location_id": location_id, "is_claimed": False})
        if existing:
            return SalvageSite(**existing)

        # 40% chance of discovering a new site when exploring
        if random.random() < 0.40:
            name, stype, owner, gold, items = random.choice(DEFAULT_SALVAGE_TEMPLATES)
            site = SalvageSite(
                name=name,
                location_id=location_id,
                salvage_type=stype,
                original_owner_name=owner,
                loot_gold=gold,
                loot_items=items,
                discovered_by_id=character_id
            )
            await db.salvage_sites.insert_one(site.to_mongo())

            await event_bus.publish(WorldEvent(
                event_type=EventType.SALVAGE_DISCOVERED,
                actor_id=character_id,
                location_id=location_id,
                visibility=EventVisibility.PUBLIC,
                state_delta=site.model_dump()
            ))

            return site

        return None

    async def claim_salvage(
        self,
        character_id: str,
        site_id: str,
        choice: str = "steal"  # "steal" or "return_to_owner"
    ) -> Dict[str, Any]:
        """Claims a discovered wreck, resolving moral and political consequences."""
        db = db_manager.db

        doc = await db.salvage_sites.find_one({"_id": site_id, "is_claimed": False})
        if not doc:
            raise ValueError("Salvage site not found or already scavenged.")

        site = SalvageSite(**doc)
        char = await db.characters.find_one({"_id": character_id, "status": "ALIVE"})
        if not char:
            raise ValueError("Character must be alive to claim salvage.")

        if choice == "return_to_owner":
            # Righteous choice: Return cargo to rightful merchant guild or navy
            # Receive 35% legal finder's fee
            reward = int(site.loot_gold * 0.35)
            await ledger.transfer(
                sender_id=None,
                receiver_id=character_id,
                amount=reward,
                reason=f"Legitimate finder's salvage reward for recovering {site.name}",
                idempotency_key=f"salv_return_{site.site_id}_{character_id}_{reward}",
                location_id=site.location_id
            )

            # Reputation reward
            await db.characters.update_one(
                {"_id": character_id},
                {"$inc": {"reputation_merchant": 15, "reputation_marine": 10}}
            )

            await db.salvage_sites.update_one(
                {"_id": site_id},
                {"$set": {"is_claimed": True}}
            )

            await event_bus.publish(WorldEvent(
                event_type=EventType.SALVAGE_CLAIMED,
                actor_id=character_id,
                location_id=site.location_id,
                visibility=EventVisibility.PUBLIC,
                state_delta={"site_id": site_id, "choice": "return_to_owner", "reward": reward}
            ))

            return {
                "site_name": site.name,
                "choice": "return_to_owner",
                "reward_gold": reward,
                "reputation_change": "+15 Merchant, +10 Marine",
                "narrative": f"You honorably returned {site.name} to {site.original_owner_name} and were granted a 35% salvage bounty!"
            }

        elif choice == "steal":
            # Outlaw choice: Pocket all gold and loot
            await ledger.transfer(
                sender_id=None,
                receiver_id=character_id,
                amount=site.loot_gold,
                reason=f"Plundered salvage from {site.name}",
                idempotency_key=f"salv_steal_{site.site_id}_{character_id}_{site.loot_gold}",
                location_id=site.location_id
            )

            # Add items to inventory
            for item in site.loot_items:
                await db.characters.update_one(
                    {"_id": character_id},
                    {"$push": {"inventory": item}}
                )

            # Slashes merchant/marine reputation if discovered
            await db.characters.update_one(
                {"_id": character_id},
                {"$inc": {"reputation_merchant": -10, "reputation_pirate": 5}}
            )

            await db.salvage_sites.update_one(
                {"_id": site_id},
                {"$set": {"is_claimed": True}}
            )

            await event_bus.publish(WorldEvent(
                event_type=EventType.SALVAGE_CLAIMED,
                actor_id=character_id,
                location_id=site.location_id,
                visibility=EventVisibility.PUBLIC,
                state_delta={"site_id": site_id, "choice": "steal", "gold": site.loot_gold}
            ))

            return {
                "site_name": site.name,
                "choice": "steal",
                "loot_gold": site.loot_gold,
                "items_acquired": [i["name"] for i in site.loot_items],
                "reputation_change": "-10 Merchant, +5 Pirate",
                "narrative": f"You stripped {site.name} clean of all gold and cargo without reporting it to authorities."
            }
        else:
            raise ValueError("Choice must be 'steal' or 'return_to_owner'.")


salvage_service = SalvageService()
