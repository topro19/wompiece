import discord
from discord import app_commands
from app.services.character_service import character_service
from app.game.businesses.business_service import business_service
from app.game.gambling.gambling_service import gambling_service


class GambleGroup(app_commands.Group):
    """Commands for in-game gambling establishments."""
    def __init__(self):
        super().__init__(name="gamble", description="Wager in-game gold in taverns and gambling dens.")


gamble_group = GambleGroup()


@gamble_group.command(name="dice", description="Play High-Low Dice (2d6) at the local gaming table.")
@app_commands.describe(
    wager="Amount of gold to bet (10 - 500)",
    choice="Your prediction"
)
@app_commands.choices(choice=[
    app_commands.Choice(name="High (Total 8-12, Pays 2x)", value="HIGH"),
    app_commands.Choice(name="Low (Total 2-6, Pays 2x)", value="LOW"),
    app_commands.Choice(name="Lucky Seven (Total 7, Pays 4x)", value="SEVEN")
])
async def gamble_dice_command(
    interaction: discord.Interaction,
    wager: int,
    choice: app_commands.Choice[str]
):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active living character found. Use `/start`.", ephemeral=True)
        return

    if char.wealth < wager:
        await interaction.response.send_message(
            f"Insufficient funds! You have {char.wealth} gold, but wagered {wager}.",
            ephemeral=True
        )
        return

    # Find local business table
    local_biz_list = await business_service.get_businesses_by_location(char.location_id)
    target_biz_id = local_biz_list[0].business_id if local_biz_list else "the_golden_anchor_default"

    try:
        outcome = await gambling_service.play_high_low_dice(
            character_id=char.character_id,
            business_id=target_biz_id,
            wager=wager,
            choice=choice.value
        )

        color = discord.Color.green() if outcome.player_won else discord.Color.red()
        title = "🎲 Dice Roll: YOU WON!" if outcome.player_won else "🎲 Dice Roll: The House Wins"

        embed = discord.Embed(
            title=title,
            description=f"**{outcome.details}**",
            color=color
        )
        embed.add_field(name="Wager", value=f"{wager} Gold", inline=True)
        embed.add_field(name="Net Result", value=f"+{outcome.payout} Gold" if outcome.player_won else f"-{wager} Gold", inline=True)

        reloaded_char = await character_service.get_active_character_by_user(user_id)
        embed.add_field(name="New Purse", value=f"{reloaded_char.wealth} Gold", inline=True)

        if outcome.rigged_detected:
            embed.set_footer(text="⚠️ Astute patrons suspect the dice are loaded!")
        else:
            embed.set_footer(text="Authoritative Gambling Engine")

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"Gambling failed: {str(e)}", ephemeral=True)
