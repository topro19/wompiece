import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class NPCFaction(str, Enum):
    PIRATE = 'PIRATE'
    MARINE = 'MARINE'
    MERCHANT = 'MERCHANT'
    CIVILIAN = 'CIVILIAN'
    UNDERWORLD = 'UNDERWORLD'
    INDEPENDENT = 'INDEPENDENT'


class NPCArchetype(str, Enum):
    # Pirates
    ROOKIE_PIRATE = 'ROOKIE_PIRATE'
    PIRATE_VETERAN = 'PIRATE_VETERAN'
    PIRATE_CAPTAIN = 'PIRATE_CAPTAIN'
    SMUGGLER = 'SMUGGLER'
    PIRATE_GAMBLER = 'PIRATE_GAMBLER'
    TREASURE_HUNTER = 'TREASURE_HUNTER'
    PIRATE_INFORMANT = 'PIRATE_INFORMANT'
    RUTHLESS_RAIDER = 'RUTHLESS_RAIDER'
    MERCHANT_PIRATE = 'MERCHANT_PIRATE'
    DRIFTER = 'DRIFTER'
    RIVAL_CAPTAIN = 'RIVAL_CAPTAIN'

    # Marines
    MARINE_RECRUIT = 'MARINE_RECRUIT'
    MARINE_SOLDIER = 'MARINE_SOLDIER'
    MARINE_SERGEANT = 'MARINE_SERGEANT'
    MARINE_INVESTIGATOR = 'MARINE_INVESTIGATOR'
    MARINE_OFFICER = 'MARINE_OFFICER'
    MARINE_INTEL_OFFICER = 'MARINE_INTEL_OFFICER'
    MARINE_CAPTAIN = 'MARINE_CAPTAIN'
    MARINE_COMMANDER = 'MARINE_COMMANDER'

    # Civilians, Trades & Specialists
    MERCHANT = 'MERCHANT'
    BARTENDER = 'BARTENDER'
    SAILOR = 'SAILOR'
    DOCKWORKER = 'DOCKWORKER'
    FISHERMAN = 'FISHERMAN'
    APOTHECARY = 'APOTHECARY'
    INFORMANT = 'INFORMANT'
    GAMBLER = 'GAMBLER'
    GUARD = 'GUARD'
    THIEF = 'THIEF'
    BOUNTY_HUNTER = 'BOUNTY_HUNTER'
    HUNTER = 'HUNTER'


class NPCScheduleEntry(BaseModel):
    start_hour: int = 0
    end_hour: int = 24
    preferred_facility: str
    activity_description: str


class NPCGoal(BaseModel):
    goal_id: str = Field(default_factory=lambda: 'ngoal_' + uuid.uuid4().hex[:8])
    goal_type: str
    description: str
    target_count: int = 1
    current_progress: int = 0
    status: str = 'ACTIVE'


class NPCCombatStats(BaseModel):
    health: int = 100
    max_health: int = 100
    attack: int = 15
    defense: int = 10
    level: int = 1


class WorldNPC(BaseModel):
    npc_id: str = Field(default_factory=lambda: 'npc_' + uuid.uuid4().hex[:10])
    name: str
    faction: NPCFaction
    role: NPCArchetype
    occupation: str
    island_id: str
    home_location_id: str
    location_id: str
    personality: List[str] = Field(default_factory=list)
    traits: List[str] = Field(default_factory=list)
    goals: List[NPCGoal] = Field(default_factory=list)
    relationships: Dict[str, int] = Field(default_factory=dict)
    reputation: int = 0
    wealth: int = 50
    inventory: List[Dict[str, Any]] = Field(default_factory=list)
    combat_stats: NPCCombatStats = Field(default_factory=NPCCombatStats)
    schedule: List[NPCScheduleEntry] = Field(default_factory=list)
    current_activity: str = 'Observing surroundings'
    secrets: List[str] = Field(default_factory=list)
    known_information: List[str] = Field(default_factory=list)
    loyalty: int = 50
    fear: int = 0
    trust: int = 50
    alive: bool = True
    wanted_status: int = 0
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data['_id'] = self.npc_id
        return data

    @property
    def is_pirate(self) -> bool:
        return self.faction == NPCFaction.PIRATE

    @property
    def is_marine(self) -> bool:
        return self.faction == NPCFaction.MARINE

    @property
    def role_title(self) -> str:
        return self.role.value.replace('_', ' ').title()
