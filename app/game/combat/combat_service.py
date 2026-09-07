import random
from typing import Dict, Any, Optional
from app.database.connection import db_manager
from app.game.models.character import Character, CharacterStatus, Faction
from app.game.models.death import permadeath_service, CauseOfDeath
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class CombatService:
    """Server-authoritative combat, damage resolution, wanted escalation, and permadeath execution."""

    async def resolve_attack(
        self,
        attacker_id: str,
        defender_id: str,
        is_lethal: bool = True
    ) -> Dict[str, Any]:
        db = db_manager.db

        attacker_doc = await db.characters.find_one({"_id": attacker_id})
        defender_doc = await db.characters.find_one({"_id": defender_id})

        if not attacker_doc or not defender_doc:
            raise ValueError("Attacker or defender not found.")

        if attacker_doc.get("status") != CharacterStatus.ALIVE.value or defender_doc.get("status") != CharacterStatus.ALIVE.value:
            raise ValueError("Dead characters cannot fight.")

        attacker_name = attacker_doc.get("name", "Attacker")
        defender_name = defender_doc.get("name", "Defender")

        # 1. Deterministic Combat Roll (Hit Chance 80%)
        hit_roll = random.random()
        if hit_roll > 0.85:
            return {
                "hit": False,
                "damage": 0,
                "narrative": f"{attacker_name} swung wildly, but {defender_name} dodged the blow!"
            }

        # 2. Damage Calculation
        base_damage = random.randint(25, 45)
        is_crit = random.random() < 0.20
        final_damage = int(base_damage * 1.5) if is_crit else base_damage

        current_hp = defender_doc.get("health", 100)
        remaining_hp = max(0, current_hp - final_damage)

        # Update Defender Health
        await db.characters.update_one(
            {"_id": defender_id},
            {"$set": {"health": remaining_hp}}
        )

        crit_str = " CRITICAL STRIKE!" if is_crit else ""
        narrative = f"{attacker_name} struck {defender_name} for {final_damage} damage!{crit_str}"

        permadeath_occurred = False
        escalation_info = None

        # 3. Lethal Permadeath Resolution
        if remaining_hp == 0 and is_lethal:
            permadeath_occurred = True
            death_rec = await permadeath_service.execute_permadeath(
                character_id=defender_id,
                cause=CauseOfDeath.COMBAT,
                location_id=defender_doc.get("location_id", "port_azure_docks"),
                killer_id=attacker_id,
                killer_name=attacker_name
            )

            narrative += f"\n☠️ **FATAL BLOW!** {defender_name} has permanently fallen in battle!"

            # Escalation: Murder of Marine or player increases wanted level & bounty
            if defender_doc.get("faction") == Faction.MARINE.value or not attacker_doc.get("is_ai"):
                escalation_info = await self.escalate_wanted_level(
                    character_id=attacker_id,
                    added_bounty=75000,
                    reason=f"Murder of {defender_name}"
                )

        return {
            "hit": True,
            "damage": final_damage,
            "defender_remaining_hp": remaining_hp,
            "permadeath": permadeath_occurred,
            "escalation": escalation_info,
            "narrative": narrative
        }

    async def escalate_wanted_level(
        self,
        character_id: str,
        added_bounty: int,
        reason: str
    ) -> Dict[str, Any]:
        db = db_manager.db

        char = await db.characters.find_one({"_id": character_id})
        if not char:
            return {}

        current_wanted = char.get("wanted_level", 0)
        new_wanted = min(6, current_wanted + 1)
        new_bounty = char.get("bounty", 0) + added_bounty

        task_force_assigned = None
        if new_wanted >= 4:
            task_force_assigned = "Task Force 'Iron Tide' (Elite Marine Commander Pursuit)"

        await db.characters.update_one(
            {"_id": character_id},
            {
                "$set": {
                    "wanted_level": new_wanted,
                    "bounty": new_bounty
                }
            }
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.BOUNTY_ISSUED,
            actor_id=character_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={
                "wanted_level": new_wanted,
                "bounty": new_bounty,
                "added_bounty": added_bounty,
                "task_force": task_force_assigned,
                "reason": reason
            }
        ))

        logger.warning(
            f"[WANTED ESCALATION] {char['name']} is now WANTED LEVEL {new_wanted}! Bounty: {new_bounty:,} Gold. Task Force: {task_force_assigned}."
        )

        return {
            "wanted_level": new_wanted,
            "bounty": new_bounty,
            "task_force": task_force_assigned
        }


combat_service = CombatService()
