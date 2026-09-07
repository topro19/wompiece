import discord
from discord import app_commands
from app.database.connection import db_manager
from app.services.character_service import character_service
from app.game.ships.ship_models import ShipClass, SHIP_CLASS_CONFIGS
from app.game.ships.ship_service import ship_service
from app.game.world.location import location_service


ship_group = app_commands.Group(
    name="ship",
    description="Command, navigate, repair, and engage in naval warfare with ocean vessels."
)


@ship_group.command(name="buy", description="Purchase a vessel from a shipyard port.")
@app_commands.describe(
    ship_class="The class of ship to purchase (SLOOP, CARAVEL, FRIGATE, GALLEON)",
    name="The name of your new vessel",
    for_crew="Purchase as the official flagship for your crew treasury (Captain only)"
)
@app_commands.choices(ship_class=[
    app_commands.Choice(name="Swift Sloop (500g, 4 Cannons, 100 HP)", value="SLOOP"),
    app_commands.Choice(name="Merchant Caravel (1,500g, 10 Cannons, 220 HP)", value="CARAVEL"),
    app_commands.Choice(name="Heavy Frigate (4,000g, 24 Cannons, 400 HP)", value="FRIGATE"),
    app_commands.Choice(name="War Galleon (10,000g, 44 Cannons, 750 HP)", value="GALLEON")
])
async def ship_buy_command(
    interaction: discord.Interaction,
    ship_class: app_commands.Choice[str],
    name: str,
    for_crew: bool = False
):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character. Use `/start` first.", ephemeral=True)
        return

    try:
        s_class = ShipClass(ship_class.value)
        ship = await ship_service.purchase_ship(
            buyer_character_id=char.character_id,
            ship_class=s_class,
            name=name,
            for_crew=for_crew
        )

        embed = discord.Embed(
            title=f"⚓ Ship Commissioned: {ship.name}",
            description=f"Congratulations, Captain! The shipyard shipwrights have finalized the outfitting of your **{ship.ship_class.value}**.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Hull Integrity", value=f"🛡️ {ship.current_hull}/{ship.max_hull} HP", inline=True)
        embed.add_field(name="Armament", value=f"💣 {ship.cannons} Cannons", inline=True)
        embed.add_field(name="Armor Plating", value=f"🧱 {ship.armor}", inline=True)
        embed.add_field(name="Speed", value=f"💨 {ship.speed} knots", inline=True)
        embed.add_field(name="Cargo Capacity", value=f"📦 {ship.cargo_capacity} units", inline=True)
        embed.add_field(name="Crew Quarters", value=f"👥 {ship.crew_capacity} sailors", inline=True)
        embed.add_field(name="Ship ID", value=f"`{ship.ship_id}`", inline=False)

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Purchase failed: {str(e)}", ephemeral=True)


@ship_group.command(name="info", description="Inspect detailed naval statistics, cargo hold, and condition of a ship.")
@app_commands.describe(ship_id="Optional Ship ID. If omitted, displays your current active command vessel.")
async def ship_info_command(interaction: discord.Interaction, ship_id: str = None):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character.", ephemeral=True)
        return

    ship = None
    if ship_id:
        ship = await ship_service.get_ship(ship_id)
    else:
        ships = await ship_service.get_ships_by_owner(char.character_id)
        if not ships and char.crew_id:
            ships = await ship_service.get_crew_ships(char.crew_id)
        if ships:
            ship = ships[0]

    if not ship:
        await interaction.response.send_message("❌ No vessel found. Provide a valid `ship_id` or commission one with `/ship buy`.", ephemeral=True)
        return

    loc = location_service.get_location(ship.location_id)
    loc_name = loc.name if loc else ship.location_id

    # Visual health bar
    pct = max(0.0, min(1.0, ship.current_hull / ship.max_hull))
    filled_blocks = int(pct * 10)
    bar = "█" * filled_blocks + "░" * (10 - filled_blocks)

    color_map = {
        "MINT": discord.Color.green(),
        "DAMAGED": discord.Color.orange(),
        "CRIPPLED": discord.Color.red(),
        "SUNK": discord.Color.dark_grey()
    }

    embed = discord.Embed(
        title=f"⛵ Vessel Dossier: {ship.name}",
        description=f"**Class:** {ship.ship_class.value} | **Condition:** `{ship.condition.value}`\n**Location:** {loc_name} ({'Docked at Harbor' if ship.is_docked else 'Underway at Sea'})",
        color=color_map.get(ship.condition.value, discord.Color.blue())
    )
    embed.add_field(name="Hull Integrity", value=f"`[{bar}]` {ship.current_hull}/{ship.max_hull} HP ({int(pct*100)}%)", inline=False)
    embed.add_field(name="Broadside Battery", value=f"💣 {ship.cannons} Cannons", inline=True)
    embed.add_field(name="Armor Plating", value=f"🧱 {ship.armor}", inline=True)
    embed.add_field(name="Max Velocity", value=f"💨 {ship.speed} kts", inline=True)
    embed.add_field(name="Hold Utilization", value=f"📦 {ship.current_cargo_weight()}/{ship.cargo_capacity} units", inline=True)
    embed.add_field(name="Crew Capacity", value=f"👥 {ship.crew_capacity} max", inline=True)

    if ship.cargo:
        cargo_lines = [
            f"• **{c.name}** x{c.quantity} {'⚠️ [CONTRABAND]' if c.is_contraband else ''}"
            for c in ship.cargo
        ]
        embed.add_field(name="Cargo Manifest", value="\n".join(cargo_lines), inline=False)
    else:
        embed.add_field(name="Cargo Manifest", value="*(Cargo hold is empty)*", inline=False)

    embed.set_footer(text=f"Ship ID: {ship.ship_id} | Captain: {ship.captain_id}")
    await interaction.response.send_message(embed=embed)


@ship_group.command(name="sail", description="Set sail and navigate your vessel across sea lanes.")
@app_commands.describe(
    destination="Destination port or sea lane (e.g., azure_sea_lane, skull_rock_anchorage, coral_bay_wharf, port_azure_docks)",
    ship_id="Optional Ship ID. If omitted, uses your active command vessel."
)
async def ship_sail_command(interaction: discord.Interaction, destination: str, ship_id: str = None):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character.", ephemeral=True)
        return

    target_ship = None
    if ship_id:
        target_ship = await ship_service.get_ship(ship_id)
    else:
        ships = await ship_service.get_ships_by_owner(char.character_id)
        if not ships and char.crew_id:
            ships = await ship_service.get_crew_ships(char.crew_id)
        if ships:
            target_ship = ships[0]

    if not target_ship:
        await interaction.response.send_message("❌ No vessel available to command.", ephemeral=True)
        return

    try:
        res = await ship_service.sail_ship(
            ship_id=target_ship.ship_id,
            captain_character_id=char.character_id,
            destination_location_id=destination
        )
        ship = res["ship"]
        dest = res["destination"]
        encounter = res["encounter"]

        embed = discord.Embed(
            title=f"🌊 {ship.name} Sets Sail!",
            description=f"Your vessel has navigated the waters and arrived safely at **{dest.name}**.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Current Position", value=f"📍 {dest.name} ({'Docked' if ship.is_docked else 'Underway'})", inline=False)
        embed.add_field(name="Encounter Log", value=f"🧭 **{encounter['type']}**\n*{encounter['narrative']}*", inline=False)

        if encounter.get("damage_taken"):
            embed.add_field(name="Storm Damage", value=f"⚠️ The tempest battered your hull for **{encounter['damage_taken']} HP**! Remaining: {ship.current_hull}/{ship.max_hull} HP", inline=False)

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Voyage failed: {str(e)}", ephemeral=True)


@ship_group.command(name="attack", description="Engage an enemy ship in broadside cannon combat.")
@app_commands.describe(
    target_ship_id="The Ship ID of the target vessel in the same sea zone/port",
    ship_id="Optional Ship ID of your attacking vessel"
)
async def ship_attack_command(interaction: discord.Interaction, target_ship_id: str, ship_id: str = None):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character.", ephemeral=True)
        return

    attacker = None
    if ship_id:
        attacker = await ship_service.get_ship(ship_id)
    else:
        ships = await ship_service.get_ships_by_owner(char.character_id)
        if not ships and char.crew_id:
            ships = await ship_service.get_crew_ships(char.crew_id)
        if ships:
            attacker = ships[0]

    if not attacker:
        await interaction.response.send_message("❌ You have no ship to command for attack.", ephemeral=True)
        return

    try:
        combat_res = await ship_service.naval_cannon_combat(
            attacker_ship_id=attacker.ship_id,
            target_ship_id=target_ship_id
        )

        target = combat_res["target"]
        damage = combat_res["damage_dealt"]
        ret_damage = combat_res["retaliation_damage"]
        crit = combat_res["is_critical"]
        target_sunk = combat_res["target_sunk"]
        attacker_sunk = combat_res["attacker_sunk"]

        embed = discord.Embed(
            title="💥 Naval Broadside Battle!",
            description=f"**{attacker.name}** fired a broadside barrage at **{target.name}**!",
            color=discord.Color.dark_red()
        )
        embed.add_field(
            name=f"Barrage on {target.name}",
            value=f"💣 Dealt **{damage} damage**! {'🔥 **CRITICAL POWDER HIT!**' if crit else ''}\nTarget Hull: {target.current_hull}/{target.max_hull} HP ({target.condition.value})",
            inline=False
        )

        if ret_damage > 0:
            embed.add_field(
                name=f"Retaliatory Fire from {target.name}",
                value=f"💥 Returned fire dealing **{ret_damage} damage**!\nYour Hull: {attacker.current_hull}/{attacker.max_hull} HP ({attacker.condition.value})",
                inline=False
            )

        if target_sunk:
            embed.add_field(
                name="☠️ SHIP SUNK!",
                value=f"🌊 **{target.name}** has broken in two and plunged into the abyss! All remaining cargo is lost to the sea.",
                inline=False
            )
        if attacker_sunk:
            embed.add_field(
                name="☠️ YOUR SHIP SUNK!",
                value=f"🌊 **{attacker.name}** suffered fatal hull breaches and went under!",
                inline=False
            )

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Broadside failed: {str(e)}", ephemeral=True)


@ship_group.command(name="repair", description="Repair hull damage at a harbor shipyard.")
@app_commands.describe(
    hp_amount="Number of hull HP to restore (Cost: 2 gold per HP)",
    ship_id="Optional Ship ID. Defaults to your active command vessel."
)
async def ship_repair_command(interaction: discord.Interaction, hp_amount: int = 50, ship_id: str = None):
    char = await character_service.get_active_character_by_user(str(interaction.user.id))
    if not char:
        await interaction.response.send_message("❌ You have no active living character.", ephemeral=True)
        return

    ship = None
    if ship_id:
        ship = await ship_service.get_ship(ship_id)
    else:
        ships = await ship_service.get_ships_by_owner(char.character_id)
        if not ships and char.crew_id:
            ships = await ship_service.get_crew_ships(char.crew_id)
        if ships:
            ship = ships[0]

    if not ship:
        await interaction.response.send_message("❌ No vessel available to repair.", ephemeral=True)
        return

    try:
        rep = await ship_service.repair_ship(
            ship_id=ship.ship_id,
            character_id=char.character_id,
            hp_amount=hp_amount
        )
        embed = discord.Embed(
            title=f"🔨 Shipwright Repairs: {ship.name}",
            description=f"Shipwrights have caulked seams and replaced shattered hull timbers.\n\n"
                        f"• **Repaired:** +{rep['repaired_points']} HP\n"
                        f"• **Current Hull:** {rep['ship'].current_hull}/{rep['ship'].max_hull} HP\n"
                        f"• **Cost:** 🪙 {rep['total_cost']} gold",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Repair failed: {str(e)}", ephemeral=True)
