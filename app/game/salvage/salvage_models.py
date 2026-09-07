import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SalvageType(str, Enum):
    SUNKEN_SHIPWRECK = "SUNKEN_SHIPWRECK"
    DRIFTING_FLOTSAM = "DRIFTING_FLOTSAM"
    BURIED_CHEST = "BURIED_CHEST"


class SalvageSite(BaseModel):
    site_id: str = Field(default_factory=lambda: f"salv_{uuid.uuid4().hex[:10]}")
    name: str
    location_id: str
    salvage_type: SalvageType
    original_owner_name: Optional[str] = None
    loot_gold: int = 250
    loot_items: List[Dict[str, Any]] = Field(default_factory=list)
    is_claimed: bool = False
    discovered_by_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.site_id
        return data
