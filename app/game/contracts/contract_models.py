import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from app.game.models.character import Faction


class ContractType(str, Enum):
    DELIVERY = "DELIVERY"
    ESCORT = "ESCORT"
    BOUNTY_HUNT = "BOUNTY_HUNT"
    INFORMATION = "INFORMATION"
    SALVAGE = "SALVAGE"
    ILLEGAL_SMUGGLE = "ILLEGAL_SMUGGLE"


class ContractStatus(str, Enum):
    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorldContract(BaseModel):
    contract_id: str = Field(default_factory=lambda: f"ct_{uuid.uuid4().hex[:10]}")
    title: str
    contract_type: ContractType
    issuer_character_id: str
    issuer_name: str
    issuer_faction: Faction
    target_name: Optional[str] = None
    target_id: Optional[str] = None
    origin_location_id: str = "port_azure_market"
    destination_location_id: Optional[str] = None
    reward_amount: int
    required_item_id: Optional[str] = None
    required_quantity: int = 1
    description: str
    assigned_contractor_id: Optional[str] = None
    status: ContractStatus = ContractStatus.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.contract_id
        return data
