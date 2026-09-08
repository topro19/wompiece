import random
import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.database.connection import db_manager
from app.game.npcs.npc_models import WorldNPC, NPCFaction, NPCArchetype
from app.game.npcs.npc_population_service import npc_population_service
from app.game.world.location import location_service
from app.game.director.relationship_service import relationship_service
from app.services.logger import logger


class NPCApproach(BaseModel):
    approach_id: str = Field(default_factory=lambda: f"app_{uuid.uuid4().hex[:8]}")
    npc_id: str
    npc_name: str
    npc_role: str
    faction: str
    dialogue: str
    approach_type: str  # ESCORT, RECRUIT, QUESTION, INTEL, GRATITUDE, CHALLENGE
    available_actions: List[str] = Field(default_factory=list)


class LocationScene(BaseModel):
    scene_id: str = Field(default_factory=lambda: f"scene_{uuid.uuid4().hex[:8]}")
    title: str
    description: str
    involved_npc_names: List[str] = Field(default_factory=list)
    suggested_actions: List[str] = Field(default_factory=list)


class LocationAtmosphere(BaseModel):
    location_id: str
    location_name: str
    island: str
    security_level: int
    ambient_overview: str
    present_npcs: List[WorldNPC] = Field(default_factory=list)
    active_scenes: List[LocationScene] = Field(default_factory=list)
    approaching_npc: Optional[NPCApproach] = None


class NPCEncounterService:
    """Generates living location atmospheres, contextual multi-NPC vignettes, and dynamic NPC approaches."""

    def _generate_scenes_for_location(self, npcs: List[WorldNPC], location_id: str) -> List[LocationScene]:
        scenes: List[LocationScene] = []
        loc = location_service.get_location(location_id)
        if not loc or not npcs:
            return scenes

        facs = loc.facilities
        marines = [n for n in npcs if n.is_marine]
        pirates = [n for n in npcs if n.is_pirate]
        merchants = [n for n in npcs if n.faction == NPCFaction.MERCHANT]
        civilians = [n for n in npcs if n.faction == NPCFaction.CIVILIAN]

        # 1. Marine & Civilian/Merchant interaction
        if marines and (merchants or civilians):
            m = random.choice(marines)
            c = random.choice(merchants if merchants else civilians)
            scenes.append(LocationScene(
                title="Customs Inspection & Interrogation",
                description=f"{m.name} ({m.role_title}) has cornered {c.name} ({c.occupation}), demanding stamped cargo manifests and inspecting sea chests.",
                involved_npc_names=[m.name, c.name],
                suggested_actions=["Intervene and vouch for the merchant", "Bribe the Marine patrol", "Observe from the shadows", "Ignore"]
            ))

        # 2. Pirate dispute / recruitment
        if len(pirates) >= 2:
            p1, p2 = random.sample(pirates, 2)
            scenes.append(LocationScene(
                title="Heated Crew Argument",
                description=f"{p1.name} and {p2.name} are arguing loudly over the spoils of a recent voyage, their hands resting menacingly on cutlass hilts.",
                involved_npc_names=[p1.name, p2.name],
                suggested_actions=["Step in to de-escalate", "Egg them into a brawl", "Pickpocket during the distraction", "Walk past"]
            ))
        elif pirates and any("tavern" in f for f in facs):
            p = pirates[0]
            scenes.append(LocationScene(
                title="Pirate Recruitment Drive",
                description=f"{p.name} ({p.role_title}) is buying tankards of ale for passing sailors, loudly promising shares in an impending raid.",
                involved_npc_names=[p.name],
                suggested_actions=["Listen to the recruitment pitch", "Ask about their captain and ship", "Report them to the Marines", "Order a drink"]
            ))

        # 3. Market / Docks commerce scene
        if merchants and civilians and any("market" in f or "dock" in f for f in facs):
            m = merchants[0]
            c = civilians[0]
            scenes.append(LocationScene(
                title="Bustling Trade & Barter",
                description=f"{m.name} is fiercely negotiating prices for salted cod and citrus barrels with {c.name}, while porters haul freight behind them.",
                involved_npc_names=[m.name, c.name],
                suggested_actions=["Browse available trade wares", "Inquire about shipping prices", "Move along"]
            ))

        # 4. Underworld / Smuggler whisper scene
        smugglers = [n for n in npcs if n.role in [NPCArchetype.SMUGGLER, NPCArchetype.INFORMANT, NPCArchetype.THIEF]]
        if smugglers:
            s = random.choice(smugglers)
            scenes.append(LocationScene(
                title="Whispered Exchange in the Shadows",
                description=f"{s.name} ({s.role_title}) is surreptitiously glancing about while concealing a sealed wax parcel inside a coat pocket.",
                involved_npc_names=[s.name],
                suggested_actions=["Confront them discreetly", "Offer to buy their information", "Pickpocket the parcel", "Leave them alone"]
            ))

        return scenes[:3]

    async def _check_npc_approach(
        self,
        character_id: str,
        character_faction: str,
        wanted_level: int,
        npcs: List[WorldNPC]
    ) -> Optional[NPCApproach]:
        """Evaluates whether an NPC physically steps forward to approach the player."""
        if not npcs:
            return None

        # 35% baseline chance to be approached when entering/inspecting
        if random.random() > 0.35:
            return None

        # Pick candidate based on player profile
        marines = [n for n in npcs if n.is_marine]
        pirates = [n for n in npcs if n.is_pirate]
        merchants = [n for n in npcs if n.faction == NPCFaction.MERCHANT]
        informants = [n for n in npcs if n.role in [NPCArchetype.INFORMANT, NPCArchetype.PIRATE_INFORMANT]]

        # High wanted level player approached by Marine patrol
        if wanted_level >= 2 and marines:
            m = random.choice(marines)
            return NPCApproach(
                npc_id=m.npc_id,
                npc_name=m.name,
                npc_role=m.role_title,
                faction=m.faction.value,
                dialogue=f"\"Halt there, traveler! You match the description on a recent naval bulletin. State your name and business in this district!\"",
                approach_type="QUESTION",
                available_actions=["Cooperate and show papers", "Bribe the officer (50 Gold)", "Intimidate", "Flee into the crowd", "Draw weapon"]
            )

        # Merchant seeking escort / help
        if merchants:
            merch = random.choice(merchants)
            return NPCApproach(
                npc_id=merch.npc_id,
                npc_name=merch.name,
                npc_role=merch.role_title,
                faction=merch.faction.value,
                dialogue=f"\"Pardon me, captain. You have the look of someone seasoned in danger. I have a precious cargo shipment arriving and cutthroats are circling. I'm prepared to pay handsomely for an escort.\"",
                approach_type="ESCORT",
                available_actions=["Accept escort job", "Demand advance payment", "Decline politely", "Demand double the price"]
            )

        # Pirate recruitment or camaraderie
        if character_faction.upper() == "PIRATE" and pirates:
            p = random.choice(pirates)
            return NPCApproach(
                npc_id=p.npc_id,
                npc_name=p.name,
                npc_role=p.role_title,
                faction=p.faction.value,
                dialogue=f"\"Ahoy, mate! I recognize the swagger of a true sea wolf. We're looking for stout hands for our next venture out past the reef. Care to share a flagon and talk business?\"",
                approach_type="RECRUIT",
                available_actions=["Join them for a drink", "Inquire about the crew and haul", "Decline", "Brag about your own feats"]
            )

        # Informant selling tips
        if informants:
            inf = random.choice(informants)
            return NPCApproach(
                npc_id=inf.npc_id,
                npc_name=inf.name,
                npc_role=inf.role_title,
                faction=inf.faction.value,
                dialogue=f"\"Keep your eyes forward and listen closely... I've got word on the Marine patrol rotation and a secret shipment coming through Dead Man's Cove. It'll only cost you 25 Gold.\"",
                approach_type="INTEL",
                available_actions=["Pay 25 Gold for intel", "Intimidate for free info", "Brush them off", "Alert the guards"]
            )

        # General approach by random NPC
        npc = random.choice(npcs)
        rel = await relationship_service.get_or_create_relationship(character_id, npc.name)
        if rel.trust >= 20:
            dialogue = f"\"Greetings again, friend! Good to see you still walking in one piece. What winds blow you back here?\""
        else:
            dialogue = f"\"Fine sea breeze today, isn't it? Mind if I ask what brings an armed stranger like you around these parts?\""

        return NPCApproach(
            npc_id=npc.npc_id,
            npc_name=npc.name,
            npc_role=npc.role_title,
            faction=npc.faction.value,
            dialogue=dialogue,
            approach_type="CONVERSATION",
            available_actions=["Greet them friendly", "Inquire about local rumors", "Trade items", "Ignore and walk away"]
        )

    async def get_location_atmosphere(self, location_id: str, character_id: str) -> LocationAtmosphere:
        """Assembles the complete living world atmosphere for a location."""
        loc = location_service.get_location(location_id)
        loc_name = loc.name if loc else location_id
        island = loc.island if loc else "High Seas"
        sec_level = loc.security_level if loc else 1

        # 1. Fetch present NPCs
        npcs = await npc_population_service.get_npcs_at_location(location_id)

        # 2. Generate active scenes between NPCs
        scenes = self._generate_scenes_for_location(npcs, location_id)

        # 3. Check player profile for approach
        db = db_manager.db
        char_doc = await db.characters.find_one({"_id": character_id})
        faction = char_doc.get("faction", "Independent") if char_doc else "Independent"
        wanted_level = char_doc.get("wanted_level", 0) if char_doc else 0

        # 4. Spontaneous approach
        approach = await self._check_npc_approach(character_id, faction, wanted_level, npcs)

        # Atmosphere summary
        npc_count = len(npcs)
        ambient_overview = (
            f"The district is bustling with {npc_count} identifiable inhabitants. "
            f"Winds carry the scent of salt spray and tar. "
            f"{len(scenes)} distinct situations are unfolding right in front of you."
        )

        return LocationAtmosphere(
            location_id=location_id,
            location_name=loc_name,
            island=island,
            security_level=sec_level,
            ambient_overview=ambient_overview,
            present_npcs=npcs,
            active_scenes=scenes,
            approaching_npc=approach
        )


npc_encounter_service = NPCEncounterService()
