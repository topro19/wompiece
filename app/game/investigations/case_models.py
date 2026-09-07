import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.game.events.event_types import EventVisibility


class CaseStatus(str, Enum):
    OPEN = "OPEN"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    WARRANT_REQUESTED = "WARRANT_REQUESTED"
    RAID_AUTHORIZED = "RAID_AUTHORIZED"
    ARRESTED = "ARRESTED"
    CLOSED = "CLOSED"
    UNSOLVED = "UNSOLVED"


class EvidenceType(str, Enum):
    TESTIMONY = "TESTIMONY"
    TRANSACTION_ANOMALY = "TRANSACTION_ANOMALY"
    DOCUMENT = "DOCUMENT"
    OBSERVATION = "OBSERVATION"
    CONTRABAND_SAMPLE = "CONTRABAND_SAMPLE"
    IDENTITY_MATCH = "IDENTITY_MATCH"


class Evidence(BaseModel):
    """Authoritative piece of verified evidence logged in a naval case file."""
    evidence_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    evidence_type: EvidenceType
    title: str
    description: str
    source: str  # Entity, document, or witness
    location_id: str
    reliability: int = Field(default=80, ge=0, le=100)
    authenticity: int = Field(default=90, ge=0, le=100)
    discovered_by_id: str
    visibility: EventVisibility = EventVisibility.CASE_RESTRICTED
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.evidence_id
        return data


class InterrogationRecord(BaseModel):
    """Immutable transcript and analysis of an official Marine questioning session."""
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    marine_id: str
    marine_name: str
    subject_id: str
    subject_name: str
    dialogue_log: List[Dict[str, str]] = Field(default_factory=list)  # [{"speaker": ..., "text": ...}]
    summary: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.record_id
        return data


class Warrant(BaseModel):
    """Legal petition for search, detention, or raid submitted to the AI Marine Head."""
    warrant_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    target_id: str
    target_name: str
    statute_id: str
    requested_action: str  # SEARCH_WARRANT, RAID_WARRANT, DETENTION
    status: str = "PENDING"  # PENDING, AUTHORIZED, DENIED
    ai_verdict: Optional[Dict[str, Any]] = None
    reviewed_by: str = "Fleet Admiral Bartholomew (AI Marine Head)"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.warrant_id
        return data


class MarineCase(BaseModel):
    """Authoritative long-lived investigation docket."""
    case_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_number: int
    title: str
    location_id: str
    assigned_marine_id: str
    assigned_marine_name: str
    status: CaseStatus = CaseStatus.OPEN
    priority: str = "NORMAL"  # LOW, NORMAL, HIGH, CRITICAL
    suspect_ids: List[str] = Field(default_factory=list)
    suspect_names: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    warrant_ids: List[str] = Field(default_factory=list)
    timeline: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.case_id
        return data
