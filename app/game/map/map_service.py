from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
import uuid

from app.database.connection import db_manager
from app.game.map.map_models import (
    MapLevel,
    Island,
    Region,
    TerrainType,
    MapDiscoveryState,
    CharacterMapDiscovery,
    MapMarker,
    MapPointOfInterest,
    WorldPosition
)
from app.game.world.location import location_service
from app.services.logger import logger


CANONICAL_ISLANDS: Dict[str, Island] = {
    "azure_island": Island(
        island_id="azure_island",
        name="Azure Island",
        title="Colonial Seat & Maritime Stronghold",
        description="The prosperous colonial capital featuring deep-water wharves, royal stone garrisons, and thriving merchant avenues.",
        coordinates=(10.0, 15.0),
        controlling_faction="Marine",
        danger_rating=2,
        regions=["azure_harbor_district", "azure_citadel_district", "azure_wild_cliffs"],
        sea_lanes=["azure_sea_lane", "colonial_express_route"],
        climate="Breezy & Sunlit"
    ),
    "skull_island": Island(
        island_id="skull_island",
        name="Skull Island",
        title="Outlaw Haven & Blackwater Atoll",
        description="A jagged, storm-swept bastion of buccaneers, treacherous jungle canopies, and forgotten volcanic caves.",
        coordinates=(45.0, 60.0),
        controlling_faction="Pirate",
        danger_rating=4,
        regions=["skull_blackwater_wharf", "skull_western_jungle", "skull_ashen_ridge", "skull_ruins"],
        sea_lanes=["smugglers_run", "bone_chasm_channel"],
        climate="Humid & Volcanic"
    ),
    "mistfall_island": Island(
        island_id="mistfall_island",
        name="Mistfall Island",
        title="Shrouded Isle of Ancients",
        description="Enveloped in perpetual sea fog, boasting coral shoals, luminescent caves, and ancient pre-colonial shrines.",
        coordinates=(80.0, 25.0),
        controlling_faction="Neutral",
        danger_rating=3,
        regions=["mistfall_outer_reefs", "mistfall_whispering_caves"],
        sea_lanes=["spectral_passage"],
        climate="Foggy & Mysterious"
    ),
    "cinder_shoals": Island(
        island_id="cinder_shoals",
        name="Cinder Shoals",
        title="Volcanic Shipyard & Smuggler Caldera",
        description="An active volcanic ring housing illicit drydocks, sulfur mines, and ruthless corsair refitting stations.",
        coordinates=(30.0, 85.0),
        controlling_faction="Pirate",
        danger_rating=5,
        regions=["cinder_drydocks", "cinder_slums"],
        sea_lanes=["ash_corridor"],
        climate="Scorching & Ash-laden"
    )
}

CANONICAL_REGIONS: Dict[str, Region] = {
    # Azure Island Regions
    "azure_harbor_district": Region(
        region_id="azure_harbor_district",
        island_id="azure_island",
        name="Harbor & Trade District",
        terrain=TerrainType.PORT_TOWN,
        danger_rating=2,
        controlling_faction="Marine",
        locations=["port_azure_docks", "port_azure", "the_crimson_parrot", "port_azure_market"],
        description="Cobblestone streets bustling with sailors, fruit vendors, and Marine customs officers.",
        coordinates=(10.0, 15.0)
    ),
    "azure_citadel_district": Region(
        region_id="azure_citadel_district",
        island_id="azure_island",
        name="Citadel & High Town",
        terrain=TerrainType.PORT_TOWN,
        danger_rating=1,
        controlling_faction="Marine",
        locations=["marine_headquarters", "governors_mansion"],
        description="Fortified bastions and ornate colonial estates overlooking the azure bay.",
        coordinates=(10.5, 15.2)
    ),
    "azure_wild_cliffs": Region(
        region_id="azure_wild_cliffs",
        island_id="azure_island",
        name="Wild Cliffs & Coves",
        terrain=TerrainType.CAVE_SYSTEM,
        danger_rating=3,
        controlling_faction="Neutral",
        locations=["smugglers_cove", "azure_lighthouse", "sunken_reef"],
        description="Jagged limestone cliffs sheltering clandestine smuggling caverns.",
        coordinates=(9.5, 14.7)
    ),

    # Skull Island Regions
    "skull_blackwater_wharf": Region(
        region_id="skull_blackwater_wharf",
        island_id="skull_island",
        name="Blackwater Wharf",
        terrain=TerrainType.PORT_TOWN,
        danger_rating=3,
        controlling_faction="Pirate",
        locations=["skull_rock_anchorage", "blackwater_tavern"],
        description="Rotting wooden piers crowded with pirate cutters and rowdy gambling parlors.",
        coordinates=(45.0, 60.0)
    ),
    "skull_western_jungle": Region(
        region_id="skull_western_jungle",
        island_id="skull_island",
        name="Western Jungle",
        terrain=TerrainType.JUNGLE,
        danger_rating=4,
        controlling_faction="Neutral",
        locations=["western_jungle", "ancient_totem_shrine"],
        description="Dense, untamed tropical foliage inhabited by predators, outlaws, and rare flora.",
        coordinates=(44.5, 60.5)
    ),
    "skull_ashen_ridge": Region(
        region_id="skull_ashen_ridge",
        island_id="skull_island",
        name="Ashen Ridge",
        terrain=TerrainType.VOLCANIC_RIDGE,
        danger_rating=4,
        controlling_faction="Pirate",
        locations=["ashen_ridge", "abandoned_mining_camp"],
        description="Sulfuric volcanic bluffs overlooking the western ocean.",
        coordinates=(45.8, 61.2)
    ),
    "skull_ruins": Region(
        region_id="skull_ruins",
        island_id="skull_island",
        name="Sunken Caldera & Ruins",
        terrain=TerrainType.ANCIENT_RUINS,
        danger_rating=5,
        controlling_faction="Neutral",
        locations=["northern_ruins", "forbidden_cavern"],
        description="Crumbling basalt pillars concealing dangerous pre-cataclysmic relics.",
        coordinates=(46.2, 60.8)
    ),

    # Mistfall Island Regions
    "mistfall_outer_reefs": Region(
        region_id="mistfall_outer_reefs",
        island_id="mistfall_island",
        name="Outer Reefs & Coral Shallows",
        terrain=TerrainType.REEF_SHOALS,
        danger_rating=3,
        controlling_faction="Neutral",
        locations=["coral_bay_wharf", "sunken_galleon_reef"],
        description="Pristine coral mazes that can rip the keel out of careless sloops.",
        coordinates=(80.0, 25.0)
    ),
    "mistfall_whispering_caves": Region(
        region_id="mistfall_whispering_caves",
        island_id="mistfall_island",
        name="Whispering Caverns",
        terrain=TerrainType.CAVE_SYSTEM,
        danger_rating=4,
        controlling_faction="Neutral",
        locations=["moonlily_grotto", "echo_cavern"],
        description="Subterranean pools where the air hums with strange acoustic resonance.",
        coordinates=(80.5, 25.4)
    ),

    # Cinder Shoals Regions
    "cinder_drydocks": Region(
        region_id="cinder_drydocks",
        island_id="cinder_shoals",
        name="Renegade Drydocks",
        terrain=TerrainType.PORT_TOWN,
        danger_rating=4,
        controlling_faction="Pirate",
        locations=["renegade_shipyard", "sulfur_foundry"],
        description="Soot-blackened docks hammering ironclad hulls day and night.",
        coordinates=(30.0, 85.0)
    ),
    "cinder_slums": Region(
        region_id="cinder_slums",
        island_id="cinder_shoals",
        name="Sulfur Flats & Slums",
        terrain=TerrainType.VOLCANIC_RIDGE,
        danger_rating=5,
        controlling_faction="Pirate",
        locations=["ash_flophouse", "smuggler_cove_south"],
        description="A lawless shantytown built directly upon warm volcanic basalt.",
        coordinates=(30.4, 85.3)
    )
}

CANONICAL_LOCATIONS: Dict[str, Dict[str, Any]] = {
    # Azure Island
    "port_azure_docks": {
        "name": "Port Azure - Grand Docks",
        "island_id": "azure_island",
        "region_id": "azure_harbor_district",
        "type": "docks",
        "coordinates": (10.0, 15.0),
        "danger": 2,
        "facilities": ["shipyard", "docks", "cargo_wharf"],
        "description": "A bustling colonial port with naval watchtowers and merchant cranes."
    },
    "the_crimson_parrot": {
        "name": "The Crimson Parrot Tavern",
        "island_id": "azure_island",
        "region_id": "azure_harbor_district",
        "type": "tavern",
        "coordinates": (10.1, 15.0),
        "danger": 1,
        "facilities": ["tavern", "gambling_den", "inn"],
        "description": "The rowdiest tavern on Harbor Row, ripe with rumors and dice games."
    },
    "port_azure_market": {
        "name": "Port Azure - Central Market",
        "island_id": "azure_island",
        "region_id": "azure_harbor_district",
        "type": "market",
        "coordinates": (10.2, 15.1),
        "danger": 2,
        "facilities": ["general_store", "bank", "trading_post"],
        "description": "Sunlit bazaar smelling of cinnamon, nutmeg, and tarred rigging."
    },
    "marine_headquarters": {
        "name": "Marine 16th Division HQ",
        "island_id": "azure_island",
        "region_id": "azure_citadel_district",
        "type": "garrison",
        "coordinates": (10.5, 15.2),
        "danger": 5,
        "facilities": ["armory", "holding_cells", "bounty_board", "warrant_office"],
        "description": "The fortified colonial naval command post flying the royal colors."
    },
    "governors_mansion": {
        "name": "Governor's Grand Estate",
        "island_id": "azure_island",
        "region_id": "azure_citadel_district",
        "type": "palace",
        "coordinates": (10.6, 15.3),
        "danger": 3,
        "facilities": ["licensing_office", "ballroom", "colonial_treasury"],
        "description": "A magnificent colonial mansion overlooking the azure bay."
    },
    "smugglers_cove": {
        "name": "Dead Man's Cove",
        "island_id": "azure_island",
        "region_id": "azure_wild_cliffs",
        "type": "cave",
        "coordinates": (9.5, 14.7),
        "danger": 3,
        "facilities": ["black_market", "hidden_dock", "fence"],
        "description": "A secret cavern beneath the cliffs where illicit cargo is transferred."
    },
    "azure_lighthouse": {
        "name": "Cape Azure Lighthouse",
        "island_id": "azure_island",
        "region_id": "azure_wild_cliffs",
        "type": "landmark",
        "coordinates": (9.3, 14.5),
        "danger": 2,
        "facilities": ["observation_deck", "signal_beacon"],
        "description": "A towering stone light keeping ships off the jagged coastal rocks."
    },
    "sunken_reef": {
        "name": "Sunken Coral Reef",
        "island_id": "azure_island",
        "region_id": "azure_wild_cliffs",
        "type": "reef",
        "coordinates": (9.1, 14.2),
        "danger": 3,
        "facilities": ["salvage_diving", "coral_shallows"],
        "description": "Treacherous underwater coral heads littered with ancient ship timbers."
    },
    "port_azure": {
        "name": "Port Azure",
        "island_id": "azure_island",
        "region_id": "azure_harbor_district",
        "type": "port",
        "coordinates": (10.0, 15.0),
        "danger": 2,
        "facilities": ["docks", "shipyard", "salty_anchor_tavern"],
        "description": "The capital port and naval hub of the Azure Archipelago."
    },
    "blackwater_port": {
        "name": "Blackwater Port",
        "island_id": "skull_island",
        "region_id": "skull_blackwater_wharf",
        "type": "port",
        "coordinates": (45.0, 60.0),
        "danger": 4,
        "facilities": ["docks", "black_market", "pirate_cove"],
        "description": "The lawless outlaw harbor of Skull Island."
    },
    "fogveil_port": {
        "name": "Fogveil Port",
        "island_id": "mistfall_island",
        "region_id": "mistfall_outer_reefs",
        "type": "port",
        "coordinates": (80.0, 25.0),
        "danger": 3,
        "facilities": ["docks", "lighthouse", "hidden_harbor"],
        "description": "The mist-shrouded harbor of Mistfall Island."
    },

    # Skull Island
    "skull_rock_anchorage": {
        "name": "Skull Rock Anchorage",
        "island_id": "skull_island",
        "region_id": "skull_blackwater_wharf",
        "type": "docks",
        "coordinates": (45.0, 60.0),
        "danger": 4,
        "facilities": ["pirate_cove", "black_market", "ship_repair"],
        "description": "A shadowy natural cove where pirate galleons hide beneath sea arches."
    },
    "blackwater_tavern": {
        "name": "The Drowned Rat Alehouse",
        "island_id": "skull_island",
        "region_id": "skull_blackwater_wharf",
        "type": "tavern",
        "coordinates": (45.1, 60.1),
        "danger": 4,
        "facilities": ["tavern", "recruitment", "gambling"],
        "description": "Where ruthless buccaneers split plunder and recruit deserters."
    },
    "western_jungle": {
        "name": "Western Dense Jungle",
        "island_id": "skull_island",
        "region_id": "skull_western_jungle",
        "type": "wilderness",
        "coordinates": (44.5, 60.5),
        "danger": 4,
        "facilities": ["herb_foraging", "hunting_grounds"],
        "description": "Overgrown jungle crawling with venomous serpents and pirate lookouts."
    },
    "ancient_totem_shrine": {
        "name": "Shrine of the Drowned Serpent",
        "island_id": "skull_island",
        "region_id": "skull_western_jungle",
        "type": "ruins",
        "coordinates": (44.2, 60.7),
        "danger": 4,
        "facilities": ["altar", "hidden_cache"],
        "description": "An ancient mossy stone serpent wrapped around an altar."
    },
    "ashen_ridge": {
        "name": "Ashen Volcanic Ridge",
        "island_id": "skull_island",
        "region_id": "skull_ashen_ridge",
        "type": "mountain",
        "coordinates": (45.8, 61.2),
        "danger": 4,
        "facilities": ["scout_post", "ore_vein"],
        "description": "Cracked volcanic rock smelling of brimstone with a commanding sea view."
    },
    "abandoned_mining_camp": {
        "name": "Old Sulfur Mine Camp",
        "island_id": "skull_island",
        "region_id": "skull_ashen_ridge",
        "type": "ruins",
        "coordinates": (46.0, 61.4),
        "danger": 4,
        "facilities": ["abandoned_shaft", "shelter"],
        "description": "Collapsed wooden barracks and mine carts abandoned by early colonizers."
    },
    "northern_ruins": {
        "name": "Forgotten Caldera Citadel",
        "island_id": "skull_island",
        "region_id": "skull_ruins",
        "type": "ruins",
        "coordinates": (46.2, 60.8),
        "danger": 5,
        "facilities": ["treasure_vault", "ancient_crypt"],
        "description": "Cyclopean ruins predating colonial arrival, filled with deadly traps."
    },
    "forbidden_cavern": {
        "name": "The Obsidian Maw",
        "island_id": "skull_island",
        "region_id": "skull_ruins",
        "type": "cave",
        "coordinates": (46.5, 60.9),
        "danger": 5,
        "facilities": ["subterranean_sea", "lost_relic"],
        "description": "A pitch-black sea cave extending deep beneath the island caldera."
    },

    # Mistfall Island
    "coral_bay_wharf": {
        "name": "Coral Bay Shallows",
        "island_id": "mistfall_island",
        "region_id": "mistfall_outer_reefs",
        "type": "docks",
        "coordinates": (80.0, 25.0),
        "danger": 3,
        "facilities": ["shallow_dock", "fish_market"],
        "description": "Wooden stilts over shallow turquoise water surrounded by mist."
    },
    "sunken_galleon_reef": {
        "name": "Reef of the Wrecked Sovereign",
        "island_id": "mistfall_island",
        "region_id": "mistfall_outer_reefs",
        "type": "landmark",
        "coordinates": (80.2, 25.1),
        "danger": 3,
        "facilities": ["salvage_site", "diving_spot"],
        "description": "The wooden ribs of a legendary treasure ship stranded on sharp coral."
    },
    "moonlily_grotto": {
        "name": "Luminescent Moonlily Grotto",
        "island_id": "mistfall_island",
        "region_id": "mistfall_whispering_caves",
        "type": "cave",
        "coordinates": (80.5, 25.4),
        "danger": 3,
        "facilities": ["rare_herb_nursery", "healing_spring"],
        "description": "A tranquil cavern bathed in blue bioluminescence where rare curative lilies bloom."
    },
    "echo_cavern": {
        "name": "Singing Stalactite Cave",
        "island_id": "mistfall_island",
        "region_id": "mistfall_whispering_caves",
        "type": "cave",
        "coordinates": (80.7, 25.6),
        "danger": 4,
        "facilities": ["acoustic_vault"],
        "description": "Winds howling through hollow rock produce haunting, musical echoes."
    },

    # Cinder Shoals
    "renegade_shipyard": {
        "name": "The Iron Anvil Drydocks",
        "island_id": "cinder_shoals",
        "region_id": "cinder_drydocks",
        "type": "shipyard",
        "coordinates": (30.0, 85.0),
        "danger": 4,
        "facilities": ["warship_refit", "cannon_foundry", "armor_plating"],
        "description": "Heavy timber scaffolds where illegal war sloops are armored with iron plating."
    },
    "sulfur_foundry": {
        "name": "Brimstone Powder Works",
        "island_id": "cinder_shoals",
        "region_id": "cinder_drydocks",
        "type": "workshop",
        "coordinates": (30.2, 85.1),
        "danger": 4,
        "facilities": ["gunpowder_mill", "explosives_shop"],
        "description": "Mills grinding volcanic sulfur into potent cannon gunpowder."
    },
    "ash_flophouse": {
        "name": "The Smoldering Cask",
        "island_id": "cinder_shoals",
        "region_id": "cinder_slums",
        "type": "tavern",
        "coordinates": (30.4, 85.3),
        "danger": 5,
        "facilities": ["gambling_pit", "bounty_contact", "safehouse"],
        "description": "A dangerous watering hole where corsair mutineers spend blood money."
    },
    "smuggler_cove_south": {
        "name": "Black Sand Slipway",
        "island_id": "cinder_shoals",
        "region_id": "cinder_slums",
        "type": "docks",
        "coordinates": (30.6, 85.5),
        "danger": 4,
        "facilities": ["contraband_depot", "skiff_rental"],
        "description": "A beach of pure black basalt sand facilitating midnight cargo drops."
    }
}


class MapService:
    """
    Authoritative World Map and Navigation Engine.
    Manages 3-tier map hierarchy, Fog of War discoveries, player coordinates,
    markers, and territory control.
    """

    def __init__(self):
        self.discoveries_col = "map_discoveries"
        self.markers_col = "map_markers"

    @property
    def discoveries(self):
        return db_manager.db[self.discoveries_col]

    @property
    def markers(self):
        return db_manager.db[self.markers_col]

    # --- Discovery & Fog of War ---

    async def get_discovery_state(self, character_id: str, location_id: str) -> MapDiscoveryState:
        """Checks the player's personal fog-of-war discovery status for a location."""
        doc = await self.discoveries.find_one({"character_id": character_id, "location_id": location_id})
        if doc:
            return MapDiscoveryState(doc.get("state", MapDiscoveryState.DISCOVERED.value))
        
        # Starter hub locations are automatically EXPLORED
        if location_id in ["port_azure", "port_azure_docks", "port_azure_market", "the_crimson_parrot"]:
            return MapDiscoveryState.EXPLORED
        return MapDiscoveryState.UNKNOWN

    async def discover_location(
        self,
        character_id: str,
        location_id: str,
        island_id: Optional[str] = None,
        discovered_via: str = "physical_exploration",
        new_state: MapDiscoveryState = MapDiscoveryState.DISCOVERED
    ) -> CharacterMapDiscovery:
        """Permanently advances discovery state on the character's map."""
        if not island_id:
            loc_meta = CANONICAL_LOCATIONS.get(location_id, {})
            island_id = loc_meta.get("island_id", "azure_island")
        existing = await self.discoveries.find_one({"character_id": character_id, "location_id": location_id})
        now = datetime.now(timezone.utc)

        if existing:
            disc = CharacterMapDiscovery(**existing)
            # Only upgrade state if higher tier
            states = list(MapDiscoveryState)
            if states.index(new_state) > states.index(disc.state):
                await self.discoveries.update_one(
                    {"_id": disc.discovery_id},
                    {"$set": {"state": new_state.value, "discovered_via": discovered_via, "discovered_at": now}}
                )
                disc.state = new_state
            return disc

        new_disc = CharacterMapDiscovery(
            character_id=character_id,
            location_id=location_id,
            island_id=island_id,
            state=new_state,
            discovered_via=discovered_via,
            discovered_at=now
        )
        await self.discoveries.insert_one(new_disc.to_mongo())
        logger.info(f"[MAP DISCOVERY] {character_id} discovered {location_id} on {island_id} ({new_state.value})")
        return new_disc

    # --- Map Views (Hierarchy) ---

    async def get_world_map_view(self, character_id: str) -> Dict[str, Any]:
        """Level 1: Global World Map overview."""
        # Find player's current location & island
        char = await db_manager.db.characters.find_one({"_id": character_id})
        curr_loc_id = char.get("location_id", "port_azure_docks") if char else "port_azure_docks"
        loc_meta = CANONICAL_LOCATIONS.get(curr_loc_id, {})
        curr_island_id = loc_meta.get("island_id", "azure_island")

        islands_data = []
        for i_id, isle in CANONICAL_ISLANDS.items():
            islands_data.append({
                "island_id": i_id,
                "name": isle.name,
                "title": isle.title,
                "description": isle.description,
                "controlling_faction": isle.controlling_faction,
                "danger_rating": isle.danger_rating,
                "is_current": (i_id == curr_island_id),
                "coordinates": isle.coordinates
            })

        # Generate Ascii representation
        ascii_map = (
            "```\n"
            "                 PIRATE WARS — GLOBAL NAUTICAL CHART\n"
            "┌────────────────────────────────────────────────────────────────────────┐\n"
            "│  [AZURE ARCHIPELAGO]                                                   │\n"
            "│                                                                        │\n"
            "│  (10,15) ⚓ [Azure Island] (Marine Fortresses, Grand Docks)            │\n"
            "│     │                                                                  │\n"
            "│     └── ~~~ Azure Shipping Lane ~~~                                    │\n"
            "│                                     │                                  │\n"
            "│  (45,60) 🏴‍☠️ [Skull Island]          └── ~~~ Spectral Passage ~~~      │\n"
            "│    (Blackwater Wharf, Jungles)                                  │      │\n"
            "│     │                                                           │      │\n"
            "│     └── ~~~ Ash Corridor ~~~                 (80,25) 🌫️ [Mistfall]     │\n"
            "│                                                (Shrouded Reefs)        │\n"
            "│  (30,85) 🌋 [Cinder Shoals] (Volcanic Drydocks, Outlaw Caldera)        │\n"
            "└────────────────────────────────────────────────────────────────────────┘\n"
            "```"
        )

        return {
            "level": MapLevel.GLOBAL.value,
            "current_island_id": curr_island_id,
            "current_location_id": curr_loc_id,
            "current_position": {
                "current_island_id": curr_island_id,
                "current_location_id": curr_loc_id
            },
            "islands": [
                {
                    **isl,
                    "id": isl["island_id"],
                    "faction": isl["controlling_faction"],
                }
                for isl in islands_data
            ],
            "ascii_chart": ascii_map,
            "ascii_art": ascii_map
        }

    async def get_island_map_view(self, character_id: str, island_id: str) -> Dict[str, Any]:
        """Level 2: Island Map detailing regions, paths, POIs, and fog-of-war."""
        isle = CANONICAL_ISLANDS.get(island_id)
        if not isle:
            raise ValueError(f"Unknown island: {island_id}")

        char = await db_manager.db.characters.find_one({"_id": character_id})
        curr_loc_id = char.get("location_id", "port_azure_docks") if char else "port_azure_docks"

        # Pull all regions for this island
        regions_data = []
        for r_id in isle.regions:
            reg = CANONICAL_REGIONS.get(r_id)
            if not reg:
                continue

            locations_data = []
            for l_id in reg.locations:
                loc_info = CANONICAL_LOCATIONS.get(l_id, {})
                disc_state = await self.get_discovery_state(character_id, l_id)

                is_known = (disc_state != MapDiscoveryState.UNKNOWN)
                name_display = loc_info.get("name", l_id) if is_known else f"❓ Unexplored {loc_info.get('type', 'Area').capitalize()}"
                desc_display = loc_info.get("description", "") if is_known else "Shrouded in fog of war. Inquire at taverns or explore to reveal."

                locations_data.append({
                    "location_id": l_id,
                    "id": l_id,
                    "name": name_display,
                    "type": loc_info.get("type", "wilderness"),
                    "terrain": loc_info.get("type", "wilderness"),
                    "danger": loc_info.get("danger", reg.danger_rating),
                    "discovery_state": disc_state.value,
                    "is_current": (l_id == curr_loc_id or (curr_loc_id.startswith("port_azure") and l_id.startswith("port_azure"))),
                    "is_player_here": (l_id == curr_loc_id or (curr_loc_id.startswith("port_azure") and l_id.startswith("port_azure"))),
                    "description": desc_display,
                    "facilities": loc_info.get("facilities", []) if is_known else []
                })

            regions_data.append({
                "region_id": r_id,
                "id": r_id,
                "name": reg.name,
                "terrain": reg.terrain.value,
                "danger": reg.danger_rating,
                "controlling_faction": reg.controlling_faction,
                "locations": locations_data
            })

        # Fetch custom markers placed by player on this island
        markers = await self.list_markers(character_id, island_id)

        return {
            "level": MapLevel.ISLAND.value,
            "island_id": island_id,
            "id": island_id,
            "island_name": isle.name,
            "name": isle.name,
            "title": isle.title,
            "description": isle.description,
            "danger_rating": isle.danger_rating,
            "controlling_faction": isle.controlling_faction,
            "current_location_id": curr_loc_id,
            "regions": regions_data,
            "markers": [m.model_dump() for m in markers]
        }

    async def get_location_map_view(self, character_id: str, location_id: str) -> Dict[str, Any]:
        """Level 3: Local Location Map detailing streets, establishments, and NPCs."""
        loc = CANONICAL_LOCATIONS.get(location_id)
        if not loc:
            # Check if canonical location prefix matches (e.g. port_azure -> port_azure_docks)
            for k, v in CANONICAL_LOCATIONS.items():
                if k.startswith(location_id) or location_id in k:
                    loc = v
                    location_id = k
                    break
        if not loc:
            return None

        # Mark as explored if visiting
        await self.discover_location(character_id, location_id, loc["island_id"], "physical_visit", MapDiscoveryState.EXPLORED)

        facilities = loc.get("facilities", [])
        if "azure" in loc["island_id"]:
            facilities = facilities + ["salty_anchor_tavern"]

        return {
            "level": MapLevel.LOCATION.value,
            "location_id": location_id,
            "id": location_id,
            "name": loc["name"],
            "island_id": loc["island_id"],
            "island_name": CANONICAL_ISLANDS.get(loc["island_id"]).name if loc["island_id"] in CANONICAL_ISLANDS else loc["island_id"],
            "region_id": loc["region_id"],
            "region_name": CANONICAL_REGIONS.get(loc["region_id"]).name if loc["region_id"] in CANONICAL_REGIONS else loc["region_id"],
            "type": loc["type"],
            "terrain": loc["type"],
            "facilities": facilities,
            "danger": loc["danger"],
            "danger_rating": loc["danger"],
            "discovery_state": MapDiscoveryState.EXPLORED.value,
            "description": loc["description"],
            "npcs_present": ["Mara", "Old Salty Bill", "Inspector Vance"] if "azure" in loc["island_id"] else ["Captain Redhook"]
        }

    # --- Player Markers & Notes ---

    async def add_marker(
        self,
        character_id: str,
        label: str,
        notes: str = "",
        island_id: Optional[str] = None,
        icon: str = "📍",
        location_id: Optional[str] = None,
        **kwargs
    ) -> MapMarker:
        """Places a persistent personal marker with custom notes on the map."""
        # Handle case where island_id was passed as the second argument: add_marker(char_id, "azure_island", "Stash")
        if label in CANONICAL_ISLANDS and not island_id:
            island_id = label
            label = notes or "Waypoint"
            notes = kwargs.get("extra_notes", "")
        if not island_id:
            char = await db_manager.db.characters.find_one({"_id": character_id})
            island_id = char.get("island_id", "azure_island") if char else "azure_island"

        marker = MapMarker(
            character_id=character_id,
            island_id=island_id,
            location_id=location_id,
            label=label,
            notes=notes,
            icon=icon
        )
        await self.markers.insert_one(marker.to_mongo())
        logger.info(f"[MAP MARKER] {character_id} placed marker '{label}' on {island_id}")
        return marker

    async def list_markers(self, character_id: str, island_id: Optional[str] = None) -> List[MapMarker]:
        query: Dict[str, Any] = {"character_id": character_id}
        if island_id:
            query["island_id"] = island_id

        cursor = self.markers.find(query)
        docs = await cursor.to_list(length=50)
        return [MapMarker(**d) for d in docs]

    async def delete_marker(self, character_id: str, marker_id: str) -> bool:
        res = await self.markers.delete_one({"_id": marker_id, "character_id": character_id})
        return res.deleted_count > 0


map_service = MapService()
