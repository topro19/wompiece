import pytest
from app.database.connection import db_manager
from app.game.models.character import Faction
from app.services.character_service import character_service
from app.game.crews.crew_service import crew_service
from app.game.ships.ship_models import ShipClass, ShipCondition
from app.game.ships.ship_service import ship_service
from app.game.economy.ledger import ledger


@pytest.mark.asyncio
async def test_ship_purchase_and_stats():
    """Validates purchasing a vessel, ledger debits, and authoritative stats."""
    db = db_manager.db
    await db.characters.delete_many({})
    await db.ships.delete_many({})
    await db.transactions.delete_many({})

    # 1. Create living buyer with enough doubloons
    buyer = await character_service.create_character(
        user_id="user_ship_buyer",
        name="Captain Drake",
        faction=Faction.PIRATE,
        starting_location_id="port_azure_docks"
    )
    # Mint 2,000 gold into buyer's wallet
    await ledger.transfer(
        receiver_id=buyer.character_id,
        amount=2000,
        reason="Ship purchase fund",
        idempotency_key="fund_buyer_drake_1"
    )

    # 2. Purchase Sloop (Cost: 500)
    sloop = await ship_service.purchase_ship(
        buyer_character_id=buyer.character_id,
        ship_class=ShipClass.SLOOP,
        name="Sea Shadow"
    )

    assert sloop.ship_id.startswith("ship_")
    assert sloop.name == "Sea Shadow"
    assert sloop.ship_class == ShipClass.SLOOP
    assert sloop.current_hull == 100
    assert sloop.max_hull == 100
    assert sloop.cannons == 4
    assert sloop.armor == 5
    assert sloop.condition == ShipCondition.MINT
    assert sloop.location_id == "port_azure_docks"
    assert sloop.is_docked is True

    # Check character wealth in DB
    updated_buyer = await db.characters.find_one({"_id": buyer.character_id})
    assert updated_buyer["wealth"] == 100 + 2000 - 500  # 1600


@pytest.mark.asyncio
async def test_ship_sailing_and_sea_encounters():
    """Validates ocean navigation from port through sea lane to island anchorage."""
    db = db_manager.db

    char = await character_service.create_character(
        user_id="user_sailor",
        name="Navigator James",
        faction=Faction.MERCHANT,
        starting_location_id="port_azure_docks"
    )
    await ledger.transfer(
        receiver_id=char.character_id,
        amount=2000,
        reason="Vessel capital",
        idempotency_key="fund_james_1"
    )

    caravel = await ship_service.purchase_ship(
        buyer_character_id=char.character_id,
        ship_class=ShipClass.CARAVEL,
        name="Fortune's Favor"
    )

    # Sail from port_azure_docks to azure_sea_lane
    sail_result1 = await ship_service.sail_ship(
        ship_id=caravel.ship_id,
        captain_character_id=char.character_id,
        destination_location_id="azure_sea_lane"
    )
    assert sail_result1["ship"].location_id == "azure_sea_lane"
    assert sail_result1["ship"].is_docked is False
    assert sail_result1["encounter"]["type"] in ["CALM_SEAS", "STORM", "MARINE_PATROL", "PIRATE_RAID", "MERCHANT_CONVOY"]

    # Sail from azure_sea_lane to skull_rock_anchorage
    sail_result2 = await ship_service.sail_ship(
        ship_id=caravel.ship_id,
        captain_character_id=char.character_id,
        destination_location_id="skull_rock_anchorage"
    )
    assert sail_result2["ship"].location_id == "skull_rock_anchorage"
    assert sail_result2["ship"].is_docked is True

    # Verify character's updated location
    updated_char = await db.characters.find_one({"_id": char.character_id})
    assert updated_char["location_id"] == "skull_rock_anchorage"


@pytest.mark.asyncio
async def test_naval_cannon_combat_and_ship_sinking():
    """Validates broadside artillery exchanges, damage calculation, and sinking."""
    db = db_manager.db

    # Create two pirate captains
    capt1 = await character_service.create_character(
        user_id="user_capt1",
        name="Redbeard",
        faction=Faction.PIRATE,
        starting_location_id="port_azure_docks"
    )
    capt2 = await character_service.create_character(
        user_id="user_capt2",
        name="Blacktide",
        faction=Faction.PIRATE,
        starting_location_id="port_azure_docks"
    )

    await ledger.transfer(
        receiver_id=capt1.character_id,
        amount=10000,
        reason="Ship funds 1",
        idempotency_key="fund_capt1_1"
    )
    await ledger.transfer(
        receiver_id=capt2.character_id,
        amount=10000,
        reason="Ship funds 2",
        idempotency_key="fund_capt2_1"
    )

    # Capt1 buys a Frigate (24 cannons, 400 HP), Capt2 buys a Sloop (4 cannons, 100 HP)
    warship = await ship_service.purchase_ship(
        buyer_character_id=capt1.character_id,
        ship_class=ShipClass.FRIGATE,
        name="Dreadnought"
    )
    sloop = await ship_service.purchase_ship(
        buyer_character_id=capt2.character_id,
        ship_class=ShipClass.SLOOP,
        name="Little Skiff"
    )

    # Set Sloop hull low to test sinking in one engagement
    await db.ships.update_one({"_id": sloop.ship_id}, {"$set": {"current_hull": 10}})

    # Naval combat engagement
    combat_res = await ship_service.naval_cannon_combat(
        attacker_ship_id=warship.ship_id,
        target_ship_id=sloop.ship_id
    )

    assert combat_res["damage_dealt"] > 0
    assert combat_res["target_sunk"] is True

    # Verify target ship is sunk in database
    target_db = await ship_service.get_ship(sloop.ship_id)
    assert target_db.condition == ShipCondition.SUNK
    assert target_db.current_hull == 0


@pytest.mark.asyncio
async def test_ship_repairs_and_cargo_transfer():
    """Validates hull restoration at shipyard and cargo loading/unloading."""
    db = db_manager.db

    capt = await character_service.create_character(
        user_id="user_cargo_capt",
        name="Merchant Paul",
        faction=Faction.MERCHANT,
        starting_location_id="port_azure_docks"
    )
    await ledger.transfer(
        receiver_id=capt.character_id,
        amount=5000,
        reason="Working capital",
        idempotency_key="fund_paul_1"
    )

    ship = await ship_service.purchase_ship(
        buyer_character_id=capt.character_id,
        ship_class=ShipClass.SLOOP,
        name="Trader Sloop"
    )

    # Damage ship hull slightly
    await db.ships.update_one({"_id": ship.ship_id}, {"$set": {"current_hull": 80}})

    # Repair 20 HP (Cost: 20 * 2 = 40 gold)
    repair_res = await ship_service.repair_ship(
        ship_id=ship.ship_id,
        character_id=capt.character_id,
        hp_amount=20
    )
    assert repair_res["repaired_points"] == 20
    assert repair_res["total_cost"] == 40
    assert repair_res["ship"].current_hull == 100

    # Cargo transfer: Add spices to character inventory
    await character_service.add_item(capt.character_id, {
        "item_id": "rare_spices",
        "name": "Crate of Rare Spices",
        "type": "cargo",
        "value": 50
    })

    load_res = await ship_service.transfer_cargo(
        ship_id=ship.ship_id,
        character_id=capt.character_id,
        item_id="rare_spices",
        quantity=1,
        direction="load"
    )
    assert load_res["direction"] == "load"

    updated_ship = await ship_service.get_ship(ship.ship_id)
    assert len(updated_ship.cargo) == 1
    assert updated_ship.cargo[0].item_id == "rare_spices"

    # Unload back to character
    unload_res = await ship_service.transfer_cargo(
        ship_id=ship.ship_id,
        character_id=capt.character_id,
        item_id="rare_spices",
        quantity=1,
        direction="unload"
    )
    assert unload_res["direction"] == "unload"

    updated_ship_empty = await ship_service.get_ship(ship.ship_id)
    assert len(updated_ship_empty.cargo) == 0
