import discord
from discord import app_commands
from typing import Optional
from app.services.character_service import character_service
from app.game.crews.crew_service import crew_service


class CrewGroup(app_commands.Group):
    """Slash command group for pirate crews and social dynamics."""
    def __init__(self):
        super().__init__(name="crew", description="Commands for managing and interacting with pirate crews.")


crew_group = CrewGroup()


@crew_group.command(name="info", description="Inspect crew roster, treasury, morale, and leadership.")
@app_commands.describe(crew_name="Name of crew to inspect (leave empty to view your own crew)")
async def crew_info_command(interaction: discord.Interaction, crew_name: Optional[str] = None):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)

    target_crew = None
    if crew_name:
        target_crew = await crew_service.get_crew_by_name(crew_name)
    elif char and char.crew_id:
        target_crew = await crew_service.get_crew(char.crew_id)

    if not target_crew:
        await interaction.response.send_message("Crew not found. Specify a crew name or join one with `/crew join`.", ephemeral=True)
        return

    mutiny_risk = target_crew.calculate_mutiny_risk()
    risk_color = discord.Color.green() if mutiny_risk < 30 else (discord.Color.gold() if mutiny_risk < 65 else discord.Color.red())

    embed = discord.Embed(
        title=f"🏴‍☠️ Crew: {target_crew.name}",
        description=f"Home Port: **{target_crew.home_port}**\nTreasury: **{target_crew.treasury:,} Gold**",
        color=risk_color
    )
    embed.add_field(name="Captain", value=f"{target_crew.captain_name} {'(AI)' if target_crew.captain_is_ai else '(Player)'}", inline=True)
    embed.add_field(name="Morale", value=f"{target_crew.morale}/100", inline=True)
    embed.add_field(name="Mutiny Risk", value=f"⚠️ {mutiny_risk}%", inline=True)

    # Roster list
    roster_lines = []
    for member in target_crew.members.values():
        player_tag = "🤖 [AI]" if member.is_ai else "👤 [Player]"
        roster_lines.append(f"• **{member.character_name}** — `{member.role.value}` {player_tag} (Loyalty: {member.loyalty}%)")

    embed.add_field(name=f"Roster ({len(target_crew.members)} members)", value="\n".join(roster_lines) if roster_lines else "None", inline=False)
    embed.set_footer(text="Authoritative Crew Ledger & Politics")

    await interaction.response.send_message(embed=embed, ephemeral=False)


@crew_group.command(name="join", description="Sign articles and join an existing pirate crew as a Deckhand.")
@app_commands.describe(crew_name="The name of the crew you wish to join (e.g., 'The Black Tide')")
async def crew_join_command(interaction: discord.Interaction, crew_name: str):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("You need an active living character to join a crew. Use `/start`.", ephemeral=True)
        return

    crew = await crew_service.get_crew_by_name(crew_name)
    if not crew:
        # Check if we should initialize canonical crews
        if crew_name.lower() == "the black tide":
            crew = await crew_service.ensure_starter_ai_crews()
        else:
            await interaction.response.send_message(f"Crew '{crew_name}' does not exist.", ephemeral=True)
            return

    try:
        updated_crew = await crew_service.join_crew(crew.crew_id, char.character_id)
        embed = discord.Embed(
            title=f"Welcome Aboard the {updated_crew.name}!",
            description=(
                f"You have sworn loyalty to **Captain {updated_crew.captain_name}**.\n"
                f"Your role is **Deckhand**.\n\n"
                f"Obey your officers, contribute to the treasury, or scheme in the shadows..."
            ),
            color=discord.Color.dark_red()
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"Failed to join crew: {str(e)}", ephemeral=True)


@crew_group.command(name="leave", description="Abandon your current crew articles.")
async def crew_leave_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active character found.", ephemeral=True)
        return

    try:
        await crew_service.leave_crew(char.character_id)
        await interaction.response.send_message("You have severed your ties with the crew and are now an independent rogue.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Cannot leave crew: {str(e)}", ephemeral=True)


@crew_group.command(name="deposit", description="Contribute gold into your crew's shared chest.")
@app_commands.describe(amount="Amount of gold to deposit")
async def crew_deposit_command(interaction: discord.Interaction, amount: int):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char or not char.crew_id:
        await interaction.response.send_message("You are not part of any crew.", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("Amount must be greater than zero.", ephemeral=True)
        return

    try:
        tx = await crew_service.deposit_to_treasury(char.crew_id, char.character_id, amount)
        await interaction.response.send_message(
            f"💰 Deposited **{amount} Gold** into the crew treasury. (Transaction ID: `{tx.tx_id[:8]}`)",
            ephemeral=False
        )
    except Exception as e:
        await interaction.response.send_message(f"Deposit failed: {str(e)}", ephemeral=True)
