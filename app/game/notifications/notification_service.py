import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any
from app.database.connection import db_manager
from app.game.notifications.notification_models import (
    NotificationPriority,
    WorldMessage,
    WorldTimelineEvent,
    OfflineRecap,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """Asynchronous notification and world event message service."""

    def __init__(self):
        self.messages_collection_name = "world_messages"
        self.timeline_collection_name = "world_timeline"

    @property
    def messages_col(self):
        return db_manager.db[self.messages_collection_name]

    @property
    def timeline_col(self):
        return db_manager.db[self.timeline_collection_name]

    async def send_world_message(
        self,
        character_id: str,
        user_id: str,
        sender_name: str,
        content: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        sender_type: str = "NPC",
        location_name: str = "Port Azure",
        requires_response: bool = False,
        options: Optional[List[str]] = None,
        opportunity_id: Optional[str] = None,
        expires_in_hours: int = 24,
    ) -> WorldMessage:
        """Creates and stores an authoritative world message with timeline logging."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=expires_in_hours)

        msg = WorldMessage(
            character_id=character_id,
            user_id=user_id,
            sender_name=sender_name,
            sender_type=sender_type,
            location_name=location_name,
            content=content,
            priority=priority,
            requires_response=requires_response,
            options=options or [],
            opportunity_id=opportunity_id,
            created_at=now,
            expires_at=expires_at,
            is_resolved=False,
        )

        await self.messages_col.insert_one(msg.to_mongo())

        # Also write into character world timeline
        timeline_snippet = f"[{sender_name} @ {location_name}] {content[:100]}"
        category = "THREAT" if priority in [NotificationPriority.HIGH, NotificationPriority.CRITICAL] else "MESSAGE"
        await self.record_timeline_event(character_id=character_id, text=timeline_snippet, category=category)

        return msg

    def format_discord_delivery(self, msg: WorldMessage) -> Dict[str, Any]:
        """Formats message for Discord output following Section 173 anti-spam rules.
        
        CRITICAL RULE:
        Tag <@user_id> ONLY on HIGH and CRITICAL priority notifications.
        LOW and NORMAL are delivered silently or logged without pinging the user.
        """
        is_urgent = msg.priority in [NotificationPriority.HIGH, NotificationPriority.CRITICAL]
        mention = f"<@{msg.user_id}>" if is_urgent else ""

        priority_prefixes = {
            NotificationPriority.LOW: "📜 [LOG]",
            NotificationPriority.NORMAL: "🌊 [WORLD]",
            NotificationPriority.HIGH: "⚠️ [DISPATCH]",
            NotificationPriority.CRITICAL: "🚨 [URGENT EMERGENCY]",
        }
        prefix = priority_prefixes.get(msg.priority, "🌊")

        title = f"{prefix} Message from {msg.sender_name} ({msg.location_name})"
        body_lines = [
            f"**From:** {msg.sender_name} ({msg.sender_type})",
            f"**Location:** {msg.location_name}",
            f"**Priority:** `{msg.priority.value}`",
            "",
            f'> "{msg.content}"',
        ]

        if msg.requires_response and msg.options:
            body_lines.append("")
            body_lines.append("**Available Responses:**")
            for idx, opt in enumerate(msg.options, start=1):
                body_lines.append(f"  `{idx}.` {opt}")

        full_content = f"{mention}\n" + "\n".join(body_lines) if mention else "\n".join(body_lines)

        return {
            "title": title,
            "content": full_content.strip(),
            "mention": mention,
            "is_urgent": is_urgent,
            "priority": msg.priority.value,
            "message_id": msg.message_id,
        }

    async def get_unread_messages(self, character_id: str, limit: int = 10) -> List[WorldMessage]:
        """Retrieves unexpired unread messages for a character."""
        now = datetime.now(timezone.utc)
        cursor = self.messages_col.find({
            "character_id": character_id,
            "read_at": None,
        }).sort("created_at", -1)
        docs = await cursor.to_list(length=limit)

        results = []
        for doc in docs:
            exp = doc.get("expires_at")
            if exp:
                exp_dt = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
                if exp_dt < now:
                    continue
            results.append(WorldMessage(**doc))
        return results

    async def mark_message_read(self, message_id: str) -> bool:
        """Marks a message as read."""
        res = await self.messages_col.update_one(
            {"_id": message_id},
            {"$set": {"read_at": datetime.now(timezone.utc)}}
        )
        return res.modified_count > 0

    async def resolve_message(self, message_id: str) -> bool:
        """Marks a message as resolved / handled."""
        now = datetime.now(timezone.utc)
        res = await self.messages_col.update_one(
            {"_id": message_id},
            {"$set": {"is_resolved": True, "read_at": now}}
        )
        return res.modified_count > 0

    async def record_timeline_event(self, character_id: str, text: str, category: str = "GENERAL") -> WorldTimelineEvent:
        """Records a world event in the character's chronological ledger."""
        evt = WorldTimelineEvent(
            character_id=character_id,
            event_text=text,
            category=category,
            timestamp=datetime.now(timezone.utc),
        )
        await self.timeline_col.insert_one(evt.to_mongo())
        return evt

    async def get_recent_timeline(self, character_id: str, limit: int = 15) -> List[WorldTimelineEvent]:
        """Fetches the latest chronological timeline events for a character."""
        cursor = self.timeline_col.find({
            "character_id": character_id
        }).sort("timestamp", -1)
        docs = await cursor.to_list(length=limit)
        return [WorldTimelineEvent(**doc) for doc in docs]

    async def get_offline_recap(
        self,
        character_id: str,
        character_name: str,
        since_timestamp: Optional[datetime] = None,
    ) -> OfflineRecap:
        """Builds a 'While You Were Away' recap summarizing unread world activity."""
        now = datetime.now(timezone.utc)
        start_time = since_timestamp or (now - timedelta(hours=24))

        # Query unread messages
        unread_msgs = await self.get_unread_messages(character_id, limit=20)
        urgent_alerts = [
            f"⚠️ [{m.priority.value}] {m.sender_name}: {m.content}"
            for m in unread_msgs
            if m.priority in [NotificationPriority.HIGH, NotificationPriority.CRITICAL]
        ]

        # Query recent timeline events
        cursor = self.timeline_col.find({
            "character_id": character_id
        }).sort("timestamp", -1)
        timeline_docs = await cursor.to_list(length=5)

        highlights = [d.get("event_text", "") for d in timeline_docs if d.get("event_text")]

        return OfflineRecap(
            character_name=character_name,
            unread_messages_count=len(unread_msgs),
            pending_opportunities_count=0,
            timeline_highlights=highlights,
            urgent_alerts=urgent_alerts,
        )


notification_service = NotificationService()
