import uuid
import random
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from app.database.connection import db_manager
from app.game.economy.ledger import ledger
from app.game.investigations.case_service import investigation_service
from app.game.investigations.case_models import EvidenceType
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class UndercoverOperation(BaseModel):
    operation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code_name: str = "OPERATION BLACK ANCHOR"
    target_marine_id: str
    target_marine_name: str
    status: str = "ACTIVE"  # ACTIVE, COMPLETED, EXPOSED
    bribe_offered: int = 500
    evidence_gathered: list = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> Dict[str, Any]:
        data = self.model_dump()
        data["_id"] = self.operation_id
        return data


class CorruptionService:
    """Service governing bribery attempts, corruption evidence trails, and undercover sting operations."""

    async def attempt_bribe(
        self,
        briber_character_id: str,
        target_marine_id: str,
        amount: int,
        reason: str,
        case_id: Optional[str] = None
    ) -> Dict[str, Any]:
        db = db_manager.db

        briber = await db.characters.find_one({"_id": briber_character_id})
        marine = await db.characters.find_one({"_id": target_marine_id})

        if not briber or not marine:
            raise ValueError("Briber or target marine not found.")

        # 1. Deduct gold from briber via ledger
        tx = await ledger.transfer(
            sender_id=briber_character_id,
            receiver_id=target_marine_id,
            amount=amount,
            reason=f"Secret illicit payment: {reason}",
            idempotency_key=f"bribe_{briber_character_id}_{uuid.uuid4()}",
            related_case_id=case_id
        )

        # 2. Check if Marine is part of an active undercover sting operation
        sting_op = await db.operations.find_one({
            "target_marine_id": target_marine_id,
            "status": "ACTIVE"
        })

        # Base detection chance of secret surveillance / third-party witness
        detected_by_internal_affairs = sting_op is not None or (random.random() < 0.35)

        if detected_by_internal_affairs:
            # Generate immutable corruption evidence
            corrupt_case_id = case_id
            if not corrupt_case_id:
                # Open or find Internal Affairs case
                ia_case = await db.cases.find_one({"title": "Internal Affairs: Bribery Surveillance"})
                if not ia_case:
                    new_case = await investigation_service.open_case(
                        assigned_marine_id="naval_intelligence_bureau",
                        title="Internal Affairs: Bribery Surveillance",
                        location_id=marine.get("location_id", "marine_headquarters"),
                        suspect_ids=[target_marine_id, briber_character_id]
                    )
                    corrupt_case_id = new_case.case_id
                else:
                    corrupt_case_id = ia_case["_id"]

            await investigation_service.add_evidence(
                case_id=corrupt_case_id,
                evidence_type=EvidenceType.TRANSACTION_ANOMALY,
                title=f"Secret Payment to {marine['name']}",
                description=f"Transaction of {amount} gold recorded from {briber['name']}. Reason: '{reason}'.",
                source="Naval Financial Audit Bureau",
                location_id=marine.get("location_id", "marine_headquarters"),
                discovered_by_id="naval_intelligence_bureau",
                reliability=95
            )

            await event_bus.publish(WorldEvent(
                event_type=EventType.BRIBE_ACCEPTED,
                actor_id=briber_character_id,
                target_ids=[target_marine_id],
                location_id=marine.get("location_id", "marine_headquarters"),
                visibility=EventVisibility.SECRET,
                state_delta={"amount": amount, "detected": True, "undercover": sting_op is not None},
                related_case_id=corrupt_case_id,
                related_transaction_id=tx.tx_id
            ))

            logger.warning(f"[CORRUPTION] Bribe of {amount} gold to {marine['name']} was recorded by Naval Intelligence!")
            return {
                "success": True,
                "amount": amount,
                "secretly_recorded": True,
                "message": f"Payment accepted by {marine['name']} in the shadows."
            }
        else:
            await event_bus.publish(WorldEvent(
                event_type=EventType.BRIBE_ACCEPTED,
                actor_id=briber_character_id,
                target_ids=[target_marine_id],
                location_id=marine.get("location_id", "marine_headquarters"),
                visibility=EventVisibility.SECRET,
                state_delta={"amount": amount, "detected": False},
                related_transaction_id=tx.tx_id
            ))
            return {
                "success": True,
                "amount": amount,
                "secretly_recorded": False,
                "message": f"Payment slipped into {marine['name']}'s coat unnoticed."
            }

    async def launch_undercover_operation(
        self,
        target_marine_id: str,
        code_name: str = "OPERATION BLACK ANCHOR"
    ) -> UndercoverOperation:
        db = db_manager.db
        target = await db.characters.find_one({"_id": target_marine_id})
        if not target:
            raise ValueError("Target marine not found.")

        op = UndercoverOperation(
            code_name=code_name,
            target_marine_id=target_marine_id,
            target_marine_name=target.get("name", "Unknown")
        )
        await db.operations.insert_one(op.to_mongo())

        await event_bus.publish(WorldEvent(
            event_type=EventType.UNDERCOVER_OPERATION_LAUNCHED,
            actor_id="naval_intelligence_headquarters",
            target_ids=[target_marine_id],
            location_id=target.get("location_id", "marine_headquarters"),
            visibility=EventVisibility.AUTHORITY_ONLY,
            state_delta={"operation": op.code_name, "target": op.target_marine_name}
        ))

        logger.info(f"Launched sting operation '{op.code_name}' targeting {op.target_marine_name}.")
        return op


corruption_service = CorruptionService()
