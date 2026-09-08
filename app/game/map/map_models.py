import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel, Field


class MapLevel(str, Enum):
    GLOBAL = "GLOBAL"
    ISLAND = "ISLAND"
    LOCATION = "LOCATION"


class MapDiscoveryState(str, Enum):
    UNKNOWN = "UNKNOWN"
    RUMORED = "RUMORED"
    DISCOVERED = "DISCOVERED"
    EXPLORED = "EXPLORED"
    MAPPED = "MAPPED"
    FULLY_INVESTIGATED = "FULLY_INVESTIGATED"


class TravelType(str, Enum):
    ISLAND_OVERLAND = "ISLAND_OVERLAND"
    SEA_VOYAGE = "SEA_VOYAGE"


class TerrainType(str, Enum):
    OCEAN = "OCEAN"
    PORT_TOWN = "PORT_TOWN"
    JUNGLE = "JUNGLE"
    VOLCANIC_RIDGE = "VOLCANIC_RIDGE"
    CAVE_SYSTEM = "CAVE_SYSTEM"
    REEF_SHOALS = "REEF_SHOALS"
    ANCIENT_RUINS = "ANCIENT_RUINS"
    PLAINS = "PLAINS"


class WorldPosition(BaseModel):
    coordinates: Tuple[float, float] = (0.0, 0.0)
    island_id: str = "azure_island"
    region_id: str = "azure_harbor_district"
    location_id: str = "port_azure_docks"


class MapPointOfInterest(BaseModel):
    poi_id: str
    name: str
    poi_type: str  # tavern, shop, garrison, landmark, hidden_dock, ruin, cave
    icon: str = "📍"
    coordinates: Tuple[float, float] = (0.0, 0.0)
    description: str
    is_hidden: bool = False
    secrets: List[str] = Field(default_factory=list)


class Region(BaseModel):
    region_id: str
    island_id: str
    name: str
    terrain: TerrainType
    danger_rating: int = Field(default=1, ge=1, le=5)
    controlling_faction: str = "Neutral"
    locations: List[str] = Field(default_factory=list)
    description: str = ""
    coordinates: Tuple[float, float] = (0.0, 0.0)


class Island(BaseModel):
    island_id: str
    name: str
    title: str
    description: str
    coordinates: Tuple[float, float] = (0.0, 0.0)
    controlling_faction: str = "Neutral"
    danger_rating: int = Field(default=1, ge=1, le=5)
    regions: List[str] = Field(default_factory=list)
    sea_lanes: List[str] = Field(default_factory=list)
    climate: str = "Temperate Maritime"


class CharacterMapDiscovery(BaseModel):
    discovery_id: str = Field(default_factory=lambda: f"disc_{uuid.uuid4().hex[:10]}")
    character_id: str
    location_id: str
    island_id: str
    state: MapDiscoveryState = MapDiscoveryState.DISCOVERED
    discovered_via: str = "exploration"  # physical, npc_info, purchased_map, rumor, intel
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.discovery_id
        return data


class MapMarker(BaseModel):
    marker_id: str = Field(default_factory=lambda: f"mark_{uuid.uuid4().hex[:8]}")
    character_id: str
    island_id: str
    location_id: Optional[str] = None
    label: str
    notes: str = ""
    icon: str = "📍"
    is_shared_with_crew: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.marker_id
        return data


class TravelState(BaseModel):
    travel_id: str = Field(default_factory=lambda: f"trv_{uuid.uuid4().hex[:10]}")
    character_id: str
    origin_location_id: str
    destination_location_id: str
    origin_island_id: str
    destination_island_id: str
    travel_type: TravelType
    route_name: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    arrival_due_at: datetime
    distance_km: float
    duration_minutes: int
    ship_id: Optional[str] = None
    danger_level: int = 1
    encountered_events: List[str] = Field(default_factory=list)
    is_completed: bool = False

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.travel_id
        return data
