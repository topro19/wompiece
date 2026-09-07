from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Location(BaseModel):
    """Authoritative location in the persistent world."""
    location_id: str
    name: str
    island: str
    description: str
    connected_locations: List[str] = Field(default_factory=list)
    is_port: bool = False
    security_level: int = Field(default=3, ge=1, le=5)  # 1: lawless, 5: naval fortress
    facilities: List[str] = Field(default_factory=list)


DEFAULT_LOCATIONS: Dict[str, Location] = {
    "port_azure_docks": Location(
        location_id="port_azure_docks",
        name="Port Azure - Grand Docks",
        island="Azure Island",
        description="A sprawling harbor lined with galleons, sloops, and sea merchants. Marine sentries eye travelers warily from elevated watchtowers.",
        connected_locations=["port_azure_market", "the_crimson_parrot", "marine_headquarters"],
        is_port=True,
        security_level=3,
        facilities=["shipyard", "docks", "cargo_wharf"]
    ),
    "the_crimson_parrot": Location(
        location_id="the_crimson_parrot",
        name="The Crimson Parrot Tavern",
        island="Azure Island",
        description="A bustling, dimly lit tavern reeking of stale rum and salt. Dice clatter in shadowy booths, and whispered bargains exchange hands.",
        connected_locations=["port_azure_docks", "smugglers_cove"],
        is_port=False,
        security_level=1,
        facilities=["tavern", "gambling_den", "rumor_mill", "inn"]
    ),
    "port_azure_market": Location(
        location_id="port_azure_market",
        name="Port Azure - Central Market",
        island="Azure Island",
        description="A vibrant bazaar filled with stalls selling spices, silks, ship provisions, and navigational charts under watchful civilian inspectors.",
        connected_locations=["port_azure_docks", "governors_mansion"],
        is_port=False,
        security_level=3,
        facilities=["general_store", "bank", "trading_post"]
    ),
    "marine_headquarters": Location(
        location_id="marine_headquarters",
        name="Port Azure - Marine 16th Division HQ",
        island="Azure Island",
        description="A fortified stone garrison flying the Marine flag. High stone walls protect interrogation holding cells, arsenals, and the office of the Marine Commander.",
        connected_locations=["port_azure_docks", "governors_mansion"],
        is_port=False,
        security_level=5,
        facilities=["interrogation_cells", "armory", "bounty_board", "warrant_office"]
    ),
    "smugglers_cove": Location(
        location_id="smugglers_cove",
        name="Dead Man's Cove",
        island="Azure Island",
        description="A hidden sea cavern behind the jagged rocks west of the port. Unsanctioned black-market contraband and illegal cargo pass through here undetected.",
        connected_locations=["the_crimson_parrot"],
        is_port=True,
        security_level=1,
        facilities=["black_market", "hidden_dock", "fence"]
    ),
    "governors_mansion": Location(
        location_id="governors_mansion",
        name="Governor's Grand Estate",
        island="Azure Island",
        description="An ornate colonial estate surrounded by wrought-iron fences and manicured gardens. The center of political power and business permits.",
        connected_locations=["port_azure_market", "marine_headquarters"],
        is_port=False,
        security_level=4,
        facilities=["licensing_office", "ballroom", "colonial_treasury"]
    )
}


class LocationService:
    """Provides deterministic location graph resolution and movement validation."""

    def __init__(self, locations: Optional[Dict[str, Location]] = None):
        self._locations = locations or DEFAULT_LOCATIONS

    def get_location(self, location_id: str) -> Optional[Location]:
        return self._locations.get(location_id)

    def can_move(self, from_location_id: str, to_location_id: str) -> bool:
        """Enforces that a character cannot teleport; must follow graph connections."""
        current = self.get_location(from_location_id)
        if not current:
            return False
        return to_location_id in current.connected_locations

    def get_destinations(self, location_id: str) -> List[Location]:
        current = self.get_location(location_id)
        if not current:
            return []
        return [self._locations[dest_id] for dest_id in current.connected_locations if dest_id in self._locations]


location_service = LocationService()
