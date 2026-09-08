import random
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.database.connection import db_manager
from app.game.director.director_models import WorldDiscovery, DiscoveryType, RewardGrant, RewardType
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.game.investigations.case_service import investigation_service
from app.game.investigations.case_models import EvidenceType
from app.services.logger import logger


class DiscoveryService:
    """Authoritative contextual discovery engine for point-of-interest exploration and crime scenes."""

    async def explore_location(self, character_id: str, location_id: Optional[str] = None) -> WorldDiscovery:
        """Explores the surroundings, producing a context-sensitive narrative discovery."""
        db = db_manager.db
        char = await db.characters.find_one({"_id": character_id})
        loc_id = location_id or (char.get("location_id") if char else "port_azure")

        # Check existing active discoveries for this player at this location
        existing = await db.discoveries.find_one({
            "character_id": character_id,
            "location_id": loc_id,
            "interacted": False
        })
        if existing:
            return WorldDiscovery(**existing)

        # Contextual discovery generator
        # Near docks or alleyways: murder body or smuggling cache
        if "dock" in loc_id or "azure" in loc_id or "alley" in loc_id:
            disc = WorldDiscovery(
                character_id=character_id,
                discovery_type=DiscoveryType.SUSPICIOUS_BODY,
                title="A Slumped Figure in the Wharf Shadows",
                description="Behind the saltfish warehouse, a well-dressed sailor lies motionless against the cold stone wall. A dark pool stains the cobblestones beneath him. Nobody else appears to be nearby.",
                location_id=loc_id,
                suggested_actions=[
                    "Inspect the body for wounds and markings",
                    "Search the victim's pockets and possessions",
                    "Report the crime scene immediately to Marine Headquarters",
                    "Track the bloody boot prints leading down the alley",
                    "Quietly slip away and ignore the situation"
                ]
            )
        elif "market" in loc_id:
            disc = WorldDiscovery(
                character_id=character_id,
                discovery_type=DiscoveryType.SMUGGLING_CACHE,
                title="A Loose Floorboard Behind the Spice Stalls",
                description="A scent of pungent medicinal sap and fine tobacco wafts from a concealed trapdoor beneath a stack of burlap grain sacks.",
                location_id=loc_id,
                suggested_actions=[
                    "Pry open the trapdoor and examine the contents",
                    "Mark the location to inform the Apothecary or Merchants",
                    "Wait in the tavern to see who accesses the cache"
                ]
            )
        else:
            disc = WorldDiscovery(
                character_id=character_id,
                discovery_type=DiscoveryType.WOUNDED_SAILOR,
                title="A Shivering Drifter in the Mist",
                description="A former merchant sailor with a bandaged leg sits huddled near a mooring post, clutching an empty bottle and shivering against the sea spray.",
                location_id=loc_id,
                suggested_actions=[
                    "Offer the sailor bread or grog",
                    "Ask what happened to his crew and vessel",
                    "Leave him to his misery"
                ]
            )

        await db.discoveries.insert_one(disc.to_mongo())
        await event_bus.publish(WorldEvent(
            event_type=EventType.DISCOVERY_MADE,
            actor_id=character_id,
            location_id=loc_id,
            visibility=EventVisibility.PRIVATE,
            state_delta={"discovery_id": disc.discovery_id, "type": disc.discovery_type.value, "title": disc.title}
        ))
        logger.info(f"{char.get('name') if char else character_id} made a discovery: '{disc.title}'.")
        return disc

    async def resolve_discovery_action(
        self,
        character_id: str,
        discovery_id: str,
        action_choice: str
    ) -> Dict[str, Any]:
        """Resolves a player's strategic choice upon making a discovery, applying cascading consequences."""
        db = db_manager.db
        doc = await db.discoveries.find_one({"_id": discovery_id, "character_id": character_id})
        if not doc:
            raise ValueError("Discovery record not found.")

        discovery = WorldDiscovery(**doc)
        char = await db.characters.find_one({"_id": character_id})
        choice_lower = action_choice.lower()

        from app.game.director.reward_service import reward_service
        from app.game.director.relationship_service import relationship_service
        from app.game.director.thread_service import thread_service
        from app.game.director.reputation_service import reputation_service

        narrative = ""
        rewards_granted = []
        thread_updates = []

        # Mark discovery interacted
        await db.discoveries.update_one(
            {"_id": discovery_id},
            {"$set": {"interacted": True, "chosen_action": action_choice}}
        )

        if discovery.discovery_type == DiscoveryType.SUSPICIOUS_BODY:
            if "report" in choice_lower or "marine" in choice_lower:
                # Open official marine case & log evidence
                case = await investigation_service.open_case(
                    assigned_marine_id="marine_customs_inspector",
                    title="Alleyway Homicide: Wharf Saltfish Warehouse",
                    location_id=discovery.location_id,
                    suspect_names=["Unknown Dock Prowler"]
                )
                await investigation_service.add_evidence(
                    case_id=case.case_id,
                    evidence_type=EvidenceType.TESTIMONY,
                    title="Citizen Report: Body Found Behind Wharf",
                    description=f"{char.get('name', 'Citizen')} reported finding a deceased sailor with blade wounds.",
                    source=char.get("name", "Good Samaritan"),
                    location_id=discovery.location_id,
                    discovered_by_id=character_id
                )
                await reputation_service.adjust_reputation(character_id, {"marine": 15, "civilian": 10, "criminal": -5})
                await reputation_service.record_action_traits(character_id, {"trustworthy": 5, "diplomatic": 3})

                # Update story thread
                th = await thread_service.get_thread_by_title("The Port Azure Murders")
                if th:
                    await thread_service.update_thread(
                        th.thread_id,
                        new_fact=f"{char.get('name')} reported victim #4 to the Marines; Case #{case.case_number} officially opened.",
                        log_entry=f"Marines secured the scene after {char.get('name')}'s report."
                    )
                narrative = f"You quickly alerted the nearest Marine patrol. Inspector Vance's men cordoned off the alleyway, opening Case #{case.case_number}. The officers note your civic cooperation with gratitude."

            elif "search" in choice_lower or "pocket" in choice_lower:
                # Search victim: find coin and stolen medicine vial with Mara's crest -> Thread Merge!
                pouch_gold = 25
                await reward_service.grant(
                    character_id=character_id,
                    rewards=[
                        RewardGrant(reward_type=RewardType.GOLD, amount=pouch_gold, description="Pocketed from victim"),
                        RewardGrant(
                            reward_type=RewardType.ITEM,
                            item_id="vial_apothecary_herb",
                            item_name="Glass Vial with Green Wax Crest",
                            quantity=1,
                            description="An unbroken medicinal tincture bearing Mara's personal apothecary crest."
                        )
                    ],
                    reason="Searched murder victim"
                )
                await reputation_service.record_action_traits(character_id, {"opportunistic": 5, "cautious": 2})

                # Thread Merge: The Port Azure Murders & The Apothecary's Missing Shipment!
                murder_th = await thread_service.get_thread_by_title("The Port Azure Murders")
                apoth_th = await thread_service.get_thread_by_title("The Apothecary's Missing Shipment")
                if murder_th and apoth_th:
                    await thread_service.merge_threads(
                        source_thread_id=apoth_th.thread_id,
                        target_thread_id=murder_th.thread_id,
                        merge_reason="Victim was carrying Mara's stolen medicinal herbal tincture with green wax seal!"
                    )
                    thread_updates.append("Merged 'The Apothecary's Missing Shipment' into 'The Port Azure Murders'!")

                narrative = f"Kneeling by the body, you search the victim's pockets. You find {pouch_gold} Gold in loose coin and an intact glass vial bearing Mara the Apothecary's green wax seal! The missing medicinal cargo and the murders are connected!"

            elif "track" in choice_lower:
                await reputation_service.record_action_traits(character_id, {"cautious": 4, "ambitious": 3})
                narrative = "You examine the damp ground and follow a trail of smeared saltwater and boots heading toward the abandoned boathouse at Skull Rock Anchorage."

            elif "inspect" in choice_lower:
                narrative = "You lean closely over the victim. The cut is clean and deliberate—inflicted with a curved naval cutlass. The victim's boots and belt buckle have been stolen."

            else:
                narrative = "You quietly step back into the shadow of the wharf, leaving the deceased undisturbed as fog blankets the harbor."

        elif discovery.discovery_type == DiscoveryType.SMUGGLING_CACHE:
            if "pry" in choice_lower or "open" in choice_lower:
                await reward_service.grant(
                    character_id=character_id,
                    rewards=[
                        RewardGrant(reward_type=RewardType.ITEM, item_id="vintage_rum", item_name="Smuggled Vintage Rum", quantity=2, description="Fine private reserve rum"),
                        RewardGrant(reward_type=RewardType.GOLD, amount=40, description="Hidden cache coins")
                    ],
                    reason="Looted smuggling cache"
                )
                narrative = "You pry up the loose timbers and pull out two bottles of contraband rum and 40 Gold wrapped in oiled canvas."
            else:
                narrative = "You note the exact location of the cache and slip away unnoticed."

        else:
            narrative = f"You approach the situation and proceed cautiously. ({action_choice})"

        return {
            "success": True,
            "discovery_id": discovery_id,
            "action_taken": action_choice,
            "narrative": narrative,
            "outcome_text": narrative,
            "thread_updates": thread_updates
        }


discovery_service = DiscoveryService()
