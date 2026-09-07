import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CharacterStatus(str, Enum):
    ALIVE = "ALIVE"
    DEAD = "DEAD"
    IMPRISONED = "IMPRISONED"


class Faction(str, Enum):
    PIRATE = "PIRATE"
    MARINE = "MARINE"
    MERCHANT = "MERCHANT"
    INDEPENDENT = "INDEPENDENT"


class Character(BaseModel):
    """The central entity model. Characters have exactly ONE LIFE."""
    character_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None  # None for AI characters
    name: str
    is_ai: bool = False
    status: CharacterStatus = CharacterStatus.ALIVE
    faction: Faction = Faction.PIRATE
    rank: str = "Recruit"
    bounty: int = 0
    infamy: int = 0
    wealth: int = 100  # Starting gold
    inventory: List[Dict[str, Any]] = Field(default_factory=list)
    location_id: str = "port_azure"
    ship_id: Optional[str] = None
    crew_id: Optional[str] = None
    crew_role: Optional[str] = None
    wanted_level: int = 0
    health: int = 100
    max_health: int = 100
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    died_at: Optional[datetime] = None

    def is_playable(self) -> bool:
        """Enforces the true one-life invariant."""
        return self.status == CharacterStatus.ALIVE

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.character_id
        return data
