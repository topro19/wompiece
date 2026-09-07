from typing import Optional, List, Dict, Any
from app.database.connection import db_manager
from app.game.crews.crew_models import Crew, CrewMember, CrewRole
from app.game.models.character import Character, CharacterStatus
from app.game.economy.ledger import ledger
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class CrewService:
    """Service governing crew organizations, memberships, roles, and treasuries."""

    async def get_crew(self, crew_id: str) -> Optional[Crew]:
        db = db_manager.db
        doc = await db.crews.find_one({"_id": crew_id})
        if not doc:
            return None
        # Parse members back into CrewMember models
        members_data = doc.get("members", {})
        members = {k: CrewMember(**v) for k, v in members_data.items()}
        doc["members"] = members
        return Crew(**doc)

    async def get_crew_by_name(self, name: str) -> Optional[Crew]:
        db = db_manager.db
        doc = await db.crews.find_one({"name": {"$regex": f"^{name.strip()}$", "$options": "i"}})
        if not doc:
            return None
        members_data = doc.get("members", {})
        doc["members"] = {k: CrewMember(**v) for k, v in members_data.items()}
        return Crew(**doc)

    async def create_crew(
        self,
        name: str,
        captain_character_id: str,
        captain_name: str,
        captain_is_ai: bool = False
    ) -> Crew:
        db = db_manager.db

        existing = await self.get_crew_by_name(name)
        if existing:
            raise ValueError(f"A crew named '{name}' already exists.")

        captain_member = CrewMember(
            character_id=captain_character_id,
            character_name=captain_name,
            is_ai=captain_is_ai,
            role=CrewRole.CAPTAIN,
            loyalty=100,
            trust_in_captain=100,
            influence=100,
            dissatisfaction=0
        )

        crew = Crew(
            name=name.strip(),
            captain_id=captain_character_id,
            captain_name=captain_name,
            captain_is_ai=captain_is_ai,
            members={captain_character_id: captain_member}
        )

        await db.crews.insert_one(crew.to_mongo())

        # Update captain character's crew reference
        await db.characters.update_one(
            {"_id": captain_character_id},
            {
                "$set": {
                    "crew_id": crew.crew_id,
                    "crew_role": CrewRole.CAPTAIN.value,
                    "rank": "Captain"
                }
            }
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.PLAYER_JOINED_CREW,
            actor_id=captain_character_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={"crew_name": crew.name, "role": CrewRole.CAPTAIN.value}
        ))

        logger.info(f"Crew '{crew.name}' created under Captain {captain_name}.")
        return crew

    async def join_crew(
        self,
        crew_id: str,
        character_id: str,
        role: CrewRole = CrewRole.DECKHAND
    ) -> Crew:
        db = db_manager.db

        char_doc = await db.characters.find_one({"_id": character_id})
        if not char_doc:
            raise ValueError(f"Character {character_id} not found.")

        if char_doc.get("status") != CharacterStatus.ALIVE.value:
            raise ValueError("Only living characters can join a crew.")

        if char_doc.get("crew_id"):
            raise ValueError("Character is already a member of a crew. Leave current crew first.")

        crew = await self.get_crew(crew_id)
        if not crew:
            raise ValueError(f"Crew {crew_id} not found.")

        member = CrewMember(
            character_id=character_id,
            character_name=char_doc.get("name", "Unknown"),
            is_ai=char_doc.get("is_ai", False),
            role=role,
            loyalty=75,
            trust_in_captain=70,
            influence=20,
            dissatisfaction=10
        )

        # Update Crew in DB
        await db.crews.update_one(
            {"_id": crew_id},
            {"$set": {f"members.{character_id}": member.model_dump()}}
        )

        # Update Character in DB
        await db.characters.update_one(
            {"_id": character_id},
            {"$set": {"crew_id": crew_id, "crew_role": role.value}}
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.PLAYER_JOINED_CREW,
            actor_id=character_id,
            target_ids=[crew.captain_id],
            visibility=EventVisibility.CREW_ONLY,
            state_delta={"crew_id": crew_id, "crew_name": crew.name, "role": role.value}
        ))

        logger.info(f"{char_doc['name']} joined crew '{crew.name}' as {role.value}.")
        return await self.get_crew(crew_id)

    async def leave_crew(self, character_id: str) -> bool:
        db = db_manager.db

        char_doc = await db.characters.find_one({"_id": character_id})
        if not char_doc or not char_doc.get("crew_id"):
            raise ValueError("Character is not in any crew.")

        crew_id = char_doc["crew_id"]
        crew = await self.get_crew(crew_id)
        if not crew:
            raise ValueError("Crew not found.")

        if crew.captain_id == character_id:
            raise ValueError("Captain cannot abandon crew directly. You must transfer leadership or disband.")

        # Remove from crew
        await db.crews.update_one(
            {"_id": crew_id},
            {"$unset": {f"members.{character_id}": ""}}
        )

        # Update Character
        await db.characters.update_one(
            {"_id": character_id},
            {"$set": {"crew_id": None, "crew_role": None}}
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.PLAYER_LEFT_CREW,
            actor_id=character_id,
            visibility=EventVisibility.CREW_ONLY,
            state_delta={"crew_id": crew_id, "crew_name": crew.name}
        ))

        logger.info(f"{char_doc['name']} left crew '{crew.name}'.")
        return True

    async def assign_role(
        self,
        crew_id: str,
        issuer_id: str,
        target_character_id: str,
        new_role: CrewRole
    ) -> CrewMember:
        """Assigns role with authority validation."""
        crew = await self.get_crew(crew_id)
        if not crew:
            raise ValueError("Crew not found.")

        issuer = crew.members.get(issuer_id)
        if not issuer or issuer.role not in [CrewRole.CAPTAIN, CrewRole.VICE_CAPTAIN]:
            raise ValueError("Only the Captain or Vice Captain can promote or assign crew roles.")

        target = crew.members.get(target_character_id)
        if not target:
            raise ValueError("Target character is not in this crew.")

        if new_role == CrewRole.CAPTAIN and issuer.role != CrewRole.CAPTAIN:
            raise ValueError("Only the current Captain can relinquish Captaincy.")

        db = db_manager.db

        # If transferring captaincy
        if new_role == CrewRole.CAPTAIN:
            await db.crews.update_one(
                {"_id": crew_id},
                {
                    "$set": {
                        "captain_id": target_character_id,
                        "captain_name": target.character_name,
                        "captain_is_ai": target.is_ai,
                        f"members.{target_character_id}.role": CrewRole.CAPTAIN.value,
                        f"members.{issuer_id}.role": CrewRole.VICE_CAPTAIN.value,
                    }
                }
            )
            await db.characters.update_one({"_id": target_character_id}, {"$set": {"crew_role": CrewRole.CAPTAIN.value, "rank": "Captain"}})
            await db.characters.update_one({"_id": issuer_id}, {"$set": {"crew_role": CrewRole.VICE_CAPTAIN.value, "rank": "Vice Captain"}})
        else:
            await db.crews.update_one(
                {"_id": crew_id},
                {"$set": {f"members.{target_character_id}.role": new_role.value}}
            )
            await db.characters.update_one({"_id": target_character_id}, {"$set": {"crew_role": new_role.value}})

        await event_bus.publish(WorldEvent(
            event_type=EventType.CREW_PROMOTION,
            actor_id=issuer_id,
            target_ids=[target_character_id],
            visibility=EventVisibility.CREW_ONLY,
            state_delta={"new_role": new_role.value, "crew_id": crew_id}
        ))

        updated_crew = await self.get_crew(crew_id)
        return updated_crew.members[target_character_id]

    async def deposit_to_treasury(self, crew_id: str, character_id: str, amount: int):
        """Authoritative economic transfer into the crew chest."""
        crew = await self.get_crew(crew_id)
        if not crew:
            raise ValueError("Crew not found.")

        if character_id not in crew.members:
            raise ValueError("Must be a member of this crew to deposit.")

        import uuid
        tx = await ledger.transfer(
            sender_id=character_id,
            receiver_id=crew_id,
            amount=amount,
            reason=f"Deposit into {crew.name} Treasury",
            idempotency_key=f"crew_dep_{crew_id}_{character_id}_{uuid.uuid4()}"
        )
        return tx

    async def ensure_starter_ai_crews(self):
        """Initializes canonical AI crews like 'The Black Tide' led by Captain Redhook."""
        existing = await self.get_crew_by_name("The Black Tide")
        if existing:
            return existing

        db = db_manager.db

        # 1. Create AI Captain Redhook
        redhook = Character(
            name="Captain Redhook",
            is_ai=True,
            status=CharacterStatus.ALIVE,
            rank="Infamous Captain",
            bounty=320000,
            infamy=78,
            wealth=2500,
            location_id="the_crimson_parrot"
        )
        await db.characters.insert_one(redhook.to_mongo())

        # 2. Create AI Officers
        navigator = Character(
            name="Old Salty Bill",
            is_ai=True,
            status=CharacterStatus.ALIVE,
            rank="Navigator",
            wealth=200,
            location_id="the_crimson_parrot"
        )
        doctor = Character(
            name="Dr. Bones",
            is_ai=True,
            status=CharacterStatus.ALIVE,
            rank="Ship Doctor",
            wealth=300,
            location_id="the_crimson_parrot"
        )
        await db.characters.insert_one(navigator.to_mongo())
        await db.characters.insert_one(doctor.to_mongo())

        # 3. Create Crew
        crew = await self.create_crew(
            name="The Black Tide",
            captain_character_id=redhook.character_id,
            captain_name=redhook.name,
            captain_is_ai=True
        )

        # 4. Add AI Officers
        await self.join_crew(crew.crew_id, navigator.character_id, role=CrewRole.NAVIGATOR)
        await self.join_crew(crew.crew_id, doctor.character_id, role=CrewRole.DOCTOR)

        # Deposit starter treasury
        await db.crews.update_one({"_id": crew.crew_id}, {"$set": {"treasury": 5000}})
        logger.info("Initialized canonical AI crew 'The Black Tide' with Captain Redhook and officers.")
        return await self.get_crew(crew.crew_id)


crew_service = CrewService()
