from typing import Optional, List, Dict, Any
from app.database.connection import db_manager
from app.game.identity.identity_models import IdentityAlias
from app.game.economy.ledger import ledger
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class IdentityService:
    """Service governing forged civilian identities, paper trails, and exposure."""

    async def get_alias(self, alias_id: str) -> Optional[IdentityAlias]:
        db = db_manager.db
        doc = await db.identities.find_one({"_id": alias_id})
        return IdentityAlias(**doc) if doc else None

    async def get_alias_by_name(self, alias_name: str) -> Optional[IdentityAlias]:
        db = db_manager.db
        doc = await db.identities.find_one({"alias_name": {"$regex": f"^{alias_name.strip()}$", "$options": "i"}})
        return IdentityAlias(**doc) if doc else None

    async def get_aliases_for_character(self, character_id: str) -> List[IdentityAlias]:
        db = db_manager.db
        cursor = db.identities.find({"true_character_id": character_id})
        docs = await cursor.to_list(length=20)
        return [IdentityAlias(**d) for d in docs]

    async def create_alias(
        self,
        character_id: str,
        alias_name: str,
        legal_occupation: str = "Merchant",
        fee: int = 150
    ) -> IdentityAlias:
        """Forges an alternate identity. Requires gold for counterfeit papers."""
        db = db_manager.db

        char_doc = await db.characters.find_one({"_id": character_id})
        if not char_doc:
            raise ValueError(f"Character {character_id} not found.")

        # Check if alias name is already registered
        existing = await self.get_alias_by_name(alias_name)
        if existing:
            raise ValueError(f"An identity with the name '{alias_name}' already exists.")

        # Deduct fee for counterfeit papers if applicable
        if fee > 0:
            import uuid
            await ledger.transfer(
                sender_id=character_id,
                receiver_id="government_registry_black_market",
                amount=fee,
                reason=f"Forged identity documents for '{alias_name}'",
                idempotency_key=f"alias_fee_{character_id}_{uuid.uuid4()}"
            )

        alias = IdentityAlias(
            true_character_id=character_id,
            true_name=char_doc.get("name", "Unknown"),
            alias_name=alias_name.strip(),
            legal_occupation=legal_occupation,
            legal_faction="Civilian",
            is_active=True
        )
        await db.identities.insert_one(alias.to_mongo())

        # Emit SECRET world event
        await event_bus.publish(WorldEvent(
            event_type=EventType.ALIAS_CREATED,
            actor_id=character_id,
            visibility=EventVisibility.SECRET,
            state_delta={
                "true_character_id": character_id,
                "alias_name": alias.alias_name,
                "legal_occupation": legal_occupation
            }
        ))

        logger.info(f"Character {char_doc['name']} created forged alias '{alias.alias_name}'.")
        return alias

    async def link_evidence(self, alias_id: str, evidence_id: str, suspicion_boost: int = 25) -> IdentityAlias:
        """Links investigative evidence to an alias, potentially exposing the true identity."""
        db = db_manager.db
        alias = await self.get_alias(alias_id)
        if not alias:
            raise ValueError("Alias not found.")

        if evidence_id not in alias.linked_evidence_ids:
            new_suspicion = min(100, alias.suspicion_level + suspicion_boost)
            await db.identities.update_one(
                {"_id": alias_id},
                {
                    "$push": {"linked_evidence_ids": evidence_id},
                    "$set": {"suspicion_level": new_suspicion}
                }
            )

            updated = await self.get_alias(alias_id)
            if updated.is_exposed():
                # Publish public or case-restricted alert that alias has cracked
                await event_bus.publish(WorldEvent(
                    event_type=EventType.ALIAS_LINKED,
                    actor_id=alias.true_character_id,
                    visibility=EventVisibility.CASE_RESTRICTED,
                    state_delta={
                        "alias_name": alias.alias_name,
                        "true_character_id": alias.true_character_id,
                        "true_name": alias.true_name,
                        "is_exposed": True
                    }
                ))
                logger.warning(f"Alias '{alias.alias_name}' has been exposed to true character '{alias.true_name}'!")
            return updated
        return alias


identity_service = IdentityService()
