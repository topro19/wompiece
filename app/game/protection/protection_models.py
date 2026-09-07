import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from app.game.models.character import Faction


class ProtectionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    BREACHED = "BREACHED"


class ProtectedEntityType(str, Enum):
    BUSINESS = "BUSINESS"
    WAREHOUSE = "WAREHOUSE"
    SHIP = "SHIP"
    INDIVIDUAL = "INDIVIDUAL"


class ProtectionContract(BaseModel):
    contract_id: str = Field(default_factory=lambda: f"prot_{uuid.uuid4().hex[:10]}")
    merchant_character_id: str
    merchant_name: str
    entity_type: ProtectedEntityType
    entity_id: str
    entity_name: str
    protector_faction: Faction
    protector_id: str  # crew_id, organization_id, or individual mercenary id
    protector_name: str
    weekly_dues: int = 150
    conditions: str = "Defense against unsanctioned raids, robberies, and piracy."
    status: ProtectionStatus = ProtectionStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.contract_id
        return data
