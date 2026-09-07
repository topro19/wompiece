from typing import Optional
from pydantic import BaseModel, Field


class NPCReaction(BaseModel):
    """Structured NPC response emitted by the NPC Simulation Engine."""
    npc_name: str
    dialogue: str = Field(description="Spoken dialogue in character")
    internal_thought: str = Field(description="Private motivation, fear, or suspicion not voiced aloud")
    attitude_delta: int = Field(default=0, ge=-10, le=10, description="Shift in trust/friendliness")
    body_language_tell: Optional[str] = Field(default=None, description="Physical cue e.g. hand on hilt, shifting gaze")
    action_taken: Optional[str] = Field(default=None, description="Physical action taken in response")
