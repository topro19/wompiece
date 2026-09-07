import random
from typing import Optional, List, Dict, Any
from app.database.connection import db_manager
from app.game.ships.ship_models import (
    Ship,
    ShipClass,
    ShipCondition,
    ShipClassConfig,
    SHIP_CLASS_CONFIGS,
    CargoItem
)
from app.game.world.location import location_service
from app.game.economy.ledger import ledger
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class ShipService:
    """Authoritative naval system governing ship purchases, sea navigation, cargo, and broadside combat."""

    async def get_ship(self, ship_id: str) -> Optional[Ship]:
        db = db_manager.db
        doc = await db.ships.find_one({"_id": ship_id})
        if not doc:
            return None
        return Ship(**doc)

    async def get_ships_by_owner(self, character_id: str) -> List[Ship]:
        db = db_manager.db
        cursor = db.ships.find({"owner_character_id": character_id})
        return [Ship(**doc) async for doc in cursor]

    async def get_crew_ships(self, crew_id: str) -> List[Ship]:
        db = db_manager.db
        cursor = db.ships.find({"owner_crew_id": crew_id})
        return [Ship(**doc) async for doc in cursor]

    async def get_ships_at_location(self, location_id: str) -> List[Ship]:
        db = db_manager.db
        cursor = db.ships.find({
            "location_id": location_id,
            "condition": {"$ne": ShipCondition.SUNK.value}
        })
        return [Ship(**doc) async for doc in cursor]

    async def purchase_ship(
        self,
        buyer_character_id: str,
        ship_class: ShipClass,
        name: str,
        for_crew: bool = False
    ) -> Ship:
        """Purchases a vessel from a shipyard and registers it in the world."""
        db = db_manager.db

        char_doc = await db.characters.find_one({"_id": buyer_character_id})
        if not char_doc or char_doc.get("status") != "ALIVE":
            raise ValueError("Only living characters can purchase a vessel.")

        current_location_id = char_doc.get("location_id", "port_azure_docks")
        loc = location_service.get_location(current_location_id)
        if not loc or "shipyard" not in loc.facilities:
            raise ValueError("You must be at a port equipped with a shipyard to purchase a vessel.")

        config = SHIP_CLASS_CONFIGS.get(ship_class)
        if not config:
            raise ValueError(f"Unknown ship class '{ship_class}'.")

        ship_name = name.strip()
        if len(ship_name) < 2 or len(ship_name) > 36:
            raise ValueError("Ship name must be between 2 and 36 characters.")

        owner_crew_id = None
        if for_crew:
            crew_id = char_doc.get("crew_id")
            if not crew_id:
                raise ValueError("You do not belong to any crew.")
            crew_doc = await db.crews.find_one({"_id": crew_id})
            if not crew_doc or crew_doc.get("captain_id") != buyer_character_id:
                raise ValueError("Only the Captain can purchase a flagship for the crew.")
            
            # Debit crew treasury
            await ledger.transfer(
                sender_id=crew_id,
                receiver_id="system_shipyard",
                amount=config.base_cost,
                reason=f"Purchased {config.name} '{ship_name}' for crew {crew_doc.get('name')}",
                idempotency_key=f"ship_purchase_{buyer_character_id}_{ship_name}_{config.base_cost}",
                location_id=current_location_id
            )
            owner_crew_id = crew_id
        else:
            # Debit personal wallet
            await ledger.transfer(
                sender_id=buyer_character_id,
                receiver_id="system_shipyard",
                amount=config.base_cost,
                reason=f"Purchased {config.name} '{ship_name}'",
                idempotency_key=f"ship_purchase_{buyer_character_id}_{ship_name}_{config.base_cost}",
                location_id=current_location_id
            )

        ship = Ship(
            name=ship_name,
            ship_class=ship_class,
            owner_character_id=buyer_character_id if not for_crew else None,
            owner_crew_id=owner_crew_id,
            captain_id=buyer_character_id,
            current_hull=config.max_hull,
            max_hull=config.max_hull,
            armor=config.armor,
            cannons=config.cannons,
            speed=config.speed,
            cargo_capacity=config.cargo_capacity,
            crew_capacity=config.crew_capacity,
            condition=ShipCondition.MINT,
            location_id=current_location_id,
            is_docked=loc.is_port
        )

        await db.ships.insert_one(ship.to_mongo())

        await event_bus.publish(WorldEvent(
            event_type=EventType.SHIP_PURCHASED,
            actor_id=buyer_character_id,
            location_id=current_location_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={
                "ship_id": ship.ship_id,
                "name": ship.name,
                "class": ship.ship_class.value,
                "cost": config.base_cost,
                "owner_crew_id": owner_crew_id
            }
        ))

        logger.info(f"Ship '{ship.name}' ({ship.ship_class.value}) purchased by character {buyer_character_id}.")
        return ship

    async def sail_ship(
        self,
        ship_id: str,
        captain_character_id: str,
        destination_location_id: str
    ) -> Dict[str, Any]:
        """Navigates ship along sea routes, resolving dynamic ocean encounters."""
        db = db_manager.db

        ship = await self.get_ship(ship_id)
        if not ship:
            raise ValueError(f"Ship {ship_id} not found.")

        if ship.condition == ShipCondition.SUNK:
            raise ValueError("This ship has been sunk and rests at the bottom of the ocean.")

        if ship.condition == ShipCondition.CRIPPLED:
            raise ValueError("This vessel is critically damaged and unseaworthy! Repair it at a shipyard first.")

        if ship.captain_id != captain_character_id and ship.owner_character_id != captain_character_id:
            raise ValueError("You are not authorized to command this ship.")

        current_loc_id = ship.location_id
        if current_loc_id == destination_location_id:
            raise ValueError("The vessel is already at this location.")

        if not location_service.can_move(current_loc_id, destination_location_id):
            dest_loc = location_service.get_location(destination_location_id)
            dest_name = dest_loc.name if dest_loc else destination_location_id
            raise ValueError(f"No navigable maritime route exists from current location to {dest_name}.")

        destination_loc = location_service.get_location(destination_location_id)
        if not destination_loc:
            raise ValueError("Unknown destination.")

        # Update ship and captain position
        ship.location_id = destination_location_id
        ship.is_docked = destination_loc.is_port

        # Sea Encounter Simulation
        encounter = self._roll_sea_encounter(ship, destination_loc)
        damage_taken = 0
        if encounter["type"] == "STORM":
            damage_taken = max(5, 25 - ship.armor)
            ship.current_hull = max(1, ship.current_hull - damage_taken)
            ship.update_condition()
            encounter["damage_taken"] = damage_taken

        # Persist Ship Update
        await db.ships.update_one(
            {"_id": ship_id},
            {
                "$set": {
                    "location_id": destination_location_id,
                    "is_docked": ship.is_docked,
                    "current_hull": ship.current_hull,
                    "condition": ship.condition.value
                }
            }
        )

        # Move captain to destination
        await db.characters.update_one(
            {"_id": captain_character_id},
            {"$set": {"location_id": destination_location_id}}
        )

        # Publish Event
        await event_bus.publish(WorldEvent(
            event_type=EventType.SHIP_SAILED,
            actor_id=captain_character_id,
            location_id=destination_location_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={
                "ship_id": ship_id,
                "from_location": current_loc_id,
                "to_location": destination_location_id,
                "encounter": encounter["type"],
                "hull_remaining": ship.current_hull
            }
        ))

        return {
            "ship": ship,
            "destination": destination_loc,
            "encounter": encounter
        }

    def _roll_sea_encounter(self, ship: Ship, dest_loc) -> Dict[str, Any]:
        """Rolls deterministic maritime encounters based on contraband, zone, and weather."""
        roll = random.random()

        if ship.has_contraband() and roll < 0.40:
            return {
                "type": "MARINE_PATROL",
                "narrative": "A naval frigate carrying Marine customs inspectors spotted your wake and signaled for inspection!",
                "threat_level": 4
            }
        elif dest_loc.security_level <= 1 and roll < 0.35:
            return {
                "type": "PIRATE_RAID",
                "narrative": "A predatory pirate sloop raised the black flag and cut across your bow, seeking plunder!",
                "threat_level": 3
            }
        elif roll < 0.20:
            return {
                "type": "STORM",
                "narrative": "A sudden gale slammed your vessel, punishing the rigging and fracturing hull timbers!",
                "threat_level": 2
            }
        elif roll < 0.40:
            return {
                "type": "MERCHANT_CONVOY",
                "narrative": "You passed a heavily laden merchant convoy sailing under civilian escort.",
                "threat_level": 1
            }
        else:
            return {
                "type": "CALM_SEAS",
                "narrative": "Fair winds filled your sails across calm ocean waters.",
                "threat_level": 0
            }

    async def naval_cannon_combat(
        self,
        attacker_ship_id: str,
        target_ship_id: str
    ) -> Dict[str, Any]:
        """Executes server-authoritative naval broadside combat between two ships."""
        db = db_manager.db

        attacker = await self.get_ship(attacker_ship_id)
        target = await self.get_ship(target_ship_id)

        if not attacker or not target:
            raise ValueError("One or both vessels could not be found.")

        if attacker.condition == ShipCondition.SUNK:
            raise ValueError("Attacking ship is already sunk.")

        if target.condition == ShipCondition.SUNK:
            raise ValueError("Target ship is already sunk.")

        if attacker.location_id != target.location_id:
            raise ValueError("Both vessels must be in the same location to engage in broadside combat.")

        # 1. Attacker Broadside Roll
        hit_count = sum(1 for _ in range(attacker.cannons) if random.random() < 0.70)
        base_damage_per_hit = 14
        gross_damage = hit_count * base_damage_per_hit
        net_damage = max(hit_count, gross_damage - target.armor)

        # Critical powder explosion check
        crit = random.random() < 0.15
        if crit:
            net_damage = int(net_damage * 1.5)

        target.current_hull = max(0, target.current_hull - net_damage)
        target.update_condition()

        target_sunk = target.condition == ShipCondition.SUNK

        # 2. Target Retaliation (if still afloat)
        retaliation_damage = 0
        attacker_sunk = False
        if not target_sunk and target.cannons > 0:
            ret_hits = sum(1 for _ in range(target.cannons) if random.random() < 0.65)
            ret_gross = ret_hits * base_damage_per_hit
            retaliation_damage = max(ret_hits, ret_gross - attacker.armor)
            attacker.current_hull = max(0, attacker.current_hull - retaliation_damage)
            attacker.update_condition()
            attacker_sunk = attacker.condition == ShipCondition.SUNK

        # 3. Persist State Changes
        await db.ships.update_one(
            {"_id": target.ship_id},
            {"$set": {"current_hull": target.current_hull, "condition": target.condition.value}}
        )
        await db.ships.update_one(
            {"_id": attacker.ship_id},
            {"$set": {"current_hull": attacker.current_hull, "condition": attacker.condition.value}}
        )

        # 4. Emit Events
        await event_bus.publish(WorldEvent(
            event_type=EventType.NAVAL_COMBAT,
            actor_id=attacker.captain_id,
            target_id=target.captain_id,
            location_id=attacker.location_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={
                "attacker_ship_id": attacker.ship_id,
                "target_ship_id": target.ship_id,
                "attacker_damage_dealt": net_damage,
                "target_damage_retaliated": retaliation_damage,
                "target_sunk": target_sunk,
                "attacker_sunk": attacker_sunk,
                "is_critical": crit
            }
        ))

        if target_sunk:
            await event_bus.publish(WorldEvent(
                event_type=EventType.SHIP_SUNK,
                actor_id=attacker.captain_id,
                target_id=target.captain_id,
                location_id=attacker.location_id,
                visibility=EventVisibility.PUBLIC,
                state_delta={"sunk_ship_id": target.ship_id, "victor_ship_id": attacker.ship_id}
            ))

        return {
            "attacker": attacker,
            "target": target,
            "damage_dealt": net_damage,
            "retaliation_damage": retaliation_damage,
            "target_sunk": target_sunk,
            "attacker_sunk": attacker_sunk,
            "is_critical": crit
        }

    async def repair_ship(
        self,
        ship_id: str,
        character_id: str,
        hp_amount: int
    ) -> Dict[str, Any]:
        """Repairs ship hull at a certified shipyard."""
        db = db_manager.db

        ship = await self.get_ship(ship_id)
        if not ship:
            raise ValueError(f"Ship {ship_id} not found.")

        if ship.condition == ShipCondition.SUNK:
            raise ValueError("Sunken vessels cannot be repaired.")

        loc = location_service.get_location(ship.location_id)
        if not loc or "shipyard" not in loc.facilities:
            raise ValueError("Vessel must be docked at a port with a shipyard to undergo repairs.")

        missing_hp = ship.max_hull - ship.current_hull
        if missing_hp <= 0:
            raise ValueError("Vessel is already at maximum hull integrity.")

        repair_points = min(hp_amount, missing_hp)
        cost_per_point = 2
        total_cost = repair_points * cost_per_point

        # Debit character
        await ledger.transfer(
            sender_id=character_id,
            receiver_id="system_shipyard",
            amount=total_cost,
            reason=f"Shipyard hull repairs for '{ship.name}' ({repair_points} HP)",
            idempotency_key=f"repair_{ship_id}_{ship.current_hull}_{repair_points}",
            location_id=ship.location_id
        )

        ship.current_hull += repair_points
        ship.update_condition()

        await db.ships.update_one(
            {"_id": ship_id},
            {"$set": {"current_hull": ship.current_hull, "condition": ship.condition.value}}
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.SHIP_REPAIRED,
            actor_id=character_id,
            location_id=ship.location_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={
                "ship_id": ship_id,
                "repaired_points": repair_points,
                "current_hull": ship.current_hull,
                "cost": total_cost
            }
        ))

        return {
            "ship": ship,
            "repaired_points": repair_points,
            "total_cost": total_cost
        }

    async def transfer_cargo(
        self,
        ship_id: str,
        character_id: str,
        item_id: str,
        quantity: int,
        direction: str = "load"
    ) -> Dict[str, Any]:
        """Transfers goods between a player's inventory and the ship's hold."""
        db = db_manager.db

        if quantity <= 0:
            raise ValueError("Quantity must be positive.")

        ship = await self.get_ship(ship_id)
        if not ship:
            raise ValueError("Ship not found.")

        char_doc = await db.characters.find_one({"_id": character_id})
        if not char_doc:
            raise ValueError("Character not found.")

        if direction == "load":
            # Check character inventory
            inventory = char_doc.get("inventory", [])
            char_item = next((i for i in inventory if i.get("item_id") == item_id), None)
            if not char_item:
                raise ValueError(f"You do not possess '{item_id}' in your inventory.")

            # Check ship cargo capacity
            current_weight = ship.current_cargo_weight()
            if current_weight + quantity > ship.cargo_capacity:
                raise ValueError(f"Not enough cargo hold space! Capacity: {ship.cargo_capacity}, Current: {current_weight}.")

            # Transfer
            await db.characters.update_one(
                {"_id": character_id},
                {"$pull": {"inventory": {"item_id": item_id}}}
            )

            existing_cargo = next((c for c in ship.cargo if c.item_id == item_id), None)
            if existing_cargo:
                existing_cargo.quantity += quantity
            else:
                is_contraband = char_item.get("is_contraband", False) or "contraband" in char_item.get("type", "").lower()
                ship.cargo.append(CargoItem(
                    item_id=item_id,
                    name=char_item.get("name", item_id),
                    quantity=quantity,
                    is_contraband=is_contraband,
                    value_per_unit=char_item.get("value", 15)
                ))

            await db.ships.update_one(
                {"_id": ship_id},
                {"$set": {"cargo": [c.model_dump() for c in ship.cargo]}}
            )

        elif direction == "unload":
            existing_cargo = next((c for c in ship.cargo if c.item_id == item_id), None)
            if not existing_cargo or existing_cargo.quantity < quantity:
                raise ValueError(f"Ship does not have {quantity} units of '{item_id}'.")

            existing_cargo.quantity -= quantity
            if existing_cargo.quantity <= 0:
                ship.cargo = [c for c in ship.cargo if c.item_id != item_id]

            # Add to character inventory
            new_inv_item = {
                "item_id": existing_cargo.item_id,
                "name": existing_cargo.name,
                "type": "cargo",
                "is_contraband": existing_cargo.is_contraband,
                "value": existing_cargo.value_per_unit
            }
            await db.characters.update_one(
                {"_id": character_id},
                {"$push": {"inventory": new_inv_item}}
            )
            await db.ships.update_one(
                {"_id": ship_id},
                {"$set": {"cargo": [c.model_dump() for c in ship.cargo]}}
            )
        else:
            raise ValueError("Direction must be 'load' or 'unload'.")

        await event_bus.publish(WorldEvent(
            event_type=EventType.CARGO_TRANSFERRED,
            actor_id=character_id,
            location_id=ship.location_id,
            visibility=EventVisibility.PRIVATE,
            state_delta={
                "ship_id": ship_id,
                "item_id": item_id,
                "quantity": quantity,
                "direction": direction
            }
        ))

        return {
            "ship_id": ship_id,
            "direction": direction,
            "item_id": item_id,
            "quantity": quantity
        }


ship_service = ShipService()
