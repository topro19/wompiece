import uuid
from typing import Optional, List, Dict, Any
from app.database.connection import db_manager
from app.game.businesses.business_models import Business, BusinessType
from app.game.identity.identity_service import identity_service
from app.game.economy.ledger import ledger
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.services.logger import logger


class BusinessService:
    """Service governing business acquisition, legitimate trade, and underhand operations."""

    async def get_business(self, business_id: str) -> Optional[Business]:
        db = db_manager.db
        doc = await db.businesses.find_one({"_id": business_id})
        return Business(**doc) if doc else None

    async def get_business_by_name(self, name: str) -> Optional[Business]:
        db = db_manager.db
        doc = await db.businesses.find_one({"name": {"$regex": f"^{name.strip()}$", "$options": "i"}})
        return Business(**doc) if doc else None

    async def get_businesses_by_location(self, location_id: str) -> List[Business]:
        db = db_manager.db
        cursor = db.businesses.find({"location_id": location_id})
        docs = await cursor.to_list(length=20)
        return [Business(**d) for d in docs]

    async def create_business(
        self,
        name: str,
        location_id: str,
        owner_character_id: str,
        business_type: BusinessType,
        owner_alias_id: Optional[str] = None,
        crew_id: Optional[str] = None,
        cost: int = 1000
    ) -> Business:
        db = db_manager.db

        char_doc = await db.characters.find_one({"_id": owner_character_id})
        if not char_doc:
            raise ValueError(f"Character {owner_character_id} not found.")

        # Determine registered name (Real name vs Alias)
        registered_name = char_doc.get("name", "Unknown")
        if owner_alias_id:
            alias = await identity_service.get_alias(owner_alias_id)
            if not alias or alias.true_character_id != owner_character_id:
                raise ValueError("Invalid alias specified.")
            registered_name = alias.alias_name

        # Deduct purchase cost via double-entry ledger
        await ledger.transfer(
            sender_id=crew_id if crew_id else owner_character_id,
            receiver_id="real_estate_colonial_authority",
            amount=cost,
            reason=f"Purchase of property and business license for '{name}'",
            idempotency_key=f"biz_buy_{owner_character_id}_{uuid.uuid4()}"
        )

        biz = Business(
            name=name.strip(),
            location_id=location_id,
            owner_character_id=owner_character_id,
            owner_name=char_doc.get("name", "Unknown"),
            owner_alias_id=owner_alias_id,
            registered_owner_name=registered_name,
            crew_id=crew_id,
            business_type=business_type,
            legitimacy_score=85,
            daily_revenue=100,
            daily_expenses=25,
            suspicion_level=0
        )

        await db.businesses.insert_one(biz.to_mongo())

        await event_bus.publish(WorldEvent(
            event_type=EventType.BUSINESS_PURCHASED,
            actor_id=owner_character_id,
            location_id=location_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={
                "business_name": biz.name,
                "registered_owner": registered_name,
                "type": business_type.value,
                "location": location_id
            },
            metadata={"is_shell_ownership": owner_alias_id is not None}
        ))

        logger.info(f"Business '{biz.name}' opened in {location_id} registered under '{registered_name}'.")
        return biz

    async def run_legitimate_operation(self, business_id: str) -> Dict[str, Any]:
        """Runs a standard daily trade cycle with ordinary profits."""
        db = db_manager.db
        biz = await self.get_business(business_id)
        if not biz:
            raise ValueError("Business not found.")

        net_profit = max(10, biz.daily_revenue - biz.daily_expenses)

        # Deposit profit to owner or crew
        beneficiary_id = biz.crew_id if biz.crew_id else biz.owner_character_id
        tx = await ledger.transfer(
            sender_id=None,  # Minted through market customer commerce
            receiver_id=beneficiary_id,
            amount=net_profit,
            reason=f"Legitimate daily commercial earnings: {biz.name}",
            idempotency_key=f"biz_profit_{biz.business_id}_{uuid.uuid4()}"
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.BUSINESS_OPERATION_RUN,
            actor_id=biz.owner_character_id,
            location_id=biz.location_id,
            visibility=EventVisibility.PUBLIC,
            state_delta={"profit": net_profit, "business_id": biz.business_id}
        ))

        return {"profit": net_profit, "tx_id": tx.tx_id, "suspicion": biz.suspicion_level}

    async def run_underhand_smuggling(self, business_id: str, cargo_value: int = 600) -> Dict[str, Any]:
        """
        Runs an illicit smuggling / money laundering operation through the business.
        Generates high profits, but increases suspicion and creates financial anomaly trails.
        """
        db = db_manager.db
        biz = await self.get_business(business_id)
        if not biz:
            raise ValueError("Business not found.")

        # Boost revenue abnormally
        new_revenue = biz.daily_revenue + cargo_value
        new_suspicion = min(100, biz.suspicion_level + 20)

        ops = biz.hidden_illegal_ops
        if "smuggling_front" not in ops:
            ops.append("smuggling_front")

        biz.daily_revenue = new_revenue
        biz.suspicion_level = new_suspicion
        biz.hidden_illegal_ops = ops

        await db.businesses.update_one(
            {"_id": business_id},
            {
                "$set": {
                    "daily_revenue": new_revenue,
                    "suspicion_level": new_suspicion,
                    "hidden_illegal_ops": ops
                }
            }
        )

        # Transfer black-market payout to beneficiary
        beneficiary_id = biz.crew_id if biz.crew_id else biz.owner_character_id
        tx = await ledger.transfer(
            sender_id=None,
            receiver_id=beneficiary_id,
            amount=cargo_value,
            reason=f"Black market contraband liquidation through {biz.name}",
            idempotency_key=f"smuggle_{biz.business_id}_{uuid.uuid4()}"
        )

        # Emit SECRET world event that can be audited by Marine investigators
        await event_bus.publish(WorldEvent(
            event_type=EventType.GOODS_SMUGGLED,
            actor_id=biz.owner_character_id,
            location_id=biz.location_id,
            visibility=EventVisibility.SECRET,
            state_delta={
                "business_id": business_id,
                "business_name": biz.name,
                "cargo_value": cargo_value,
                "anomaly_score": biz.calculate_financial_anomaly(),
                "registered_owner": biz.registered_owner_name
            },
            metadata={"audit_trail_created": True}
        ))

        logger.warning(f"Illicit smuggling run through '{biz.name}'! Suspicion is now {new_suspicion}%.")
        return {
            "payout": cargo_value,
            "suspicion": new_suspicion,
            "anomaly_score": biz.calculate_financial_anomaly(),
            "tx_id": tx.tx_id
        }

    async def ensure_starter_crew_business(self, crew_id: str, captain_id: str) -> Business:
        """
        Ensures the canonical starter business 'The Golden Anchor' in Port Azure,
        owned by The Black Tide under the alias 'Marcus Vale'.
        """
        existing = await self.get_business_by_name("The Golden Anchor")
        if existing:
            return existing

        db = db_manager.db
        char_doc = await db.characters.find_one({"_id": captain_id})
        captain_name = char_doc.get("name", "Captain Redhook") if char_doc else "Captain Redhook"
        if not char_doc:
            await db.characters.insert_one({
                "_id": captain_id,
                "character_id": captain_id,
                "name": captain_name,
                "is_ai": True,
                "status": "ALIVE",
                "wealth": 2500,
                "bounty": 320000,
                "location_id": "the_crimson_parrot"
            })

        # 1. Create Alias 'Marcus Vale' for Captain Redhook
        alias = await identity_service.create_alias(
            character_id=captain_id,
            alias_name="Marcus Vale",
            legal_occupation="Merchant Importer",
            fee=0
        )

        # 2. Create Business
        biz = Business(
            name="The Golden Anchor",
            location_id="port_azure_docks",
            owner_character_id=captain_id,
            owner_name="Captain Redhook",
            owner_alias_id=alias.alias_id,
            registered_owner_name="Marcus Vale",
            crew_id=crew_id,
            business_type=BusinessType.GAMBLING_DEN,
            legitimacy_score=60,
            daily_revenue=450,  # Abnormally high revenue!
            daily_expenses=50,
            suspicion_level=35,
            hidden_illegal_ops=["smuggling_front", "rigged_gambling"]
        )

        await db.businesses.insert_one(biz.to_mongo())
        logger.info("Initialized canonical starter business 'The Golden Anchor' under alias Marcus Vale.")
        return biz


business_service = BusinessService()
