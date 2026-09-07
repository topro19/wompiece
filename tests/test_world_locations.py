import pytest
from app.game.world.location import location_service
from app.game.world.time import world_time_service


def test_location_graph_connectivity():
    """Verify default location network and security ratings."""
    docks = location_service.get_location("port_azure_docks")
    assert docks is not None
    assert docks.is_port is True
    assert docks.security_level == 3

    parrot = location_service.get_location("the_crimson_parrot")
    assert parrot is not None
    assert parrot.security_level == 1
    assert "gambling_den" in parrot.facilities

    # Check connection reciprocity / validity
    assert location_service.can_move("port_azure_docks", "the_crimson_parrot")
    assert location_service.can_move("the_crimson_parrot", "smugglers_cove")
    assert not location_service.can_move("smugglers_cove", "marine_headquarters")


@pytest.mark.asyncio
async def test_world_time_clock(test_db):
    """Verify persistent clock advancement."""
    initial_clock = await world_time_service.get_world_time()
    assert initial_clock.day == 1

    advanced = await world_time_service.advance_time(minutes=45)
    assert advanced.minute == (initial_clock.minute + 45) % 60

    formatted = world_time_service.format_clock(advanced)
    assert "Day 1" in formatted
