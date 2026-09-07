import pytest
from app.game.models.character import Faction
from app.services.character_service import character_service
from app.game.investigations.corruption_service import corruption_service


@pytest.mark.asyncio
async def test_bribery_and_undercover_sting_operation(test_db):
    """Verify that bribing an officer under an undercover sting operation generates audit evidence."""
    # Create pirate and marine
    pirate = await character_service.create_character(
        user_id="briber_user_1",
        name="Silver Tongue Sam",
        faction=Faction.PIRATE
    )
    # Give gold
    await test_db.characters.update_one({"_id": pirate.character_id}, {"$set": {"wealth": 1000}})

    marine = await character_service.create_character(
        user_id="corrupt_marine_1",
        name="Ensign Greedy",
        faction=Faction.MARINE
    )

    # Launch undercover sting operation on marine
    op = await corruption_service.launch_undercover_operation(
        target_marine_id=marine.character_id,
        code_name="OPERATION BLACK ANCHOR"
    )
    assert op.code_name == "OPERATION BLACK ANCHOR"

    # Attempt bribe
    res = await corruption_service.attempt_bribe(
        briber_character_id=pirate.character_id,
        target_marine_id=marine.character_id,
        amount=400,
        reason="Forget about the cargo on Dock 4"
    )

    assert res["success"] is True
    assert res["secretly_recorded"] is True

    # Verify money transferred via ledger
    reloaded_pirate = await character_service.get_active_character_by_user("briber_user_1")
    reloaded_marine = await character_service.get_active_character_by_user("corrupt_marine_1")
    assert reloaded_pirate.wealth == 600
    assert reloaded_marine.wealth == 550  # Started with 150 + 400 = 550

    # Verify IA evidence was generated in DB
    ev = await test_db.evidence.find_one({"title": {"$regex": "Secret Payment"}})
    assert ev is not None
    assert "400" in ev["description"]
