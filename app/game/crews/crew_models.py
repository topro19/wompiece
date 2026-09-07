import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class CrewRole(str, Enum):
    CAPTAIN = "CAPTAIN"
    VICE_CAPTAIN = "VICE_CAPTAIN"
    QUARTERMASTER = "QUARTERMASTER"
    NAVIGATOR = "NAVIGATOR"
    GUNNER = "GUNNER"
    DOCTOR = "DOCTOR"
    BOARDING_TEAM = "BOARDING_TEAM"
    DECKHAND = "DECKHAND"


class CrewMember(BaseModel):
    """Authoritative representation of a single crew member (Real Player or AI NPC)."""
    character_id: str
    character_name: str
    is_ai: bool = False
    role: CrewRole = CrewRole.DECKHAND
    loyalty: int = Field(default=75, ge=0, le=100)
    trust_in_captain: int = Field(default=75, ge=0, le=100)
    influence: int = Field(default=20, ge=0, le=100)
    dissatisfaction: int = Field(default=10, ge=0, le=100)
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Crew(BaseModel):
    """Authoritative organization model for mixed real-player and AI pirate crews."""
    crew_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    captain_id: str
    captain_name: str
    captain_is_ai: bool = False
    treasury: int = 0
    morale: int = Field(default=80, ge=0, le=100)
    captain_authority: int = Field(default=85, ge=0, le=100)
    home_port: str = "port_azure_docks"
    ship_id: Optional[str] = None
    members: Dict[str, CrewMember] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def calculate_mutiny_risk(self) -> float:
        """
        Deterministic calculation of mutiny risk based on:
        - Captain authority
        - Average crew dissatisfaction
        - Average loyalty of high-influence officers
        """
        if not self.members:
            return 0.0

        total_dissatisfaction = sum(m.dissatisfaction for m in self.members.values())
        avg_dissatisfaction = total_dissatisfaction / len(self.members)

        total_loyalty = sum(m.loyalty for m in self.members.values())
        avg_loyalty = total_loyalty / len(self.members)

        # Risk scales with dissatisfaction and inversely with captain authority & loyalty
        base_risk = (avg_dissatisfaction * 1.2) + (100 - avg_loyalty) * 0.5 - (self.captain_authority * 0.4)
        return max(0.0, min(100.0, round(base_risk, 1)))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.crew_id
        # Convert member datetimes/models to dicts
        data["members"] = {k: v.model_dump() for k, v in self.members.items()}
        return data
