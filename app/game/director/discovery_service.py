import random
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.database.connection import db_manager
from app.game.director.director_models import WorldDiscovery, DiscoveryType, RewardGrant, RewardType
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.game.investigations.case_service import investigation_service
from app.game.investigations.case_models import EvidenceType
from app.services.logger import logger


DISCOVERY_TEMPLATES: List[Dict[str, Any]] = [
    # 1. Crime Scenes & Bodies
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
    # 2. Abandoned Cargo & Flotsam
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
    # 3. Secret Meetings & Plotters
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
    # 4. Smuggling Caches
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
    # 5. Wounded Sailors & Castaways
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
    # 6. Lost Treasures & Relics
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
    # 7. Underground Games
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
    # 8. Secret Passages
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
    """Authoritative contextual discovery engine for point-of-interest exploration and crime scenes."""

    async def explore_location(self, character_id: str, location_id: Optional[str] = None) -> WorldDiscovery:
        """Explores the surroundings, producing a context-sensitive, non-repeating narrative discovery."""
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

        # 2. Fetch titles of the player's recent discoveries to prevent repetitive encounters
        recent_cursor = db.discoveries.find(
            {"character_id": character_id}
        ).sort("discovered_at", -1).limit(6)
        recent_docs = await recent_cursor.to_list(length=6)
        recent_titles = set(d.get("title") for d in recent_docs if d.get("title"))

        # 3. Filter candidate templates matching the location or environment
        loc_lower = loc_id.lower()
        matching_candidates = []
        for t in DISCOVERY_TEMPLATES:
            # Check if environment matches
            env_match = any(env in loc_lower for env in t["environments"])
            if env_match and t["title"] not in recent_titles:
                matching_candidates.append(t)

        # 4. Fallback pool if all environment-matching templates have been seen recently
        if not matching_candidates:
            matching_candidates = [t for t in DISCOVERY_TEMPLATES if t["title"] not in recent_titles]

        # 5. Ultimate fallback if literally all templates were seen
        if not matching_candidates:
            last_title = recent_docs[0].get("title") if recent_docs else None
            matching_candidates = [t for t in DISCOVERY_TEMPLATES if t["title"] != last_title] or DISCOVERY_TEMPLATES

        chosen = random.choice(matching_candidates)

        disc = WorldDiscovery(
            character_id=character_id,
            discovery_type=chosen["type"],
            title=chosen["title"],
            description=chosen["description"],
            location_id=loc_id,
            suggested_actions=chosen["suggested_actions"]
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
        merged_thread = None

        # Mark discovery interacted immediately
        await db.discoveries.update_one(
            {"_id": discovery_id},
            {"$set": {"interacted": True, "chosen_action": action_choice}}
        )

        # -------------------------------------------------------------
        # 1. SUSPICIOUS_BODY
        # -------------------------------------------------------------
        if discovery.discovery_type == DiscoveryType.SUSPICIOUS_BODY:
            if "report" in choice_lower or "marine" in choice_lower:
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

                th = await thread_service.get_thread_by_title("The Port Azure Murders")
                if th:
                    await thread_service.update_thread(
                        th.thread_id,
                        new_fact=f"{char.get('name')} reported victim #4 to the Marines; Case #{case.case_number} officially opened.",
                        log_entry=f"Marines secured the scene after {char.get('name')}'s report."
                    )
                narrative = f"You alerted the Marine patrol. Inspector Vance's men cordoned off the alleyway, opening Case #{case.case_number}. The officers note your civic cooperation with gratitude."

            elif "search" in choice_lower or "pocket" in choice_lower or "satchel" in choice_lower:
                pouch_gold = 25
                rew = [
                    RewardGrant(reward_type=RewardType.GOLD, amount=pouch_gold, description="Pocketed from victim"),
                    RewardGrant(
                        reward_type=RewardType.ITEM,
                        item_id="vial_apothecary_herb",
                        item_name="Glass Vial with Green Wax Crest",
                        quantity=1,
                        description="An unbroken medicinal tincture bearing Mara's personal apothecary crest."
                    )
                ]
                await reward_service.grant(character_id=character_id, rewards=rew, reason="Searched murder victim")
                rewards_granted = [r.model_dump() for r in rew]
                await reputation_service.record_action_traits(character_id, {"opportunistic": 5, "cautious": 2})

                murder_th = await thread_service.get_thread_by_title("The Port Azure Murders")
                apoth_th = await thread_service.get_thread_by_title("The Apothecary's Missing Shipment")
                if murder_th and apoth_th:
                    await thread_service.merge_threads(
                        source_thread_id=apoth_th.thread_id,
                        target_thread_id=murder_th.thread_id,
                        merge_reason="Victim was carrying Mara's stolen medicinal herbal tincture with green wax seal!"
                    )
                    merged_thread = "The Apothecary's Missing Shipment → The Port Azure Murders"
                    thread_updates.append("Merged 'The Apothecary's Missing Shipment' into 'The Port Azure Murders'!")

                narrative = f"Kneeling by the body, you search the pockets. You find {pouch_gold} Gold and an intact glass vial bearing Mara the Apothecary's green wax seal! The missing medicinal cargo and the murders are connected!"

            elif "track" in choice_lower or "trail" in choice_lower:
                await reputation_service.record_action_traits(character_id, {"cautious": 4, "ambitious": 3})
                narrative = "You examine the damp ground and follow a trail of smeared saltwater bootprints leading toward the abandoned boathouse at Skull Rock Anchorage."

            elif "inspect" in choice_lower or "life" in choice_lower or "wound" in choice_lower:
                narrative = "You lean over the victim. The mortal blow was clean and deliberate—inflicted with a curved naval cutlass. The victim's boots and coin purse are gone, but you spot a faint tattoo of a severed rope on the forearm."

            else:
                narrative = "You quietly step back into the shadows of the wharf, leaving the scene undisturbed as thick harbor fog rolls in."

        # -------------------------------------------------------------
        # 2. ABANDONED_CARGO
        # -------------------------------------------------------------
        elif discovery.discovery_type == DiscoveryType.ABANDONED_CARGO:
            if "haul" in choice_lower or "salvage" in choice_lower or "pry" in choice_lower:
                rew = [
                    RewardGrant(reward_type=RewardType.GOLD, amount=35, description="Salvaged coin purse"),
                    RewardGrant(reward_type=RewardType.ITEM, item_id="cask_fine_rum", item_name="Cask of Fine Rum", quantity=2, description="Well-sealed privateer rum casks")
                ]
                await reward_service.grant(character_id=character_id, rewards=rew, reason="Salvaged abandoned cargo")
                rewards_granted = [r.model_dump() for r in rew]
                await reputation_service.record_action_traits(character_id, {"opportunistic": 4, "resourceful": 4})
                narrative = "You successfully haul the waterlogged cargo out of the brine. Prying open the seams reveals 35 Gold in waterproof oilcloth and two casks of prime rum!"

            elif "report" in choice_lower:
                await reputation_service.adjust_reputation(character_id, {"merchant": 12, "civilian": 8})
                narrative = "You turn the cargo manifest over to the harbor customs clerk. Grateful for the honesty, the merchant guild hands you a 20 Gold finder's reward and promises favorable trade rates."

            else:
                narrative = "You stash the cargo behind the breakers and take careful bearings so you can retrieve it under cover of darkness."

        # -------------------------------------------------------------
        # 3. SECRET_MEETING
        # -------------------------------------------------------------
        elif discovery.discovery_type == DiscoveryType.SECRET_MEETING:
            if "eavesdrop" in choice_lower or "listen" in choice_lower or "creep" in choice_lower:
                await reputation_service.record_action_traits(character_id, {"stealthy": 5, "cautious": 3})
                narrative = "Holding your breath behind the timber ribs, you overhear the pair: Marcus Vale has bribed the evening watch, and a contraband schooner is docking at Midnight Cove tonight."
                thread_updates.append("Uncovered smuggling rendezvous schedule for Marcus Vale's crew.")

            elif "confront" in choice_lower or "standoff" in choice_lower:
                rew = [RewardGrant(reward_type=RewardType.GOLD, amount=40, description="Hush money extorted")]
                await reward_service.grant(character_id=character_id, rewards=rew, reason="Extorted conspirators")
                rewards_granted = [r.model_dump() for r in rew]
                await reputation_service.adjust_reputation(character_id, {"criminal": 10, "marine": -10})
                narrative = "You step from the shadows with blade partially drawn. Startled, the conspirators toss you a heavy purse of 40 Gold to buy your silence before fleeing into the alleys."

            else:
                narrative = "You slip away silently through the warehouse labyrinth, committing their faces and conversation to memory."

        # -------------------------------------------------------------
        # 4. SMUGGLING_CACHE
        # -------------------------------------------------------------
        elif discovery.discovery_type == DiscoveryType.SMUGGLING_CACHE:
            if "pry" in choice_lower or "open" in choice_lower or "silver" in choice_lower or "slip" in choice_lower:
                rew = [
                    RewardGrant(reward_type=RewardType.ITEM, item_id="contraband_silver", item_name="Wrapped Silver Ingot", quantity=1, description="Refined silver stamped with colonial hallmark"),
                    RewardGrant(reward_type=RewardType.GOLD, amount=45, description="Pouched cache coins")
                ]
                await reward_service.grant(character_id=character_id, rewards=rew, reason="Looted smuggling cache")
                rewards_granted = [r.model_dump() for r in rew]
                await reputation_service.record_action_traits(character_id, {"opportunistic": 5, "bold": 3})
                narrative = "You pry up the concealed hatch. Inside is a wrapped silver bullion ingot and 45 Gold! You quickly pocket the loot and replace the cover."

            elif "inform" in choice_lower or "customs" in choice_lower:
                await reputation_service.adjust_reputation(character_id, {"marine": 20, "merchant": 10, "criminal": -15})
                narrative = "You alert customs officers to the secret cache. The Marines seize the illegal bullion and award you an official commendation for aiding the Crown."

            else:
                narrative = "You quietly memorize the trapdoor location and melt back into the harbor crowd."

        # -------------------------------------------------------------
        # 5. WOUNDED_SAILOR
        # -------------------------------------------------------------
        elif discovery.discovery_type == DiscoveryType.WOUNDED_SAILOR:
            if "offer" in choice_lower or "bread" in choice_lower or "rum" in choice_lower or "grog" in choice_lower:
                await reputation_service.adjust_reputation(character_id, {"civilian": 15, "independent": 10})
                await reputation_service.record_action_traits(character_id, {"compassionate": 5, "diplomatic": 3})
                narrative = "You hand the shivering sailor a flask of warm rum and bread. Tears well in his eyes; he whispers of an uncharted reef where a sunken galleon's gold sits in four fathoms of water."

            elif "ask" in choice_lower or "happen" in choice_lower:
                narrative = "The sailor shivers as he speaks: 'Captain Redhook's brigantine chased our merchant caravel down three nights ago off Mistfall. They spared no one who raised a cutlass...'"

            elif "demand" in choice_lower or "rob" in choice_lower or "intimidate" in choice_lower:
                rew = [RewardGrant(reward_type=RewardType.GOLD, amount=12, description="Shaken from sailor")]
                await reward_service.grant(character_id=character_id, rewards=rew, reason="Robbed wounded sailor")
                rewards_granted = [r.model_dump() for r in rew]
                await reputation_service.adjust_reputation(character_id, {"criminal": 8, "civilian": -12})
                narrative = "You intimidate the helpless sailor, stripping 12 loose copper and silver coins from his rags before shoving him into the mud."

            else:
                narrative = "You glance past the huddled drifter and keep walking along the foggy dock."

        # -------------------------------------------------------------
        # 6. LOST_TREASURE
        # -------------------------------------------------------------
        elif discovery.discovery_type == DiscoveryType.LOST_TREASURE:
            if "smash" in choice_lower or "pick" in choice_lower or "rope" in choice_lower or "haul" in choice_lower:
                rew = [
                    RewardGrant(reward_type=RewardType.GOLD, amount=60, description="Plundered from iron chest"),
                    RewardGrant(reward_type=RewardType.ITEM, item_id="brass_astrolabe", item_name="Engraved Brass Astrolabe", quantity=1, description="Vintage navigational instrument valued by captains")
                ]
                await reward_service.grant(character_id=character_id, rewards=rew, reason="Opened lost treasure chest")
                rewards_granted = [r.model_dump() for r in rew]
                narrative = "With a sharp crack, the rusted lock gives way! Inside lies 60 gleaming Gold and an exquisite engraved brass astrolabe preserved in velvet."

            elif "study" in choice_lower or "unseal" in choice_lower:
                rew = [
                    RewardGrant(reward_type=RewardType.MAP, item_id="chart_dead_mans_cove", item_name="Sea Chart: Dead Man's Cove", quantity=1, description="Hand-drawn chart revealing shoals and safe anchorages")
                ]
                await reward_service.grant(character_id=character_id, rewards=rew, reason="Studied lost nautical chart")
                rewards_granted = [r.model_dump() for r in rew]
                narrative = "You carefully unfurl the brittle vellum chart. It details safe passage coordinates through the treacherous razor reefs of Dead Man's Cove!"

            else:
                narrative = "You secure the find and prepare to take it to the tavern for valuation."

        # -------------------------------------------------------------
        # 7. ILLEGAL_GAMBLING
        # -------------------------------------------------------------
        elif discovery.discovery_type == DiscoveryType.ILLEGAL_GAMBLING:
            if "toss" in choice_lower or "roll" in choice_lower or "barrel" in choice_lower:
                # 60% win chance
                if random.random() < 0.60:
                    winnings = 30
                    rew = [RewardGrant(reward_type=RewardType.GOLD, amount=winnings, description="Won at street dice")]
                    await reward_service.grant(character_id=character_id, rewards=rew, reason="Won street dice game")
                    rewards_granted = [r.model_dump() for r in rew]
                    narrative = f"You step into the ring and toss your coin. The bone dice tumble across the barrel top—a pair of aces! A cheer erupts and you scoop 30 Gold into your pouch."
                else:
                    narrative = "You join the roll, but fortune is fickle on the docks. The dice betray you and the grinning dice-roller rakes in your wager."

            elif "watch" in choice_lower or "spot" in choice_lower:
                narrative = "Leaning against the wall, you watch the roller's fingers. The left die has lead shavings in the six-pip! You now hold leverage over the gambling ring."

            else:
                narrative = "You step into the circle with cutlass bared. Recognizing a seasoned rogue, the gamblers quickly divide a 20 Gold payoff to keep your mouth shut."

        # -------------------------------------------------------------
        # 8. HIDDEN_ROOM
        # -------------------------------------------------------------
        elif discovery.discovery_type == DiscoveryType.HIDDEN_ROOM:
            if "descend" in choice_lower or "vault" in choice_lower or "speakeasy" in choice_lower:
                rew = [RewardGrant(reward_type=RewardType.GOLD, amount=40, description="Found in hidden cellar")]
                await reward_service.grant(character_id=character_id, rewards=rew, reason="Explored secret cellar")
                rewards_granted = [r.model_dump() for r in rew]
                narrative = "Creeping down the mossy stairs, you find a clandestine tasting vault. You uncover 40 Gold and a private cask of aged vintage wine."

            else:
                narrative = "You press your ear against the cellar seam. You hear merchant guildmasters whispering about an impending blockade off the southern cape."

        # -------------------------------------------------------------
        # 9. GENERAL FALLBACK
        # -------------------------------------------------------------
        else:
            narrative = f"You proceed with caution and take action: {action_choice}. Your presence in the district does not go unnoticed."

        return {
            "success": True,
            "discovery_id": discovery_id,
            "action_taken": action_choice,
            "narrative": narrative,
            "outcome_text": narrative,
            "rewards": rewards_granted,
            "thread_updates": thread_updates,
            "merged_thread": merged_thread
        }


discovery_service = DiscoveryService()
