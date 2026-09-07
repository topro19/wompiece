import pytest
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility


@pytest.mark.asyncio
async def test_event_publishing_and_persistence(test_db):
    """Verify events are saved immutably to the events collection."""
    received = []

    async def sample_handler(evt: WorldEvent):
        received.append(evt)

    event_bus.subscribe(EventType.PLAYER_CREATED, sample_handler)

    test_event = WorldEvent(
        event_type=EventType.PLAYER_CREATED,
        actor_id="pirate_001",
        visibility=EventVisibility.PUBLIC,
        metadata={"name": "Blackbeard"}
    )
    await event_bus.publish(test_event)

    assert len(received) == 1
    assert received[0].actor_id == "pirate_001"

    # Verify persistent query
    history = await event_bus.get_history(event_type=EventType.PLAYER_CREATED)
    assert len(history) >= 1
    assert history[0]["actor_id"] == "pirate_001"
