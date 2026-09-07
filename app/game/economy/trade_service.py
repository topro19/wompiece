import random
from typing import Dict, Any, List, Optional
from app.database.connection import db_manager
from app.game.economy.trade_models import (
    CommodityType,
    Commodity,
    COMMODITIES_REGISTRY,
    LOCATION_MARKET_MULTIPLIERS
)
from app.game.economy.ledger import ledger, TransactionError
from app.game.world.location import location_service
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.game.investigations.case_service import investigation_service
from app.game.investigations.case_models import EvidenceType
from app.services.logger import logger


class TradeService:
    """Authoritative regional commodity trade and arbitrage market engine."""

    def get_market_prices(self, location_id: str) -> List[Dict[str, Any]]:
        """Returns commodity prices, legality, and margins for a specific port or market."""
        loc = location_service.get_location(location_id)
        if not loc:
            return []

        multipliers = LOCATION_MARKET_MULTIPLIERS.get(location_id)
        # Default fallback to Port Azure pricing if not an explicit trading post
        if not multipliers:
            multipliers = LOCATION_MARKET_MULTIPLIERS.get("port_azure_market", {})

        catalog = []
        for ctype, commodity in COMMODITIES_REGISTRY.items():
            buy_mult, sell_mult = multipliers.get(ctype, (1.0, 0.8))
            buy_price = max(1, int(commodity.base_price * buy_mult))
            sell_price = max(1, int(commodity.base_price * sell_mult))

            # Contraband legality check
            is_illegal_here = commodity.is_contraband and loc.security_level >= 2

            catalog.append({
                "commodity_id": commodity.commodity_id.value,
                "name": commodity.name,
                "base_price": commodity.base_price,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "is_contraband": commodity.is_contraband,
                "is_illegal_here": is_illegal_here,
                "description": commodity.description
            })

        return catalog

    async def buy_commodity(
        self,
        character_id: str,
        commodity_id: str,
        quantity: int
    ) -> Dict[str, Any]:
        """Buys goods from the local market, deducting coin via ledger."""
        db = db_manager.db

        if quantity <= 0:
            raise ValueError("Quantity must be positive.")

        char_doc = await db.characters.find_one({"_id": character_id})
        if not char_doc or char_doc.get("status") != "ALIVE":
            raise ValueError("Only living characters can conduct trade.")

        loc_id = char_doc.get("location_id", "port_azure_market")
        loc = location_service.get_location(loc_id)
        if not loc or not any(f in loc.facilities for f in ["general_store", "trading_post", "spice_exchange", "black_market"]):
            raise ValueError(f"There is no active merchant exchange or market in {loc.name if loc else loc_id}.")

        try:
            ctype = CommodityType(commodity_id)
        except ValueError:
            raise ValueError(f"Unknown commodity '{commodity_id}'.")

        commodity = COMMODITIES_REGISTRY[ctype]
        multipliers = LOCATION_MARKET_MULTIPLIERS.get(loc_id, LOCATION_MARKET_MULTIPLIERS.get("port_azure_market", {}))
        buy_mult, _ = multipliers.get(ctype, (1.0, 0.8))
        unit_price = max(1, int(commodity.base_price * buy_mult))
        total_cost = unit_price * quantity

        # Atomic Ledger Debit
        await ledger.transfer(
            sender_id=character_id,
            receiver_id="market_escrow",
            amount=total_cost,
            reason=f"Purchased {quantity}x {commodity.name} at {loc.name}",
            idempotency_key=f"trade_buy_{character_id}_{commodity_id}_{quantity}_{total_cost}",
            location_id=loc_id
        )

        # Add to character inventory
        trade_item = {
            "item_id": commodity.commodity_id.value,
            "name": commodity.name,
            "type": "commodity",
            "quantity": quantity,
            "is_contraband": commodity.is_contraband,
            "purchase_price": unit_price,
            "purchased_at": loc_id
        }

        # Check existing stack
        inventory = char_doc.get("inventory", [])
        existing = next((item for item in inventory if item.get("item_id") == trade_item["item_id"]), None)
        if existing:
            await db.characters.update_one(
                {"_id": character_id, "inventory.item_id": trade_item["item_id"]},
                {"$inc": {"inventory.$.quantity": quantity}}
            )
        else:
            await db.characters.update_one(
                {"_id": character_id},
                {"$push": {"inventory": trade_item}}
            )

        # Increase merchant reputation slightly for successful business
        await db.characters.update_one(
            {"_id": character_id},
            {"$inc": {"reputation_merchant": 1}}
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.GOODS_TRADED,
            actor_id=character_id,
            location_id=loc_id,
            visibility=EventVisibility.PUBLIC if not commodity.is_contraband else EventVisibility.SECRET,
            state_delta={
                "action": "BUY",
                "commodity": commodity_id,
                "quantity": quantity,
                "unit_price": unit_price,
                "total_cost": total_cost
            }
        ))

        return {
            "action": "BUY",
            "commodity": commodity.name,
            "quantity": quantity,
            "unit_price": unit_price,
            "total_cost": total_cost,
            "location": loc.name
        }

    async def sell_commodity(
        self,
        character_id: str,
        commodity_id: str,
        quantity: int
    ) -> Dict[str, Any]:
        """Sells cargo to the local market with customs contraband risk."""
        db = db_manager.db

        if quantity <= 0:
            raise ValueError("Quantity must be positive.")

        char_doc = await db.characters.find_one({"_id": character_id})
        if not char_doc or char_doc.get("status") != "ALIVE":
            raise ValueError("Only living characters can conduct trade.")

        loc_id = char_doc.get("location_id", "port_azure_market")
        loc = location_service.get_location(loc_id)
        if not loc or not any(f in loc.facilities for f in ["general_store", "trading_post", "spice_exchange", "black_market"]):
            raise ValueError(f"There is no active merchant exchange or market in {loc.name if loc else loc_id}.")

        try:
            ctype = CommodityType(commodity_id)
        except ValueError:
            raise ValueError(f"Unknown commodity '{commodity_id}'.")

        commodity = COMMODITIES_REGISTRY[ctype]

        # Verify possession
        inventory = char_doc.get("inventory", [])
        inv_item = next((item for item in inventory if item.get("item_id") == commodity_id), None)
        if not inv_item or inv_item.get("quantity", 1) < quantity:
            current_qty = inv_item.get("quantity", 1) if inv_item else 0
            raise ValueError(f"You do not possess {quantity}x {commodity.name} (Current: {current_qty}).")

        # Contraband Customs Interception Check
        is_caught = False
        if commodity.is_contraband and loc.security_level >= 3:
            # 50% chance of customs seizure at high security colonial ports
            detection_roll = random.random()
            if detection_roll < 0.50:
                is_caught = True

        if is_caught:
            # Confiscate goods, escalate wanted level, open Marine investigation
            await db.characters.update_one(
                {"_id": character_id},
                {
                    "$pull": {"inventory": {"item_id": commodity_id}},
                    "$inc": {"wanted_level": 2, "reputation_marine": -20, "reputation_merchant": -10}
                }
            )

            # Open or escalate case
            case = await investigation_service.open_case(
                assigned_marine_id="marine_customs_inspector",
                title=f"Customs Seizure: Illicit {commodity.name}",
                location_id=loc_id,
                suspect_ids=[character_id],
                suspect_names=[char_doc.get("name")]
            )
            await investigation_service.add_evidence(
                case_id=case.case_id,
                evidence_type=EvidenceType.CONTRABAND_SAMPLE,
                title=f"Impounded {commodity.name}",
                description=f"Seized {quantity} units of {commodity.name} during dock inspection.",
                source="Customs Port Inspection",
                location_id=loc_id,
                discovered_by_id="marine_customs_inspector"
            )

            raise ValueError(
                f"🚨 CUSTOMS SEIZURE! Marine dock inspectors discovered your {quantity}x {commodity.name}! "
                f"The cargo has been impounded, Case #{case.case_number} has been opened, and your Wanted Level increased!"
            )

        multipliers = LOCATION_MARKET_MULTIPLIERS.get(loc_id, LOCATION_MARKET_MULTIPLIERS.get("port_azure_market", {}))
        _, sell_mult = multipliers.get(ctype, (1.0, 0.8))
        unit_price = max(1, int(commodity.base_price * sell_mult))
        total_payout = unit_price * quantity

        # Deduct from inventory
        if inv_item.get("quantity", 1) == quantity:
            await db.characters.update_one(
                {"_id": character_id},
                {"$pull": {"inventory": {"item_id": commodity_id}}}
            )
        else:
            await db.characters.update_one(
                {"_id": character_id, "inventory.item_id": commodity_id},
                {"$inc": {"inventory.$.quantity": -quantity}}
            )

        # Credit Character via Ledger
        await ledger.transfer(
            sender_id=None,  # Minted from market liquidity
            receiver_id=character_id,
            amount=total_payout,
            reason=f"Sold {quantity}x {commodity.name} at {loc.name}",
            idempotency_key=f"trade_sell_{character_id}_{commodity_id}_{quantity}_{total_payout}",
            location_id=loc_id
        )

        # Increase merchant reputation
        await db.characters.update_one(
            {"_id": character_id},
            {"$inc": {"reputation_merchant": 2}}
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.GOODS_TRADED,
            actor_id=character_id,
            location_id=loc_id,
            visibility=EventVisibility.PUBLIC if not commodity.is_contraband else EventVisibility.SECRET,
            state_delta={
                "action": "SELL",
                "commodity": commodity_id,
                "quantity": quantity,
                "unit_price": unit_price,
                "total_payout": total_payout
            }
        ))

        return {
            "action": "SELL",
            "commodity": commodity.name,
            "quantity": quantity,
            "unit_price": unit_price,
            "total_payout": total_payout,
            "location": loc.name
        }


trade_service = TradeService()
