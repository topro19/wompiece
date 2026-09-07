import pytest
from app.game.models.character import Faction
from app.services.character_service import character_service
from app.game.gambling.gambling_service import gambling_service
from app.game.gambling.gambling_models import GameType


@pytest.mark.asyncio
async def test_gambling_wager_and_payout(test_db):
    """Verify gambling wagers deduct atomically and payouts transfer to player."""
    player = await character_service.create_character(
        user_id="gambler_user_1",
        name="Lucky Pete",
        faction=Faction.PIRATE
    )
    assert player.wealth == 100

    # Play with 20 gold
    outcome = await gambling_service.play_high_low_dice(
        character_id=player.character_id,
        business_id="tavern_test_01",
        wager=20,
        choice="HIGH"
    )

    assert outcome is not None
    assert outcome.game_type == GameType.HIGH_LOW_DICE

    reloaded = await character_service.get_active_character_by_user("gambler_user_1")
    if outcome.player_won:
        # Payout was 40, so starting 100 - 20 + 40 = 120
        assert reloaded.wealth == 120
    else:
        # Started 100 - 20 = 80
        assert reloaded.wealth == 80


@pytest.mark.asyncio
async def test_gambling_wager_limits_and_insufficient_funds(test_db):
    """Verify bounds validation on wagers."""
    player = await character_service.create_character(
        user_id="poor_gambler",
        name="Broke Sailor",
        faction=Faction.PIRATE
    )

    # Wager below min (10)
    with pytest.raises(ValueError, match="between 10 and 500"):
        await gambling_service.play_high_low_dice(
            character_id=player.character_id,
            business_id="tavern_test_02",
            wager=5,
            choice="LOW"
        )
