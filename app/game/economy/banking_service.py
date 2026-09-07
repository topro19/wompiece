from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from app.database.connection import db_manager
from app.game.economy.banking_models import LoanRecord, LoanStatus
from app.game.economy.ledger import ledger, TransactionError
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class BankingService:
    """Authoritative merchant banking engine for loans, credit, and debt collection."""

    async def issue_loan(
        self,
        banker_character_id: str,
        borrower_character_id: str,
        principal_amount: int,
        interest_rate_percent: int = 15,
        duration_days: int = 7
    ) -> LoanRecord:
        """Issues a peer-to-peer or merchant bank loan with double-entry ledger settlement."""
        db = db_manager.db

        if principal_amount <= 0:
            raise ValueError("Principal loan amount must be positive.")

        if banker_character_id == borrower_character_id:
            raise ValueError("You cannot issue a loan to yourself.")

        banker = await db.characters.find_one({"_id": banker_character_id, "status": "ALIVE"})
        borrower = await db.characters.find_one({"_id": borrower_character_id, "status": "ALIVE"})

        if not banker or not borrower:
            raise ValueError("Banker and borrower must both be active living characters.")

        # Check existing active loans for borrower
        active_loan = await db.loans.find_one({
            "borrower_character_id": borrower_character_id,
            "status": LoanStatus.ACTIVE.value
        })
        if active_loan:
            raise ValueError(f"{borrower.get('name')} already has an outstanding unpaid loan (#{active_loan['_id']}).")

        # Disburse funds from Banker to Borrower
        total_due = principal_amount + int(principal_amount * (interest_rate_percent / 100))
        due_at = datetime.now(timezone.utc) + timedelta(days=duration_days)

        await ledger.transfer(
            sender_id=banker_character_id,
            receiver_id=borrower_character_id,
            amount=principal_amount,
            reason=f"Disbursed loan #{borrower.get('name')} ({interest_rate_percent}% interest)",
            idempotency_key=f"loan_disburse_{banker_character_id}_{borrower_character_id}_{principal_amount}_{due_at.timestamp()}"
        )

        loan = LoanRecord(
            banker_character_id=banker_character_id,
            borrower_character_id=borrower_character_id,
            principal_amount=principal_amount,
            interest_rate_percent=interest_rate_percent,
            total_due=total_due,
            due_at=due_at
        )
        await db.loans.insert_one(loan.to_mongo())

        # Update merchant banker reputation
        await db.characters.update_one(
            {"_id": banker_character_id},
            {"$inc": {"reputation_merchant": 3}}
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.LOAN_ISSUED,
            actor_id=banker_character_id,
            target_ids=[borrower_character_id],
            visibility=EventVisibility.PRIVATE,
            state_delta=loan.model_dump()
        ))

        logger.info(f"Loan #{loan.loan_id} issued by {banker.get('name')} to {borrower.get('name')} for {principal_amount}g (Due: {total_due}g).")
        return loan

    async def repay_loan(self, loan_id: str, borrower_character_id: str) -> Dict[str, Any]:
        """Repays an active loan in full via double-entry ledger."""
        db = db_manager.db

        loan_doc = await db.loans.find_one({"_id": loan_id})
        if not loan_doc:
            raise ValueError(f"Loan {loan_id} not found.")

        loan = LoanRecord(**loan_doc)
        if loan.status != LoanStatus.ACTIVE:
            raise ValueError(f"Loan {loan_id} is not active (Status: {loan.status.value}).")

        if loan.borrower_character_id != borrower_character_id:
            raise ValueError("Only the registered borrower can repay this debt.")

        # Transfer total due from Borrower back to Banker
        await ledger.transfer(
            sender_id=borrower_character_id,
            receiver_id=loan.banker_character_id,
            amount=loan.total_due,
            reason=f"Repaid loan #{loan.loan_id} in full",
            idempotency_key=f"loan_repay_{loan.loan_id}_{loan.total_due}"
        )

        now = datetime.now(timezone.utc)
        await db.loans.update_one(
            {"_id": loan_id},
            {"$set": {"status": LoanStatus.REPAID.value, "repaid_at": now}}
        )

        # Reputation bonuses
        await db.characters.update_one(
            {"_id": borrower_character_id},
            {"$inc": {"reputation_merchant": 5}}
        )
        await db.characters.update_one(
            {"_id": loan.banker_character_id},
            {"$inc": {"reputation_merchant": 3}}
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.LOAN_REPAID,
            actor_id=borrower_character_id,
            target_ids=[loan.banker_character_id],
            visibility=EventVisibility.PRIVATE,
            state_delta={"loan_id": loan_id, "amount_paid": loan.total_due}
        ))

        return {
            "loan_id": loan_id,
            "status": "REPAID",
            "amount_paid": loan.total_due,
            "repaid_at": now
        }

    async def check_and_default_overdue_loans(self) -> List[str]:
        """Scans for overdue loans and transitions them to DEFAULTED status."""
        db = db_manager.db
        now = datetime.now(timezone.utc)
        overdue_cursor = db.loans.find({
            "status": LoanStatus.ACTIVE.value,
            "due_at": {"$lt": now}
        })

        defaulted_ids = []
        async for ldoc in overdue_cursor:
            lid = ldoc["_id"]
            await db.loans.update_one(
                {"_id": lid},
                {"$set": {"status": LoanStatus.DEFAULTED.value}}
            )
            # Penalize borrower reputation
            await db.characters.update_one(
                {"_id": ldoc["borrower_character_id"]},
                {"$inc": {"reputation_merchant": -25}}
            )
            defaulted_ids.append(lid)

            await event_bus.publish(WorldEvent(
                event_type=EventType.LOAN_DEFAULTED,
                actor_id=ldoc["borrower_character_id"],
                target_ids=[ldoc["banker_character_id"]],
                visibility=EventVisibility.PUBLIC,
                state_delta={"loan_id": lid, "amount_unpaid": ldoc["total_due"]}
            ))

        return defaulted_ids


banking_service = BankingService()
