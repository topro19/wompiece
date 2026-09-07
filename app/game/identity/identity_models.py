import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from pydantic import BaseModel, Field


class IdentityAlias(BaseModel):
    """Authoritative representation of a forged legal identity."""
    alias_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    true_character_id: str
    true_name: str
    alias_name: str
    legal_occupation: str = "Merchant"
    legal_faction: str = "Civilian"
    is_active: bool = False
    suspicion_level: int = Field(default=0, ge=0, le=100)
    linked_evidence_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_exposed(self) -> bool:
        """Alias is exposed if enough credible evidence has linked it to the true criminal identity."""
        return len(self.linked_evidence_ids) >= 3 or self.suspicion_level >= 85

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.alias_id
        return data
