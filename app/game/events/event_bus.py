import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable, Awaitable
from pydantic import BaseModel, Field
from app.game.events.event_types import EventType, EventVisibility
from app.database.connection import db_manager
from app.services.logger import logger


class WorldEvent(BaseModel):
    """Immutable record of an authoritative event in the game world."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    actor_id: Optional[str] = None
    target_ids: List[str] = Field(default_factory=list)
    location_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    visibility: EventVisibility = EventVisibility.PUBLIC
    state_delta: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    related_case_id: Optional[str] = None
    related_transaction_id: Optional[str] = None

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.event_id
        return data


class EventBus:
    """Central event dispatcher and persistence sink for the game world."""

    def __init__(self):
        self._handlers: Dict[EventType, List[Callable[[WorldEvent], Awaitable[None]]]] = {}

    def subscribe(self, event_type: EventType, handler: Callable[[WorldEvent], Awaitable[None]]):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(self, event: WorldEvent) -> WorldEvent:
        """Persists the event immutably to the database and notifies subscribers."""
        db = db_manager.db
        await db.events.insert_one(event.to_mongo())
        logger.info(f"[EVENT] [{event.event_type.value}] id={event.event_id} actor={event.actor_id} vis={event.visibility.value}")

        # Dispatch to in-memory listeners
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Error in event handler for {event.event_type}: {e}", exc_info=True)

        return event

    async def get_history(
        self,
        event_type: Optional[EventType] = None,
        actor_id: Optional[str] = None,
        case_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Retrieves chronological events from the persistent event log."""
        db = db_manager.db
        query: Dict[str, Any] = {}
        if event_type:
            query["event_type"] = event_type.value
        if actor_id:
            query["actor_id"] = actor_id
        if case_id:
            query["related_case_id"] = case_id

        cursor = db.events.find(query).sort("timestamp", -1).limit(limit)
        events = await cursor.to_list(length=limit)
        return events


event_bus = EventBus()
