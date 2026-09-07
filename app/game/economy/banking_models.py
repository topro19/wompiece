import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class LoanStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REPAID = "REPAID"
    DEFAULTED = "DEFAULTED"


class LoanRecord(BaseModel):
    loan_id: str = Field(default_factory=lambda: f"loan_{uuid.uuid4().hex[:10]}")
    banker_character_id: str
    borrower_character_id: str
    principal_amount: int
    interest_rate_percent: int = 15  # e.g. 15% flat fee
    total_due: int
    status: LoanStatus = LoanStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    due_at: datetime
    repaid_at: Optional[datetime] = None

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.loan_id
        return data
