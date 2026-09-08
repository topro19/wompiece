import random
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.database.connection import db_manager
from app.config.settings import settings
from app.game.director.director_models import WorldDiscovery, DiscoveryType, RewardGrant, RewardType
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.game.investigations.case_service import investigation_service
from app.game.investigations.case_models import EvidenceType
from app.ai.providers.gemini_provider import gemini_provider
from app.ai.schemas.discovery_schemas import AIDiscoveryProposal, AIDiscoveryResolution
from app.services.logger import logger


DISCOVERY_TEMPLATES: List[Dict[str, Any]] = [
    {
        "type": DiscoveryType.SUSPICIOUS_BODY,
        "title": "A Slumped Figure in the Wharf Shadows",
        "description": "Behind the saltfish warehouse, a well-dressed sailor lies motionless against the cold stone wall. A dark pool stains the cobblestones beneath him. Nobody else appears to be nearby.",
        "environments": ["dock", "wharf", "alley", "harbor", "port"],
        "suggested_actions": [
            "Inspect the body for wounds and markings",
            "Search the victim's pockets and possessions",
            "Report the crime scene immediately to Marine Headquarters",
            "Track the bloody boot prints leading down the alley",
            "Quietly slip away and ignore the situation"
        ]
    },
    {
        "type": DiscoveryType.SUSPICIOUS_BODY,
        "title": "An Adrift Skiff with a Fallen Sailor",
        "description": "A small wooden rowboat bumps rhythmically against the barnacled pilings. Inside, a sailor lies slumped across the thwart, an empty satchel clutched tightly in his stiffened fingers.",
        "environments": ["dock", "port", "cove", "anchorage", "bay"],
        "suggested_actions": [
            "Haul the skiff in and pry open the satchel",
            "Check for signs of life or poison",
            "Search beneath the floorboards for hidden cargo",
            "Call out to the dock watch"
        ]
    },
    {
        "type": DiscoveryType.ABANDONED_CARGO,
        "title": "Waterlogged Rum Casks by the Breakers",
        "description": "Two heavy oak casks, bound with rusted iron hoops and branded with the East Azure Trading seal, bob in the surf caught in tangled dark kelp.",
        "environments": ["dock", "beach", "cove", "port", "reef"],
        "suggested_actions": [
            "Haul the casks ashore and pry the bungs open",
            "Inspect the company markings for shipment origin",
            "Stash the casks in the rocks to sell later",
            "Report the flotsam to the harbor master"
        ]
    },
    {
        "type": DiscoveryType.ABANDONED_CARGO,
        "title": "A Smashed Tea Crate Behind the Fishmarket",
        "description": "A splintered wooden crate lies half-buried under discarded nets. Fragrant dry tea leaves and wrapped packets of pressed spices spill across the damp stones.",
        "environments": ["market", "port", "dock", "square"],
        "suggested_actions": [
            "Salvage the undamaged spice packets",
            "Search the packaging for merchant stamps",
            "Ask local stallholders whose cart dropped it"
        ]
    },
    {
        "type": DiscoveryType.SECRET_MEETING,
        "title": "Muffled Whispers Behind the Drydock Keel",
        "description": "In the deep shadow of an overturned merchant hull, two figures speak in urgent hushed tones. One wears a Marine officer's cloak; the other bears the rough scars of a pirate corsair.",
        "environments": ["dock", "drydock", "alley", "cove", "anchorage"],
        "suggested_actions": [
            "Creep closer and eavesdrop on the conversation",
            "Confront the pair with hand on your cutlass",
            "Shadow the pirate once they part ways",
            "Sneak away and sell the rumor to the tavernkeeper"
        ]
    },
    {
        "type": DiscoveryType.SECRET_MEETING,
        "title": "A Lantern Signal from the Old Belltower",
        "description": "High above the town roofs, a hooded lookout flashes a tin lantern three times toward an unlit schooner anchored out past the reef.",
        "environments": ["town", "port", "fort", "hill", "lookout"],
        "suggested_actions": [
            "Climb the tower stairs to confront the signaller",
            "Note the schooner's bearing and watch for landing boats",
            "Alert the Marine customs post of an illegal night landing"
        ]
    },
    {
        "type": DiscoveryType.SMUGGLING_CACHE,
        "title": "A Loose Floorboard Behind the Spice Stalls",
        "description": "A scent of pungent medicinal sap and fine tobacco wafts from a concealed trapdoor beneath a stack of burlap grain sacks.",
        "environments": ["market", "alley", "warehouse", "port"],
        "suggested_actions": [
            "Pry open the trapdoor and examine the contents",
            "Mark the location to inform the Apothecary or Merchants",
            "Wait in the shadows to see who accesses the cache"
        ]
    },
    {
        "type": DiscoveryType.SMUGGLING_CACHE,
        "title": "A False-Bottom Cask at the Cooperage",
        "description": "A stack of seasoned oak barrels hides a hollow timber lined with pitch, packed with wrapped bars of contraband silver bullion.",
        "environments": ["dock", "warehouse", "workshop", "market"],
        "suggested_actions": [
            "Slip a silver bar into your coat and conceal the cask",
            "Leave a discreet chalk mark for your crew to collect tonight",
            "Turn the cache in to customs for a finder's bounty"
        ]
    },
    {
        "type": DiscoveryType.WOUNDED_SAILOR,
        "title": "A Shivering Drifter in the Mist",
        "description": "A former merchant sailor with a bandaged leg sits huddled near a mooring post, clutching an empty bottle and shivering against the sea spray.",
        "environments": ["dock", "cove", "beach", "port", "alley"],
        "suggested_actions": [
            "Offer the sailor bread or spiced rum",
            "Ask what happened to his crew and vessel",
            "Intimidate him into revealing who robbed him",
            "Leave him to his misery"
        ]
    },
    {
        "type": DiscoveryType.WOUNDED_SAILOR,
        "title": "A Deserting Marine Hidden in the Coal Chute",
        "description": "A young seaman in a mud-caked Marine tunic cowers behind an iron coal grate, clutching an armory key ring and bleeding from a bayonet graze.",
        "environments": ["fort", "town", "port", "alley", "barracks"],
        "suggested_actions": [
            "Offer to smuggle him past the dock gates for a price",
            "Demand the keys he stole from the armory",
            "Shout for the Marine guard to claim the deserter bounty"
        ]
    },
    {
        "type": DiscoveryType.LOST_TREASURE,
        "title": "A Barnacle-Encrusted Sea Chest in the Silt",
        "description": "Exposed by the receding tide, an iron-banded cedar chest lies wedged beneath the rotting pilings of the old pier. Its padlock is green with verdigris.",
        "environments": ["dock", "cove", "beach", "reef", "pier"],
        "suggested_actions": [
            "Smash the corroded lock with a heavy iron belaying pin",
            "Carefully pick the lock with a fine wire",
            "Rope the chest and haul it to safety before the tide rises"
        ]
    },
    {
        "type": DiscoveryType.LOST_TREASURE,
        "title": "A Dropped Leather Map Case",
        "description": "Under an abandoned wagon near the harbor gates, you spot an oiled calfskin tube sealed with beeswax, embossed with nautical compass roses.",
        "environments": ["gate", "market", "road", "port", "dock"],
        "suggested_actions": [
            "Unseal the tube and study the hand-drawn chart",
            "Look around for the flustered captain who lost it",
            "Take it to the local tavern to auction to the highest bidder"
        ]
    },
    {
        "type": DiscoveryType.ILLEGAL_GAMBLING,
        "title": "A Midnight Dice Ring Behind the Cooperage",
        "description": "A circle of off-duty dockers and privateer deckhands huddle in the tallow-candle glow, tossing carved bone dice on an upturned barrel as coins clink loudly.",
        "environments": ["alley", "dock", "tavern", "port", "cellar"],
        "suggested_actions": [
            "Toss 10 Gold on the barrel and call the next roll",
            "Watch closely to see if the dice are weighted",
            "Threaten to call the watch unless cut in on the pot"
        ]
    },
    {
        "type": DiscoveryType.HIDDEN_ROOM,
        "title": "A Concealed Cellar Behind the Keg Stacks",
        "description": "Moving an empty cider tun reveals a narrow stone staircase descending beneath the street, faint candlelight and clinking glassware audible from below.",
        "environments": ["tavern", "cellar", "warehouse", "dock"],
        "suggested_actions": [
            "Descend into the underground speakeasy with weapon ready",
            "Listen at the trapdoor opening to gather intel",
            "Push the keg back into place and carve a secret mark"
        ]
    }
]


class DiscoveryService:
    """Authoritative AI-driven contextual discovery engine with living story thread integration and procedural backup."""

    async def explore_location(self, character_id: str, location_id: Optional[str] = None) -> WorldDiscovery:
        """
        Explores the surroundings. Dynamically generates novel discoveries via Gemini AI
        tailored to active story threads, world events, and environment, preventing repetition.
        """
        db = db_manager.db
        char = await db.characters.find_one({"_id": character_id})
        loc_id = location_id or (char.get("location_id") if char else "port_azure")

        # 1. Check existing un-interacted discovery for this player at this location
        existing = await db.discoveries.find_one({
            "character_id": character_id,
            "location_id": loc_id,
            "interacted": False
        })
        if existing:
            return WorldDiscovery(**existing)

        # 2. Retrieve recent discoveries to enforce anti-repetition
        recent_cursor = db.discoveries.find(
            {"character_id": character_id}
        ).sort("discovered_at", -1).limit(6)
        recent_docs = await recent_cursor.to_list(length=6)
        recent_titles = [d.get("title") for d in recent_docs if d.get("title")]

        # 3. Retrieve living world context (Active Story Threads, NPCs, Character)
        from app.game.director.thread_service import thread_service
        from app.game.director.relationship_service import relationship_service

        active_threads = await thread_service.list_active_threads()
        thread_bullets = []
        for t in active_threads[:4]:
            facts = ", ".join(t.known_facts[-2:]) if t.known_facts else "No confirmed facts"
            thread_bullets.append(f"- **{t.title}** ({t.status.value}): {t.summary} [Known clues: {facts}]")
        threads_summary = "\n".join(thread_bullets) if thread_bullets else "No active story threads in this sector."

        rels = await relationship_service.list_relationships(character_id)
        npc_bullets = [f"{r.npc_name} ({r.level.value})" for r in rels[:4]] if rels else []
        npcs_summary = ", ".join(npc_bullets) if npc_bullets else "None yet"

        char_name = char.get("name", "Wanderer") if char else "Wanderer"
        char_faction = char.get("faction", "Independent") if char else "Independent"
        char_rank = char.get("rank", "Deckhand") if char else "Deckhand"

        # 4. Attempt AI-Powered Dynamic Generation via Gemini
        ai_generated_discovery = None
        try:
            system_instruction = (
                "You are the Master Game Director AI for Pirate Wars, a living gritty pirate world simulation.\n"
                "Your objective is to generate an organic, dynamic, non-repetitive contextual discovery for a player exploring their surroundings.\n"
                "RULES:\n"
                "1. Deeply tie the discovery to the player's physical location, atmosphere, and the active story threads.\n"
                "2. The discovery can be: an unexpected crime scene clue, dropped contraband, plotters meeting in secret, an injured or shady NPC, a concealed cache, an occult relic, an illegal game, or an old sea chart.\n"
                "3. NEVER repeat or closely imitate any discovery the player has already encountered recently.\n"
                "4. Provide 3 to 4 distinct, evocative action choices (under 75 characters each) offering moral, daring, cautious, or self-serving avenues.\n"
                "5. Ensure the tone is authentic 18th-century nautical fiction (cutlasses, tallow lanterns, brine, colonial tensions)."
            )
            prompt = (
                f"=== EXPLORING CHARACTER ===\n"
                f"Name: {char_name} | Faction: {char_faction} | Rank: {char_rank}\n"
                f"Current Location: {loc_id}\n"
                f"Known Acquaintances: {npcs_summary}\n\n"
                f"=== LIVING WORLD STORY THREADS ===\n"
                f"{threads_summary}\n\n"
                f"=== RECENT DISCOVERIES EXPERIENCED (STRICTLY DO NOT DUPLICATE) ===\n"
                f"{', '.join(recent_titles) if recent_titles else 'None'}\n\n"
                f"Generate a unique contextual exploration discovery for {char_name} at {loc_id}."
            )

            proposal: AIDiscoveryProposal = await gemini_provider.structured_output(
                prompt=prompt,
                schema=AIDiscoveryProposal,
                system_instruction=system_instruction,
                model=settings.GEMINI_MODEL_HEAVY
            )

            # Validate type against DiscoveryType enum
            raw_type = (proposal.discovery_type or "SUSPICIOUS_BODY").upper().strip()
            valid_type = DiscoveryType.SUSPICIOUS_BODY
            for dt in DiscoveryType:
                if dt.value == raw_type or dt.name == raw_type:
                    valid_type = dt
                    break

            actions = [a.strip() for a in proposal.suggested_actions if a.strip()][:4]
            if len(actions) < 2:
                actions = ["Inspect the discovery closely", "Pocket what you can and slip away", "Alert local citizens"]

            ai_generated_discovery = WorldDiscovery(
                character_id=character_id,
                discovery_type=valid_type,
                title=proposal.title.strip(),
                description=proposal.description.strip(),
                location_id=loc_id,
                suggested_actions=actions
            )
            logger.info(f"[AI DISCOVERY] Generated dynamic discovery '{ai_generated_discovery.title}' for {char_name} at {loc_id}.")

        except Exception as e:
            logger.warning(f"AI discovery generation fell back to procedural catalogue: {e}")

        # 5. Procedural Fallback if AI fails or returns duplicate
        if not ai_generated_discovery or ai_generated_discovery.title in recent_titles:
            loc_lower = loc_id.lower()
            matching_candidates = [
                t for t in DISCOVERY_TEMPLATES
                if any(env in loc_lower for env in t["environments"]) and t["title"] not in recent_titles
            ]
            if not matching_candidates:
                matching_candidates = [t for t in DISCOVERY_TEMPLATES if t["title"] not in recent_titles]
            if not matching_candidates:
                last_title = recent_titles[0] if recent_titles else None
                matching_candidates = [t for t in DISCOVERY_TEMPLATES if t["title"] != last_title] or DISCOVERY_TEMPLATES

            chosen = random.choice(matching_candidates)
            ai_generated_discovery = WorldDiscovery(
                character_id=character_id,
                discovery_type=chosen["type"],
                title=chosen["title"],
                description=chosen["description"],
                location_id=loc_id,
                suggested_actions=chosen["suggested_actions"]
            )

        disc = ai_generated_discovery
        await db.discoveries.insert_one(disc.to_mongo())
        await event_bus.publish(WorldEvent(
            event_type=EventType.DISCOVERY_MADE,
            actor_id=character_id,
            location_id=loc_id,
            visibility=EventVisibility.PRIVATE,
            state_delta={"discovery_id": disc.discovery_id, "type": disc.discovery_type.value, "title": disc.title}
        ))
        logger.info(f"{char_name} recorded new discovery: '{disc.title}'.")
        return disc

    async def resolve_discovery_action(
        self,
        character_id: str,
        discovery_id: str,
        action_choice: str
    ) -> Dict[str, Any]:
        """Resolves a player's strategic choice upon making a discovery, using AI reasoning with procedural fallback."""
        db = db_manager.db
        doc = await db.discoveries.find_one({"_id": discovery_id, "character_id": character_id})
        if not doc:
            raise ValueError("Discovery record not found.")

        # If already resolved (e.g. repeated click), return cached summary immediately
        if doc.get("interacted") and doc.get("resolution_summary"):
            return doc["resolution_summary"]

        discovery = WorldDiscovery(**doc)
        char = await db.characters.find_one({"_id": character_id})
        char_name = char.get("name", "Traveler") if char else "Traveler"
        char_faction = char.get("faction", "Independent") if char else "Independent"

        from app.game.director.reward_service import reward_service
        from app.game.director.relationship_service import relationship_service
        from app.game.director.thread_service import thread_service
        from app.game.director.reputation_service import reputation_service

        # Mark discovery interacted immediately
        await db.discoveries.update_one(
            {"_id": discovery_id},
            {"$set": {"interacted": True, "chosen_action": action_choice}}
        )

        # Retrieve active story threads for context
        active_threads = await thread_service.list_active_threads()
        threads_summary = "\n".join([f"- {t.title}: {t.summary}" for t in active_threads[:3]])

        narrative = ""
        rewards_granted: List[Dict[str, Any]] = []
        thread_updates: List[str] = []
        merged_thread = None

        # 1. Attempt AI-driven consequence resolution
        try:
            res_system = (
                "You are the Game Director for Pirate Wars evaluating a player's choice on a world discovery.\n"
                "Determine the immediate consequence, any physical loot or gold found, reputation changes, "
                "and whether this action uncovers a clue that updates or connects an active story thread.\n"
                "Keep the outcome realistic to pirate and maritime law fiction."
            )
            res_prompt = (
                f"Character: {char_name} (Faction: {char_faction})\n"
                f"Encountered Discovery '{discovery.title}' ({discovery.discovery_type.value}):\n"
                f"\"{discovery.description}\"\n\n"
                f"Action Chosen by Player:\n> {action_choice}\n\n"
                f"Active Story Threads:\n{threads_summary or 'None'}\n\n"
                f"Resolve the physical outcome and state consequences for {char_name}."
            )

            resolution: AIDiscoveryResolution = await gemini_provider.structured_output(
                prompt=res_prompt,
                schema=AIDiscoveryResolution,
                system_instruction=res_system,
                model=settings.GEMINI_MODEL_BASIC
            )

            narrative = resolution.outcome_narrative.strip()

            # Process AI rewards
            grants: List[RewardGrant] = []
            if resolution.gold_reward > 0:
                grants.append(RewardGrant(
                    reward_type=RewardType.GOLD,
                    amount=resolution.gold_reward,
                    description=f"Acquired during exploration ({discovery.title})"
                ))
            if resolution.item_name:
                item_slug = resolution.item_name.lower().replace(" ", "_")
                grants.append(RewardGrant(
                    reward_type=RewardType.ITEM,
                    item_id=f"item_{item_slug[:16]}",
                    item_name=resolution.item_name,
                    quantity=1,
                    description=f"Discovered while exploring: {discovery.title}"
                ))

            if grants:
                await reward_service.grant(
                    character_id=character_id,
                    rewards=grants,
                    reason=f"Discovery choice: {action_choice[:50]}"
                )
                rewards_granted = [g.model_dump() for g in grants]

            # Process AI reputation changes
            if resolution.reputation_faction and resolution.reputation_delta != 0:
                fac = resolution.reputation_faction.lower()
                if fac in ["marine", "pirate", "merchant", "civilian", "criminal", "independent"]:
                    await reputation_service.adjust_reputation(character_id, {fac: resolution.reputation_delta})

            # Process AI thread clues
            if resolution.thread_clue:
                thread_updates.append(resolution.thread_clue)
                # Find matching thread or append to top active thread
                for th in active_threads:
                    if th.title.lower() in narrative.lower() or (resolution.merged_thread_title and th.title.lower() in resolution.merged_thread_title.lower()):
                        await thread_service.update_thread(
                            th.thread_id,
                            new_fact=resolution.thread_clue,
                            log_entry=f"Clue uncovered by {char_name} during exploration."
                        )
                        break

            if resolution.merged_thread_title:
                merged_thread = resolution.merged_thread_title

        except Exception as e:
            logger.warning(f"AI discovery resolution fell back to procedural logic: {e}")

        # 2. Procedural Fallback if AI resolution returned empty narrative
        if not narrative:
            choice_lower = action_choice.lower()
            if "search" in choice_lower or "pocket" in choice_lower or "pry" in choice_lower or "haul" in choice_lower or "smash" in choice_lower:
                rew = [
                    RewardGrant(reward_type=RewardType.GOLD, amount=30, description="Plundered during exploration"),
                    RewardGrant(reward_type=RewardType.ITEM, item_id="cask_fine_rum", item_name="Cask of Fine Rum", quantity=1, description="Found during exploration")
                ]
                await reward_service.grant(character_id=character_id, rewards=rew, reason="Exploration search")
                rewards_granted = [r.model_dump() for r in rew]
                narrative = f"You search the area thoroughly and secure valuable spoils: 30 Gold and a well-sealed Cask of Fine Rum!"
            elif "report" in choice_lower or "marine" in choice_lower:
                await reputation_service.adjust_reputation(character_id, {"marine": 10, "civilian": 5})
                narrative = "You report your findings to the local authorities. The watch thanks you for your vigilance."
            else:
                narrative = f"You proceed cautiously: {action_choice}. Your actions ripple subtly across the harbor district."

        resolution_data = {
            "success": True,
            "discovery_id": discovery_id,
            "action_taken": action_choice,
            "narrative": narrative,
            "outcome_text": narrative,
            "rewards": rewards_granted,
            "thread_updates": thread_updates,
            "merged_thread": merged_thread
        }
        await db.discoveries.update_one(
            {"_id": discovery_id},
            {"$set": {"resolution_summary": resolution_data}}
        )
        return resolution_data


discovery_service = DiscoveryService()
