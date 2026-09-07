import discord
from discord import app_commands
from typing import Optional
from app.services.character_service import character_service
from app.game.businesses.business_service import business_service
from app.game.identity.identity_service import identity_service


class BusinessGroup(app_commands.Group):
    """Commands for inspecting and operating commercial establishments."""
    def __init__(self):
        super().__init__(name="business", description="Manage commercial properties and hidden fronts.")


business_group = BusinessGroup()


@business_group.command(name="info", description="Inspect official registry and operations of a commercial business.")
@app_commands.describe(name="Name of the business (e.g. 'The Golden Anchor')")
async def business_info_command(interaction: discord.Interaction, name: str):
    biz = await business_service.get_business_by_name(name)
    if not biz:
        await interaction.response.send_message(f"Business '{name}' not found on public registries.", ephemeral=True)
        return

    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)

    is_owner_or_crew = False
    if char:
        if char.character_id == biz.owner_character_id or (char.crew_id and char.crew_id == biz.crew_id):
            is_owner_or_crew = True

    anomaly = biz.calculate_financial_anomaly()

    embed = discord.Embed(
        title=f"🏢 {biz.name}",
        description=f"Type: `{biz.business_type.value}`\nLocation: `{biz.location_id}`",
        color=discord.Color.gold()
    )
    embed.add_field(name="Registered Owner", value=f"📜 {biz.registered_owner_name}", inline=True)
    embed.add_field(name="Daily Revenue", value=f"{biz.daily_revenue:,} Gold", inline=True)
    embed.add_field(name="Legitimacy Rating", value=f"{biz.legitimacy_score}/100", inline=True)

    if is_owner_or_crew:
        embed.add_field(name="⚠️ Internal Suspicion", value=f"{biz.suspicion_level}%", inline=True)
        embed.add_field(name="Hidden Operations", value=", ".join(biz.hidden_illegal_ops) if biz.hidden_illegal_ops else "None", inline=False)
        embed.set_footer(text="Private Owner Ledger View")
    else:
        embed.add_field(name="Financial Anomaly Score", value=f"{int(anomaly * 100)}%", inline=True)
        embed.set_footer(text="Colonial Commercial Registry")

    await interaction.response.send_message(embed=embed, ephemeral=not is_owner_or_crew)


@business_group.command(name="operate", description="Run a legitimate daily commercial trade shift.")
@app_commands.describe(name="Name of your business")
async def business_operate_command(interaction: discord.Interaction, name: str):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active character found.", ephemeral=True)
        return

    biz = await business_service.get_business_by_name(name)
    if not biz:
        await interaction.response.send_message(f"Business '{name}' not found.", ephemeral=True)
        return

    if biz.owner_character_id != char.character_id and biz.crew_id != char.crew_id:
        await interaction.response.send_message("You do not have management authority over this business.", ephemeral=True)
        return

    try:
        res = await business_service.run_legitimate_operation(biz.business_id)
        embed = discord.Embed(
            title=f"📈 Commercial Shift: {biz.name}",
            description=f"Legitimate customers served. Net profit generated: **+{res['profit']} Gold**.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"Operation failed: {str(e)}", ephemeral=True)


@business_group.command(name="smuggle", description="Liquidate contraband or run illicit gambling through your front.")
@app_commands.describe(name="Name of your business")
async def business_smuggle_command(interaction: discord.Interaction, name: str):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active character found.", ephemeral=True)
        return

    biz = await business_service.get_business_by_name(name)
    if not biz:
        await interaction.response.send_message(f"Business '{name}' not found.", ephemeral=True)
        return

    if biz.owner_character_id != char.character_id and biz.crew_id != char.crew_id:
        await interaction.response.send_message("You do not have management authority over this business.", ephemeral=True)
        return

    try:
        res = await business_service.run_underhand_smuggling(biz.business_id)
        embed = discord.Embed(
            title=f"🤫 Illicit Operation Executed: {biz.name}",
            description=(
                f"Contraband crates offloaded in secret. Black market cut: **+{res['payout']} Gold**!\n\n"
                f"⚠️ **Suspicion Level Increased:** Now `{res['suspicion']}%`\n"
                f"📊 **Financial Anomaly Rating:** `{int(res['anomaly_score'] * 100)}%`\n"
                f"*Marine revenue inspectors may notice this discrepancy if an investigation opens.*"
            ),
            color=discord.Color.dark_purple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Smuggling run failed: {str(e)}", ephemeral=True)


class AliasGroup(app_commands.Group):
    """Commands for forging and managing paper civilian identities."""
    def __init__(self):
        super().__init__(name="alias", description="Manage forged legal identities to mask pirate status.")


alias_group = AliasGroup()


@alias_group.command(name="forge", description="Purchase forged civilian papers to create an alternate identity (150 Gold).")
@app_commands.describe(
    alias_name="The forged name to appear on official records",
    occupation="Civilian cover occupation (e.g. 'Merchant Importer', 'Tavern Keeper')"
)
async def alias_forge_command(interaction: discord.Interaction, alias_name: str, occupation: str = "Merchant"):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active character found.", ephemeral=True)
        return

    try:
        alias = await identity_service.create_alias(
            character_id=char.character_id,
            alias_name=alias_name,
            legal_occupation=occupation,
            fee=150
        )
        embed = discord.Embed(
            title="📜 Forged Papers Procured",
            description=(
                f"You have acquired official-looking documents under the name **{alias.alias_name}**.\n"
                f"**Legal Occupation:** {alias.legal_occupation}\n"
                f"**Apparent Faction:** {alias.legal_faction}\n\n"
                f"You can now register properties and business licenses under this alias to evade Marine bounties."
            ),
            color=discord.Color.dark_teal()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to forge alias: {str(e)}", ephemeral=True)


@alias_group.command(name="list", description="Review all forged identities linked to your true character.")
async def alias_list_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active character found.", ephemeral=True)
        return

    aliases = await identity_service.get_aliases_for_character(char.character_id)
    if not aliases:
        await interaction.response.send_message("You have no registered aliases. Use `/alias forge` to acquire one.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🤫 Secret Dossier: {char.name}'s Aliases",
        description="Only you can see this secret record.",
        color=discord.Color.dark_grey()
    )

    for al in aliases:
        status_str = "🚨 EXPOSED TO MARINES" if al.is_exposed() else f"Active (Suspicion: {al.suspicion_level}%)"
        embed.add_field(
            name=f"Name: {al.alias_name}",
            value=f"Occupation: `{al.legal_occupation}` | Status: `{status_str}` | Linked Clues: `{len(al.linked_evidence_ids)}`",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)
