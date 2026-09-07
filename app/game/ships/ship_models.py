from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import BaseModel, Field


class ShipClass(str, Enum):
    SLOOP = "SLOOP"
    CARAVEL = "CARAVEL"
    FRIGATE = "FRIGATE"
    GALLEON = "GALLEON"


class ShipCondition(str, Enum):
    MINT = "MINT"
    DAMAGED = "DAMAGED"
    CRIPPLED = "CRIPPLED"
    SUNK = "SUNK"


class ShipClassConfig(BaseModel):
    ship_class: ShipClass
    name: str
    base_cost: int
    max_hull: int
    armor: int
    cannons: int
    speed: int  # knots
    cargo_capacity: int
    crew_capacity: int
    description: str


SHIP_CLASS_CONFIGS: Dict[ShipClass, ShipClassConfig] = {
    ShipClass.SLOOP: ShipClassConfig(
        ship_class=ShipClass.SLOOP,
        name="Swift Sloop",
        base_cost=500,
        max_hull=100,
        armor=5,
        cannons=4,
        speed=12,
        cargo_capacity=50,
        crew_capacity=6,
        description="A light and agile single-masted vessel. Favored by smugglers, scouts, and lone privateers for its superior speed and shallow draft."
    ),
    ShipClass.CARAVEL: ShipClassConfig(
        ship_class=ShipClass.CARAVEL,
        name="Merchant Caravel",
        base_cost=1500,
        max_hull=220,
        armor=10,
        cannons=10,
        speed=10,
        cargo_capacity=160,
        crew_capacity=20,
        description="A sturdy two-masted merchantman designed for profitable long-distance trading voyages while packing enough broadside iron to deter casual raiders."
    ),
    ShipClass.FRIGATE: ShipClassConfig(
        ship_class=ShipClass.FRIGATE,
        name="Heavy Frigate",
        base_cost=4000,
        max_hull=400,
        armor=20,
        cannons=24,
        speed=8,
        cargo_capacity=350,
        crew_capacity=50,
        description="A lethal three-masted warship fielding formidable broadside batteries and reinforced oak planking. The mainstay of Marine anti-piracy squadrons."
    ),
    ShipClass.GALLEON: ShipClassConfig(
        ship_class=ShipClass.GALLEON,
        name="War Galleon",
        base_cost=10000,
        max_hull=750,
        armor=30,
        cannons=44,
        speed=6,
        cargo_capacity=800,
        crew_capacity=120,
        description="A towering ocean fortress bristling with heavy iron cannons and expansive treasure vaults. Dominates naval fleet engagements."
    )
}


class CargoItem(BaseModel):
    item_id: str
    name: str
    quantity: int = Field(default=1, ge=1)
    is_contraband: bool = False
    value_per_unit: int = 10


class Ship(BaseModel):
    ship_id: str = Field(default_factory=lambda: f"ship_{uuid4().hex[:10]}")
    name: str
    ship_class: ShipClass
    owner_character_id: Optional[str] = None
    owner_crew_id: Optional[str] = None
    captain_id: str
    current_hull: int
    max_hull: int
    armor: int
    cannons: int
    speed: int
    cargo_capacity: int
    crew_capacity: int
    condition: ShipCondition = ShipCondition.MINT
    location_id: str = "port_azure_docks"
    is_docked: bool = True
    cargo: List[CargoItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def update_condition(self):
        """Deterministically recalculates condition based on hull percentage."""
        if self.current_hull <= 0:
            self.current_hull = 0
            self.condition = ShipCondition.SUNK
        elif self.current_hull < self.max_hull * 0.3:
            self.condition = ShipCondition.CRIPPLED
        elif self.current_hull < self.max_hull * 0.8:
            self.condition = ShipCondition.DAMAGED
        else:
            self.condition = ShipCondition.MINT

    def current_cargo_weight(self) -> int:
        return sum(item.quantity for item in self.cargo)

    def has_contraband(self) -> bool:
        return any(item.is_contraband for item in self.cargo)

    def to_mongo(self) -> Dict[str, Any]:
        return {
            "_id": self.ship_id,
            "ship_id": self.ship_id,
            "name": self.name,
            "ship_class": self.ship_class.value,
            "owner_character_id": self.owner_character_id,
            "owner_crew_id": self.owner_crew_id,
            "captain_id": self.captain_id,
            "current_hull": self.current_hull,
            "max_hull": self.max_hull,
            "armor": self.armor,
            "cannons": self.cannons,
            "speed": self.speed,
            "cargo_capacity": self.cargo_capacity,
            "crew_capacity": self.crew_capacity,
            "condition": self.condition.value,
            "location_id": self.location_id,
            "is_docked": self.is_docked,
            "cargo": [c.model_dump() for c in self.cargo],
            "created_at": self.created_at
        }
