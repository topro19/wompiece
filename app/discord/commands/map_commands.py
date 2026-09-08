import discord
from discord import app_commands
from typing import Optional, List

from app.services.character_service import character_service
from app.game.map.map_service import map_service
from app.game.map.travel_engine import travel_engine
from app.game.map.map_models import MapLevel
from app.game.notifications.notification_service import notification_service


class MapLevelSwitchButton(discord.ui.Button):
    """Button to switch between World, Island, and Local map views."""

    def __init__(self, target_level: str, label: str, emoji: str, current_island: Optional[str] = None):
        super().__init__(style=discord.ButtonStyle.primary, label=label, emoji=emoji)
        self.target_level = target_level
        self.current_island = current_island

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        char = await character_service.get_active_character_by_user(user_id)
        if not char:
            await interaction.response.send_message("No active living character.", ephemeral=True)
            return

        embed, view = await build_map_presentation(char, self.target_level, self.current_island)
        await interaction.response.edit_message(embed=embed, view=view)


class TravelSelectButton(discord.ui.Button):
    """Button to initiate immediate voyage to a destination."""

    def __init__(self, destination_id: str, label: str, route_type: str):
        super().__init__(style=discord.ButtonStyle.success, label=label[:80], emoji="⛵")
        self.destination_id = destination_id
        self.route_type = route_type

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        char = await character_service.get_active_character_by_user(user_id)
        if not char:
            await interaction.response.send_message("No active living character.", ephemeral=True)
            return

        result = await travel_engine.execute_travel(char.character_id, self.destination_id)
        if not result["success"]:
            await interaction.response.send_message(f"❌ Travel failed: {result['message']}", ephemeral=True)
            return

        embed = build_travel_result_embed(result)
        await interaction.response.send_message(embed=embed)


class MapView(discord.ui.View):
    """Interactive navigation view for switching map layers and quick-travel."""

    def __init__(self, current_level: str, island_id: Optional[str] = None, destinations: Optional[List[dict]] = None):
        super().__init__(timeout=180)
        if current_level != "world":
            self.add_item(MapLevelSwitchButton("world", "Global Chart", "🗺️", island_id))
        if current_level != "island":
            self.add_item(MapLevelSwitchButton("island", "Island Map", "🏝️", island_id))
        if current_level != "local":
            self.add_item(MapLevelSwitchButton("local", "Local District", "📍", island_id))

        # Add up to 2 travel shortcuts if available
        if destinations:
            for dest in destinations[:2]:
                self.add_item(TravelSelectButton(dest["id"], f"Set Sail: {dest['name']}", dest["route_type"]))


def build_travel_result_embed(result: dict) -> discord.Embed:
    """Builds a rich narrative travel resolution embed without artificial waiting."""
    embed = discord.Embed(
        title=f"⚓ VOYAGE COMPLETE: {result['arrival_name']}",
        description=result["voyage_narrative"],
        color=discord.Color.blue()
    )

    if result.get("encounter"):
        enc = result["encounter"]
        embed.add_field(
            name=f"⚡ Route Encounter: {enc.get('title', 'Event at Sea')}",
            value=f"> {enc.get('narrative', '')}\n\n**Outcome:** {enc.get('resolution', '')}",
            inline=False
        )

    embed.add_field(
        name="🏝️ Current Location",
        value=f"**District / Port:** {result['arrival_name']}\n**Island:** `{result['destination_island_id'].replace('_', ' ').title()}`",
        inline=True
    )
    embed.add_field(
        name="🗺️ Navigation Status",
        value=f"Discovery State: `{result['discovery_state'].upper()}`\nMovement resolved immediately. Ready for orders.",
        inline=True
    )
    embed.set_footer(text="Pirate Wars Navigation • Fast Travel System (No Waiting)")
    return embed


async def build_map_presentation(char, level: str, target_island: Optional[str] = None):
    """Generates the appropriate map embed and view based on requested hierarchy level."""
    char_id = char.character_id
    current_loc = getattr(char, "location_id", "port_azure") or "port_azure"
    current_island = getattr(char, "island_id", "azure_island") or "azure_island"

    if level == "world":
        view_data = await map_service.get_world_map_view(char_id)
        embed = discord.Embed(
            title="🗺️ GLOBAL NAUTICAL CHART",
            description="The known oceans, faction spheres of influence, and major island anchorages.",
            color=discord.Color.dark_teal()
        )
        embed.add_field(
            name="Sea Chart",
            value=f"```{view_data['ascii_chart']}```",
            inline=False
        )
        islands_text = []
        for isl in view_data["islands"]:
            status_icon = "📍" if isl["id"] == view_data["current_position"]["current_island_id"] else "⛵"
            islands_text.append(f"{status_icon} **{isl['name']}** `({isl['coordinates']})` — Faction: *{isl['faction']}* | Danger: `{isl['danger_rating']}/5`")
        embed.add_field(name="Charted Islands", value="\n".join(islands_text), inline=False)
        destinations = await travel_engine.get_available_destinations(char_id)
        return embed, MapView("world", current_island, destinations)

    elif level == "local":
        loc_id = current_loc
        view_data = await map_service.get_location_map_view(char_id, loc_id)
        if not view_data:
            embed = discord.Embed(title="📍 Local Area Map", description="Current district is uncharted.", color=discord.Color.orange())
            return embed, MapView("local", current_island)

        embed = discord.Embed(
            title=f"📍 LOCAL DISTRICT: {view_data['name']}",
            description=view_data["description"],
            color=discord.Color.dark_green()
        )
        embed.add_field(name="District Details", value=f"**Island:** `{view_data['island_name']}`\n**Region:** `{view_data['region_name']}`\n**Terrain:** `{view_data['terrain'].title()}`\n**Discovery State:** `{view_data['discovery_state'].upper()}`", inline=False)

        if view_data.get("facilities"):
            facilities_text = "\n".join([f"• 🏛️ **{f.replace('_', ' ').title()}**" for f in view_data["facilities"]])
            embed.add_field(name="Local Establishments & Docks", value=facilities_text, inline=True)

        if view_data.get("npcs_present"):
            npcs_text = "\n".join([f"• 👤 **{npc}**" for npc in view_data["npcs_present"]])
            embed.add_field(name="People of Note Here", value=npcs_text, inline=True)

        return embed, MapView("local", current_island)

    else:  # island map
        isl_id = target_island or current_island
        view_data = await map_service.get_island_map_view(char_id, isl_id)
        if not view_data:
            embed = discord.Embed(title="🏝️ Island Map", description="Island not found or shrouded in thick mist.", color=discord.Color.red())
            return embed, MapView("island", isl_id)

        embed = discord.Embed(
            title=f"🏝️ REGIONAL CHART: {view_data['name']}",
            description=f"{view_data['description']}\n\n**Controlling Faction:** {view_data['controlling_faction']} | **Danger:** `{view_data['danger_rating']}/5`",
            color=discord.Color.gold()
        )

        for reg in view_data["regions"]:
            loc_lines = []
            for loc in reg["locations"]:
                state = loc["discovery_state"]
                if state == "unknown":
                    loc_lines.append("• ❓ *Fog of War (Uncharted)*")
                elif state == "rumored":
                    loc_lines.append(f"• 🌫️ *Rumored:* **{loc['name']}** (Unverified)")
                else:
                    here_badge = " **[YOU ARE HERE]**" if loc["is_player_here"] else ""
                    loc_lines.append(f"• 📍 **{loc['name']}** `[{loc['terrain']}]`{here_badge}")
            embed.add_field(
                name=f"Region: {reg['name']} ({reg['terrain'].title()})",
                value="\n".join(loc_lines) if loc_lines else "No recorded locations.",
                inline=False
            )

        destinations = await travel_engine.get_available_destinations(char_id)
        return embed, MapView("island", isl_id, destinations)


# --- Slash Commands ---

@app_commands.command(name="map", description="Display the interactive World Map, Island Regional Chart, or Local District.")
@app_commands.describe(
    level="Map detail level to display: world (Global Ocean), island (Regional), or local (District/Port)",
    island_name="Optional island ID or keyword (e.g. skull_island, mistfall, azure)"
)
@app_commands.choices(level=[
    app_commands.Choice(name="Global Ocean Chart (Level 1)", value="world"),
    app_commands.Choice(name="Island Regional Map (Level 2)", value="island"),
    app_commands.Choice(name="Local District / Port (Level 3)", value="local")
])
async def map_command(
    interaction: discord.Interaction,
    level: Optional[app_commands.Choice[str]] = None,
    island_name: Optional[str] = None
):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active living character found. Use `/start` to begin.", ephemeral=True)
        return

    requested_level = level.value if level else "island"
    embed, view = await build_map_presentation(char, requested_level, island_name)
    await interaction.response.send_message(embed=embed, view=view)


@app_commands.command(name="travel", description="Set sail or march to another destination with instant resolution and rich route encounters.")
@app_commands.describe(destination="Target destination name or ID (e.g. Skull Island, Sunken Reef, Mistfall)")
async def travel_command(interaction: discord.Interaction, destination: Optional[str] = None):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active living character found. Use `/start` to begin.", ephemeral=True)
        return

    if not destination:
        # Show destination picker
        destinations = await travel_engine.get_available_destinations(char.character_id)
        if not destinations:
            await interaction.response.send_message("No accessible routes found from your current location.", ephemeral=True)
            return

        embed = discord.Embed(
            title="⛵ CHART A COURSE — AVAILABLE ROUTES",
            description="Select a destination to set sail immediately. No waiting timers required.",
            color=discord.Color.teal()
        )
        view = discord.ui.View(timeout=120)
        for dest in destinations[:5]:
            embed.add_field(
                name=f"📍 {dest['name']} ({dest['route_type'].upper()})",
                value=f"**Island:** {dest['island_id'].replace('_', ' ').title()}\n**Danger:** `{dest['danger_rating']}/5` | **Passage:** `{dest['distance_leagues']} leagues`",
                inline=True
            )
            view.add_item(TravelSelectButton(dest["id"], f"Go to {dest['name']}", dest["route_type"]))

        await interaction.response.send_message(embed=embed, view=view)
        return

    # Execute travel
    result = await travel_engine.execute_travel(char.character_id, destination)
    if not result["success"]:
        await interaction.response.send_message(f"❌ Cannot navigate to '{destination}': {result['message']}", ephemeral=True)
        return

    embed = build_travel_result_embed(result)
    await interaction.response.send_message(embed=embed)


@app_commands.command(name="mark", description="Place a custom waypoint or personal note on your nautical chart.")
@app_commands.describe(label="Short label for this marker", notes="Secret or tactical notes for this location")
async def mark_command(interaction: discord.Interaction, label: str, notes: str = ""):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active living character found.", ephemeral=True)
        return

    marker = await map_service.add_marker(char.character_id, label, notes)
    embed = discord.Embed(
        title="📌 Waypoint Placed",
        description=f"Added custom marker **{marker.label}** at `{marker.island_id}` ({marker.location_id or 'coordinates recorded'}).",
        color=discord.Color.purple()
    )
    if notes:
        embed.add_field(name="Notes", value=notes)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.command(name="markers", description="List all your custom map markers and waypoints.")
async def markers_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active living character found.", ephemeral=True)
        return

    markers = await map_service.list_markers(char.character_id)
    if not markers:
        await interaction.response.send_message("You have no custom markers placed. Use `/mark` to create one.", ephemeral=True)
        return

    embed = discord.Embed(
        title="📌 YOUR CHARTED WAYPOINTS",
        description="Personal markings, hidden caches, and notes recorded on your map.",
        color=discord.Color.purple()
    )
    for m in markers:
        embed.add_field(
            name=f"📍 {m.label} (`{m.marker_id}`)",
            value=f"**Location:** `{m.island_id}` ({m.location_id or 'Seas'})\n**Notes:** {m.notes or 'None'}",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.command(name="timeline", description="View recent chronological world history, dispatch logs, and incoming messages.")
async def timeline_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active living character found.", ephemeral=True)
        return

    events = await notification_service.get_recent_timeline(char.character_id, limit=10)
    recap = await notification_service.get_offline_recap(char.character_id, char.name)

    embed = discord.Embed(
        title=f"📜 WORLD TIMELINE: {char.name}",
        description="Chronological log of events, NPC movements, and world shifts.",
        color=discord.Color.dark_magenta()
    )

    if recap.urgent_alerts:
        embed.add_field(name="⚠️ URGENT DISPATCHES", value="\n".join(recap.urgent_alerts[:3]), inline=False)

    if events:
        lines = [f"• `{evt.timestamp.strftime('%H:%M:%S')}` [{evt.category}] {evt.event_text}" for evt in events]
        embed.add_field(name="Recent World Events", value="\n".join(lines[:8]), inline=False)
    else:
        embed.add_field(name="Recent World Events", value="No recorded events yet in this timeline.", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)
