import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from app.game.models.character import Faction


class IntelCategory(str, Enum):
    PIRATE_MOVEMENT = "PIRATE_MOVEMENT"
    MARINE_PATROL = "MARINE_PATROL"
    CONTRABAND_SHIPMENT = "CONTRABAND_SHIPMENT"
    WANTED_FUGITIVE = "WANTED_FUGITIVE"
    BUSINESS_ANOMALY = "BUSINESS_ANOMALY"


class IntelReport(BaseModel):
    intel_id: str = Field(default_factory=lambda: f"intel_{uuid.uuid4().hex[:10]}")
    category: IntelCategory
    title: str
    detail: str
    source_character_id: str
    seller_name: str
    reliability: float = Field(default=0.85, ge=0.0, le=1.0)
    is_truth: bool = True
    target_faction: Optional[Faction] = None
    market_value: int = 100
    buyer_character_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.intel_id
        return data
