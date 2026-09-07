import pytest
from app.game.crews.crew_models import CrewRole
from app.game.crews.crew_service import crew_service
from app.services.character_service import character_service
from app.game.models.character import Faction


@pytest.mark.asyncio
async def test_canonical_ai_crew_initialization(test_db):
    """Verify initialization of The Black Tide led by AI Captain Redhook."""
    crew = await crew_service.ensure_starter_ai_crews()
    assert crew.name == "The Black Tide"
    assert crew.captain_name == "Captain Redhook"
    assert crew.captain_is_ai is True
    assert crew.treasury == 5000

    # Verify initial AI officers
    assert len(crew.members) >= 3
    roles = [m.role for m in crew.members.values()]
    assert CrewRole.CAPTAIN in roles
    assert CrewRole.NAVIGATOR in roles
    assert CrewRole.DOCTOR in roles


@pytest.mark.asyncio
async def test_real_player_joining_and_leaving_ai_crew(test_db):
    """Verify a real player can join an AI captain's crew and later leave."""
    # Ensure crew exists
    crew = await crew_service.ensure_starter_ai_crews()

    # Create real player
    player = await character_service.create_character(
        user_id="user_player_99",
        name="Jack Rackham",
        faction=Faction.PIRATE
    )

    # Join crew
    updated_crew = await crew_service.join_crew(crew.crew_id, player.character_id, role=CrewRole.DECKHAND)
    assert player.character_id in updated_crew.members
    assert updated_crew.members[player.character_id].role == CrewRole.DECKHAND

    # Verify character document is updated
    updated_char = await character_service.get_active_character_by_user("user_player_99")
    assert updated_char.crew_id == crew.crew_id
    assert updated_char.crew_role == CrewRole.DECKHAND.value

    # Leave crew
    success = await crew_service.leave_crew(player.character_id)
    assert success is True

    char_after_leave = await character_service.get_active_character_by_user("user_player_99")
    assert char_after_leave.crew_id is None
    assert char_after_leave.crew_role is None


@pytest.mark.asyncio
async def test_crew_treasury_deposit(test_db):
    """Verify player can deposit funds into crew treasury using the ledger."""
    crew = await crew_service.ensure_starter_ai_crews()
    player = await character_service.create_character(
        user_id="user_player_100",
        name="Rich Deckhand",
        faction=Faction.PIRATE
    )

    await crew_service.join_crew(crew.crew_id, player.character_id)

    # Deposit 50 gold
    initial_treasury = crew.treasury
    await crew_service.deposit_to_treasury(crew.crew_id, player.character_id, 50)

    reloaded_crew = await crew_service.get_crew(crew.crew_id)
    assert reloaded_crew.treasury == initial_treasury + 50

    reloaded_player = await character_service.get_active_character_by_user("user_player_100")
    assert reloaded_player.wealth == 50  # Started with 100 - 50 = 50


@pytest.mark.asyncio
async def test_mutiny_risk_calculation(test_db):
    """Verify mutiny risk dynamics based on crew satisfaction and captain authority."""
    crew = await crew_service.ensure_starter_ai_crews()
    initial_risk = crew.calculate_mutiny_risk()

    # Now simulate high dissatisfaction across crew
    for member in crew.members.values():
        member.dissatisfaction = 90
        member.loyalty = 20
    crew.captain_authority = 30

    elevated_risk = crew.calculate_mutiny_risk()
    assert elevated_risk > initial_risk
    assert elevated_risk > 50.0
