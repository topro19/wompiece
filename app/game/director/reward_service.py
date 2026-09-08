import uuid
from typing import List, Dict, Any, Optional
from app.database.connection import db_manager
from app.services.character_service import character_service
from app.game.economy.ledger import ledger
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.game.director.director_models import RewardGrant, RewardType
from app.services.logger import logger


class RewardService:
    """Centralized contextual reward engine replacing generic reward spam with meaningful outcomes."""

    async def grant(
        self,
        character_id: str,
        rewards: List[RewardGrant],
        reason: str,
        actor_npc_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Grants contextual rewards (gold, items, favors, information, access, introductions)."""
        db = db_manager.db
        char = await db.characters.find_one({"_id": character_id, "status": "ALIVE"})
        if not char:
            raise ValueError(f"Active character {character_id} not found.")

        granted_items: List[str] = []
        gold_granted = 0
        favors_granted = 0
        introductions_granted: List[str] = []
        access_granted: List[str] = []
        intel_granted: List[str] = []

        for reward in rewards:
            if reward.reward_type == RewardType.GOLD and reward.amount > 0:
                await ledger.transfer(
                    sender_id=None,
                    receiver_id=character_id,
                    amount=reward.amount,
                    reason=f"Reward: {reason}",
                    idempotency_key=f"reward_gold_{character_id}_{uuid.uuid4().hex[:8]}"
                )
                gold_granted += reward.amount
                granted_items.append(f"{reward.amount} Gold")

            elif reward.reward_type in [
                RewardType.ITEM,
                RewardType.MEDICINE,
                RewardType.WEAPON,
                RewardType.AMMUNITION,
                RewardType.MAP,
                RewardType.RARE_MATERIAL,
                RewardType.RECIPE
            ]:
                item_doc = {
                    "item_id": reward.item_id or f"item_{reward.reward_type.value.lower()}_{uuid.uuid4().hex[:6]}",
                    "name": reward.item_name or reward.description,
                    "type": reward.reward_type.value.lower(),
                    "quantity": reward.quantity,
                    "metadata": reward.metadata
                }
                await character_service.add_item(character_id, item_doc)
                granted_items.append(f"{reward.quantity}x {item_doc['name']}")

            elif reward.reward_type == RewardType.FAVOR and actor_npc_name:
                from app.game.director.relationship_service import relationship_service
                await relationship_service.add_favor(
                    character_id=character_id,
                    npc_name=actor_npc_name,
                    favors=reward.amount or 1,
                    reason=reward.description
                )
                favors_granted += (reward.amount or 1)
                granted_items.append(f"Favor owed by {actor_npc_name}")

            elif reward.reward_type == RewardType.INTRODUCTION:
                contact_name = reward.metadata.get("contact_name") or reward.description
                from app.game.director.relationship_service import relationship_service
                await relationship_service.get_or_create_relationship(character_id, contact_name)
                introductions_granted.append(contact_name)
                granted_items.append(f"Introduction to {contact_name}")

            elif reward.reward_type in [RewardType.INFORMATION, RewardType.SECRET]:
                secret_title = reward.item_name or reward.description
                intel_doc = {
                    "intel_id": f"intel_{uuid.uuid4().hex[:8]}",
                    "title": secret_title,
                    "description": reward.description,
                    "source": actor_npc_name or "Observation",
                    "value_grade": reward.metadata.get("value_grade", "VALUABLE")
                }
                await db.characters.update_one(
                    {"_id": character_id},
                    {"$push": {"inventory": {
                        "item_id": intel_doc["intel_id"],
                        "name": f"Confidential Intel: {secret_title}",
                        "type": "intel",
                        "quantity": 1,
                        "metadata": intel_doc
                    }}}
                )
                intel_granted.append(secret_title)
                granted_items.append(f"Secret: {secret_title}")

            elif reward.reward_type == RewardType.ACCESS:
                access_key = reward.metadata.get("facility_id", reward.description)
                access_granted.append(access_key)
                granted_items.append(f"Access granted: {access_key}")

        summary_text = ", ".join(granted_items) if granted_items else "Experience & Wisdom"

        await event_bus.publish(WorldEvent(
            event_type=EventType.REWARD_GRANTED,
            actor_id=character_id,
            location_id=char.get("location_id", "port_azure"),
            visibility=EventVisibility.PRIVATE,
            state_delta={
                "character_id": character_id,
                "reason": reason,
                "gold": gold_granted,
                "favors": favors_granted,
                "items": granted_items,
                "source_npc": actor_npc_name
            }
        ))

        logger.info(f"Granted contextual rewards to {char.get('name')} for '{reason}': {summary_text}")
        return {
            "summary": summary_text,
            "gold_granted": gold_granted,
            "favors_granted": favors_granted,
            "introductions_granted": introductions_granted,
            "intel_granted": intel_granted,
            "access_granted": access_granted,
            "items_granted": granted_items
        }


reward_service = RewardService()
