import discord
from discord import app_commands
from app.services.character_service import character_service
from app.game.combat.combat_service import combat_service
from app.database.connection import db_manager


class CombatGroup(app_commands.Group):
    """Commands for player-vs-player and player-vs-NPC tactical combat."""
    def __init__(self):
        super().__init__(name="combat", description="Engage in authoritative lethal and non-lethal combat.")


combat_group = CombatGroup()


@combat_group.command(name="attack", description="Engage an opponent in lethal combat. ⚠️ Permadeath warning applies!")
@app_commands.describe(target_name="Name of character to attack in the current location")
async def combat_attack_command(interaction: discord.Interaction, target_name: str):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active character found. Use `/start`.", ephemeral=True)
        return

    db = db_manager.db
    target_doc = await db.characters.find_one({
        "name": {"$regex": f"^{target_name.strip()}$", "$options": "i"},
        "status": "ALIVE"
    })
    if not target_doc:
        await interaction.response.send_message(f"Living target '{target_name}' not found.", ephemeral=True)
        return

    if target_doc["_id"] == char.character_id:
        await interaction.response.send_message("You cannot attack yourself.", ephemeral=True)
        return

    try:
        res = await combat_service.resolve_attack(
            attacker_id=char.character_id,
            defender_id=target_doc["_id"],
            is_lethal=True
        )

        embed = discord.Embed(
            title="⚔️ Combat Clash",
            description=res["narrative"],
            color=discord.Color.red() if res.get("permadeath") else discord.Color.gold()
        )

        if res.get("hit"):
            embed.add_field(name="Damage Dealt", value=f"{res['damage']} DMG", inline=True)
            embed.add_field(name="Target Remaining HP", value=f"{res['defender_remaining_hp']} HP", inline=True)

        if res.get("escalation"):
            esc = res["escalation"]
            embed.add_field(
                name="🚨 WANTED LEVEL ESCALATED!",
                value=f"New Wanted Level: ⭐ **{esc['wanted_level']}**\nBounty: **{esc['bounty']:,} Gold**\n{esc.get('task_force', '')}",
                inline=False
            )

        if res.get("permadeath"):
            embed.set_footer(text="☠️ PERMANENT DEATH: Character is deceased and cannot return.")
        else:
            embed.set_footer(text="Server-Authoritative Combat Engine")

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"Combat error: {str(e)}", ephemeral=True)
