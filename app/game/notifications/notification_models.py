import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class NotificationPriority(str, Enum):
    LOW = "LOW"            # Background event (no ping, silent ledger/timeline)
    NORMAL = "NORMAL"      # Ambient world update (sent to bot log, no @mention)
    HIGH = "HIGH"          # Relevant NPC seeks player (pings <@user_id>)
    CRITICAL = "CRITICAL"  # Immediate raid, ambush, or execution threat (urgent <@user_id> ping)


class WorldMessage(BaseModel):
    """Authoritative asynchronous communication from an NPC, crew, or faction to a character."""
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:10]}")
    character_id: str
    user_id: str
    sender_name: str
    sender_type: str = "NPC"  # NPC, CREW, MARINE, MERCHANT, PIRATE
    location_name: str = "Port Azure"
    content: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    requires_response: bool = False
    options: List[str] = Field(default_factory=list)
    opportunity_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_resolved: bool = False

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.message_id
        return data


class WorldTimelineEvent(BaseModel):
    """Chronological event entry recording living world movements."""
    event_id: str = Field(default_factory=lambda: f"time_{uuid.uuid4().hex[:8]}")
    character_id: str
    event_text: str
    category: str = "GENERAL"  # MESSAGE, OPPORTUNITY, TRAVEL, WORLD_SHIFT, THREAT
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.event_id
        return data


class OfflineRecap(BaseModel):
    """Structured summary presented to a player returning to the persistent world."""
    character_name: str
    unread_messages_count: int
    pending_opportunities_count: int
    timeline_highlights: List[str] = Field(default_factory=list)
    urgent_alerts: List[str] = Field(default_factory=list)
