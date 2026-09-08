from datetime import datetime, timezone
import random
import uuid
from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel, Field

from app.database.connection import db_manager
from app.game.map.map_models import (
    TravelType,
    MapDiscoveryState
)
from app.game.map.map_service import CANONICAL_ISLANDS, CANONICAL_LOCATIONS, map_service
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger
from app.game.notifications.notification_service import notification_service


class TravelEncounter(BaseModel):
    encounter_id: str = Field(default_factory=lambda: f"enc_{uuid.uuid4().hex[:8]}")
    title: str
    description: str
    narrative: str = ""
    resolution: str = "Concluded safely without incident."
    encounter_type: str = "patrol"  # merchant, patrol, wreck, survivor, smuggler, wildlife, weather
    danger_level: int = 1
    options: List[str] = Field(default_factory=lambda: ["Approach", "Observe from distance", "Ignore and sail on"])
    consequence_hint: Optional[str] = None
    created_opportunity: Optional[Dict[str, Any]] = None
    revealed_location_id: Optional[str] = None

    def __contains__(self, item):
        return item in ["title", "description", "narrative", "resolution", "encounter_type", "danger_level", "options"] or hasattr(self, item)

    def __getitem__(self, item):
        if item == "narrative":
            return self.narrative or self.description
        if item == "resolution":
            return self.resolution or "Concluded safely without incident."
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def get(self, item, default=None):
        try:
            return self[item]
        except KeyError:
            return default


class TravelEventRecord(BaseModel):
    event_id: str = Field(default_factory=lambda: f"trv_evt_{uuid.uuid4().hex[:10]}")
    character_id: str
    origin_location_id: str
    origin_island_id: str
    destination_location_id: str
    destination_island_id: str
    travel_type: str  # SEA_VOYAGE or ISLAND_OVERLAND
    route_name: str
    encounter_occurred: bool = False
    encounter_title: Optional[str] = None
    encounter_outcome: Optional[str] = None
    discoveries_made: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.event_id
        return data


class TravelResult(BaseModel):
    success: bool
    origin_name: str
    destination_name: str
    destination_island: str
    destination_island_id: str = "azure_island"
    arrival_name: str = "Port"
    route_name: str
    journey_narrative: str
    voyage_narrative: str = ""
    discovery_state: str = "discovered"
    encounter: Optional[TravelEncounter] = None
    discoveries: List[str] = Field(default_factory=list)
    nearby_facilities: List[str] = Field(default_factory=list)
    nearby_locations: List[Dict[str, Any]] = Field(default_factory=list)

    def __getitem__(self, item):
        if item == "arrival_name":
            return self.arrival_name or self.destination_name
        if item == "voyage_narrative":
            return self.voyage_narrative or self.journey_narrative
        if item == "destination_island_id":
            return self.destination_island_id
        if item == "discovery_state":
            return self.discovery_state
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def get(self, item, default=None):
        try:
            return self[item]
        except KeyError:
            return default


# Contextual Travel Encounters pool based on routes
ROUTE_ENCOUNTERS = {
    "PIRATE_WATERS": [
        TravelEncounter(
            title="Smuggler Sloop Flashing Signals",
            description="A sleek black sloop sits low in the water ahead, flashing a lantern shutter twice in a smuggler's code.",
            encounter_type="smuggler",
            danger_level=3,
            options=["Signal back and pull alongside", "Ready cannons and approach cautiously", "Ignore and maintain bearing"],
            consequence_hint="Could yield contraband trade or Black Tide contacts.",
            created_opportunity={
                "title": "Clandestine Sea Exchange",
                "description": "A smuggler looking to offload untaxed spirits before entering harbor.",
                "opp_type": "TRADE_LEAD",
                "urgency": "MODERATE"
            }
        ),
        TravelEncounter(
            title="Drifting Cargo Crates & Debris",
            description="You spot several wooden barrels and lashed crates bobbing gently amidst shattered deck timbers.",
            encounter_type="wreck",
            danger_level=2,
            options=["Fish the crates from the sea", "Search for survivors", "Sail past the wreckage"],
            consequence_hint="May contain valuable spices, cloth, or clues to a sunken galleon."
        ),
        TravelEncounter(
            title="Desperate Castaway on a Raft",
            description="A solitary sailor on a makeshift spar waves a sun-bleached flag, parched and delirious.",
            encounter_type="survivor",
            danger_level=2,
            options=["Rescue the castaway", "Question them from the deck", "Leave them to the currents"],
            consequence_hint="The survivor possesses a rumor regarding a hidden sea cavern.",
            revealed_location_id="smugglers_cove"
        )
    ],
    "MARINE_PATROL_WATERS": [
        TravelEncounter(
            title="Colonial Naval Cutter on Interception Course",
            description="A fast 10-gun Marine cutter cuts across your bow, signal flags demanding you heave to for customs inspection.",
            encounter_type="patrol",
            danger_level=3,
            options=["Submit politely to customs search", "Present forged trade manifests", "Attempt to outrun them"],
            consequence_hint="Tests your reputation with the Marine faction."
        ),
        TravelEncounter(
            title="Armed Merchant Convoy",
            description="Two heavily laden merchant brigantines escorted by a privateer frigate sail parallel to your course.",
            encounter_type="merchant",
            danger_level=1,
            options=["Hail them to trade supplies", "Exchange news and nautical rumors", "Pass without contact"],
            consequence_hint="Opportunity to buy provisions or glean port news."
        )
    ],
    "OVERLAND_WILDERNESS": [
        TravelEncounter(
            title="Suspicious Trail Footprints",
            description="Fresh bootprints veer sharply off the overgrown dirt track into the dark thicket.",
            encounter_type="wildlife",
            danger_level=2,
            options=["Track the footprints into the bush", "Inspect the disturbed brush", "Stick to the main path"],
            consequence_hint="Might lead to a hidden stash or an outlaw ambush."
        ),
        TravelEncounter(
            title="Wayside Shrine Offerings",
            description="A weathered stone marker dedicated to ancient sea gods stands at the crossroads, fresh coins resting on its base.",
            encounter_type="landmark",
            danger_level=1,
            options=["Leave an offering of 5 gold", "Pocket the loose coins", "Inspect the engravings and pass"],
            consequence_hint="Influences subtle fortune and moral standing."
        )
    ]
}


class TravelEngine:
    """
    Simulates instantaneous, zero-waiting travel with rich contextual route simulation.
    Fast transition + possibility + persistent consequences.
    """

    def __init__(self):
        self.events_col = "travel_event_history"

    @property
    def history_collection(self):
        return db_manager.db[self.events_col]

    async def get_available_destinations(self, character_id: str) -> List[Dict[str, Any]]:
        """Lists accessible overland destinations and sea voyage ports from current position."""
        char = await db_manager.db.characters.find_one({"_id": character_id})
        curr_loc_id = char.get("location_id", "port_azure_docks") if char else "port_azure_docks"
        curr_meta = CANONICAL_LOCATIONS.get(curr_loc_id, {})
        curr_island_id = curr_meta.get("island_id", "azure_island")

        destinations = []

        # 1. Overland destinations on the same island
        for loc_id, meta in CANONICAL_LOCATIONS.items():
            if loc_id == curr_loc_id:
                continue

            if meta.get("island_id") == curr_island_id:
                disc_state = await map_service.get_discovery_state(character_id, loc_id)
                name = meta.get("name") if disc_state != MapDiscoveryState.UNKNOWN else f"❓ Unexplored {meta.get('type', 'Area').capitalize()}"

                destinations.append({
                    "id": loc_id,
                    "location_id": loc_id,
                    "name": name,
                    "island_id": curr_island_id,
                    "island_name": CANONICAL_ISLANDS[curr_island_id].name,
                    "travel_type": "OVERLAND",
                    "route_type": "overland",
                    "danger_level": meta.get("danger", 1),
                    "danger_rating": meta.get("danger", 1),
                    "distance_leagues": 5,
                    "description": meta.get("description", ""),
                    "is_known": disc_state != MapDiscoveryState.UNKNOWN
                })

        # 2. Sea voyages to other islands
        for isl_id, isle in CANONICAL_ISLANDS.items():
            if isl_id != curr_island_id:
                port_id = "port_azure_docks"
                if isl_id == "skull_island":
                    port_id = "blackwater_port"
                elif isl_id == "mistfall_island":
                    port_id = "fogveil_port"
                elif isl_id == "cinder_shoals":
                    port_id = "renegade_shipyard"

                destinations.append({
                    "id": isl_id,
                    "location_id": port_id,
                    "name": f"{isle.name}",
                    "island_id": isl_id,
                    "island_name": isle.name,
                    "travel_type": "SEA_VOYAGE",
                    "route_type": "sea",
                    "danger_level": isle.danger_rating,
                    "danger_rating": isle.danger_rating,
                    "distance_leagues": 25,
                    "description": f"Set sail for {isle.name}. {isle.description}",
                    "is_known": True
                })

        return destinations

    async def execute_travel(
        self,
        character_id: str,
        destination_location_id: str,
        roll_encounter: bool = True
    ) -> TravelResult:
        """
        Executes an authoritative journey with zero real-time waiting.
        Simulates the transit event immediately, moves the character,
        updates the map, and returns the narrative.
        """
        char = await db_manager.db.characters.find_one({"_id": character_id})
        curr_loc_id = char.get("location_id", "port_azure_docks") if char else "port_azure_docks"
        curr_meta = CANONICAL_LOCATIONS.get(curr_loc_id, {})

        # Resolve destination if passed as island ID, island name, or port alias
        dest_input = destination_location_id.lower().strip().replace(" ", "_")
        island_default_ports = {
            "azure_island": "port_azure",
            "skull_island": "blackwater_port",
            "mistfall_island": "fogveil_port",
            "cinder_shoals": "renegade_shipyard",
        }
        dest_loc_id = destination_location_id
        for isl_id, port_id in island_default_ports.items():
            if dest_input in [isl_id, isl_id.replace("_island", ""), CANONICAL_ISLANDS[isl_id].name.lower().replace(" ", "_")]:
                dest_loc_id = port_id
                break

        if dest_loc_id in CANONICAL_LOCATIONS:
            dest_meta = CANONICAL_LOCATIONS[dest_loc_id]
        elif dest_input in CANONICAL_LOCATIONS:
            dest_loc_id = dest_input
            dest_meta = CANONICAL_LOCATIONS[dest_loc_id]
        else:
            found = False
            for k, v in CANONICAL_LOCATIONS.items():
                if dest_input in k or dest_input in v["name"].lower():
                    dest_loc_id = k
                    dest_meta = v
                    found = True
                    break
            if not found:
                raise ValueError(f"Destination '{destination_location_id}' is not recognized on the charts.")

        curr_island_id = curr_meta.get("island_id", "azure_island")
        dest_island_id = dest_meta.get("island_id", "azure_island")
        is_sea = (curr_island_id != dest_island_id)

        isle_origin = CANONICAL_ISLANDS.get(curr_island_id, CANONICAL_ISLANDS["azure_island"])
        isle_dest = CANONICAL_ISLANDS.get(dest_island_id, CANONICAL_ISLANDS["azure_island"])

        if is_sea:
            route_name = f"{isle_origin.name} → {isle_dest.name} Sea Corridor"
            travel_type_str = "SEA_VOYAGE"
        else:
            route_name = f"{curr_meta.get('name', curr_loc_id)} Trail"
            travel_type_str = "ISLAND_OVERLAND"

        # 1. Roll for simulated journey encounter
        encounter = None
        narrative_parts = []

        if is_sea:
            narrative_parts.append(f"⚓ Setting course from **{curr_meta.get('name', 'the port')}** toward **{isle_dest.name}**.")
        else:
            narrative_parts.append(f"🥾 You depart **{curr_meta.get('name', 'your location')}** and hike along the {route_name}.")

        discoveries_made = []

        if roll_encounter:
            roll = random.random()
            if roll < 0.50:
                if is_sea:
                    if dest_island_id in ["skull_island", "cinder_shoals"]:
                        encounter = random.choice(ROUTE_ENCOUNTERS["PIRATE_WATERS"])
                    else:
                        encounter = random.choice(ROUTE_ENCOUNTERS["MARINE_PATROL_WATERS"])
                else:
                    encounter = random.choice(ROUTE_ENCOUNTERS["OVERLAND_WILDERNESS"])

                narrative_parts.append(f"⚠️ **EVENT ON THE WAY**: {encounter.title}!\n*{encounter.description}*")
            else:
                encounter = TravelEncounter(
                    title="Fair Winds and Open Skies",
                    description="The trade winds blow steady at your back. The passage is swift and uneventful.",
                    narrative="The trade winds blow steady at your back. The passage is swift and uneventful.",
                    resolution="Passed through cleanly under good weather.",
                    encounter_type="weather",
                    danger_level=1
                )
                if is_sea:
                    narrative_parts.append("🌊 The trade winds blow steady at your back. The voyage across open water is swift and uneventful.")
                else:
                    narrative_parts.append("🌲 The path is quiet, save for seabirds wheeling overhead.")

        # 2. Authoritative Move: Update character location in database IMMEDIATELY
        await db_manager.db.characters.update_one(
            {"_id": character_id},
            {
                "$set": {
                    "location_id": dest_loc_id,
                    "island_id": dest_island_id,
                    "is_traveling": False,
                    "active_travel_id": None
                }
            }
        )

        # 3. Permanently mark destination as EXPLORED on character's map
        await map_service.discover_location(
            character_id=character_id,
            location_id=dest_loc_id,
            island_id=dest_island_id,
            discovered_via="travel_arrival",
            new_state=MapDiscoveryState.EXPLORED
        )
        discoveries_made.append(dest_meta.get("name", dest_loc_id))

        # If encounter revealed an extra secret location, mark it as RUMORED/DISCOVERED
        if encounter and encounter.revealed_location_id:
            secret_meta = CANONICAL_LOCATIONS.get(encounter.revealed_location_id, {})
            if secret_meta:
                await map_service.discover_location(
                    character_id=character_id,
                    location_id=encounter.revealed_location_id,
                    island_id=secret_meta.get("island_id", dest_island_id),
                    discovered_via="travel_rumor",
                    new_state=MapDiscoveryState.RUMORED
                )
                discoveries_made.append(f"Rumor: {secret_meta.get('name')}")

        narrative_parts.append(f"📍 **Arrival**: You have reached **{dest_meta.get('name')}** on **{isle_dest.name}**.")

        # 4. Fetch nearby facilities and locations on the arrived island
        nearby_locations = []
        for l_id, meta in CANONICAL_LOCATIONS.items():
            if meta.get("island_id") == dest_island_id and l_id != dest_loc_id:
                disc = await map_service.get_discovery_state(character_id, l_id)
                nearby_locations.append({
                    "location_id": l_id,
                    "name": meta.get("name") if disc != MapDiscoveryState.UNKNOWN else f"❓ Unexplored {meta.get('type', 'Area').capitalize()}",
                    "type": meta.get("type"),
                    "danger": meta.get("danger")
                })

        # 5. Persist Travel Event Record
        event_record = TravelEventRecord(
            character_id=character_id,
            origin_location_id=curr_loc_id,
            origin_island_id=curr_island_id,
            destination_location_id=dest_loc_id,
            destination_island_id=dest_island_id,
            travel_type=travel_type_str,
            route_name=route_name,
            encounter_occurred=(encounter is not None),
            encounter_title=encounter.title if encounter else None,
            discoveries_made=discoveries_made
        )
        await self.history_collection.insert_one(event_record.to_mongo())

        # Record into living world timeline
        await notification_service.record_timeline_event(
            character_id=character_id,
            text=f"Voyage: Arrived at {dest_meta.get('name')} on {isle_dest.name}.",
            category="TRAVEL"
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.SHIP_DOCKED if is_sea else EventType.TRANSACTION_EXECUTED,
            actor_id=character_id,
            location_id=dest_loc_id,
            visibility=EventVisibility.PUBLIC,
            metadata={
                "origin": curr_loc_id,
                "destination": dest_loc_id,
                "encounter": encounter.title if encounter else None
            }
        ))

        logger.info(f"[TRAVEL EXECUTED] {character_id} moved {curr_loc_id} -> {dest_loc_id} immediately (Encounter: {bool(encounter)}).")

        return TravelResult(
            success=True,
            origin_name=curr_meta.get("name", curr_loc_id),
            destination_name=dest_meta.get("name"),
            destination_island=isle_dest.name,
            destination_island_id=dest_island_id,
            arrival_name=dest_meta.get("name"),
            route_name=route_name,
            journey_narrative="\n\n".join(narrative_parts),
            voyage_narrative=f"⚓ VOYAGE TO {dest_meta.get('name').upper()}\n\n" + "\n\n".join(narrative_parts),
            encounter=encounter,
            discovery_state="discovered",
            discoveries=discoveries_made,
            nearby_facilities=dest_meta.get("facilities", []),
            nearby_locations=nearby_locations[:5]
        )


travel_engine = TravelEngine()
