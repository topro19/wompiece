import discord
from discord import app_commands
from app.game.models.character import Faction
from app.services.character_service import character_service
from app.game.world.location import location_service
from app.game.world.time import world_time_service


class TravelButton(discord.ui.Button):
    """Button triggering authoritative movement to an adjacent location."""
    def __init__(self, target_id: str, label: str):
        super().__init__(style=discord.ButtonStyle.primary, label=f"Go to: {label}", custom_id=f"travel_{target_id}")
        self.target_id = target_id

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        char = await character_service.get_active_character_by_user(user_id)
        if not char:
            await interaction.response.send_message("You do not have an active living character. Use `/start` first.", ephemeral=True)
            return

        try:
            dest = await character_service.move_character(char.character_id, self.target_id)
            clock = await world_time_service.get_world_time()
            clock_str = world_time_service.format_clock(clock)

            embed = discord.Embed(
                title=f"Arrived at: {dest.name}",
                description=dest.description,
                color=discord.Color.green()
            )
            embed.add_field(name="Island", value=dest.island, inline=True)
            embed.add_field(name="Security Rating", value=f"{'⭐' * dest.security_level} (Level {dest.security_level})", inline=True)
            embed.add_field(name="Local Facilities", value=", ".join(dest.facilities) if dest.facilities else "None", inline=False)
            embed.set_footer(text=clock_str)

            # Generate new travel view for next destinations
            view = LocationTravelView(dest.location_id)
            await interaction.response.edit_message(embed=embed, view=view)
        except Exception as e:
            await interaction.response.send_message(f"Travel failed: {str(e)}", ephemeral=True)


class LocationTravelView(discord.ui.View):
    """View rendering movement buttons for all connected locations."""
    def __init__(self, current_location_id: str):
        super().__init__(timeout=120)
        destinations = location_service.get_destinations(current_location_id)
        for dest in destinations:
            self.add_item(TravelButton(target_id=dest.location_id, label=dest.name.split(" - ")[-1]))


# --- Slash Commands ---

@app_commands.command(name="start", description="Create your character and enter the persistent world (One-Life).")
@app_commands.describe(
    name="Your character's public name",
    faction="Choose your starting path in the world"
)
@app_commands.choices(faction=[
    app_commands.Choice(name="Pirate (High seas, plunder, infamy)", value="PIRATE"),
    app_commands.Choice(name="Marine (Law enforcement, cases, naval authority)", value="MARINE"),
    app_commands.Choice(name="Merchant (Trade, business, banking)", value="MERCHANT"),
    app_commands.Choice(name="Independent (Bounty hunter, drifter, freelance)", value="INDEPENDENT")
])
async def start_command(interaction: discord.Interaction, name: str, faction: app_commands.Choice[str]):
    """Enters the world as a distinct individual."""
    user_id = str(interaction.user.id)

    try:
        chosen_faction = Faction(faction.value)
        char = await character_service.create_character(
            user_id=user_id,
            name=name,
            faction=chosen_faction
        )

        clock = await world_time_service.get_world_time()
        clock_str = world_time_service.format_clock(clock)
        start_loc = location_service.get_location(char.location_id)

        embed = discord.Embed(
            title=f"⚓ Welcome to Pirate Wars, {char.name}!",
            description=(
                f"You have stepped ashore in **{start_loc.name}** as an individual.\n\n"
                f"**Path:** {char.faction.value.capitalize()}\n"
                f"**Initial Rank:** {char.rank}\n"
                f"**Purse:** {char.wealth} gold\n\n"
                f"⚠️ **True One-Life System**: Your character has exactly one life. If you fall in combat or execution, "
                f"your character permanently dies and becomes part of the world's history."
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text=clock_str)

        await interaction.response.send_message(embed=embed, ephemeral=False)
    except ValueError as ve:
        await interaction.response.send_message(f"⚠️ {str(ve)}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Error creating character: {str(e)}", ephemeral=True)


@app_commands.command(name="profile", description="View your current character's authoritative dossier and status.")
async def profile_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)

    if not char:
        await interaction.response.send_message(
            "You do not have an active living character. Use `/start` to enter the world.",
            ephemeral=True
        )
        return

    loc = location_service.get_location(char.location_id)
    loc_name = loc.name if loc else char.location_id

    embed = discord.Embed(
        title=f"Dossier: {char.name}",
        color=discord.Color.blue() if char.faction == Faction.MARINE else discord.Color.red()
    )
    embed.add_field(name="Status", value=f"🟢 {char.status.value}", inline=True)
    embed.add_field(name="Faction", value=char.faction.value.capitalize(), inline=True)
    embed.add_field(name="Rank", value=char.rank, inline=True)

    embed.add_field(name="Health", value=f"{char.health}/{char.max_health} HP", inline=True)
    embed.add_field(name="Wealth", value=f"{char.wealth} Gold", inline=True)
    embed.add_field(name="Wanted Level", value=f"⭐ {char.wanted_level}", inline=True)

    embed.add_field(name="Bounty", value=f"{char.bounty:,} Gold", inline=True)
    embed.add_field(name="Current Location", value=loc_name, inline=True)
    embed.add_field(name="Crew", value=char.crew_id or "Independent (None)", inline=True)

    embed.set_footer(text="Authoritative State Record")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.command(name="inventory", description="Inspect your personal inventory and equipment.")
async def inventory_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)

    if not char:
        await interaction.response.send_message("No active living character found. Use `/start`.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"{char.name}'s Sea Chest & Inventory",
        description=f"Coinpurse: **{char.wealth} Gold**\n\n**Possessions:**",
        color=discord.Color.dark_teal()
    )

    if not char.inventory:
        embed.description += "\n*Your pockets are empty.*"
    else:
        for item in char.inventory:
            embed.add_field(
                name=f"📦 {item.get('name', 'Unknown Item')} ({item.get('type', 'gear')})",
                value=item.get('desc', 'No description.'),
                inline=False
            )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.command(name="location", description="Inspect your current surroundings and see available travel routes.")
async def location_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)

    if not char:
        await interaction.response.send_message("No active living character found. Use `/start`.", ephemeral=True)
        return

    loc = location_service.get_location(char.location_id)
    if not loc:
        await interaction.response.send_message("Current location data not found in registry.", ephemeral=True)
        return

    clock = await world_time_service.get_world_time()
    clock_str = world_time_service.format_clock(clock)

    embed = discord.Embed(
        title=f"📍 {loc.name}",
        description=loc.description,
        color=discord.Color.gold()
    )
    embed.add_field(name="Island", value=loc.island, inline=True)
    embed.add_field(name="Security Rating", value=f"{'⭐' * loc.security_level} (Level {loc.security_level})", inline=True)
    embed.add_field(name="Facilities", value=", ".join(loc.facilities) if loc.facilities else "None", inline=False)
    embed.set_footer(text=clock_str)

    view = LocationTravelView(loc.location_id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
