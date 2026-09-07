import uuid
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class GameType(str, Enum):
    LIARS_DICE = "LIARS_DICE"
    BLACKJACK = "BLACKJACK"
    HIGH_LOW_DICE = "HIGH_LOW_DICE"


class GamblingOutcome(BaseModel):
    game_type: GameType
    wager: int
    player_won: bool
    payout: int
    details: str
    is_rigged: bool = False
    rigged_detected: bool = False
    suspicion_delta: int = 0


class GamblingTable(BaseModel):
    """Authoritative gambling table hosted inside a tavern or casino business."""
    table_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    business_id: str
    business_name: str
    game_type: GameType = GameType.HIGH_LOW_DICE
    min_wager: int = 10
    max_wager: int = 500
    is_rigged: bool = False
    house_bank: int = 5000

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.table_id
        return data
