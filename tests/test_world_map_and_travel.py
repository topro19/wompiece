import pytest
from datetime import datetime, timezone

from app.game.models.character import Character, Faction
from app.services.character_service import character_service
from app.game.map.map_models import (
    MapLevel,
    MapDiscoveryState,
    TravelType,
    TerrainType,
)
from app.game.map.map_service import map_service
from app.game.map.travel_engine import travel_engine
from app.game.notifications.notification_models import (
    NotificationPriority,
    WorldMessage,
    OfflineRecap,
)
from app.game.notifications.notification_service import NotificationService


@pytest.mark.asyncio
async def test_3_level_map_hierarchy():
    """
    Verifies Section 145:
    Level 1: Global World Map
    Level 2: Island Map
    Level 3: Local Location Map
    """
    char = await character_service.create_character("user_map_test", "Captain Vane", Faction.PIRATE)
    char_id = char.character_id

    # 1. Level 1: Global World Map
    world_view = await map_service.get_world_map_view(char_id)
    assert world_view["level"] == MapLevel.GLOBAL.value
    assert len(world_view["islands"]) >= 4
    assert "ascii_chart" in world_view
    assert "NAUTICAL CHART" in world_view["ascii_chart"]

    # 2. Level 2: Island Map (Azure Island)
    island_view = await map_service.get_island_map_view(char_id, "azure_island")
    assert island_view is not None
    assert island_view["id"] == "azure_island"
    assert len(island_view["regions"]) >= 2

    # Port Azure should be discovered by default for new character
    port_azure_loc = None
    for reg in island_view["regions"]:
        for loc in reg["locations"]:
            if loc["id"] == "port_azure":
                port_azure_loc = loc
                break
    assert port_azure_loc is not None
    assert port_azure_loc["discovery_state"] in [MapDiscoveryState.DISCOVERED.value, MapDiscoveryState.EXPLORED.value]
    assert port_azure_loc["is_player_here"] is True

    # 3. Level 3: Local Location Map
    local_view = await map_service.get_location_map_view(char_id, "port_azure")
    assert local_view is not None
    assert local_view["name"] == "Port Azure"
    assert "salty_anchor_tavern" in local_view["facilities"]
    assert "Mara" in local_view["npcs_present"]


@pytest.mark.asyncio
async def test_fog_of_war_and_discovery_progression():
    """
    Verifies Section 149 & 150:
    Fog of War masks unexplored regions; discovery state transitions properly.
    """
    char = await character_service.create_character("user_fog_test", "Explorer Kai", Faction.INDEPENDENT)
    char_id = char.character_id

    # Initially, sunken_reef should be unknown
    island_view = await map_service.get_island_map_view(char_id, "azure_island")
    reef_loc = None
    for reg in island_view["regions"]:
        for loc in reg["locations"]:
            if loc["id"] == "sunken_reef":
                reef_loc = loc
                break
    assert reef_loc is not None
    assert reef_loc["discovery_state"] == MapDiscoveryState.UNKNOWN.value

    # Discover the location
    updated = await map_service.discover_location(
        character_id=char_id,
        location_id="sunken_reef",
        new_state=MapDiscoveryState.DISCOVERED
    )
    assert updated.state == MapDiscoveryState.DISCOVERED

    # Re-fetch island map view; sunken reef should now be discovered
    island_view_after = await map_service.get_island_map_view(char_id, "azure_island")
    reef_loc_after = None
    for reg in island_view_after["regions"]:
        for loc in reg["locations"]:
            if loc["id"] == "sunken_reef":
                reef_loc_after = loc
                break
    assert reef_loc_after["discovery_state"] == MapDiscoveryState.DISCOVERED.value


@pytest.mark.asyncio
async def test_player_custom_map_markers():
    """
    Verifies Section 156:
    Player can place, view, and remove custom map markers.
    """
    char = await character_service.create_character("user_marker_test", "Navigator Flint", Faction.PIRATE)
    char_id = char.character_id

    # Add marker
    m1 = await map_service.add_marker(
        character_id=char_id,
        label="Buried Stash",
        notes="Under the hollow sea cliff near Pier 2",
        island_id="azure_island",
        location_id="port_azure"
    )
    assert m1.marker_id.startswith("mark_")

    # List markers
    markers = await map_service.list_markers(char_id)
    assert len(markers) == 1
    assert markers[0].label == "Buried Stash"

    # Delete marker
    deleted = await map_service.delete_marker(char_id, m1.marker_id)
    assert deleted is True
    assert len(await map_service.list_markers(char_id)) == 0


@pytest.mark.asyncio
async def test_fast_simulated_travel_no_waiting():
    """
    Verifies Sections 190–206:
    CRITICAL DESIGN MANDATE: NO REAL WAITING.
    - Zero blocking timers (no waiting 3, 8, or 12 hours).
    - Travel resolves immediately.
    - Contextual simulated route encounter is generated.
    - Player arrives and can immediately act at destination.
    """
    char = await character_service.create_character("user_travel_test", "Sailor Jim", Faction.PIRATE)
    char_id = char.character_id

    # 1. Available destinations from Port Azure
    destinations = await travel_engine.get_available_destinations(char_id)
    assert len(destinations) >= 3
    dest_ids = [d["id"] for d in destinations]
    assert "skull_island" in dest_ids

    # 2. Execute voyage to Skull Island
    start_time = datetime.now(timezone.utc)
    result = await travel_engine.execute_travel(char_id, "skull_island")
    end_time = datetime.now(timezone.utc)

    # Verification: Execution is instantaneous (sub-second)
    elapsed = (end_time - start_time).total_seconds()
    assert elapsed < 2.0, "Travel must NOT block with artificial delays!"

    # Verification: Successful arrival with rich journey narrative
    assert result["success"] is True
    assert result["destination_island_id"] == "skull_island"
    assert result["arrival_name"] == "Blackwater Port"
    assert "VOYAGE" in result["voyage_narrative"]
    assert result["encounter"] is not None
    assert "title" in result["encounter"]
    assert "resolution" in result["encounter"]

    # Verification: Character DB position was updated immediately
    updated_char = await character_service.get_character(char_id)
    assert updated_char.location_id == "blackwater_port"
    assert updated_char.island_id == "skull_island"

    # Verification: New location was added to character's discovered map
    loc_view = await map_service.get_location_map_view(char_id, "blackwater_port")
    assert loc_view is not None
    assert loc_view["discovery_state"] in [MapDiscoveryState.DISCOVERED.value, MapDiscoveryState.EXPLORED.value]


@pytest.mark.asyncio
async def test_notification_service_priority_and_anti_spam():
    """
    Verifies Section 173:
    - Notification priority handling (LOW, NORMAL, HIGH, CRITICAL).
    - Strict anti-spam rule: Tag <@user_id> ONLY on HIGH and CRITICAL.
    - LOW and NORMAL must NEVER ping the user.
    """
    notif_service = NotificationService()
    char_id = "char_notif_1"
    user_id = "1234567890"

    # 1. LOW priority (silent world ledger)
    low_msg = await notif_service.send_world_message(
        character_id=char_id,
        user_id=user_id,
        sender_name="Harbor Ledger",
        content="Flour prices rose by 2 groats in Port Azure.",
        priority=NotificationPriority.LOW,
    )
    low_delivery = notif_service.format_discord_delivery(low_msg)
    assert f"<@{user_id}>" not in low_delivery["content"], "LOW priority must never ping user!"
    assert low_delivery["mention"] == ""
    assert low_delivery["is_urgent"] is False

    # 2. NORMAL priority (ambient world event)
    norm_msg = await notif_service.send_world_message(
        character_id=char_id,
        user_id=user_id,
        sender_name="Old Salty Bill",
        content="I spotted some strange sails north of the shoals.",
        priority=NotificationPriority.NORMAL,
    )
    norm_delivery = notif_service.format_discord_delivery(norm_msg)
    assert f"<@{user_id}>" not in norm_delivery["content"], "NORMAL priority must never ping user!"
    assert norm_delivery["mention"] == ""

    # 3. HIGH priority (relevant NPC seeks player)
    high_msg = await notif_service.send_world_message(
        character_id=char_id,
        user_id=user_id,
        sender_name="Inspector Vance",
        content="Report to Marine Headquarters before midnight or a warrant will be signed.",
        priority=NotificationPriority.HIGH,
        requires_response=True,
        options=["Comply and report", "Slip out of town"]
    )
    high_delivery = notif_service.format_discord_delivery(high_msg)
    assert f"<@{user_id}>" in high_delivery["content"], "HIGH priority MUST ping user!"
    assert high_delivery["is_urgent"] is True
    assert "Comply and report" in high_delivery["content"]

    # 4. CRITICAL priority (immediate raid / threat)
    crit_msg = await notif_service.send_world_message(
        character_id=char_id,
        user_id=user_id,
        sender_name="First Mate",
        content="BATTLE STATIONS! Pirate raiders are boarding the docks right now!",
        priority=NotificationPriority.CRITICAL,
    )
    crit_delivery = notif_service.format_discord_delivery(crit_msg)
    assert f"<@{user_id}>" in crit_delivery["content"], "CRITICAL priority MUST ping user!"
    assert crit_delivery["is_urgent"] is True

    # 5. Offline Recap ("While You Were Away...")
    recap = await notif_service.get_offline_recap(char_id, "Test Sailor")
    assert recap.unread_messages_count >= 4
    assert len(recap.urgent_alerts) >= 2
    assert len(recap.timeline_highlights) >= 4


@pytest.mark.asyncio
async def test_end_to_end_voyage_and_timeline_workflow():
    """
    Verifies Section 188 Full Acceptance Test Workflow:
    1. Player checks world map and island chart.
    2. Player marks a secret stash location.
    3. Player receives a critical dispatch.
    4. Player decides to flee/travel to another island.
    5. Instant voyage with route encounter resolves and logs to timeline.
    6. Player arrives ready to play.
    """
    char = await character_service.create_character("user_e2e_voyage", "Captain Sterling", Faction.PIRATE)
    char_id = char.character_id

    # Step 1: Check initial map
    island_view = await map_service.get_island_map_view(char_id, "azure_island")
    assert island_view["name"] == "Azure Island"

    # Step 2: Add marker
    marker = await map_service.add_marker(char_id, "Smuggler Cove Stash", "Hidden under loose planks")
    assert marker.marker_id is not None

    # Step 3: Critical dispatch arrives
    notif_service = NotificationService()
    alert = await notif_service.send_world_message(
        character_id=char_id,
        user_id="user_e2e_voyage",
        sender_name="Harbor Watch",
        content="Marine gunboats have blocked Port Azure main gate! Flee while the fog holds!",
        priority=NotificationPriority.CRITICAL
    )
    assert alert.priority == NotificationPriority.CRITICAL

    # Step 4: Player travels to Mistfall Island
    res = await travel_engine.execute_travel(char_id, "mistfall_island")
    assert res["success"] is True
    assert res["destination_island_id"] == "mistfall_island"
    assert res["arrival_name"] == "Fogveil Port"

    # Step 5: Timeline contains recorded events
    timeline = await notif_service.get_recent_timeline(char_id, limit=10)
    assert len(timeline) >= 2
    timeline_texts = [e.event_text for e in timeline]
    assert any("Harbor Watch" in t for t in timeline_texts)
    assert any("Voyage" in t or "Fogveil Port" in t for t in timeline_texts)
