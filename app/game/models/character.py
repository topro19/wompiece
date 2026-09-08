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
    island_id: str = "azure_island"
    ship_id: Optional[str] = None
    crew_id: Optional[str] = None
    crew_role: Optional[str] = None
    wanted_level: int = 0
    health: int = 100
    max_health: int = 100
    # Multi-Track Faction & Social Reputation (-100 to +100)
    reputation_marine: int = Field(default=0, ge=-100, le=100)
    reputation_pirate: int = Field(default=0, ge=-100, le=100)
    reputation_merchant: int = Field(default=0, ge=-100, le=100)
    reputation_independent: int = Field(default=0, ge=-100, le=100)
    reputation_civilian: int = Field(default=0, ge=-100, le=100)
    reputation_criminal: int = Field(default=0, ge=-100, le=100)
    # Behavioral Traits inferred from player agency (e.g. generous, violent, trustworthy, cautious)
    behavioral_traits: Dict[str, int] = Field(default_factory=dict)
    long_term_ambition: Optional[str] = None
    personal_motivations: List[str] = Field(default_factory=list)
    specialization: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    died_at: Optional[datetime] = None

    def is_playable(self) -> bool:
        """Enforces the true one-life invariant."""
        return self.status == CharacterStatus.ALIVE

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.character_id
        return data
