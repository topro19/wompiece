import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class GoalTier(str, Enum):
    SHORT_TERM = "SHORT_TERM"
    MEDIUM_TERM = "MEDIUM_TERM"
    LONG_TERM = "LONG_TERM"


class GoalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABANDONED = "ABANDONED"


class PlayerGoal(BaseModel):
    goal_id: str = Field(default_factory=lambda: f"goal_{uuid.uuid4().hex[:10]}")
    character_id: str
    tier: GoalTier
    title: str
    description: str
    target_entity_id: Optional[str] = None
    status: GoalStatus = GoalStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    reward_notes: Optional[str] = None

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.goal_id
        return data


class OpportunityType(str, Enum):
    CRIME_DISCOVERY = "CRIME_DISCOVERY"
    NPC_REQUEST = "NPC_REQUEST"
    RUMOR = "RUMOR"
    FACTION_CONFLICT = "FACTION_CONFLICT"
    JOB_OFFER = "JOB_OFFER"
    MYSTERY = "MYSTERY"
    SOCIAL_ENCOUNTER = "SOCIAL_ENCOUNTER"
    TRADE_LEAD = "TRADE_LEAD"


class OpportunityUrgency(str, Enum):
    URGENT = "URGENT"
    MODERATE = "MODERATE"
    LEISURELY = "LEISURELY"
    TIMED = "TIMED"


class OpportunityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISCOVERED = "DISCOVERED"
    IGNORED = "IGNORED"
    RESOLVED = "RESOLVED"
    EXPIRED = "EXPIRED"


class Opportunity(BaseModel):
    opportunity_id: str = Field(default_factory=lambda: f"opp_{uuid.uuid4().hex[:10]}")
    character_id: str
    title: str
    description: str
    opportunity_type: OpportunityType
    location_id: str
    urgency: OpportunityUrgency = OpportunityUrgency.MODERATE
    related_npc_name: Optional[str] = None
    suggested_actions: List[str] = Field(default_factory=list)
    consequence_summary: Optional[str] = None
    is_hidden: bool = False
    reward_preview: Optional[str] = None
    status: OpportunityStatus = OpportunityStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.opportunity_id
        return data


class StoryThreadStatus(str, Enum):
    ACTIVE = "ACTIVE"
    STALLED = "STALLED"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    MERGED = "MERGED"


class StoryThread(BaseModel):
    thread_id: str = Field(default_factory=lambda: f"th_{uuid.uuid4().hex[:10]}")
    title: str
    status: StoryThreadStatus = StoryThreadStatus.ACTIVE
    summary: str
    known_facts: List[str] = Field(default_factory=list)
    unknown_questions: List[str] = Field(default_factory=list)
    player_involvement: str = "Observer"
    related_npc_names: List[str] = Field(default_factory=list)
    history: List[str] = Field(default_factory=list)
    merged_into_thread_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.thread_id
        return data


class RelationshipLevel(str, Enum):
    STRANGER = "STRANGER"
    ACQUAINTANCE = "ACQUAINTANCE"
    FRIENDLY = "FRIENDLY"
    TRUSTED = "TRUSTED"
    FRIEND = "FRIEND"
    CLOSE_FRIEND = "CLOSE_FRIEND"
    LOYAL_ALLY = "LOYAL_ALLY"
    RIVAL = "RIVAL"
    HOSTILE = "HOSTILE"
    BITTER_ENEMY = "BITTER_ENEMY"


class NPCMemory(BaseModel):
    memory_id: str = Field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:8]}")
    summary: str
    emotional_value: str = "MEDIUM"  # LOW, MEDIUM, HIGH
    trust_change: int = 0
    favor_owed: bool = False
    related_event_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NPCRelationship(BaseModel):
    relationship_id: str = Field(default_factory=lambda: f"rel_{uuid.uuid4().hex[:10]}")
    character_id: str
    npc_name: str
    level: RelationshipLevel = RelationshipLevel.STRANGER
    trust: int = Field(default=0, ge=-100, le=100)
    affection: int = Field(default=0, ge=-100, le=100)
    respect: int = Field(default=0, ge=-100, le=100)
    fear: int = Field(default=0, ge=-100, le=100)
    favors_owed_to_player: int = 0
    favors_owed_to_npc: int = 0
    memories: List[NPCMemory] = Field(default_factory=list)
    shared_secrets: List[str] = Field(default_factory=list)
    last_interaction_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.relationship_id
        return data


class RewardType(str, Enum):
    GOLD = "GOLD"
    ITEM = "ITEM"
    MEDICINE = "MEDICINE"
    WEAPON = "WEAPON"
    AMMUNITION = "AMMUNITION"
    MAP = "MAP"
    INFORMATION = "INFORMATION"
    DISCOUNT = "DISCOUNT"
    INTRODUCTION = "INTRODUCTION"
    FAVOR = "FAVOR"
    FRIENDSHIP = "FRIENDSHIP"
    BUSINESS_OPPORTUNITY = "BUSINESS_OPPORTUNITY"
    CREW_INVITE = "CREW_INVITE"
    SAFEHOUSE = "SAFEHOUSE"
    RECIPE = "RECIPE"
    TRAINING = "TRAINING"
    RARE_MATERIAL = "RARE_MATERIAL"
    ACCESS = "ACCESS"
    SECRET = "SECRET"
    LEGAL_PROTECTION = "LEGAL_PROTECTION"


class RewardGrant(BaseModel):
    reward_type: RewardType
    amount: int = 0
    item_id: Optional[str] = None
    item_name: Optional[str] = None
    quantity: int = 1
    description: str
    source_npc_name: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DiscoveryType(str, Enum):
    SUSPICIOUS_BODY = "SUSPICIOUS_BODY"
    HIDDEN_ROOM = "HIDDEN_ROOM"
    WOUNDED_SAILOR = "WOUNDED_SAILOR"
    ABANDONED_CARGO = "ABANDONED_CARGO"
    SECRET_MEETING = "SECRET_MEETING"
    SMUGGLING_CACHE = "SMUGGLING_CACHE"
    LOST_TREASURE = "LOST_TREASURE"
    ILLEGAL_GAMBLING = "ILLEGAL_GAMBLING"


class WorldDiscovery(BaseModel):
    discovery_id: str = Field(default_factory=lambda: f"disc_{uuid.uuid4().hex[:10]}")
    character_id: str
    discovery_type: DiscoveryType
    title: str
    description: str
    location_id: str
    suggested_actions: List[str] = Field(default_factory=list)
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    interacted: bool = False
    chosen_action: Optional[str] = None

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.discovery_id
        return data
