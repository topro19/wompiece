import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from app.database.connection import db_manager
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class TransactionRecord(BaseModel):
    """Immutable double-entry transaction record."""
    tx_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    idempotency_key: str
    sender_id: Optional[str] = None  # None indicates system mint / treasure / world
    receiver_id: str
    amount: int
    currency: str = "gold"
    reason: str
    location_id: Optional[str] = None
    related_case_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.tx_id
        return data


class TransactionError(Exception):
    """Raised when an economic transfer fails invariant checks."""
    pass


class LedgerService:
    """Authoritative economic ledger enforcing non-negative balances and idempotency."""

    async def transfer(
        self,
        receiver_id: str,
        amount: int,
        reason: str,
        idempotency_key: str,
        sender_id: Optional[str] = None,
        location_id: Optional[str] = None,
        related_case_id: Optional[str] = None,
    ) -> TransactionRecord:
        if amount <= 0:
            raise TransactionError(f"Transfer amount must be positive. Got: {amount}")

        db = db_manager.db

        # 1. Check Idempotency
        existing_tx = await db.transactions.find_one({"idempotency_key": idempotency_key})
        if existing_tx:
            logger.warning(f"Duplicate transaction attempt detected with key: {idempotency_key}")
            return TransactionRecord(**existing_tx)

        # 2. Check Sender Balance (if sender is not the world mint)
        if sender_id is not None:
            sender = await db.characters.find_one({"_id": sender_id})
            if not sender:
                # Could be a business or crew treasury
                sender = await db.businesses.find_one({"_id": sender_id}) or await db.crews.find_one({"_id": sender_id})
            
            if not sender:
                raise TransactionError(f"Sender {sender_id} does not exist in authoritative state.")

            current_balance = sender.get("wealth", sender.get("treasury", 0))
            if current_balance < amount:
                raise TransactionError(
                    f"Insufficient funds: Sender {sender_id} has {current_balance} gold, but {amount} is required."
                )

        # 3. Deduct from Sender
        if sender_id is not None:
            # Check if character or organization
            res = await db.characters.update_one(
                {"_id": sender_id, "wealth": {"$gte": amount}},
                {"$inc": {"wealth": -amount}}
            )
            if res.modified_count == 0:
                # Try crew or business
                res_crew = await db.crews.update_one(
                    {"_id": sender_id, "treasury": {"$gte": amount}},
                    {"$inc": {"treasury": -amount}}
                )
                if res_crew.modified_count == 0:
                    res_biz = await db.businesses.update_one(
                        {"_id": sender_id, "daily_revenue": {"$gte": amount}},
                        {"$inc": {"daily_revenue": -amount}}
                    )
                    if res_biz.modified_count == 0:
                        raise TransactionError("Atomic deduction failed due to concurrent modification or insufficient balance.")

        # 4. Credit to Receiver
        res_rcv = await db.characters.update_one(
            {"_id": receiver_id},
            {"$inc": {"wealth": amount}}
        )
        if res_rcv.modified_count == 0:
            # Try crew or business receiver
            await db.crews.update_one({"_id": receiver_id}, {"$inc": {"treasury": amount}})
            await db.businesses.update_one({"_id": receiver_id}, {"$inc": {"daily_revenue": amount}})

        # 5. Record Transaction
        tx = TransactionRecord(
            idempotency_key=idempotency_key,
            sender_id=sender_id,
            receiver_id=receiver_id,
            amount=amount,
            reason=reason,
            location_id=location_id,
            related_case_id=related_case_id
        )
        await db.transactions.insert_one(tx.to_mongo())

        # 6. Emit Authoritative World Event
        await event_bus.publish(WorldEvent(
            event_type=EventType.TRANSACTION_EXECUTED,
            actor_id=sender_id,
            target_ids=[receiver_id],
            location_id=location_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={"amount": amount, "currency": "gold", "reason": reason},
            related_transaction_id=tx.tx_id,
            related_case_id=related_case_id
        ))

        return tx


ledger = LedgerService()
