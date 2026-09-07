from typing import List, Optional
from pydantic import BaseModel, Field


class MarineHeadDecision(BaseModel):
    """Structured verdict from the AI Marine Head evaluating a warrant or penalty request."""
    decision: str = Field(description="AUTHORIZED, DENIED, or REQUEST_MORE_EVIDENCE")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score based on presented evidence")
    reason: str = Field(description="Legal rationale citing case circumstances and statutory thresholds")
    statute_analyzed: str = Field(description="The primary law or statute assessed")
    required_evidence: List[str] = Field(default_factory=list, description="Missing clues or proof required if not authorized")
    authorized_actions: List[str] = Field(default_factory=list, description="Specific actions legally permitted (e.g. SEARCH, RAID, DETENTION)")
