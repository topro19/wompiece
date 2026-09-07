import random
import asyncio
from typing import Optional, List, Dict, Any
from app.database.connection import db_manager
from app.game.simulation.scheduler_models import TickTier, TickResult
from app.game.world.time import world_time_service, WorldClock
from app.game.crews.crew_models import Crew
from app.game.investigations.case_models import CaseStatus
from app.game.investigations.case_service import investigation_service
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


WEATHER_SYSTEMS = [
    "Fair Winds & Clear Skies",
    "Dense Sea Fog",
    "Tropical Rain Squall",
    "Gale-Force Wind",
    "Stagnant Calm Waters"
]

TIDE_SYSTEMS = ["High Tide", "Ebb Tide", "Low Tide", "Flood Tide"]


class SimulationScheduler:
    """Authoritative background world simulation engine executing tiered priority ticks."""

    def __init__(self):
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

    async def tick_high(self) -> TickResult:
        """High-frequency tick: real-time combat checks, immediate expiration."""
        db = db_manager.db
        entities_count = 0

        # Scan active combat or transient conditions if any
        # Check for wounded characters
        res = await db.characters.count_documents({"status": "ALIVE", "health": {"$lt": 100}})
        entities_count += res

        result = TickResult(
            tier=TickTier.HIGH,
            entities_processed=entities_count,
            events_emitted=1,
            details={"wounded_characters": res},
            summary="High-tier simulation tick completed: transient checks verified."
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.SIMULATION_TICK,
            visibility=EventVisibility.PRIVATE,
            state_delta=result.model_dump()
        ))

        return result

    async def tick_medium(self) -> TickResult:
        """Medium-frequency tick: world clock, weather, business revenue, crew mutiny, NPC routines."""
        db = db_manager.db
        events_emitted = 0
        entities_processed = 0
        details = {}

        # 1. Advance World Clock (30 mins) & Shift Environmental Conditions
        new_clock = await world_time_service.advance_time(minutes=30)
        new_weather = random.choice(WEATHER_SYSTEMS)
        new_tide = random.choice(TIDE_SYSTEMS)
        await db.world_state.update_one(
            {"_id": "global_clock"},
            {"$set": {"weather": new_weather, "tide": new_tide}}
        )
        details["weather"] = new_weather
        details["tide"] = new_tide
        details["world_time"] = world_time_service.format_clock(new_clock)

        # 2. Process Business Passive Operations
        businesses_cursor = db.businesses.find({})
        biz_count = 0
        async for bdoc in businesses_cursor:
            biz_count += 1
            # Add modest passive foot-traffic commerce to business daily revenue
            daily_growth = random.randint(15, 45)
            await db.businesses.update_one(
                {"_id": bdoc["_id"]},
                {"$inc": {"daily_revenue": daily_growth}}
            )
        entities_processed += biz_count
        details["businesses_processed"] = biz_count

        # 3. Process Crew Dynamics & Mutiny Risk
        crews_cursor = db.crews.find({})
        crew_count = 0
        mutinies_triggered = 0
        async for cdoc in crews_cursor:
            crew_count += 1
            crew = Crew(**cdoc)
            risk = crew.calculate_mutiny_risk()
            await db.crews.update_one(
                {"_id": crew.crew_id},
                {"$set": {"mutiny_risk": risk}}
            )
            if risk >= 75.0:
                mutinies_triggered += 1
                await event_bus.publish(WorldEvent(
                    event_type=EventType.MUTINY_STARTED,
                    actor_id=crew.crew_id,
                    location_id=crew.home_port,
                    visibility=EventVisibility.PUBLIC,
                    state_delta={"crew_id": crew.crew_id, "crew_name": crew.name, "mutiny_risk": risk}
                ))
                events_emitted += 1
        entities_processed += crew_count
        details["crews_processed"] = crew_count
        details["mutinies_triggered"] = mutinies_triggered

        # 4. Autonomous NPC Goal Progression
        npc_actions = []
        # A. Captain Redhook (Pirate Captain)
        redhook = await db.characters.find_one({"name": "Captain Redhook", "status": "ALIVE"})
        if redhook:
            entities_processed += 1
            npc_actions.append("Captain Redhook inspected the Black Tide armory at Skull Rock Anchorage.")
            await event_bus.publish(WorldEvent(
                event_type=EventType.NPC_GOAL_PROGRESSED,
                actor_id=redhook["_id"],
                location_id=redhook.get("location_id", "skull_rock_anchorage"),
                visibility=EventVisibility.PUBLIC,
                state_delta={"npc": "Captain Redhook", "action": "prepping_raids"}
            ))
            events_emitted += 1

        # B. Inspector Vance (Marine Investigator)
        vance = await db.characters.find_one({"name": "Inspector Vance", "status": "ALIVE"})
        if vance:
            entities_processed += 1
            # Check open cases that have evidence
            open_case = await db.cases.find_one({"status": CaseStatus.OPEN.value})
            if open_case and len(open_case.get("evidence", [])) >= 2:
                npc_actions.append(f"Inspector Vance advanced Case #{open_case['case_id']} to warrant review.")
                await db.cases.update_one(
                    {"_id": open_case["_id"]},
                    {"$set": {"status": CaseStatus.UNDER_REVIEW.value}}
                )
                await event_bus.publish(WorldEvent(
                    event_type=EventType.CASE_STATUS_CHANGED,
                    actor_id=vance["_id"],
                    location_id="marine_headquarters",
                    visibility=EventVisibility.PUBLIC,
                    state_delta={"case_id": open_case["case_id"], "new_status": CaseStatus.UNDER_REVIEW.value}
                ))
                events_emitted += 1
            else:
                npc_actions.append("Inspector Vance conducted port patrols and cross-referenced shipping manifests.")

        details["npc_actions"] = npc_actions

        result = TickResult(
            tier=TickTier.MEDIUM,
            entities_processed=entities_processed,
            events_emitted=events_emitted + 1,
            details=details,
            summary=f"Medium simulation tick completed. Time: {details['world_time']}. Weather: {new_weather}."
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.SIMULATION_TICK,
            visibility=EventVisibility.PUBLIC,
            state_delta=result.model_dump()
        ))

        return result

    async def tick_low(self) -> TickResult:
        """Low-frequency tick: daily market cycles, statute of limitations, bounty escalation."""
        db = db_manager.db
        entities_processed = 0
        events_emitted = 0
        details = {}

        # 1. Wanted Level Bounty Escalation
        wanted_cursor = db.characters.find({"wanted_level": {"$gt": 0}, "status": "ALIVE"})
        escalated_count = 0
        async for wanted_char in wanted_cursor:
            entities_processed += 1
            current_bounty = wanted_char.get("bounty", 0)
            # Increase active bounties slightly over time to simulate Marine priority
            bounty_increase = wanted_char.get("wanted_level", 1) * 25
            await db.characters.update_one(
                {"_id": wanted_char["_id"]},
                {"$inc": {"bounty": bounty_increase}}
            )
            escalated_count += 1
        details["bounties_escalated"] = escalated_count

        # 2. Market price shifts or reset daily revenue stats
        details["market_stability"] = "Normal colonial supply lines"

        result = TickResult(
            tier=TickTier.LOW,
            entities_processed=entities_processed,
            events_emitted=events_emitted + 1,
            details=details,
            summary="Low-frequency world cycle completed: bounties adjusted and market stability verified."
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.SIMULATION_TICK,
            visibility=EventVisibility.PUBLIC,
            state_delta=result.model_dump()
        ))

        return result

    async def advance_time(self, hours: float) -> List[TickResult]:
        """Manually or administratively fast-forwards world time, running simulation ticks."""
        if hours <= 0:
            raise ValueError("Hours must be positive.")

        results: List[TickResult] = []
        minutes_to_advance = int(hours * 60)

        # 1. Advance clock
        await world_time_service.advance_time(minutes=minutes_to_advance)

        # 2. Execute medium tick
        med_result = await self.tick_medium()
        results.append(med_result)

        # 3. If advanced >= 24 hours, execute low tick
        if hours >= 24.0:
            low_result = await self.tick_low()
            results.append(low_result)

        logger.info(f"Advanced world time by {hours} hours ({len(results)} tick cycles executed).")
        return results


simulation_scheduler = SimulationScheduler()
