import discord
from discord import app_commands
from app.services.character_service import character_service
from app.game.economy.trade_service import trade_service
from app.game.contracts.contract_service import contract_service
from app.game.contracts.contract_models import ContractType
from app.game.information.intel_service import intel_service
from app.game.information.intel_models import IntelCategory
from app.game.protection.protection_service import protection_service
from app.game.protection.protection_models import ProtectedEntityType
from app.game.salvage.salvage_service import salvage_service
from app.game.models.character import Faction


trade_group = app_commands.Group(
    name="trade",
    description="Buy, sell, and transport commodities across island markets for commercial profit."
)

contract_group = app_commands.Group(
    name="contract",
    description="Browse, post, accept, and complete delivery, escort, and mercenary contracts."
)

intel_group = app_commands.Group(
    name="intel",
    description="Gather, fabricate, and broker high-value intelligence reports across factions."
)

protect_group = app_commands.Group(
    name="protect",
    description="Negotiate and manage formal faction protection pacts for properties and convoys."
)

salvage_group = app_commands.Group(
    name="salvage",
    description="Scout open seas for sunken shipwrecks, flotsam, and buried pirate caches."
)


# --- TRADE COMMANDS ---

@trade_group.command(name="market", description="Inspect the local commodity exchange and market prices.")
async def trade_market_command(interaction: discord.Interaction):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character. Use `/start` first.", ephemeral=True)
        return

    catalog = trade_service.get_market_prices(char.location_id)
    if not catalog:
        await interaction.response.send_message("❌ There is no active merchant market at your current location.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"⚖️ Regional Exchange — Market Prices",
        description=f"Current trading board for `{char.location_id}`.\nBuy low here and sail to other islands to arbitrage for massive profits!",
        color=discord.Color.gold()
    )

    for item in catalog:
        contraband_tag = "⚠️ **[CONTRABAND]**" if item["is_illegal_here"] else ""
        embed.add_field(
            name=f"{item['name']} `{item['commodity_id']}` {contraband_tag}",
            value=f"• **Buy:** 🪙 {item['buy_price']}g | **Sell:** 🪙 {item['sell_price']}g\n*{item['description']}*",
            inline=False
        )

    embed.set_footer(text="Trade runs update dynamically across ports • Use /trade buy and /trade sell")
    await interaction.response.send_message(embed=embed)


@trade_group.command(name="buy", description="Purchase commodities from the local port market.")
@app_commands.describe(
    commodity="Commodity ID (e.g. iron_ore, fine_silk, rare_spices, vintage_rum, timber, gunpowder, contraband_opium)",
    quantity="Number of units to purchase"
)
async def trade_buy_command(interaction: discord.Interaction, commodity: str, quantity: int = 1):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character.", ephemeral=True)
        return

    try:
        res = await trade_service.buy_commodity(char.character_id, commodity, quantity)
        embed = discord.Embed(
            title="📦 Cargo Acquired!",
            description=f"Successfully purchased **{res['quantity']}x {res['commodity']}** at **{res['location']}**.",
            color=discord.Color.green()
        )
        embed.add_field(name="Unit Price", value=f"🪙 {res['unit_price']}g", inline=True)
        embed.add_field(name="Total Disbursed", value=f"🪙 {res['total_cost']}g", inline=True)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Purchase failed: {str(e)}", ephemeral=True)


@trade_group.command(name="sell", description="Sell commodities to the local market (Beware customs with contraband!).")
@app_commands.describe(
    commodity="Commodity ID (e.g. iron_ore, fine_silk, rare_spices, vintage_rum, timber, gunpowder, contraband_opium)",
    quantity="Number of units to sell"
)
async def trade_sell_command(interaction: discord.Interaction, commodity: str, quantity: int = 1):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character.", ephemeral=True)
        return

    try:
        res = await trade_service.sell_commodity(char.character_id, commodity, quantity)
        embed = discord.Embed(
            title="💰 Cargo Liquidated!",
            description=f"Successfully sold **{res['quantity']}x {res['commodity']}** at **{res['location']}**.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Unit Sale Price", value=f"🪙 {res['unit_price']}g", inline=True)
        embed.add_field(name="Total Revenue", value=f"🪙 {res['total_payout']}g", inline=True)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Trade failed: {str(e)}", ephemeral=True)


# --- CONTRACT COMMANDS ---

@contract_group.command(name="board", description="Inspect the dynamic public contract board for open contracts.")
@app_commands.describe(contract_type="Optional filter: DELIVERY, ESCORT, BOUNTY_HUNT, INFORMATION, SALVAGE")
async def contract_board_command(interaction: discord.Interaction, contract_type: str = None):
    ctype = None
    if contract_type:
        try:
            ctype = ContractType(contract_type)
        except ValueError:
            pass

    contracts = await contract_service.get_open_contracts(ctype)
    if not contracts:
        await interaction.response.send_message("No open contracts available on the board right now.", ephemeral=True)
        return

    embed = discord.Embed(
        title="📜 Public Maritime Contract Board",
        description="Escrow-backed contracts posted by merchants, navies, and pirate syndicates.",
        color=discord.Color.blue()
    )

    for c in contracts:
        req = f"• **Requires:** {c.required_quantity}x `{c.required_item_id}`\n" if c.required_item_id else ""
        embed.add_field(
            name=f"[{c.contract_type.value}] {c.title} — 🪙 {c.reward_amount}g",
            value=f"{c.description}\n{req}• **Issuer:** {c.issuer_name} ({c.issuer_faction.value})\n• **ID:** `{c.contract_id}`",
            inline=False
        )

    embed.set_footer(text="Accept with /contract accept <contract_id>")
    await interaction.response.send_message(embed=embed)


@contract_group.command(name="post", description="Post a contract on the public board, locking reward into escrow.")
@app_commands.describe(
    contract_type="Type of contract (DELIVERY, ESCORT, BOUNTY_HUNT, INFORMATION, SALVAGE)",
    title="Short descriptive title of the task",
    reward_amount="Gold reward deposited into escrow",
    description="Detailed description of terms and expectations",
    required_item_id="Optional item ID required to prove completion (e.g. timber, rare_spices)"
)
@app_commands.choices(contract_type=[
    app_commands.Choice(name="DELIVERY (Cargo transport)", value="DELIVERY"),
    app_commands.Choice(name="ESCORT (Vessel/convoy protection)", value="ESCORT"),
    app_commands.Choice(name="BOUNTY_HUNT (Capture/neutralize fugitive)", value="BOUNTY_HUNT"),
    app_commands.Choice(name="INFORMATION (Gather intelligence/recon)", value="INFORMATION"),
    app_commands.Choice(name="SALVAGE (Recover wreckage/lost goods)", value="SALVAGE")
])
async def contract_post_command(
    interaction: discord.Interaction,
    contract_type: app_commands.Choice[str],
    title: str,
    reward_amount: int,
    description: str,
    required_item_id: str = None
):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character.", ephemeral=True)
        return

    try:
        c = await contract_service.post_contract(
            issuer_character_id=char.character_id,
            contract_type=ContractType(contract_type.value),
            title=title,
            reward_amount=reward_amount,
            description=description,
            required_item_id=required_item_id
        )

        embed = discord.Embed(
            title="📜 Contract Posted & Escrow Locked",
            description=f"Your contract **'{c.title}'** has been listed on the world board. **🪙 {reward_amount}g** is secured in escrow.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Contract ID: {c.contract_id}")
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to post contract: {str(e)}", ephemeral=True)


@contract_group.command(name="accept", description="Accept an open contract from the board.")
@app_commands.describe(contract_id="The ID of the contract to take on")
async def contract_accept_command(interaction: discord.Interaction, contract_id: str):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character.", ephemeral=True)
        return

    try:
        c = await contract_service.accept_contract(contract_id, char.character_id)
        embed = discord.Embed(
            title="⚔️ Contract Accepted!",
            description=f"You have committed to: **{c.title}**\n\n*{c.description}*",
            color=discord.Color.teal()
        )
        embed.add_field(name="Escrow Bounty", value=f"🪙 {c.reward_amount}g", inline=True)
        embed.add_field(name="Issuer", value=f"{c.issuer_name} ({c.issuer_faction.value})", inline=True)
        embed.set_footer(text="When terms are met, use /contract complete <contract_id>")
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Could not accept contract: {str(e)}", ephemeral=True)


@contract_group.command(name="complete", description="Turn in completed contract terms and claim escrow reward.")
@app_commands.describe(contract_id="The ID of the accepted contract")
async def contract_complete_command(interaction: discord.Interaction, contract_id: str):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character.", ephemeral=True)
        return

    try:
        res = await contract_service.complete_contract(contract_id, char.character_id)
        embed = discord.Embed(
            title="🏆 Contract Completed & Reward Disbursed!",
            description=f"The terms of **'{res['title']}'** were verified.\n\n"
                        f"• **Escrow Disbursed:** 🪙 **{res['reward_amount']}g** credited to your purse!\n"
                        f"• **Reputation:** +5 Independent, +3 Merchant",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Settlement failed: {str(e)}", ephemeral=True)


# --- INTEL COMMANDS ---

@intel_group.command(name="gather", description="Gather rumors and intelligence from taverns, ports, or forge lies.")
@app_commands.describe(
    category="Intel category (PIRATE_MOVEMENT, MARINE_PATROL, CONTRABAND_SHIPMENT)",
    fabricate="Set to True to forge false/misleading intelligence (Double-agent playstyle)"
)
@app_commands.choices(category=[
    app_commands.Choice(name="PIRATE_MOVEMENT (Raider locations, ambushes)", value="PIRATE_MOVEMENT"),
    app_commands.Choice(name="MARINE_PATROL (Customs schedules, navy routes)", value="MARINE_PATROL"),
    app_commands.Choice(name="CONTRABAND_SHIPMENT (Illegal cargo arrivals)", value="CONTRABAND_SHIPMENT")
])
async def intel_gather_command(
    interaction: discord.Interaction,
    category: app_commands.Choice[str],
    fabricate: bool = False
):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character.", ephemeral=True)
        return

    try:
        intel = await intel_service.gather_intel(
            character_id=char.character_id,
            category=IntelCategory(category.value),
            is_fabrication=fabricate
        )

        embed = discord.Embed(
            title=f"🔎 Intel Gathered: {intel.title}",
            description=f"*{intel.detail}*",
            color=discord.Color.purple()
        )
        embed.add_field(name="Reliability Rating", value=f"{int(intel.reliability * 100)}%", inline=True)
        embed.add_field(name="Market Street Value", value=f"🪙 {intel.market_value}g", inline=True)
        embed.add_field(name="Dossier ID", value=f"`{intel.intel_id}`", inline=False)
        embed.set_footer(text="Sell to Marines or Pirates using /intel sell")

        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Intel scouting failed: {str(e)}", ephemeral=True)


# --- PROTECTION COMMANDS ---

@protect_group.command(name="hire", description="Contract formal faction protection for your character or business.")
@app_commands.describe(
    faction="Faction to hire for protection (PIRATE, MARINE, INDEPENDENT)",
    protector_name="Name of protecting crew or division (e.g. 'The Black Tide', 'Marine 16th Division')",
    weekly_dues="Weekly protection dues in gold"
)
@app_commands.choices(faction=[
    app_commands.Choice(name="PIRATE (Underworld immunity, pirate retaliation)", value="PIRATE"),
    app_commands.Choice(name="MARINE (Navy sentries, automatic felony cases)", value="MARINE"),
    app_commands.Choice(name="INDEPENDENT (Mercenary bodyguards)", value="INDEPENDENT")
])
async def protect_hire_command(
    interaction: discord.Interaction,
    faction: app_commands.Choice[str],
    protector_name: str,
    weekly_dues: int = 150
):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character.", ephemeral=True)
        return

    try:
        f = Faction(faction.value)
        c = await protection_service.create_contract(
            merchant_character_id=char.character_id,
            entity_type=ProtectedEntityType.INDIVIDUAL,
            entity_id=char.character_id,
            protector_faction=f,
            protector_id=f"prot_org_{protector_name.strip().replace(' ', '_').lower()}",
            protector_name=protector_name,
            weekly_dues=weekly_dues
        )

        embed = discord.Embed(
            title="🛡️ Protection Treaty Enacted",
            description=f"You are now under formal jurisdictional protection of **{c.protector_name}** ({f.value}).",
            color=discord.Color.blue()
        )
        embed.add_field(name="Retainer Paid", value=f"🪙 {weekly_dues}g / cycle", inline=True)
        embed.add_field(name="Immunity Clause", value="Anyone who attacks you commits a hostile act against your protector's faction!", inline=False)
        embed.set_footer(text=f"Contract ID: {c.contract_id}")

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Protection failed: {str(e)}", ephemeral=True)


# --- SALVAGE COMMANDS ---

@salvage_group.command(name="explore", description="Explore current waters for shipwrecks, adrift flotsam, and buried caches.")
async def salvage_explore_command(interaction: discord.Interaction):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character.", ephemeral=True)
        return

    try:
        site = await salvage_service.explore_for_salvage(char.character_id, char.location_id)
        if not site:
            await interaction.response.send_message("🌊 You swept the area thoroughly, but found no visible wreckage or drifting flotsam.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"⚓ Salvage Discovered: {site.name}!",
            description=f"**Type:** {site.salvage_type.value}\n**Original Owner:** {site.original_owner_name or 'Unknown'}\n**Estimated Gold:** 🪙 ~{site.loot_gold}g",
            color=discord.Color.teal()
        )
        embed.add_field(name="Salvage Site ID", value=f"`{site.site_id}`", inline=False)
        embed.add_field(
            name="Moral Dilemma",
            value="• Return to owner (`/salvage claim choice:return_to_owner`): 35% legal finder's fee + reputation boost.\n"
                  "• Scavenge/Steal (`/salvage claim choice:steal`): 100% loot, but risk outlaw status.",
            inline=False
        )

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Scouting failed: {str(e)}", ephemeral=True)


@salvage_group.command(name="claim", description="Claim salvage by returning it honorably or stealing the cargo.")
@app_commands.describe(
    site_id="ID of the discovered salvage site",
    choice="Moral choice: 'return_to_owner' (Legal finder's fee) or 'steal' (Outlaw plundering)"
)
@app_commands.choices(choice=[
    app_commands.Choice(name="Return to Owner (35% finder's fee + high reputation)", value="return_to_owner"),
    app_commands.Choice(name="Steal Cargo (100% loot + outlaw risk)", value="steal")
])
async def salvage_claim_command(interaction: discord.Interaction, site_id: str, choice: app_commands.Choice[str]):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character.", ephemeral=True)
        return

    try:
        res = await salvage_service.claim_salvage(char.character_id, site_id, choice.value)
        embed = discord.Embed(
            title=f"🌊 Salvage Resolved: {res['site_name']}",
            description=res["narrative"],
            color=discord.Color.green() if choice.value == "return_to_owner" else discord.Color.dark_gold()
        )
        if "reward_gold" in res:
            embed.add_field(name="Legal Finder's Reward", value=f"🪙 {res['reward_gold']}g", inline=True)
        if "loot_gold" in res:
            embed.add_field(name="Plundered Wealth", value=f"🪙 {res['loot_gold']}g", inline=True)
        embed.add_field(name="Reputation Shift", value=res["reputation_change"], inline=False)

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Salvage claim failed: {str(e)}", ephemeral=True)
