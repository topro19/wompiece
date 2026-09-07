from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.database.connection import db_manager
from app.game.models.character import Faction
from app.game.contracts.contract_models import WorldContract, ContractType, ContractStatus
from app.game.economy.ledger import ledger, TransactionError
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class ContractService:
    """Authoritative dynamic contract board and escrow management engine."""

    async def post_contract(
        self,
        issuer_character_id: str,
        contract_type: ContractType,
        title: str,
        reward_amount: int,
        description: str,
        origin_location_id: str = "port_azure_market",
        destination_location_id: Optional[str] = None,
        target_name: Optional[str] = None,
        target_id: Optional[str] = None,
        required_item_id: Optional[str] = None,
        required_quantity: int = 1
    ) -> WorldContract:
        """Posts a new work contract, locking the reward in escrow via double-entry ledger."""
        db = db_manager.db

        if reward_amount <= 0:
            raise ValueError("Reward amount must be positive.")

        issuer = await db.characters.find_one({"_id": issuer_character_id, "status": "ALIVE"})
        if not issuer:
            raise ValueError("Issuer must be an active living character.")

        # Lock reward in escrow
        await ledger.transfer(
            sender_id=issuer_character_id,
            receiver_id="contract_escrow",
            amount=reward_amount,
            reason=f"Escrow lock for contract '{title}'",
            idempotency_key=f"contract_post_{issuer_character_id}_{reward_amount}_{title.strip().replace(' ', '_')}"
        )

        contract = WorldContract(
            title=title,
            contract_type=contract_type,
            issuer_character_id=issuer_character_id,
            issuer_name=issuer.get("name", "Unknown Issuer"),
            issuer_faction=Faction(issuer.get("faction", Faction.MERCHANT.value)),
            origin_location_id=origin_location_id,
            destination_location_id=destination_location_id,
            reward_amount=reward_amount,
            target_name=target_name,
            target_id=target_id,
            required_item_id=required_item_id,
            required_quantity=required_quantity,
            description=description
        )

        await db.contracts.insert_one(contract.to_mongo())

        await event_bus.publish(WorldEvent(
            event_type=EventType.CONTRACT_POSTED,
            actor_id=issuer_character_id,
            location_id=origin_location_id,
            visibility=EventVisibility.PUBLIC,
            state_delta=contract.model_dump()
        ))

        logger.info(f"Contract '{title}' ({contract_type.value}) posted by {contract.issuer_name} (Reward: {reward_amount}g).")
        return contract

    async def get_open_contracts(
        self,
        contract_type: Optional[ContractType] = None,
        limit: int = 10
    ) -> List[WorldContract]:
        """Retrieves available contracts from the public board."""
        db = db_manager.db
        query: Dict[str, Any] = {"status": ContractStatus.OPEN.value}
        if contract_type:
            query["contract_type"] = contract_type.value

        cursor = db.contracts.find(query).limit(limit)
        return [WorldContract(**doc) async for doc in cursor]

    async def accept_contract(
        self,
        contract_id: str,
        contractor_character_id: str
    ) -> WorldContract:
        """Assigns an open contract to a player or mercenary."""
        db = db_manager.db

        doc = await db.contracts.find_one({"_id": contract_id})
        if not doc:
            raise ValueError(f"Contract {contract_id} not found.")

        contract = WorldContract(**doc)
        if contract.status != ContractStatus.OPEN:
            raise ValueError(f"Contract is no longer open (Status: {contract.status.value}).")

        if contract.issuer_character_id == contractor_character_id:
            raise ValueError("You cannot accept your own contract.")

        contractor = await db.characters.find_one({"_id": contractor_character_id, "status": "ALIVE"})
        if not contractor:
            raise ValueError("Contractor must be an active living character.")

        await db.contracts.update_one(
            {"_id": contract_id},
            {"$set": {"status": ContractStatus.ACCEPTED.value, "assigned_contractor_id": contractor_character_id}}
        )

        contract.status = ContractStatus.ACCEPTED
        contract.assigned_contractor_id = contractor_character_id

        await event_bus.publish(WorldEvent(
            event_type=EventType.CONTRACT_ACCEPTED,
            actor_id=contractor_character_id,
            target_ids=[contract.issuer_character_id],
            location_id=contract.origin_location_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={"contract_id": contract_id, "contractor_id": contractor_character_id}
        ))

        return contract

    async def complete_contract(
        self,
        contract_id: str,
        contractor_character_id: str
    ) -> Dict[str, Any]:
        """Verifies contract conditions, consumes required items, and disburses escrow reward."""
        db = db_manager.db

        doc = await db.contracts.find_one({"_id": contract_id})
        if not doc:
            raise ValueError(f"Contract {contract_id} not found.")

        contract = WorldContract(**doc)
        if contract.status != ContractStatus.ACCEPTED:
            raise ValueError(f"Contract is not accepted (Status: {contract.status.value}).")

        if contract.assigned_contractor_id != contractor_character_id:
            raise ValueError("You are not the designated contractor for this mission.")

        contractor = await db.characters.find_one({"_id": contractor_character_id, "status": "ALIVE"})
        if not contractor:
            raise ValueError("Contractor must be alive to collect payment.")

        # Verification of required cargo or proof item
        if contract.required_item_id:
            inventory = contractor.get("inventory", [])
            item = next((i for i in inventory if i.get("item_id") == contract.required_item_id), None)
            if not item or item.get("quantity", 1) < contract.required_quantity:
                raise ValueError(f"You do not possess the required proof/cargo: {contract.required_quantity}x {contract.required_item_id}.")

            # Consume item
            if item.get("quantity", 1) == contract.required_quantity:
                await db.characters.update_one(
                    {"_id": contractor_character_id},
                    {"$pull": {"inventory": {"item_id": contract.required_item_id}}}
                )
            else:
                await db.characters.update_one(
                    {"_id": contractor_character_id, "inventory.item_id": contract.required_item_id},
                    {"$inc": {"inventory.$.quantity": -contract.required_quantity}}
                )

        # Release reward from escrow to contractor
        await ledger.transfer(
            sender_id=None,
            receiver_id=contractor_character_id,
            amount=contract.reward_amount,
            reason=f"Settlement for completing contract '{contract.title}'",
            idempotency_key=f"contract_settle_{contract_id}_{contractor_character_id}_{contract.reward_amount}"
        )

        now = datetime.now(timezone.utc)
        await db.contracts.update_one(
            {"_id": contract_id},
            {"$set": {"status": ContractStatus.COMPLETED.value, "completed_at": now}}
        )

        # Reputation bonuses
        await db.characters.update_one(
            {"_id": contractor_character_id},
            {"$inc": {"reputation_independent": 5, "reputation_merchant": 3}}
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.CONTRACT_COMPLETED,
            actor_id=contractor_character_id,
            target_ids=[contract.issuer_character_id],
            visibility=EventVisibility.PUBLIC,
            state_delta={
                "contract_id": contract_id,
                "reward_paid": contract.reward_amount,
                "contractor_id": contractor_character_id
            }
        ))

        return {
            "contract_id": contract_id,
            "title": contract.title,
            "reward_amount": contract.reward_amount,
            "completed_at": now
        }


contract_service = ContractService()
