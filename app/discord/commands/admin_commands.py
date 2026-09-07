import discord
from discord import app_commands
from app.database.connection import db_manager
from app.game.models.character import Character, CharacterStatus, Faction
from app.game.simulation.scheduler_service import simulation_scheduler
from app.game.simulation.scheduler_models import TickTier
from app.game.world.location import location_service
from app.game.world.time import world_time_service


admin_group = app_commands.Group(
    name="admin",
    description="Developer and simulation administration tools for managing world state."
)


@admin_group.command(name="simulate_tick", description="Trigger an authoritative world simulation tick.")
@app_commands.describe(tier="Priority tier to simulate (HIGH, MEDIUM, LOW)")
@app_commands.choices(tier=[
    app_commands.Choice(name="HIGH (Fast real-time / transient checks)", value="HIGH"),
    app_commands.Choice(name="MEDIUM (Clock, weather, businesses, crew mutiny, NPC routines)", value="MEDIUM"),
    app_commands.Choice(name="LOW (Market prices, bounty escalation, case decay)", value="LOW")
])
async def admin_simulate_tick_command(interaction: discord.Interaction, tier: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True)
    try:
        if tier.value == "HIGH":
            res = await simulation_scheduler.tick_high()
        elif tier.value == "MEDIUM":
            res = await simulation_scheduler.tick_medium()
        else:
            res = await simulation_scheduler.tick_low()

        embed = discord.Embed(
            title=f"⚙️ Simulation Tick Executed: {res.tier.value}",
            description=res.summary,
            color=discord.Color.teal()
        )
        embed.add_field(name="Entities Evaluated", value=str(res.entities_processed), inline=True)
        embed.add_field(name="Events Emitted", value=str(res.events_emitted), inline=True)
        
        detail_lines = [f"• **{k}:** {v}" for k, v in res.details.items()]
        if detail_lines:
            embed.add_field(name="Execution Breakdown", value="\n".join(detail_lines)[:1000], inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Tick simulation failed: {str(e)}", ephemeral=True)


@admin_group.command(name="advance_time", description="Fast-forward the persistent world clock and run simulation.")
@app_commands.describe(hours="Number of hours to fast-forward world time")
async def admin_advance_time_command(interaction: discord.Interaction, hours: float):
    await interaction.response.defer(ephemeral=True)
    try:
        results = await simulation_scheduler.advance_time(hours)
        clock = await world_time_service.get_world_time()
        time_str = world_time_service.format_clock(clock)

        embed = discord.Embed(
            title=f"⏳ World Time Fast-Forwarded by {hours} Hours",
            description=f"New Current Time: **{time_str}**\nExecuted {len(results)} background simulation cycle(s).",
            color=discord.Color.purple()
        )
        for r in results:
            embed.add_field(name=f"Tick [{r.tier.value}]", value=r.summary, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Time advancement failed: {str(e)}", ephemeral=True)


@admin_group.command(name="spawn_npc", description="Spawn an autonomous AI character into the world.")
@app_commands.describe(
    name="Name of the NPC",
    faction="Faction (PIRATE, MARINE, MERCHANT, INDEPENDENT)",
    location="Starting location ID",
    rank="Title / rank of the NPC"
)
@app_commands.choices(faction=[
    app_commands.Choice(name="PIRATE", value="PIRATE"),
    app_commands.Choice(name="MARINE", value="MARINE"),
    app_commands.Choice(name="MERCHANT", value="MERCHANT"),
    app_commands.Choice(name="INDEPENDENT", value="INDEPENDENT")
])
async def admin_spawn_npc_command(
    interaction: discord.Interaction,
    name: str,
    faction: app_commands.Choice[str],
    location: str = "port_azure_docks",
    rank: str = "Wanderer"
):
    db = db_manager.db
    try:
        loc = location_service.get_location(location)
        if not loc:
            await interaction.response.send_message(f"❌ Invalid location '{location}'.", ephemeral=True)
            return

        npc = Character(
            user_id="ai_system_agent",
            name=name.strip(),
            is_ai=True,
            status=CharacterStatus.ALIVE,
            faction=Faction(faction.value),
            rank=rank,
            wealth=300,
            location_id=location,
            health=100,
            max_health=100
        )
        await db.characters.insert_one(npc.to_mongo())

        embed = discord.Embed(
            title=f"👤 Autonomous AI Spawned: {npc.name}",
            description=f"**Faction:** {npc.faction.value} | **Rank:** {npc.rank}\n**Location:** {loc.name} (`{location}`)",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Character ID: {npc.character_id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Spawn failed: {str(e)}", ephemeral=True)


@admin_group.command(name="inspect_character", description="Inspect complete authoritative state of any character.")
@app_commands.describe(query="Character ID or Name")
async def admin_inspect_character_command(interaction: discord.Interaction, query: str):
    db = db_manager.db
    doc = await db.characters.find_one({
        "$or": [
            {"_id": query},
            {"character_id": query},
            {"name": {"$regex": f"^{query}$", "$options": "i"}}
        ]
    })
    if not doc:
        await interaction.response.send_message(f"❌ Character '{query}' not found.", ephemeral=True)
        return

    char = Character(**doc)
    loc = location_service.get_location(char.location_id)
    loc_name = loc.name if loc else char.location_id

    embed = discord.Embed(
        title=f"🔍 State Dossier: {char.name}",
        description=f"**Status:** `{char.status.value}` | **Type:** {'🤖 AI Agent' if char.is_ai else '👤 Real Player'}",
        color=discord.Color.dark_teal()
    )
    embed.add_field(name="Faction & Rank", value=f"{char.faction.value} — {char.rank}", inline=True)
    embed.add_field(name="Location", value=f"{loc_name} (`{char.location_id}`)", inline=True)
    embed.add_field(name="Vitals", value=f"❤️ {char.health}/{char.max_health} HP", inline=True)
    embed.add_field(name="Wealth", value=f"🪙 {char.wealth} gold", inline=True)
    embed.add_field(name="Wanted Level", value=f"⭐ Level {char.wanted_level} (Bounty: 🪙{char.bounty}g)", inline=True)
    embed.add_field(name="Crew", value=char.crew_id or "None", inline=True)

    inv_text = ", ".join([f"{item.get('name', item.get('item_id'))}" for item in char.inventory]) or "Empty"
    embed.add_field(name="Inventory", value=inv_text[:1000], inline=False)
    embed.set_footer(text=f"Character ID: {char.character_id}")

    await interaction.response.send_message(embed=embed, ephemeral=True)


@admin_group.command(name="list_ships", description="List all naval vessels in the world.")
async def admin_list_ships_command(interaction: discord.Interaction):
    db = db_manager.db
    cursor = db.ships.find({}).limit(20)
    ships = [doc async for doc in cursor]

    if not ships:
        await interaction.response.send_message("No ships registered in the world.", ephemeral=True)
        return

    lines = []
    for s in ships:
        lines.append(
            f"• **{s.get('name')}** ({s.get('ship_class')}) — Hull: {s.get('current_hull')}/{s.get('max_hull')} HP "
            f"| `{s.get('condition')}` | Loc: `{s.get('location_id')}` | ID: `{s.get('_id')}`"
        )

    embed = discord.Embed(
        title="🚢 Naval Registry (Global Ships)",
        description="\n".join(lines)[:4000],
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
