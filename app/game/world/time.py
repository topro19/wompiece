from datetime import datetime, timezone
from pydantic import BaseModel, Field
from app.database.connection import db_manager


class WorldClock(BaseModel):
    day: int = 1
    hour: int = 2
    minute: int = 15
    weather: str = "Dense Fog"
    tide: str = "Low Tide"


class WorldTimeService:
    """Maintains persistent in-game world time and environmental conditions."""

    async def get_world_time(self) -> WorldClock:
        db = db_manager.db
        state = await db.world_state.find_one({"_id": "global_clock"})
        if not state:
            clock = WorldClock()
            await db.world_state.update_one(
                {"_id": "global_clock"},
                {"$set": clock.model_dump()},
                upsert=True
            )
            return clock
        return WorldClock(
            day=state.get("day", 1),
            hour=state.get("hour", 2),
            minute=state.get("minute", 15),
            weather=state.get("weather", "Dense Fog"),
            tide=state.get("tide", "Low Tide")
        )

    async def advance_time(self, minutes: int = 15) -> WorldClock:
        db = db_manager.db
        clock = await self.get_world_time()

        total_minutes = clock.minute + minutes
        add_hours = total_minutes // 60
        new_minute = total_minutes % 60

        total_hours = clock.hour + add_hours
        add_days = total_hours // 24
        new_hour = total_hours % 24
        new_day = clock.day + add_days

        await db.world_state.update_one(
            {"_id": "global_clock"},
            {
                "$set": {
                    "day": new_day,
                    "hour": new_hour,
                    "minute": new_minute
                }
            },
            upsert=True
        )
        return WorldClock(
            day=new_day,
            hour=new_hour,
            minute=new_minute,
            weather=clock.weather,
            tide=clock.tide
        )

    def format_clock(self, clock: WorldClock) -> str:
        am_pm = "AM" if clock.hour < 12 else "PM"
        display_hour = clock.hour % 12
        if display_hour == 0:
            display_hour = 12
        return f"Day {clock.day}, {display_hour:02d}:{clock.minute:02d} {am_pm} ({clock.weather}, {clock.tide})"


world_time_service = WorldTimeService()
