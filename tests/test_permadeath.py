import pytest
from app.database.connection import db_manager
from app.game.models.character import Character, CharacterStatus, Faction
from app.game.models.death import permadeath_service, CauseOfDeath
from app.game.events.event_types import EventType


@pytest.mark.asyncio
async def test_permadeath_lifecycle(test_db):
    """Verify permanent character death state transition, history archive, and death event."""
    db = db_manager.db

    # Create user and active character
    user_id = "discord_user_12345"
    char = Character(
        user_id=user_id,
        name="Silver Jim",
        faction=Faction.PIRATE,
        bounty=50000,
        wealth=1200
    )
    await db.characters.insert_one(char.to_mongo())
    await db.users.insert_one({
        "_id": user_id,
        "active_character_id": char.character_id,
        "deceased_character_ids": []
    })

    # Execute permadeath
    death_rec = await permadeath_service.execute_permadeath(
        character_id=char.character_id,
        cause=CauseOfDeath.EXECUTION,
        location_id="port_azure_scaffold",
        killer_name="Admiral Drake",
        related_case_id="case_777"
    )

    assert death_rec is not None
    assert death_rec.character_name == "Silver Jim"

    # Verify character is marked permanently DEAD
    char_in_db = await db.characters.find_one({"_id": char.character_id})
    assert char_in_db["status"] == CharacterStatus.DEAD.value
    assert char_in_db["health"] == 0
    assert char_in_db["died_at"] is not None

    # Verify user's active character is cleared and added to deceased history
    user_in_db = await db.users.find_one({"_id": user_id})
    assert user_in_db["active_character_id"] is None
    assert char.character_id in user_in_db["deceased_character_ids"]

    # Verify death event in event log
    death_events = await db.events.find({"event_type": EventType.DEATH_EVENT.value}).to_list(length=10)
    assert len(death_events) == 1
    assert death_events[0]["state_delta"]["victim_name"] == "Silver Jim"

    # Verify character cannot be killed again
    with pytest.raises(ValueError, match="already permanently dead"):
        await permadeath_service.execute_permadeath(
            character_id=char.character_id,
            cause=CauseOfDeath.COMBAT,
            location_id="port_azure_scaffold"
        )
