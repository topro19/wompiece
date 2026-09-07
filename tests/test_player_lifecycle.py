import pytest
from app.game.models.character import CharacterStatus, Faction
from app.services.character_service import character_service
from app.game.models.death import permadeath_service, CauseOfDeath


@pytest.mark.asyncio
async def test_character_creation_and_starter_kit(test_db):
    """Verify player character creation with faction-specific starter equipment."""
    char = await character_service.create_character(
        user_id="user_discord_001",
        name="Edward Teach",
        faction=Faction.PIRATE
    )

    assert char.name == "Edward Teach"
    assert char.faction == Faction.PIRATE
    assert char.rank == "Deckhand"
    assert char.wealth == 100
    assert char.status == CharacterStatus.ALIVE
    assert len(char.inventory) == 3
    assert any(item["item_id"] == "rusty_cutlass" for item in char.inventory)

    # Active character retrieval
    retrieved = await character_service.get_active_character_by_user("user_discord_001")
    assert retrieved is not None
    assert retrieved.character_id == char.character_id


@pytest.mark.asyncio
async def test_one_life_prevents_duplicate_creation_while_alive(test_db):
    """Under One-Life rules, a living player cannot create another character."""
    await character_service.create_character(
        user_id="user_discord_002",
        name="Captain Morgan",
        faction=Faction.PIRATE
    )

    with pytest.raises(ValueError, match="already have an active living character"):
        await character_service.create_character(
            user_id="user_discord_002",
            name="New Guy",
            faction=Faction.MARINE
        )


@pytest.mark.asyncio
async def test_player_can_create_new_character_after_permadeath(test_db):
    """After permanent death, a player may create a fresh new independent character."""
    user_id = "user_discord_003"
    char1 = await character_service.create_character(
        user_id=user_id,
        name="Brave Pirate",
        faction=Faction.PIRATE
    )

    # Character dies permanently
    await permadeath_service.execute_permadeath(
        character_id=char1.character_id,
        cause=CauseOfDeath.COMBAT,
        location_id="port_azure_docks"
    )

    # User no longer has an active living character
    assert await character_service.get_active_character_by_user(user_id) is None

    # Now the user can create a brand new character
    char2 = await character_service.create_character(
        user_id=user_id,
        name="Revenge Seeker",
        faction=Faction.MARINE
    )
    assert char2.character_id != char1.character_id
    assert char2.status == CharacterStatus.ALIVE
    assert char2.faction == Faction.MARINE


@pytest.mark.asyncio
async def test_character_movement_validation(test_db):
    """Verify graph-based authoritative movement and rejection of invalid teleportation."""
    char = await character_service.create_character(
        user_id="user_discord_004",
        name="Cartographer",
        faction=Faction.INDEPENDENT,
        starting_location_id="port_azure_docks"
    )

    # Valid step: port_azure_docks -> the_crimson_parrot
    dest = await character_service.move_character(char.character_id, "the_crimson_parrot")
    assert dest.location_id == "the_crimson_parrot"

    # Verify updated DB state
    updated = await character_service.get_active_character_by_user("user_discord_004")
    assert updated.location_id == "the_crimson_parrot"

    # Invalid step: the_crimson_parrot -> governors_mansion (not connected!)
    with pytest.raises(ValueError, match="not connected"):
        await character_service.move_character(char.character_id, "governors_mansion")
