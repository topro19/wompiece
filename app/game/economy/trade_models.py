from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class CommodityType(str, Enum):
    IRON_ORE = "iron_ore"
    FINE_SILK = "fine_silk"
    RARE_SPICES = "rare_spices"
    VINTAGE_RUM = "vintage_rum"
    TIMBER = "timber"
    GUNPOWDER = "gunpowder"
    CONTRABAND_OPIUM = "contraband_opium"


class Commodity(BaseModel):
    commodity_id: CommodityType
    name: str
    base_price: int
    is_contraband: bool = False
    description: str


COMMODITIES_REGISTRY: Dict[CommodityType, Commodity] = {
    CommodityType.IRON_ORE: Commodity(
        commodity_id=CommodityType.IRON_ORE,
        name="High-Grade Iron Ore",
        base_price=25,
        is_contraband=False,
        description="Heavy smelted ore essential for forge-work, cannon casting, and armor plating."
    ),
    CommodityType.FINE_SILK: Commodity(
        commodity_id=CommodityType.FINE_SILK,
        name="Oriental Fine Silk",
        base_price=80,
        is_contraband=False,
        description="Lustrous spun textiles coveted by colonial governors and affluent nobility."
    ),
    CommodityType.RARE_SPICES: Commodity(
        commodity_id=CommodityType.RARE_SPICES,
        name="Verdant Saffron & Cinnamon",
        base_price=60,
        is_contraband=False,
        description="Exotic pungent spices harvested from the fertile microclimates of Verdant Atoll."
    ),
    CommodityType.VINTAGE_RUM: Commodity(
        commodity_id=CommodityType.VINTAGE_RUM,
        name="Old Buccaneer Cask Rum",
        base_price=30,
        is_contraband=False,
        description="Fermented sugarcane molasses distilled in oak casks. Vital for crew morale."
    ),
    CommodityType.TIMBER: Commodity(
        commodity_id=CommodityType.TIMBER,
        name="Seasoned Oak Timber",
        base_price=15,
        is_contraband=False,
        description="Felled ancient hardwoods treated for shipbuilding, hull careening, and dock pilings."
    ),
    CommodityType.GUNPOWDER: Commodity(
        commodity_id=CommodityType.GUNPOWDER,
        name="Refined Black Gunpowder",
        base_price=45,
        is_contraband=False,
        description="Milled saltpetre, sulphur, and charcoal for small-arms and naval broadsides."
    ),
    CommodityType.CONTRABAND_OPIUM: Commodity(
        commodity_id=CommodityType.CONTRABAND_OPIUM,
        name="Smuggled Medicinal Opium",
        base_price=150,
        is_contraband=True,
        description="Strictly outlawed narcotic resin fetched at astronomical prices in back-alley dens."
    )
}


# Price multipliers per market location (Simulating supply & demand across islands)
# [buy_multiplier, sell_multiplier]
LOCATION_MARKET_MULTIPLIERS: Dict[str, Dict[CommodityType, tuple[float, float]]] = {
    # Port Azure (Colonial Capital: High demand for spices, silk; cheap iron & timber)
    "port_azure_market": {
        CommodityType.IRON_ORE: (0.9, 0.75),
        CommodityType.TIMBER: (0.85, 0.70),
        CommodityType.RARE_SPICES: (1.5, 1.35),
        CommodityType.FINE_SILK: (1.4, 1.25),
        CommodityType.VINTAGE_RUM: (1.1, 0.95),
        CommodityType.GUNPOWDER: (1.0, 0.85),
        CommodityType.CONTRABAND_OPIUM: (2.0, 1.7)  # Illegal, severe customs scrutiny
    },
    # Verdant Atoll (Coral Bay: Cheap spices & silk, hungry for iron & gunpowder)
    "coral_bay_market": {
        CommodityType.RARE_SPICES: (0.7, 0.55),
        CommodityType.FINE_SILK: (0.8, 0.65),
        CommodityType.IRON_ORE: (1.6, 1.45),
        CommodityType.GUNPOWDER: (1.4, 1.25),
        CommodityType.TIMBER: (1.1, 0.95),
        CommodityType.VINTAGE_RUM: (1.0, 0.85),
        CommodityType.CONTRABAND_OPIUM: (1.3, 1.1)
    },
    # Isla de la Muerte (Skull Rock: Pirate Haven, cheap rum & contraband, desperate for timber & gunpowder)
    "skull_rock_anchorage": {
        CommodityType.VINTAGE_RUM: (0.6, 0.45),
        CommodityType.CONTRABAND_OPIUM: (0.8, 0.65),
        CommodityType.GUNPOWDER: (1.7, 1.50),
        CommodityType.TIMBER: (1.5, 1.30),
        CommodityType.IRON_ORE: (1.3, 1.15),
        CommodityType.FINE_SILK: (1.1, 0.90),
        CommodityType.RARE_SPICES: (1.2, 1.00)
    },
    # Dead Man's Cove (Smuggler's Cove: Black market hub)
    "smugglers_cove": {
        CommodityType.CONTRABAND_OPIUM: (1.1, 0.95),
        CommodityType.VINTAGE_RUM: (0.8, 0.65),
        CommodityType.GUNPOWDER: (1.3, 1.15),
        CommodityType.FINE_SILK: (1.2, 1.05),
        CommodityType.RARE_SPICES: (1.3, 1.15),
        CommodityType.IRON_ORE: (1.2, 1.00),
        CommodityType.TIMBER: (1.2, 1.00)
    }
}
