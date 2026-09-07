from enum import Enum
from typing import Dict, Any, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class TickTier(str, Enum):
    HIGH = "HIGH"       # Fast cycle (combat timers, urgent proximity)
    MEDIUM = "MEDIUM"   # Standard cycle (businesses, weather, NPC routines, mutiny risk)
    LOW = "LOW"         # Slow cycle (market economy, bounties, case decay)


class TickResult(BaseModel):
    tier: TickTier
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    entities_processed: int = 0
    events_emitted: int = 0
    details: Dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
