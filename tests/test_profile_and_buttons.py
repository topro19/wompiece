import pytest
from app.database.connection import db_manager
from app.services.character_service import character_service
from app.game.models.character import Faction
from app.game.director.reputation_service import reputation_service
from app.game.director.discovery_service import discovery_service


@pytest.mark.asyncio
async def test_reputation_methods_and_profile_data():
    """Verify get_all_reputations and get_reputation_title work cleanly without AttributeError."""
    await db_manager.connect(force_mock=True)
    char = await character_service.create_character("user_prof_test", "Captain Profile", Faction.PIRATE)
    
    reps = await reputation_service.get_all_reputations(char.character_id)
    assert isinstance(reps, dict)
    assert "Pirates" in reps
    assert "Marines" in reps
    
    title = reputation_service.get_reputation_title(50)
    assert title == "Trusted Ally"
    
    title_bad = reputation_service.get_reputation_title(-50)
    assert title_bad == "Hated Outlaw"


@pytest.mark.asyncio
async def test_discovery_resolution_caching_idempotent():
    """Verify that clicking/resolving discovery is idempotent and caches resolution_summary."""
    await db_manager.connect(force_mock=True)
    char = await character_service.create_character("user_cache_test", "Clicker Joe", Faction.MERCHANT)
    
    disc = await discovery_service.explore_location(char.character_id, "port_azure_docks")
    
    res1 = await discovery_service.resolve_discovery_action(
        character_id=char.character_id,
        discovery_id=disc.discovery_id,
        action_choice=disc.suggested_actions[0]
    )
    assert res1["success"] is True
    assert "narrative" in res1
    
    res2 = await discovery_service.resolve_discovery_action(
        character_id=char.character_id,
        discovery_id=disc.discovery_id,
        action_choice=disc.suggested_actions[0]
    )
    assert res2["success"] is True
    assert res2["narrative"] == res1["narrative"]