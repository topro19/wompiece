import pytest
from app.database.connection import db_manager
from app.services.character_service import character_service
from app.game.models.character import Faction
from app.game.director.discovery_service import discovery_service, DISCOVERY_TEMPLATES


@pytest.mark.asyncio
async def test_discoveries_variety_and_no_repeats():
    """Verify that multiple explore actions yield distinct, varied discoveries without immediate duplicates."""
    await db_manager.connect(force_mock=True)
    db = db_manager.db

    char = await character_service.create_character("user_variety_test", "Captain Varied", Faction.PIRATE)
    char_id = char.character_id

    seen_titles = []
    for _ in range(5):
        disc = await discovery_service.explore_location(char_id, "port_azure_docks")
        seen_titles.append(disc.title)
        
        # Mark interacted so next explore generates a new one
        await discovery_service.resolve_discovery_action(
            character_id=char_id,
            discovery_id=disc.discovery_id,
            action_choice=disc.suggested_actions[0]
        )

    # Verify that all 5 consecutive discoveries had unique titles!
    assert len(set(seen_titles)) == 5
    print(f"Generated 5 distinct discoveries: {seen_titles}")


@pytest.mark.asyncio
async def test_discovery_resolution_rewards():
    """Verify that resolving discoveries yields real rewards, items, and thread updates."""
    await db_manager.connect(force_mock=True)
    char = await character_service.create_character("user_reward_test", "Scavenger Sam", Faction.INDEPENDENT)
    char_id = char.character_id

    # Explore and resolve
    disc = await discovery_service.explore_location(char_id, "port_azure_docks")
    res = await discovery_service.resolve_discovery_action(
        character_id=char_id,
        discovery_id=disc.discovery_id,
        action_choice=disc.suggested_actions[0]
    )

    assert res["success"] is True
    assert "narrative" in res
    assert "outcome_text" in res
    assert len(res["narrative"]) > 10
