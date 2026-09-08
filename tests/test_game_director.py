import pytest
from datetime import datetime, timezone, timedelta

from app.game.models.character import Character, Faction
from app.services.character_service import character_service
from app.game.director.director_models import (
    GoalTier,
    OpportunityType,
    OpportunityUrgency,
    OpportunityStatus,
    StoryThreadStatus,
    RelationshipLevel,
    RewardType,
    RewardGrant
)
from app.game.director.director_service import game_director
from app.game.director.goal_service import goal_service
from app.game.director.opportunity_service import opportunity_engine
from app.game.director.relationship_service import relationship_service
from app.game.director.thread_service import thread_service
from app.game.director.reward_service import reward_service
from app.game.director.reputation_service import reputation_service
from app.game.director.discovery_service import discovery_service
from app.game.director.consequence_service import consequence_service


@pytest.mark.asyncio
async def test_vertical_slice_1_apothecary_opportunity_and_rewards():
    """
    VERTICAL SLICE 1: Apothecary Opportunity & Contextual Relationship Chain
    - Player meets Mara, discovers her herbal shipment dilemma.
    - Resolves dilemma contextually.
    - Relationship trust and respect increase; contextual non-spam reward is granted.
    """
    char = await character_service.create_character("user_slice1", "Julian Vane", Faction.INDEPENDENT)
    char_id = char.character_id

    # 1. Initialize world
    await game_director.initialize_player_world(char_id, "port_azure", "Independent")

    # 2. Check Mara opportunity exists
    opps = await opportunity_engine.list_active_opportunities(char_id, "port_azure")
    mara_opp = next((o for o in opps if o.related_npc_name == "Mara"), None)
    assert mara_opp is not None
    assert "Apothecary" in mara_opp.title
    assert mara_opp.urgency == OpportunityUrgency.URGENT

    # 3. Apply consequence cascade of helping Mara recover her intact herbs
    report = await consequence_service.apply_consequence_cascade(
        character_id=char_id,
        action_name="Help Mara secure the herb crates",
        outcome_text="You tracked down the dropped shipment near Pier 4 before Marcus Vale's crew could seize it.",
        npc_target="Mara",
        npc_delta_trust=25,
        npc_delta_respect=20,
        npc_memory_text="Julian recovered the rare silverleaf herbs when no one else would help.",
        npc_favor_earned=True,
        npc_favor_reason="Mara owes Julian an emergency antitoxin pouch.",
        reputation_changes={"civilian": 15, "criminal": -5},
        behavioral_traits={"reliable": 2, "compassionate": 2},
        thread_id="thread_apothecary_shipment",
        thread_new_fact="The herb crate had Marcus Vale's smuggling cipher stamped beneath the false bottom.",
        completed_opportunity_id=mara_opp.opportunity_id,
        rewards=[RewardGrant(
            reward_type=RewardType.MEDICINE,
            item_id="silverleaf_balm",
            item_name="Potent Silverleaf Balm",
            quantity=1,
            description="Restores 35 HP and purges poisons."
        )]
    )

    # 4. Verify consequences
    assert len(report.relationship_shifts) == 1
    assert report.relationship_shifts[0]["trust"] == 25
    assert report.relationship_shifts[0]["standing"] == RelationshipLevel.TRUSTED.value
    assert report.reputation_shifts["civilian"] == 15
    assert "reliable" in report.traits_recorded

    # Verify opportunity is completed
    updated_opp = await opportunity_engine.get_opportunity_by_id(char_id, mara_opp.opportunity_id)
    assert updated_opp.status == OpportunityStatus.RESOLVED

    # Verify contextual reward granted to character inventory
    updated_char = await character_service.get_character(char_id)
    has_medicine = any(item.get("item_id") == "silverleaf_balm" or item.get("id") == "silverleaf_balm" for item in updated_char.inventory)
    assert has_medicine is True

    # Verify favor was recorded
    rel = await relationship_service.get_or_create_relationship(char_id, "Mara")
    assert rel.favors_owed_to_player >= 1


@pytest.mark.asyncio
async def test_vertical_slice_2_murder_investigation_and_thread_merging():
    """
    VERTICAL SLICE 2: Murder Discovery & Story Thread Merging
    - Player investigates the Port Azure Murders and Apothecary Shipment.
    - Clues reveal both threads connect to Marcus Vale's smuggling ring.
    - Threads are merged dynamically into a unified conspiracy thread.
    """
    char = await character_service.create_character("user_slice2", "Kaelen Drake", Faction.MARINE)
    char_id = char.character_id

    # Seed threads
    await thread_service.ensure_starter_story_threads()
    active_threads = await thread_service.list_active_threads()
    assert len(active_threads) >= 2

    t_murder = await thread_service.get_thread_by_title("The Port Azure Murders")
    t_apoth = await thread_service.get_thread_by_title("The Apothecary's Missing Shipment")
    assert t_murder is not None
    assert t_apoth is not None

    # Add clue to Apothecary thread
    await thread_service.update_thread(
        thread_id=t_apoth.thread_id,
        new_fact="Apothecary shipment was stolen by the same crew operating out of Warehouse 7.",
        log_entry="Identified warehouse connection"
    )

    # Add clue to Murders thread
    await thread_service.update_thread(
        thread_id=t_murder.thread_id,
        new_fact="The dockworker victim was killed with an ornate Stiletto bearing an anchor crest.",
        log_entry="Weapon recovered"
    )

    # Perform thread merge: Apothecary thread merges into Port Azure Murders
    merged_target = await thread_service.merge_threads(
        source_thread_id=t_apoth.thread_id,
        target_thread_id=t_murder.thread_id,
        merge_reason="The dockworker was executed because he caught Marcus Vale's men hijacking Mara's herb shipment."
    )

    assert merged_target is not None
    assert merged_target.thread_id == t_murder.thread_id
    # Source thread facts should be transferred
    assert any("silverleaf" in f.lower() or "apothecary" in f.lower() or "warehouse 7" in f.lower() for f in merged_target.known_facts)

    # Check source thread status is MERGED
    source_thread = await thread_service.get_thread(t_apoth.thread_id)
    assert source_thread.status == StoryThreadStatus.MERGED
    assert source_thread.merged_into_thread_id == t_murder.thread_id

    # Only active non-merged threads should be listed
    current_active = await thread_service.list_active_threads()
    active_ids = [t.thread_id for t in current_active]
    assert t_murder.thread_id in active_ids
    assert t_apoth.thread_id not in active_ids


@pytest.mark.asyncio
async def test_vertical_slice_3_relationship_gifts_and_favor_exchange():
    """
    VERTICAL SLICE 3: Deep NPC Memory, Unsolicited Gifts & Calling in Favors
    - Player reaches Trusted standing with Mara.
    - Mara sends an unsolicited gift to the player.
    - Player calls in an emergency favor from an NPC.
    """
    char = await character_service.create_character("user_slice3", "Aria Hawke", Faction.MERCHANT)
    char_id = char.character_id

    # Raise relationship with Mara
    rel = await relationship_service.adjust_relationship(
        character_id=char_id,
        npc_name="Mara",
        trust_delta=60,
        respect_delta=40,
        affection_delta=30,
        memory_summary="Aria funded the reconstruction of the community infirmary."
    )
    assert rel.level == RelationshipLevel.CLOSE_FRIEND

    # Mara sends an unsolicited gift
    gift_res = await relationship_service.send_npc_gift(
        character_id=char_id,
        npc_name="Mara",
        item_name="Midnight Salve",
        item_id="midnight_salve",
        quantity=1,
        reason="For your constant protection of our community."
    )
    assert gift_res["success"] is True

    # Check character inventory received gift
    updated_char = await character_service.get_character(char_id)
    assert any(i.get("item_id") == "midnight_salve" or i.get("name") == "Midnight Salve" for i in updated_char.inventory)

    # Test calling in a favor
    await relationship_service.add_favor(
        character_id=char_id,
        npc_name="Thomas",
        favors=1,
        reason="Safe harbour passage papers"
    )
    favor_called = await relationship_service.call_in_favor(
        character_id=char_id,
        npc_name="Thomas",
        favor_type="INFORMATION"
    )
    assert favor_called["success"] is True

    # Calling it again raises ValueError because favors were consumed
    with pytest.raises(ValueError):
        await relationship_service.call_in_favor(
            character_id=char_id,
            npc_name="Thomas",
            favor_type="INFORMATION"
        )


@pytest.mark.asyncio
async def test_director_player_briefing_and_opportunity_expiration():
    """
    Verifies that the Game Director generates the comprehensive Player Home Screen Briefing,
    and accurately advances the world when an opportunity expires.
    """
    char = await character_service.create_character("user_briefing", "Dorian Gray", Faction.INDEPENDENT)
    char_id = char.character_id

    # Initialize and get briefing
    briefing = await game_director.get_player_briefing(char_id, "port_azure")
    assert briefing.character_name == "Dorian Gray"
    assert len(briefing.immediate_opportunities) >= 1
    assert len(briefing.active_threads) >= 1
    assert "Short-Term" in briefing.active_goals
    assert len(briefing.known_people) >= 2

    # Create an opportunity that expired 10 minutes ago
    past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    opp = await opportunity_engine.create_opportunity(
        character_id=char_id,
        title="Time-Sensitive Smuggler Meet",
        description="A courier waits by the bell tower.",
        opp_type=OpportunityType.NPC_REQUEST,
        urgency=OpportunityUrgency.URGENT,
        duration_minutes=1,
        consequence_summary="The courier grew anxious and fled, leaving a dead drop behind."
    )

    # Force expiration in DB
    await opportunity_engine.collection.update_one(
        {"_id": opp.opportunity_id},
        {"$set": {"expires_at": past_time}}
    )

    # Check expiration via director briefing
    briefing_after = await game_director.get_player_briefing(char_id, "port_azure")
    assert any("Time-Sensitive Smuggler Meet" in update for update in briefing_after.world_updates)

    # Opp should now be marked EXPIRED
    expired_opp = await opportunity_engine.get_opportunity_by_id(char_id, opp.opportunity_id)
    assert expired_opp.status == OpportunityStatus.EXPIRED
