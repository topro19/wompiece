import pytest
from app.database.connection import db_manager
from app.game.models.character import Character, CharacterStatus, Faction
from app.game.crews.crew_models import Crew, CrewMember, CrewRole
from app.game.businesses.business_models import Business, BusinessType
from app.game.simulation.scheduler_service import simulation_scheduler
from app.game.simulation.scheduler_models import TickTier
from app.game.world.time import world_time_service


@pytest.mark.asyncio
async def test_simulation_ticks_execution():
    """Validates HIGH, MEDIUM, and LOW priority ticks modifying world state authoritatively."""
    db = db_manager.db
    await db.characters.delete_many({})
    await db.crews.delete_many({})
    await db.businesses.delete_many({})
    await db.world_state.delete_many({})

    # 1. Setup World Clock
    await world_time_service.advance_time(minutes=0)

    # 2. Seed a business
    biz = Business(
        business_id="biz_dock_tavern",
        name="Dockside Alehouse",
        business_type=BusinessType.TAVERN,
        location_id="port_azure_docks",
        owner_character_id="char_marcus",
        owner_name="Marcus Vale",
        registered_owner_name="Marcus Vale",
        daily_revenue=100
    )
    await db.businesses.insert_one(biz.to_mongo())

    # 3. Seed a crew with high dissatisfaction to test mutiny triggering
    mutinous_crew = Crew(
        name="The Salty Dogs",
        captain_id="capt_rogers",
        captain_name="Captain Rogers",
        captain_authority=10,  # very low authority
        home_port="skull_rock_anchorage",
        members={
            "rebel1": CrewMember(
                character_id="rebel1",
                character_name="Barnaby",
                role=CrewRole.QUARTERMASTER,
                loyalty=10,
                dissatisfaction=90
            ),
            "rebel2": CrewMember(
                character_id="rebel2",
                character_name="Grub",
                role=CrewRole.DECKHAND,
                loyalty=15,
                dissatisfaction=85
            )
        }
    )
    await db.crews.insert_one(mutinous_crew.to_mongo())

    # 4. Seed Captain Redhook and a wanted outlaw
    redhook = Character(
        name="Captain Redhook",
        is_ai=True,
        faction=Faction.PIRATE,
        location_id="skull_rock_anchorage"
    )
    outlaw = Character(
        name="Smuggler Jim",
        faction=Faction.PIRATE,
        wanted_level=2,
        bounty=100
    )
    await db.characters.insert_one(redhook.to_mongo())
    await db.characters.insert_one(outlaw.to_mongo())

    # --- Test HIGH Tick ---
    high_res = await simulation_scheduler.tick_high()
    assert high_res.tier == TickTier.HIGH
    assert high_res.events_emitted >= 1

    # --- Test MEDIUM Tick ---
    med_res = await simulation_scheduler.tick_medium()
    assert med_res.tier == TickTier.MEDIUM
    assert med_res.entities_processed >= 3  # biz, crew, redhook
    assert med_res.details["mutinies_triggered"] >= 1  # Salty Dogs mutiny risk >= 75%
    
    # Verify business earned revenue
    updated_biz = await db.businesses.find_one({"_id": biz.business_id})
    assert updated_biz["daily_revenue"] > 100

    # --- Test LOW Tick ---
    low_res = await simulation_scheduler.tick_low()
    assert low_res.tier == TickTier.LOW
    assert low_res.details["bounties_escalated"] >= 1

    # Verify outlaw's bounty increased
    updated_outlaw = await db.characters.find_one({"_id": outlaw.character_id})
    assert updated_outlaw["bounty"] > 100


@pytest.mark.asyncio
async def test_advance_time_multi_cycle():
    """Validates administrative fast-forwarding of time triggering multi-tier cycles."""
    db = db_manager.db

    # Advance 25 hours: should trigger medium tick and low tick
    results = await simulation_scheduler.advance_time(hours=25.0)
    assert len(results) == 2
    assert results[0].tier == TickTier.MEDIUM
    assert results[1].tier == TickTier.LOW

    # Check that world clock has progressed days
    clock = await world_time_service.get_world_time()
    assert clock.day >= 2
