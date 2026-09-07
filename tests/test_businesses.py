import pytest
from app.game.businesses.business_models import BusinessType
from app.game.businesses.business_service import business_service
from app.game.identity.identity_service import identity_service
from app.services.character_service import character_service
from app.game.models.character import Faction


@pytest.mark.asyncio
async def test_forging_alias_and_evidence_exposure(test_db):
    """Verify alias creation, gold deduction, and evidence accumulation leading to exposure."""
    # Create pirate with gold
    pirate = await character_service.create_character(
        user_id="user_forger_1",
        name="Smuggler Jim",
        faction=Faction.PIRATE
    )
    # Give extra gold for forge fee
    pirate.wealth = 300
    await test_db.characters.update_one({"_id": pirate.character_id}, {"$set": {"wealth": 300}})

    # Forge alias
    alias = await identity_service.create_alias(
        character_id=pirate.character_id,
        alias_name="Marcus The Tailor",
        legal_occupation="Clothier",
        fee=150
    )
    assert alias.alias_name == "Marcus The Tailor"
    assert alias.true_character_id == pirate.character_id
    assert alias.is_exposed() is False

    # Verify fee deducted
    reloaded_pirate = await character_service.get_active_character_by_user("user_forger_1")
    assert reloaded_pirate.wealth == 150

    # Link 3 pieces of evidence to expose
    await identity_service.link_evidence(alias.alias_id, "clue_cloth_fiber_01", suspicion_boost=30)
    await identity_service.link_evidence(alias.alias_id, "clue_ship_manifest_02", suspicion_boost=30)
    exposed_alias = await identity_service.link_evidence(alias.alias_id, "witness_testimony_03", suspicion_boost=30)

    assert exposed_alias.is_exposed() is True
    assert exposed_alias.suspicion_level >= 85


@pytest.mark.asyncio
async def test_business_creation_and_underhand_smuggling(test_db):
    """Verify shell business registration, legitimate trade, and smuggling operations."""
    pirate = await character_service.create_character(
        user_id="user_owner_1",
        name="Baron Flint",
        faction=Faction.PIRATE
    )
    await test_db.characters.update_one({"_id": pirate.character_id}, {"$set": {"wealth": 2000}})

    # Create alias
    alias = await identity_service.create_alias(
        character_id=pirate.character_id,
        alias_name="Lord Archibald",
        legal_occupation="Gentleman Merchant",
        fee=150
    )

    # Buy Business under alias
    biz = await business_service.create_business(
        name="The Gilded Flagon",
        location_id="port_azure_docks",
        owner_character_id=pirate.character_id,
        owner_alias_id=alias.alias_id,
        business_type=BusinessType.TAVERN,
        cost=1000
    )
    assert biz.registered_owner_name == "Lord Archibald"
    assert biz.owner_character_id == pirate.character_id

    # Run legitimate operation
    legit_res = await business_service.run_legitimate_operation(biz.business_id)
    assert legit_res["profit"] > 0

    # Run illegal smuggling operation
    smuggle_res = await business_service.run_underhand_smuggling(biz.business_id, cargo_value=500)
    assert smuggle_res["payout"] == 500
    assert smuggle_res["suspicion"] > 0
    assert smuggle_res["anomaly_score"] > 0.0


@pytest.mark.asyncio
async def test_canonical_starter_business_initialization(test_db):
    """Verify initialization of The Golden Anchor gambling den owned by The Black Tide under Marcus Vale."""
    biz = await business_service.ensure_starter_crew_business(
        crew_id="crew_black_tide_123",
        captain_id="captain_redhook_999"
    )
    assert biz.name == "The Golden Anchor"
    assert biz.registered_owner_name == "Marcus Vale"
    assert "smuggling_front" in biz.hidden_illegal_ops
    assert biz.suspicion_level > 0
    assert biz.calculate_financial_anomaly() > 0.0
