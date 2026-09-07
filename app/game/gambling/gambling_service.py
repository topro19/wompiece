import uuid
import random
from typing import Dict, Any, Optional
from app.database.connection import db_manager
from app.game.gambling.gambling_models import GamblingTable, GamblingOutcome, GameType
from app.game.economy.ledger import ledger
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class GamblingService:
    """Authoritative in-game gambling engine with ledger integration and risk/reward dynamics."""

    async def get_or_create_table(self, business_id: str, game_type: GameType) -> GamblingTable:
        db = db_manager.db
        doc = await db.gambling_tables.find_one({"business_id": business_id, "game_type": game_type.value})
        if doc:
            return GamblingTable(**doc)

        biz = await db.businesses.find_one({"_id": business_id})
        biz_name = biz.get("name", "Local Tavern") if biz else "Local Tavern"
        is_rigged = "rigged_gambling" in biz.get("hidden_illegal_ops", []) if biz else False

        table = GamblingTable(
            business_id=business_id,
            business_name=biz_name,
            game_type=game_type,
            is_rigged=is_rigged
        )
        await db.gambling_tables.insert_one(table.to_mongo())
        return table

    async def play_high_low_dice(
        self,
        character_id: str,
        business_id: str,
        wager: int,
        choice: str  # "HIGH", "LOW", "SEVEN"
    ) -> GamblingOutcome:
        """Plays High-Low dice (2d6). Strict double-entry ledger transactions."""
        db = db_manager.db
        table = await self.get_or_create_table(business_id, GameType.HIGH_LOW_DICE)

        if wager < table.min_wager or wager > table.max_wager:
            raise ValueError(f"Wager must be between {table.min_wager} and {table.max_wager} gold.")

        # 1. Deduct wager from player into table
        tx_wager = await ledger.transfer(
            sender_id=character_id,
            receiver_id=business_id,
            amount=wager,
            reason=f"Wager on High-Low Dice at {table.business_name}",
            idempotency_key=f"gamble_wager_{character_id}_{uuid.uuid4()}"
        )

        # 2. Roll 2d6
        choice_upper = choice.strip().upper()
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)

        # Rigged table logic
        rigged_detected = False
        suspicion_delta = 0
        if table.is_rigged:
            # Rigged dice reduce player win chance
            if choice_upper == "HIGH" and (d1 + d2) >= 8 and random.random() < 0.4:
                d1 = max(1, d1 - 2)
            elif choice_upper == "LOW" and (d1 + d2) <= 6 and random.random() < 0.4:
                d1 = min(6, d1 + 2)

            # 15% risk that loaded dice are spotted by astute patrons
            if random.random() < 0.15:
                rigged_detected = True
                suspicion_delta = 25
                await db.businesses.update_one(
                    {"_id": business_id},
                    {"$inc": {"suspicion_level": suspicion_delta}}
                )
                logger.warning(f"Patron noticed loaded dice at '{table.business_name}'! Suspicion +{suspicion_delta}%.")

        total = d1 + d2
        player_won = False
        payout = 0

        if choice_upper == "HIGH" and total >= 8:
            player_won = True
            payout = wager * 2
        elif choice_upper == "LOW" and total <= 6:
            player_won = True
            payout = wager * 2
        elif choice_upper == "SEVEN" and total == 7:
            player_won = True
            payout = wager * 4

        # 3. Pay out winnings if won
        if player_won and payout > 0:
            await ledger.transfer(
                sender_id=business_id,
                receiver_id=character_id,
                amount=payout,
                reason=f"Winnings from High-Low Dice at {table.business_name}",
                idempotency_key=f"gamble_win_{character_id}_{uuid.uuid4()}"
            )

        details = f"Rolled [{d1}] + [{d2}] = {total}. Your bet was '{choice_upper}'."
        if rigged_detected:
            details += " ⚠️ A patron shouted about loaded dice! The room grew tense."

        outcome = GamblingOutcome(
            game_type=GameType.HIGH_LOW_DICE,
            wager=wager,
            player_won=player_won,
            payout=payout,
            details=details,
            is_rigged=table.is_rigged,
            rigged_detected=rigged_detected,
            suspicion_delta=suspicion_delta
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.GAMBLING_GAME_PLAYED,
            actor_id=character_id,
            location_id=business_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={
                "game": "HIGH_LOW_DICE",
                "wager": wager,
                "won": player_won,
                "payout": payout,
                "rigged_detected": rigged_detected
            }
        ))

        return outcome


gambling_service = GamblingService()
