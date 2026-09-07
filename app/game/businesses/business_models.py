import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class BusinessType(str, Enum):
    TAVERN = "TAVERN"
    GAMBLING_DEN = "GAMBLING_DEN"
    SHIPYARD = "SHIPYARD"
    WAREHOUSE = "WAREHOUSE"
    TRADING_POST = "TRADING_POST"
    BLACK_MARKET = "BLACK_MARKET"


class Business(BaseModel):
    """Authoritative persistent commercial establishment with legitimate and criminal fronts."""
    business_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    location_id: str
    owner_character_id: str
    owner_name: str
    owner_alias_id: Optional[str] = None  # Shell ownership via fake identity
    registered_owner_name: str  # Displayed on public government registry
    crew_id: Optional[str] = None
    business_type: BusinessType = BusinessType.TAVERN
    legitimacy_score: int = Field(default=80, ge=0, le=100)
    daily_revenue: int = 0
    daily_expenses: int = 25
    suspicion_level: int = Field(default=0, ge=0, le=100)
    hidden_illegal_ops: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def calculate_financial_anomaly(self) -> float:
        """
        Determines if revenue/expense patterns deviate suspiciously from standard civilian trade.
        High financial anomalies create audit leads for Marine investigators.
        """
        base_expected_revenue = {
            BusinessType.TAVERN: 120,
            BusinessType.GAMBLING_DEN: 250,
            BusinessType.WAREHOUSE: 180,
            BusinessType.TRADING_POST: 200,
            BusinessType.SHIPYARD: 300,
            BusinessType.BLACK_MARKET: 400
        }.get(self.business_type, 150)

        if self.daily_revenue <= base_expected_revenue:
            return 0.0

        # Discrepancy ratio
        ratio = (self.daily_revenue - base_expected_revenue) / base_expected_revenue
        return min(1.0, round(ratio * 0.4, 2))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.business_id
        return data
