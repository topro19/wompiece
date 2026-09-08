import random
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from app.database.connection import db_manager
from app.game.npcs.npc_models import (
    WorldNPC,
    NPCFaction,
    NPCArchetype,
    NPCScheduleEntry,
    NPCGoal,
    NPCCombatStats
)
from app.game.world.location import location_service, Location
from app.services.logger import logger

FIRST_NAMES = [
    "Jack", "Edward", "Anne", "Mary", "Bartholomew", "Henry", "Grace", "Calico",
    "Samuel", "Charles", "Morgan", "William", "Eliza", "Gideon", "Silas", "Blythe",
    "Finley", "Ronan", "Caleb", "Thaddeus", "Cassian", "Kaelen", "Dorothy", "Maeve",
    "Orion", "Garrett", "Tobias", "Jocelyn", "Barnaby", "Vance", "Coyle", "Redhook"
]

EPITHETS = [
    "Iron-Grip", "Salty", "One-Eye", "The Bold", "Whisper", "Kraken-Bane", "Silver-Tongue",
    "The Quick", "Black-Tide", "Crow-Feather", "Reef-Stalker", "Drunken", "Gallows", "Scar-Face"
]

LAST_NAMES = [
    "Drake", "Morgan", "Vane", "Teach", "Bonny", "Read", "Avery", "Kidd",
    "Low", "Bellamy", "Hawkins", "Flint", "Silver", "Bones", "Cross", "Sterling",
    "Vance", "Barlow", "Mercer", "Aldridge", "Castor", "Finch", "Lockwood"
]

PERSONALITY_TRAITS = [
    "Honorable", "Corrupt", "Strict", "Lazy", "Ambitious", "Suspicious",
    "Friendly", "Ruthless", "Easily bribed", "Incorruptible", "Greedy",
    "Cautious", "Hot-tempered", "Proud", "Witty", "Paranoid"
]

COMMON_ACTIVITIES = {
    "docks": [
        "Inspecting cargo crates and manifests at the pier",
        "Watching sea birds wheel above incoming schooners",
        "Coiling mooring ropes beside a docked brigantine",
        "Mending torn sails with a bone needle",
        "Arguing with a harbor purser over dockage tariffs"
    ],
    "tavern": [
        "Sipping spiced grog in a shadowy corner booth",
        "Rolling knuckle-bone dice on a grease-stained table",
        "Singing a bawdy sea shanty with passing sailors",
        "Eavesdropping on merchant sea-captains near the hearth",
        "Nursing a bruised knuckle after a minor bar scuffle"
    ],
    "market": [
        "Haggling aggressively over a crate of dried citrus",
        "Checking the edge of a fresh steel cutlass at an armorer stall",
        "Weighing sacks of cloves and cinnamon on bronze scales",
        "Keeping a vigilant hand on their coin purse amid the throng",
        "Peddling contraband tobacco from beneath a burlap coat"
    ],
    "marine_headquarters": [
        "Drilling with bayonets in the central parade ground",
        "Filing arrest warrants and logging bounty proclamations",
        "Polishing naval buttons and inspecting iron flintlocks",
        "Interrogating a nervous dock laborer behind barred cells",
        "Reviewing maritime patrol routes across the archipelago"
    ],
    "smugglers_cove": [
        "Offloading unmarked rum kegs under the tidal spray",
        "Concealing an illicit cache beneath sea-cave boulders",
        "Sharpening boarding hooks in the dim lantern light",
        "Whispering passwords with an arriving rowboat crew"
    ],
    "default": [
        "Observing the flow of harbor traffic",
        "Sharing maritime gossip with passing strangers",
        "Counting brass coins in the palm of their hand",
        "Keeping an eye out for Marine patrols or pirate informants"
    ]
}


class NPCPopulationService:
    """Authoritative baseline population seeder and manager for all game islands and settlements."""

    def _generate_name(self) -> str:
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        if random.random() < 0.35:
            epithet = random.choice(EPITHETS)
            return f'{first} "{epithet}" {last}'
        return f"{first} {last}"

    def _create_schedule(self, island_locations: List[Location], primary_facility: str) -> List[NPCScheduleEntry]:
        """Generates a 4-block 24-hour deterministic schedule matching island facilities."""
        schedule = [
            NPCScheduleEntry(start_hour=6, end_hour=11, preferred_facility="docks", activity_description="Morning dockside preparations and ship inspections"),
            NPCScheduleEntry(start_hour=12, end_hour=17, preferred_facility="market", activity_description="Afternoon business, bartering, and market errands"),
            NPCScheduleEntry(start_hour=18, end_hour=23, preferred_facility="tavern", activity_description="Evening tavern drinking, gambling, and rumors"),
            NPCScheduleEntry(start_hour=0, end_hour=5, preferred_facility="residence", activity_description="Late night resting and watchkeeping")
        ]
        return schedule

    def _generate_archetype_npc(self, archetype: NPCArchetype, location: Location, island_locations: List[Location]) -> WorldNPC:
        name = self._generate_name()
        traits = random.sample(PERSONALITY_TRAITS, k=random.randint(2, 3))
        
        # Faction & Stats based on archetype
        if "MARINE" in archetype.value:
            faction = NPCFaction.MARINE
            wanted_status = 0
            wealth = random.randint(30, 150)
            health = 100 + (20 if "SERGEANT" in archetype.value or "OFFICER" in archetype.value else 0)
            attack = 20 if "OFFICER" in archetype.value or "COMMANDER" in archetype.value else 14
            defense = 15
            level = 3 if "COMMANDER" in archetype.value else (2 if "OFFICER" in archetype.value else 1)
            inventory = [{"name": "Marine Regulation Cutlass", "type": "weapon"}, {"name": "Service Flintlock", "type": "weapon"}]
            primary_fac = "marine_headquarters"
            goal = NPCGoal(goal_type="SOLVE_CASE", description="Investigate contraband smuggling networks in the harbor", target_count=3)
            occupation = archetype.value.replace("MARINE_", "").capitalize() + " in the Marine Garrison"
        elif "PIRATE" in archetype.value or archetype in [NPCArchetype.SMUGGLER, NPCArchetype.RUTHLESS_RAIDER, NPCArchetype.DRIFTER]:
            faction = NPCFaction.PIRATE
            wanted_status = random.randint(150, 1200) if archetype != NPCArchetype.ROOKIE_PIRATE else 50
            wealth = random.randint(25, 250)
            health = 90 + (30 if archetype in [NPCArchetype.PIRATE_CAPTAIN, NPCArchetype.PIRATE_VETERAN, NPCArchetype.RIVAL_CAPTAIN] else 0)
            attack = 18 if archetype in [NPCArchetype.PIRATE_CAPTAIN, NPCArchetype.RUTHLESS_RAIDER] else 13
            defense = 12
            level = 3 if archetype in [NPCArchetype.PIRATE_CAPTAIN, NPCArchetype.RIVAL_CAPTAIN] else 1
            inventory = [{"name": "Notched Boarding Saber", "type": "weapon"}, {"name": "Flask of Spiced Rum", "type": "consumable"}]
            primary_fac = "tavern"
            goal = NPCGoal(goal_type="RECRUIT_CREW", description="Recruit willing hands for the next ocean raid", target_count=2)
            occupation = archetype.value.replace("_", " ").title()
        elif archetype == NPCArchetype.MERCHANT:
            faction = NPCFaction.MERCHANT
            wanted_status = 0
            wealth = random.randint(150, 600)
            health = 80
            attack = 8
            defense = 8
            level = 1
            inventory = [{"name": "Trade Ledger", "type": "tool"}, {"name": "Pocket Coin Scale", "type": "tool"}]
            primary_fac = "market"
            goal = NPCGoal(goal_type="MAKE_MONEY", description="Secure profitable escort contracts for high-value silk cargo", target_count=300)
            occupation = "Maritime Merchant"
        else:
            faction = NPCFaction.CIVILIAN
            wanted_status = 0
            wealth = random.randint(10, 60)
            health = 80
            attack = 10
            defense = 8
            level = 1
            inventory = [{"name": "Pocket Knife", "type": "tool"}, {"name": "Coarse Bread & Cheese", "type": "consumable"}]
            primary_fac = "docks" if archetype in [NPCArchetype.DOCKWORKER, NPCArchetype.SAILOR, NPCArchetype.FISHERMAN] else "tavern"
            goal = NPCGoal(goal_type="MAKE_MONEY", description="Earn enough daily wages to purchase fresh ship timber", target_count=50)
            occupation = archetype.value.title()

        schedule = self._create_schedule(island_locations, primary_fac)
        initial_activity = random.choice(COMMON_ACTIVITIES.get(primary_fac, COMMON_ACTIVITIES["default"]))

        return WorldNPC(
            name=name,
            faction=faction,
            role=archetype,
            occupation=occupation,
            island_id=location.island,
            home_location_id=location.location_id,
            location_id=location.location_id,
            personality=traits,
            traits=traits,
            goals=[goal],
            wealth=wealth,
            inventory=inventory,
            combat_stats=NPCCombatStats(health=health, max_health=health, attack=attack, defense=defense, level=level),
            schedule=schedule,
            current_activity=initial_activity,
            secrets=[f"Keeps a hidden stash near {location.name}"],
            known_information=[f"Heard rumors of heavy ship movement near {location.island}"],
            wanted_status=wanted_status
        )

    async def seed_location_population(self, location_id: str) -> List[WorldNPC]:
        """Generates and persists baseline population for a specific location based on its facilities."""
        loc = location_service.get_location(location_id)
        if not loc or loc.is_sea_zone:
            return []

        all_locs = list(location_service._locations.values())
        island_locs = [l for l in all_locs if l.island == loc.island and not l.is_sea_zone]

        archetypes_to_spawn: List[NPCArchetype] = []

        facs = loc.facilities
        if any("tavern" in f for f in facs):
            archetypes_to_spawn.extend([
                NPCArchetype.BARTENDER,
                NPCArchetype.SAILOR,
                NPCArchetype.SAILOR,
                NPCArchetype.PIRATE_VETERAN,
                NPCArchetype.PIRATE_GAMBLER,
                NPCArchetype.GAMBLER,
                NPCArchetype.INFORMANT,
                NPCArchetype.MERCHANT
            ])
        elif any("dock" in f or "wharf" in f or "shipyard" in f for f in facs):
            archetypes_to_spawn.extend([
                NPCArchetype.DOCKWORKER,
                NPCArchetype.DOCKWORKER,
                NPCArchetype.SAILOR,
                NPCArchetype.FISHERMAN,
                NPCArchetype.MERCHANT,
                NPCArchetype.ROOKIE_PIRATE,
                NPCArchetype.MARINE_SOLDIER,
                NPCArchetype.SMUGGLER
            ])
        elif any("market" in f or "store" in f or "trade" in f for f in facs):
            archetypes_to_spawn.extend([
                NPCArchetype.MERCHANT,
                NPCArchetype.MERCHANT,
                NPCArchetype.GUARD,
                NPCArchetype.THIEF,
                NPCArchetype.APOTHECARY,
                NPCArchetype.SAILOR,
                NPCArchetype.MARINE_RECRUIT
            ])
        elif any("marine" in f or "armory" in f or "interrogation" in f for f in facs):
            archetypes_to_spawn.extend([
                NPCArchetype.MARINE_COMMANDER,
                NPCArchetype.MARINE_OFFICER,
                NPCArchetype.MARINE_SERGEANT,
                NPCArchetype.MARINE_INVESTIGATOR,
                NPCArchetype.MARINE_INTEL_OFFICER,
                NPCArchetype.MARINE_SOLDIER,
                NPCArchetype.MARINE_SOLDIER,
                NPCArchetype.MARINE_RECRUIT
            ])
        elif any("black_market" in f or "hidden_dock" in f or "cove" in f for f in facs):
            archetypes_to_spawn.extend([
                NPCArchetype.PIRATE_CAPTAIN,
                NPCArchetype.SMUGGLER,
                NPCArchetype.RUTHLESS_RAIDER,
                NPCArchetype.PIRATE_INFORMANT,
                NPCArchetype.PIRATE_VETERAN,
                NPCArchetype.TREASURE_HUNTER
            ])
        else:
            archetypes_to_spawn.extend([
                NPCArchetype.HUNTER,
                NPCArchetype.SAILOR,
                NPCArchetype.DRIFTER
            ])

        spawned_npcs = [self._generate_archetype_npc(arch, loc, island_locs) for arch in archetypes_to_spawn]

        db = db_manager.db
        docs = [npc.to_mongo() for npc in spawned_npcs]
        if docs:
            await db.npcs.insert_many(docs)
            logger.info(f"[NPC POPULATION] Seeded {len(docs)} persistent NPCs at {location_id} ({loc.island})")

        return spawned_npcs

    async def get_npcs_at_location(self, location_id: str) -> List[WorldNPC]:
        """Retrieves active alive NPCs physically present at location, auto-seeding if empty."""
        db = db_manager.db
        cursor = db.npcs.find({"location_id": location_id, "alive": True})
        npcs = []
        async for doc in cursor:
            npcs.append(WorldNPC(**doc))

        if not npcs:
            loc = location_service.get_location(location_id)
            if loc and not loc.is_sea_zone:
                npcs = await self.seed_location_population(location_id)

        return npcs

    async def ensure_world_populated(self) -> int:
        """Validates that every non-sea location in the world has a baseline population."""
        total_seeded = 0
        db = db_manager.db
        for loc_id, loc in location_service._locations.items():
            if loc.is_sea_zone:
                continue
            count = await db.npcs.count_documents({"location_id": loc_id, "alive": True})
            if count < 3:
                new_npcs = await self.seed_location_population(loc_id)
                total_seeded += len(new_npcs)
        return total_seeded

    async def simulate_npc_schedules(self, current_hour: int) -> Dict[str, Any]:
        """Moves NPCs across connected locations according to their schedules and advances goals."""
        db = db_manager.db
        cursor = db.npcs.find({"alive": True})
        moved_count = 0
        goals_advanced = 0

        async for doc in cursor:
            npc = WorldNPC(**doc)
            target_fac = "docks"
            for entry in npc.schedule:
                if entry.start_hour <= current_hour <= entry.end_hour:
                    target_fac = entry.preferred_facility
                    break

            current_loc = location_service.get_location(npc.location_id)
            if not current_loc:
                continue

            if not any(target_fac in f for f in current_loc.facilities):
                destinations = location_service.get_destinations(npc.location_id)
                best_dest = None
                for d in destinations:
                    if d.island == current_loc.island and not d.is_sea_zone:
                        if any(target_fac in f for f in d.facilities):
                            best_dest = d
                            break

                if best_dest and best_dest.location_id != npc.location_id:
                    new_act = random.choice(COMMON_ACTIVITIES.get(target_fac, COMMON_ACTIVITIES["default"]))
                    await db.npcs.update_one(
                        {"_id": npc.npc_id},
                        {"$set": {
                            "location_id": best_dest.location_id,
                            "current_activity": new_act,
                            "last_seen": datetime.now(timezone.utc)
                        }}
                    )
                    moved_count += 1

            if npc.goals and random.random() < 0.15:
                active_goal = npc.goals[0]
                if active_goal.status == "ACTIVE":
                    new_prog = active_goal.current_progress + 1
                    status = "COMPLETED" if new_prog >= active_goal.target_count else "ACTIVE"
                    await db.npcs.update_one(
                        {"_id": npc.npc_id},
                        {"$set": {
                            "goals.0.current_progress": new_prog,
                            "goals.0.status": status
                        }}
                    )
                    goals_advanced += 1

        return {"npcs_moved": moved_count, "goals_advanced": goals_advanced}


npc_population_service = NPCPopulationService()
