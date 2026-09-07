from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.database.connection import db_manager
from app.game.models.character import Faction
from app.game.protection.protection_models import ProtectionContract, ProtectionStatus, ProtectedEntityType
from app.game.economy.ledger import ledger, TransactionError
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.game.investigations.case_service import investigation_service
from app.services.logger import logger


class ProtectionService:
    """Authoritative political protection contract and jurisdictional enforcement engine."""

    async def create_contract(
        self,
        merchant_character_id: str,
        entity_type: ProtectedEntityType,
        entity_id: str,
        protector_faction: Faction,
        protector_id: str,
        protector_name: str,
        weekly_dues: int = 150
    ) -> ProtectionContract:
        """Enacts a formal protection pact between a merchant property and a faction/crew."""
        db = db_manager.db

        merchant = await db.characters.find_one({"_id": merchant_character_id, "status": "ALIVE"})
        if not merchant:
            raise ValueError("Merchant must be an active living character.")

        # Resolve entity name
        entity_name = entity_id
        if entity_type == ProtectedEntityType.BUSINESS:
            bdoc = await db.businesses.find_one({"_id": entity_id})
            if bdoc:
                entity_name = bdoc.get("name", entity_id)
        elif entity_type == ProtectedEntityType.SHIP:
            sdoc = await db.ships.find_one({"_id": entity_id})
            if sdoc:
                entity_name = sdoc.get("name", entity_id)
        elif entity_type == ProtectedEntityType.INDIVIDUAL:
            cdoc = await db.characters.find_one({"_id": entity_id})
            if cdoc:
                entity_name = cdoc.get("name", entity_id)

        # Pay initial retainer via double-entry ledger
        await ledger.transfer(
            sender_id=merchant_character_id,
            receiver_id=protector_id,
            amount=weekly_dues,
            reason=f"Retainer fee for protection of {entity_name} by {protector_name}",
            idempotency_key=f"prot_init_{merchant_character_id}_{entity_id}_{protector_id}_{weekly_dues}"
        )

        contract = ProtectionContract(
            merchant_character_id=merchant_character_id,
            merchant_name=merchant.get("name", "Merchant"),
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            protector_faction=protector_faction,
            protector_id=protector_id,
            protector_name=protector_name,
            weekly_dues=weekly_dues
        )

        await db.protection_contracts.insert_one(contract.to_mongo())

        # Reputation bonus with the protector faction
        if protector_faction == Faction.PIRATE:
            await db.characters.update_one({"_id": merchant_character_id}, {"$inc": {"reputation_pirate": 10}})
        elif protector_faction == Faction.MARINE:
            await db.characters.update_one({"_id": merchant_character_id}, {"$inc": {"reputation_marine": 10}})
        elif protector_faction == Faction.INDEPENDENT:
            await db.characters.update_one({"_id": merchant_character_id}, {"$inc": {"reputation_independent": 10}})

        await event_bus.publish(WorldEvent(
            event_type=EventType.PROTECTION_CONTRACT_CREATED,
            actor_id=merchant_character_id,
            target_ids=[protector_id],
            visibility=EventVisibility.PUBLIC,
            state_delta=contract.model_dump()
        ))

        logger.info(f"Protection contract enacted: {entity_name} is now protected by {protector_name} ({protector_faction.value}).")
        return contract

    async def get_active_contract(self, entity_id: str) -> Optional[ProtectionContract]:
        db = db_manager.db
        doc = await db.protection_contracts.find_one({
            "$or": [{"entity_id": entity_id}, {"merchant_character_id": entity_id}],
            "status": ProtectionStatus.ACTIVE.value
        })
        return ProtectionContract(**doc) if doc else None

    async def check_hostile_action(
        self,
        attacker_id: str,
        victim_entity_id: str,
        location_id: str = "port_azure_market"
    ) -> Optional[Dict[str, Any]]:
        """
        Determines whether attacking an entity violates formal faction protection,
        triggering political and military retaliation across the world.
        """
        contract = await self.get_active_contract(victim_entity_id)
        if not contract:
            return None  # Unprotected target; standard crime/combat rules apply

        db = db_manager.db
        attacker = await db.characters.find_one({"_id": attacker_id})
        attacker_name = attacker.get("name", "Unknown Attacker") if attacker else "Unknown Attacker"

        consequences = {
            "is_protected": True,
            "contract_id": contract.contract_id,
            "protector_faction": contract.protector_faction.value,
            "protector_name": contract.protector_name,
            "victim_name": contract.entity_name,
            "penalties": []
        }

        if contract.protector_faction == Faction.PIRATE:
            # Pirate retaliation: Slashes pirate rep, issues pirate bounty
            await db.characters.update_one(
                {"_id": attacker_id},
                {
                    "$inc": {"reputation_pirate": -50, "bounty": 250},
                    "$set": {"wanted_by_pirates": True}
                }
            )
            consequences["penalties"].append("Pirate Rep -50")
            consequences["penalties"].append("Pirate Underworld Bounty +250g")
            consequences["narrative"] = f"⚠️ {contract.protector_name} declared a death warrant on {attacker_name} for violating their protected domain!"

        elif contract.protector_faction == Faction.MARINE:
            # Marine response: Immediate felony case, +2 wanted level, slashes marine rep
            await db.characters.update_one(
                {"_id": attacker_id},
                {"$inc": {"wanted_level": 2, "reputation_marine": -60}}
            )
            case = await investigation_service.open_case(
                assigned_marine_id="marine_patrol_command",
                title=f"Hostile Assault on Navy-Protected Entity: {contract.entity_name}",
                location_id=location_id,
                suspect_ids=[attacker_id],
                suspect_names=[attacker_name]
            )
            consequences["case_number"] = case.case_number
            consequences["penalties"].append("Marine Rep -60")
            consequences["penalties"].append("Wanted Level +2")
            consequences["penalties"].append(f"Marine Case #{case.case_number} Opened")
            consequences["narrative"] = f"🚨 The Marine 16th Division dispatched rapid-response sentries to defend {contract.entity_name}!"

        elif contract.protector_faction == Faction.INDEPENDENT:
            await db.characters.update_one(
                {"_id": attacker_id},
                {"$inc": {"reputation_independent": -40}}
            )
            consequences["penalties"].append("Independent Guild Rep -40")
            consequences["narrative"] = f"⚔️ Private mercenary guards rushed to defend {contract.entity_name}!"

        # Emit authoritative world event
        await event_bus.publish(WorldEvent(
            event_type=EventType.HOSTILE_ACTION_AGAINST_PROTECTED_ENTITY,
            actor_id=attacker_id,
            target_ids=[victim_entity_id, contract.protector_id],
            location_id=location_id,
            visibility=EventVisibility.PUBLIC,
            state_delta=consequences
        ))

        return consequences


protection_service = ProtectionService()
