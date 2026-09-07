import pytest
from app.game.models.character import Faction, CharacterStatus
from app.services.character_service import character_service
from app.game.crews.crew_service import crew_service
from app.game.crews.crew_models import CrewRole
from app.game.businesses.business_service import business_service
from app.game.investigations.case_service import investigation_service
from app.game.investigations.case_models import EvidenceType, CaseStatus
from app.game.actions.action_engine import action_engine
from app.ai.npc.npc_engine import npc_engine
from app.game.models.death import permadeath_service, CauseOfDeath
from app.game.events.event_types import EventType


@pytest.mark.asyncio
async def test_full_playable_vertical_slice(test_db):
    """
    End-to-End verification of the complete First Playable Vertical Slice:
    1. Real Player 1 joins as Pirate.
    2. Player 1 joins AI Captain Redhook's crew 'The Black Tide'.
    3. Real Player 2 joins the same crew and gets a specialized role.
    4. Player 1 converses in-character with AI Captain Redhook.
    5. Players travel through the port graph.
    6. Crew operates 'The Golden Anchor' under forged civilian alias 'Marcus Vale'.
    7. Business runs an illegal smuggling operation creating a financial anomaly.
    8. Real Marine Player investigates: opens case, logs evidence, interviews NPC.
    9. Marine interrogates Player 1 (transcript logged into evidence).
    10. AI Marine Head evaluates warrant petition and authorizes search/raid.
    11. Player 2 attempts betrayal against the crew.
    12. Lethal combat triggers One-Life Permadeath atomically.
    13. All events immutably persisted in MongoDB.
    """

    # --- STEP 1: Real Player 1 enters the world as a Pirate ---
    pirate_1 = await character_service.create_character(
        user_id="discord_player_1",
        name="Jack Hawkins",
        faction=Faction.PIRATE
    )
    assert pirate_1.status == CharacterStatus.ALIVE
    assert pirate_1.wealth == 100

    # --- STEP 2: Player 1 joins AI Crew 'The Black Tide' ---
    crew = await crew_service.ensure_starter_ai_crews()
    assert crew.name == "The Black Tide"
    assert crew.captain_is_ai is True

    await crew_service.join_crew(crew.crew_id, pirate_1.character_id, role=CrewRole.DECKHAND)
    p1_reloaded = await character_service.get_active_character_by_user("discord_player_1")
    assert p1_reloaded.crew_id == crew.crew_id

    # --- STEP 3: Real Player 2 joins the same crew and is assigned Quartermaster ---
    pirate_2 = await character_service.create_character(
        user_id="discord_player_2",
        name="Long John Silver",
        faction=Faction.PIRATE
    )
    await crew_service.join_crew(crew.crew_id, pirate_2.character_id, role=CrewRole.QUARTERMASTER)
    p2_reloaded = await character_service.get_active_character_by_user("discord_player_2")
    assert p2_reloaded.crew_role == CrewRole.QUARTERMASTER.value

    # --- STEP 4: Player interacts with AI Captain Redhook ---
    dialogue_res = await npc_engine.converse_with_npc(
        character_id=pirate_1.character_id,
        npc_name="Captain Redhook",
        player_speech="Captain, the cargo is ready at the docks. What are your orders?"
    )
    assert len(dialogue_res.dialogue) > 0
    assert len(dialogue_res.internal_thought) > 0

    # --- STEP 5: Exploration of Port Graph ---
    dest = await character_service.move_character(pirate_1.character_id, "the_crimson_parrot")
    assert dest.location_id == "the_crimson_parrot"

    # --- STEP 6 & 7: Business Operations under Alias 'Marcus Vale' & Smuggling Run ---
    biz = await business_service.ensure_starter_crew_business(
        crew_id=crew.crew_id,
        captain_id=crew.captain_id
    )
    assert biz.registered_owner_name == "Marcus Vale"

    # Execute illicit smuggling run
    smuggle_res = await business_service.run_underhand_smuggling(biz.business_id, cargo_value=600)
    assert smuggle_res["payout"] == 600
    assert smuggle_res["anomaly_score"] > 0.0

    # --- STEP 8: Marine Player Opens Case & Discovers Evidence ---
    marine = await character_service.create_character(
        user_id="discord_marine_1",
        name="Inspector Vance",
        faction=Faction.MARINE
    )

    case = await investigation_service.open_case(
        assigned_marine_id=marine.character_id,
        title="Smuggling Anomaly at The Golden Anchor",
        location_id="port_azure_docks"
    )
    assert case.status == CaseStatus.OPEN

    # Marine logs financial anomaly evidence
    await investigation_service.add_evidence(
        case_id=case.case_id,
        evidence_type=EvidenceType.TRANSACTION_ANOMALY,
        title="Excess Revenue Discrepancy",
        description="The Golden Anchor reported 600 gold in unmanifested black-market profits.",
        source="Colonial Customs Ledger",
        location_id="port_azure_docks",
        discovered_by_id=marine.character_id
    )

    # Marine interviews NPC (Tavern Bartender)
    npc_interview = await npc_engine.converse_with_npc(
        character_id=marine.character_id,
        npc_name="Tavern Bartender",
        player_speech="Tell me what you know about the crates delivered to Marcus Vale."
    )
    assert len(npc_interview.dialogue) > 0

    # --- STEP 9: Marine Interrogates Real Player 1 ---
    interrogation = await investigation_service.log_interrogation(
        case_id=case.case_id,
        marine_id=marine.character_id,
        marine_name=marine.name,
        subject_id=pirate_1.character_id,
        subject_name=pirate_1.name,
        dialogue_log=[
            {"speaker": marine.name, "text": "We saw you hauling unmarked barrels behind The Golden Anchor."},
            {"speaker": pirate_1.name, "text": "I was just moving barrels of salted pork, officer!"}
        ],
        summary="Suspect claims cargo was salted pork, but customs records show no food permits."
    )
    assert len(interrogation.dialogue_log) == 2

    # Add physical contraband evidence
    await investigation_service.add_evidence(
        case_id=case.case_id,
        evidence_type=EvidenceType.CONTRABAND_SAMPLE,
        title="Unmarked Naval Muskets",
        description="Stolen colonial arms discovered concealed in the rear storage lockers.",
        source="Harbor Patrol Seizure",
        location_id="port_azure_docks",
        discovered_by_id=marine.character_id
    )

    # --- STEP 10: AI Marine Head Warrant Adjudication ---
    warrant = await investigation_service.request_warrant_review(
        case_id=case.case_id,
        requesting_marine_id=marine.character_id,
        target_id=biz.business_id,
        target_name=biz.name,
        statute_id="SMUGGLING",
        requested_action="SEARCH_WARRANT"
    )
    assert warrant.status == "AUTHORIZED"
    updated_case = await investigation_service.get_case(case.case_id)
    assert updated_case.status == CaseStatus.RAID_AUTHORIZED

    # --- STEP 11: Player 2 Attempts Crew Betrayal ---
    betrayal_res = await action_engine.resolve_freeform_action(
        character_id=pirate_2.character_id,
        untrusted_action_text="I secretly pocket 200 gold from the crew treasury and plan to turn informant for the Marines."
    )
    assert "betrayal_detected" in betrayal_res["state_deltas"]

    # --- STEP 12: Permadeath Resolution (One-Life System) ---
    # Suppose Player 2 is confronted and executed in combat
    death_rec = await permadeath_service.execute_permadeath(
        character_id=pirate_2.character_id,
        cause=CauseOfDeath.EXECUTION,
        location_id="port_azure_docks",
        killer_id=marine.character_id,
        killer_name=marine.name,
        related_case_id=case.case_id
    )
    assert death_rec.character_name == "Long John Silver"

    # Verify permadeath invariants
    dead_p2 = await test_db.characters.find_one({"_id": pirate_2.character_id})
    assert dead_p2["status"] == CharacterStatus.DEAD.value
    p2_user = await test_db.users.find_one({"_id": "discord_player_2"})
    assert p2_user["active_character_id"] is None
    assert pirate_2.character_id in p2_user["deceased_character_ids"]

    # --- STEP 13: World Event History Stream Verification ---
    all_events = await test_db.events.find({}).to_list(length=100)
    event_types = [e["event_type"] for e in all_events]

    assert EventType.PLAYER_CREATED.value in event_types
    assert EventType.PLAYER_JOINED_CREW.value in event_types
    assert EventType.GOODS_SMUGGLED.value in event_types
    assert EventType.CASE_OPENED.value in event_types
    assert EventType.EVIDENCE_DISCOVERED.value in event_types
    assert EventType.WARRANT_DECISION.value in event_types
    assert EventType.CREW_BETRAYAL_ATTEMPTED.value in event_types
    assert EventType.DEATH_EVENT.value in event_types

    print("\n✅ COMPLETE FIRST PLAYABLE VERTICAL SLICE VERIFIED END-TO-END!")
