import random
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.database.connection import db_manager
from app.game.models.character import Faction
from app.game.information.intel_models import IntelReport, IntelCategory
from app.game.economy.ledger import ledger, TransactionError
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


INTEL_TEMPLATES = {
    IntelCategory.PIRATE_MOVEMENT: [
        ("The Black Tide Sloop Preparing Ambush", "Captain Redhook's vanguard was spotted sounding the reefs west of Azure Shipping Lane.", 150),
        ("Raiders Anchored at Dead Man's Cove", "Smugglers are transferring black-powder casks into longboats at the midnight low-tide.", 120)
    ],
    IntelCategory.MARINE_PATROL: [
        ("16th Division Frigate Rotation", "Marine customs patrol will be delayed due to boiler refits near Port Azure Grand Docks tonight.", 180),
        ("Inspector Vance Surveillance Docket", "Navy sentries are logging all arrivals purchasing large quantities of medical opium.", 200)
    ],
    IntelCategory.CONTRABAND_SHIPMENT: [
        ("Unmanifested Silk & Contraband", "A merchant caravel flying neutral colors is unloading concealed crates under Marcus Vale's warehouse.", 220),
        ("Stolen Gold Ingot Cache", "Pirates from Isla de la Muerte are fencing colonial doubloons through tavern dice runners.", 160)
    ]
}


class IntelService:
    """Authoritative intelligence brokerage, informant tracking, and double-agent engine."""

    async def gather_intel(
        self,
        character_id: str,
        category: IntelCategory,
        is_fabrication: bool = False
    ) -> IntelReport:
        """Gathers whispers from tavern rumors, dock watchers, or forges false intelligence."""
        db = db_manager.db

        char_doc = await db.characters.find_one({"_id": character_id, "status": "ALIVE"})
        if not char_doc:
            raise ValueError("Only living characters can collect intelligence.")

        templates = INTEL_TEMPLATES.get(category, [("Suspicious Port Movements", "Whispers of secretive dealings in the docks.", 100)])
        title, detail, base_val = random.choice(templates)

        if is_fabrication:
            title = f"[Fabricated] {title}"
            detail = f"{detail} (Deliberately exaggerated to mislead rivals)."
            reliability = 0.35
            is_truth = False
        else:
            reliability = 0.90
            is_truth = True

        report = IntelReport(
            category=category,
            title=title,
            detail=detail,
            source_character_id=character_id,
            seller_name=char_doc.get("name", "Informant"),
            reliability=reliability,
            is_truth=is_truth,
            market_value=base_val
        )

        await db.intel_reports.insert_one(report.to_mongo())

        # Give small reputation boost to Independent / Merchant
        await db.characters.update_one(
            {"_id": character_id},
            {"$inc": {"reputation_independent": 2}}
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.INTEL_GATHERED,
            actor_id=character_id,
            location_id=char_doc.get("location_id", "port_azure_market"),
            visibility=EventVisibility.PRIVATE,
            state_delta={"intel_id": report.intel_id, "category": category.value, "is_truth": is_truth}
        ))

        return report

    async def sell_intel(
        self,
        intel_id: str,
        seller_character_id: str,
        buyer_character_id: str,
        negotiated_price: Optional[int] = None
    ) -> Dict[str, Any]:
        """Sells an intelligence report to a buyer via double-entry ledger."""
        db = db_manager.db

        doc = await db.intel_reports.find_one({"_id": intel_id})
        if not doc:
            raise ValueError("Intelligence dossier not found.")

        report = IntelReport(**doc)
        if report.source_character_id != seller_character_id:
            raise ValueError("You do not possess the rights to sell this intelligence.")

        price = negotiated_price if negotiated_price is not None else report.market_value

        buyer = await db.characters.find_one({"_id": buyer_character_id, "status": "ALIVE"})
        seller = await db.characters.find_one({"_id": seller_character_id, "status": "ALIVE"})
        if not buyer or not seller:
            raise ValueError("Both buyer and seller must be active living characters.")

        # Atomic Ledger Transfer
        await ledger.transfer(
            sender_id=buyer_character_id,
            receiver_id=seller_character_id,
            amount=price,
            reason=f"Purchased intelligence dossier: {report.title}",
            idempotency_key=f"intel_sale_{intel_id}_{buyer_character_id}_{price}"
        )

        # Mark buyer on report
        await db.intel_reports.update_one(
            {"_id": intel_id},
            {"$set": {"buyer_character_id": buyer_character_id}}
        )

        # Check for double-agent activity (e.g. seller has sold to both Marines and Pirates)
        await self._check_double_agent_status(seller_character_id, buyer.get("faction"))

        await event_bus.publish(WorldEvent(
            event_type=EventType.INTEL_SOLD,
            actor_id=seller_character_id,
            target_ids=[buyer_character_id],
            visibility=EventVisibility.SECRET,
            state_delta={
                "intel_id": intel_id,
                "price": price,
                "buyer_faction": buyer.get("faction")
            }
        ))

        return {
            "intel_id": intel_id,
            "title": report.title,
            "detail": report.detail,
            "reliability": report.reliability,
            "price_paid": price,
            "buyer": buyer.get("name")
        }

    async def _check_double_agent_status(self, character_id: str, new_buyer_faction: str):
        """Scans if the seller is peddling secrets across opposing ideological lines."""
        db = db_manager.db

        cursor = db.intel_reports.find({"source_character_id": character_id, "buyer_character_id": {"$ne": None}})
        sold_reports = [doc async for doc in cursor]

        buyer_ids = [r["buyer_character_id"] for r in sold_reports]
        buyers_cursor = db.characters.find({"_id": {"$in": buyer_ids}})
        buyers = [b async for b in buyers_cursor]

        factions = set(b.get("faction") for b in buyers)
        if "MARINE" in factions and "PIRATE" in factions:
            # Informant is playing both sides! Double agent exposed risk
            if random.random() < 0.25:  # 25% chance of leak per cross-faction transaction
                await db.characters.update_one(
                    {"_id": character_id},
                    {
                        "$inc": {"reputation_marine": -40, "reputation_pirate": -40, "bounty": 300},
                        "$set": {"is_exposed_double_agent": True}
                    }
                )
                await event_bus.publish(WorldEvent(
                    event_type=EventType.DOUBLE_AGENT_EXPOSED,
                    actor_id=character_id,
                    visibility=EventVisibility.PUBLIC,
                    state_delta={"double_agent_id": character_id, "penalties": "Both factions marked suspect as untrustworthy informant"}
                ))


intel_service = IntelService()
