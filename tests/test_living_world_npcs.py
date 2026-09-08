import pytest
import mongomock
from unittest.mock import AsyncMock, patch

from app.database.connection import db_manager
from app.game.npcs.npc_models import (
    WorldNPC,
    NPCFaction,
    NPCArchetype,
    NPCScheduleEntry,
    NPCGoal,
    NPCCombatStats
)
from app.game.npcs.npc_population_service import npc_population_service
from app.game.npcs.npc_encounter_service import npc_encounter_service
from app.game.npcs.npc_interaction_service import npc_interaction_service
from app.game.world.location import Location, location_service


@pytest.fixture(autouse=True)
async def setup_mock_db():
    await db_manager.connect(force_mock=True)
    # Clear collections before each test
    await db_manager.db.npcs.delete_many({})
    await db_manager.db.characters.delete_many({})
    await db_manager.db.relationships.delete_many({})
    yield



@pytest.mark.asyncio
async def test_world_npc_model_integrity():
    """Verify WorldNPC schema, serialization, and properties."""
    npc = WorldNPC(
        name="Barnaby 'One-Eye' Drake",
        faction=NPCFaction.PIRATE,
        role=NPCArchetype.PIRATE_VETERAN,
        occupation="Pirate Veteran",
        island_id="Isla de la Muerte",
        home_location_id="skull_rock_tavern",
        location_id="skull_rock_tavern",
        personality=["Ruthless", "Ambitious"],
        wealth=120,
        wanted_status=450
    )
    assert npc.is_pirate is True
    assert npc.is_marine is False
    assert npc.role_title == "Pirate Veteran"
    
    mongo_dict = npc.to_mongo()
    assert mongo_dict["_id"] == npc.npc_id
    assert mongo_dict["wanted_status"] == 450


@pytest.mark.asyncio
async def test_procedural_population_seeding():
    """Verify procedural seeding populates taverns, docks, and marine garrisons with correct archetypes."""
    # 1. Seed docks
    docks_npcs = await npc_population_service.seed_location_population("port_azure_docks")
    assert len(docks_npcs) >= 6
    dock_roles = [n.role for n in docks_npcs]
    assert any(r in [NPCArchetype.DOCKWORKER, NPCArchetype.SAILOR, NPCArchetype.FISHERMAN] for r in dock_roles)
    assert any(n.is_marine for n in docks_npcs)

    # 2. Seed tavern
    tavern_npcs = await npc_population_service.seed_location_population("the_crimson_parrot")
    assert len(tavern_npcs) >= 6
    tavern_roles = [n.role for n in tavern_npcs]
    assert NPCArchetype.BARTENDER in tavern_roles
    assert any(n.is_pirate for n in tavern_npcs)

    # 3. Seed Marine HQ
    marine_npcs = await npc_population_service.seed_location_population("marine_headquarters")
    assert len(marine_npcs) >= 6
    assert all(n.is_marine for n in marine_npcs)
    marine_roles = [n.role for n in marine_npcs]
    assert any(r in [NPCArchetype.MARINE_COMMANDER, NPCArchetype.MARINE_OFFICER, NPCArchetype.MARINE_SERGEANT] for r in marine_roles)


@pytest.mark.asyncio
async def test_dynamic_generic_island_population():
    """Verify that newly added locations/islands automatically populate without manual intervention."""
    # Register a new synthetic island location
    synthetic_loc = Location(
        location_id="new_isle_market",
        name="New Isle Grand Bazaar",
        island="New Mystery Isle",
        description="A newly discovered frontier trading station.",
        connected_locations=[],
        security_level=2,
        facilities=["market", "general_store", "trading_post"]
    )
    location_service._locations["new_isle_market"] = synthetic_loc

    # Querying NPCs at this location should auto-seed baseline population
    npcs = await npc_population_service.get_npcs_at_location("new_isle_market")
    assert len(npcs) >= 5
    assert all(n.location_id == "new_isle_market" for n in npcs)
    assert any(n.faction == NPCFaction.MERCHANT for n in npcs)


@pytest.mark.asyncio
async def test_location_atmosphere_and_active_scenes():
    """Verify get_location_atmosphere returns ambient description, active scenes, and NPC roster."""
    # Seed location
    await npc_population_service.seed_location_population("port_azure_docks")

    atmosphere = await npc_encounter_service.get_location_atmosphere(
        location_id="port_azure_docks",
        character_id="char_test_1"
    )

    assert atmosphere.location_id == "port_azure_docks"
    assert len(atmosphere.present_npcs) >= 6
    assert len(atmosphere.active_scenes) >= 1
    # Check that scenes describe interactions
    first_scene = atmosphere.active_scenes[0]
    assert len(first_scene.title) > 0
    assert len(first_scene.description) > 0
    assert len(first_scene.suggested_actions) > 0


@pytest.mark.asyncio
async def test_npc_interaction_and_relationship_memory():
    """Verify talking to, bribing, and recruiting an NPC updates relationships and records memories."""
    # Create test NPC in DB
    corrupt_marine = WorldNPC(
        name="Sergeant Barlow",
        faction=NPCFaction.MARINE,
        role=NPCArchetype.MARINE_SERGEANT,
        occupation="Marine Sergeant",
        island_id="Azure Island",
        home_location_id="port_azure_docks",
        location_id="port_azure_docks",
        personality=["Corrupt", "Easily bribed"],
        wealth=50
    )
    await db_manager.db.npcs.insert_one(corrupt_marine.to_mongo())

    # Create test character
    await db_manager.db.characters.insert_one({
        "_id": "char_player_1",
        "name": "Captain Morgan",
        "faction": "PIRATE",
        "wealth": 200
    })

    # Test Bribe
    bribe_res = await npc_interaction_service.interact(
        character_id="char_player_1",
        npc_id=corrupt_marine.npc_id,
        action_type="BRIBE_50"
    )
    assert bribe_res.trust_delta > 0
    assert "bribed" in bribe_res.memory_logged.lower()

    # Verify relationship persisted in db.relationships
    rel_doc = await db_manager.db.relationships.find_one({"character_id": "char_player_1"})
    assert rel_doc is not None
    assert rel_doc["trust"] > 0
    assert len(rel_doc["memories"]) >= 1


@pytest.mark.asyncio
async def test_npc_custom_speech_and_work_inquiry():
    """Verify player custom speech input and work inquiries produce constructive dialogue."""
    dockworker = WorldNPC(
        name="Calico 'Scar-Face' Low",
        faction=NPCFaction.CIVILIAN,
        role=NPCArchetype.DOCKWORKER,
        occupation="Dockworker",
        island_id="Azure Island",
        home_location_id="port_azure_docks",
        location_id="port_azure_docks",
        personality=["Ruthless", "Suspicious", "Proud"],
        wealth=41
    )
    await db_manager.db.npcs.insert_one(dockworker.to_mongo())

    await db_manager.db.characters.insert_one({
        "_id": "char_player_custom",
        "name": "gintoki shwarma",
        "faction": "PIRATE",
        "wealth": 100
    })

    # 1. Custom Player Input (e.g. asking who runs the docks)
    custom_res = await npc_interaction_service.interact(
        character_id="char_player_custom",
        npc_id=dockworker.npc_id,
        action_type="CUSTOM_SPEECH",
        player_speech="Who runs this stretch of docks, and what kind of work can a stout pirate find here?"
    )
    assert custom_res.npc_name == dockworker.name
    assert len(custom_res.dialogue) > 20
    assert not custom_res.dialogue.endswith("Keep your wits sharp in this district.'\"")

    # 2. Inquire for Work / Jobs
    work_res = await npc_interaction_service.interact(
        character_id="char_player_custom",
        npc_id=dockworker.npc_id,
        action_type="ASK_WORK"
    )
    assert len(work_res.dialogue) > 30



@pytest.mark.asyncio
async def test_npc_schedule_and_routine_simulation():
    """Verify simulate_npc_schedules moves NPCs between connected locations according to routine."""
    # Create an NPC at docks whose schedule dictates evening tavern
    traveling_sailor = WorldNPC(
        name="Finley Bones",
        faction=NPCFaction.CIVILIAN,
        role=NPCArchetype.SAILOR,
        occupation="Sailor",
        island_id="Azure Island",
        home_location_id="port_azure_docks",
        location_id="port_azure_docks",
        personality=["Friendly"],
        schedule=[
            NPCScheduleEntry(start_hour=18, end_hour=23, preferred_facility="tavern", activity_description="Drinking at tavern")
        ],
        goals=[
            NPCGoal(goal_type="MAKE_MONEY", description="Earn wages", target_count=5, current_progress=0)
        ]
    )
    await db_manager.db.npcs.insert_one(traveling_sailor.to_mongo())

    # Simulate tick at 20:00 (evening)
    sim_res = await npc_population_service.simulate_npc_schedules(current_hour=20)
    assert sim_res["npcs_moved"] >= 1

    # Verify NPC moved to the connected tavern
    updated_doc = await db_manager.db.npcs.find_one({"_id": traveling_sailor.npc_id})
    assert updated_doc["location_id"] == "the_crimson_parrot"


@pytest.mark.asyncio
async def test_marine_commander_recruitment_rejection():
    """Verify Marine Commanders reject recruit attempts with authentic Marine authority and no swabbing-decks template."""
    marine_cmd = WorldNPC(
        name='Calico "The Bold" Cross',
        faction=NPCFaction.MARINE,
        role=NPCArchetype.MARINE_COMMANDER,
        role_title="Marine Commander",
        occupation="Garrison Commander",
        island_id="Azure Island",
        home_location_id="marine_headquarters",
        location_id="marine_headquarters",
        personality=["Strict", "Disciplined", "Honorable"],
        wealth=150
    )
    await db_manager.db.npcs.insert_one(marine_cmd.to_mongo())

    await db_manager.db.characters.insert_one({
        "_id": "char_pirate_test",
        "name": "Captain Silver",
        "faction": "PIRATE",
        "wealth": 500
    })

    res = await npc_interaction_service.interact(
        character_id="char_pirate_test",
        npc_id=marine_cmd.npc_id,
        action_type="RECRUIT"
    )

    assert res.npc_name == marine_cmd.name
    assert res.trust_delta < 0  # Reprimanded
    # Critical: Must NOT be the old static template!
    assert "Swabbing decks for another captain" not in res.dialogue
    assert len(res.dialogue) > 30


@pytest.mark.asyncio
async def test_incorruptible_marine_bribe_rejection():
    """Verify an incorruptible Marine harshly rebukes bribe attempts dynamically."""
    strict_marine = WorldNPC(
        name="Sergeant Marcus Vane",
        faction=NPCFaction.MARINE,
        role=NPCArchetype.MARINE_SERGEANT,
        role_title="Marine Sergeant",
        occupation="Patrol Leader",
        island_id="Azure Island",
        home_location_id="port_azure_docks",
        location_id="port_azure_docks",
        personality=["Incorruptible", "Vigilant"],
        wealth=30
    )
    await db_manager.db.npcs.insert_one(strict_marine.to_mongo())

    await db_manager.db.characters.insert_one({
        "_id": "char_smuggler_test",
        "name": "Shady Pete",
        "faction": "PIRATE",
        "wealth": 200
    })

    res = await npc_interaction_service.interact(
        character_id="char_smuggler_test",
        npc_id=strict_marine.npc_id,
        action_type="BRIBE_50"
    )

    assert res.trust_delta < 0
    assert res.respect_delta < 0
    assert "rebuked" in res.memory_logged.lower() or "attempted" in res.memory_logged.lower()
    assert len(res.dialogue) > 25

