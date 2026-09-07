import discord
from discord import app_commands
from typing import Dict, Any


GUIDE_CHAPTERS: Dict[str, Dict[str, Any]] = {
    "overview": {
        "title": "🧭 Welcome to PIRATE WARS — Living World Guide",
        "description": (
            "**Pirate Wars** is a persistent multiplayer simulation world where real players and autonomous AI agents "
            "co-exist in a world of high-seas adventure, naval law, criminal enterprises, and political intrigue.\n\n"
            "Unlike simple RPG bots, Pirate Wars is governed by **Server-Authoritative Game State** and a **Deterministic Economic Ledger**. "
            "Google Gemini acts as an intelligent interpreter, reasoner, and narrator—it never arbitrarily invents state or cheats.\n\n"
            "Use the dropdown menu below to explore every system in depth!"
        ),
        "fields": [
            ("⚡ The 3 Golden Rules", (
                "1. **True One-Life Permadeath**: You have exactly 1 life. If you reach 0 HP or are executed, you die permanently.\n"
                "2. **Real Consequences**: Every transaction, crime, warrant, and broadside is permanently recorded.\n"
                "3. **Living Simulation**: AI agents (merchants, pirates, marines) have their own goals, schedules, and reactions."
            ), False),
            ("🚀 Getting Started", "Use `/start` to select your faction, name your character, and receive your starter kit.", False)
        ]
    },
    "lifecycle": {
        "title": "☠️ Player Lifecycle, Permadeath & Rebirth",
        "description": (
            "In Pirate Wars, death is permanent and final. There are no respawns or revives."
        ),
        "fields": [
            ("🛡️ One Living Character Invariant", "You can only have **one active living character** at any time. You cannot create a second character while your current one lives.", False),
            ("💀 The Graveyard & Legacy", (
                "When your health drops to 0 in combat or you face tribunal execution:\n"
                "• Your character is permanently marked `DEAD`.\n"
                "• An immutable `DeathRecord` is inscribed in the public Graveyard recording your killer, cause of death, and lifetime achievements.\n"
                "• If you had a Marine bounty, your killer receives it via the world treasury."
            ), False),
            ("🔄 Rebirth & Name Reclamation", (
                "• After death, you are immediately free to run `/start` again.\n"
                "• You can choose a completely new name, or **reclaim your previous name** if no other living player has claimed it.\n"
                "• All character names among living players are strictly unique."
            ), False),
            ("Commands", "`/start` — Create character\n`/profile` — View vitals, purse & rank\n`/inventory` — View gear & items\n`/location` — View surroundings & travel", False)
        ]
    },
    "ships": {
        "title": "⛵ Ships, Ocean Navigation & Naval Warfare",
        "description": (
            "Vessels allow you to traverse open sea zones (`azure_sea_lane`) to reach foreign islands like Isla de la Muerte and Verdant Atoll."
        ),
        "fields": [
            ("🚢 Ship Classes", (
                "• **Swift Sloop** (500g): 100 HP, 4 Cannons, 12 kts, 50 cargo. Fast & agile scout.\n"
                "• **Merchant Caravel** (1,500g): 220 HP, 10 Cannons, 10 kts, 160 cargo. Heavy trading hold.\n"
                "• **Heavy Frigate** (4,000g): 400 HP, 24 Cannons, 8 kts, 350 cargo. Navy warship.\n"
                "• **War Galleon** (10,000g): 750 HP, 44 Cannons, 6 kts, 800 cargo. Floating fortress."
            ), False),
            ("💥 Broadside Cannon Battles", (
                "When vessels clash in the same sea zone or harbor (`/ship attack`):\n"
                "• Each cannon rolls hit chance based on ship maneuverability.\n"
                "• Armor absorbs incoming damage. Critical powder magazine explosions deal 1.5× damage!\n"
                "• Vessels reaching 0 HP **sink permanently**, consigning all loaded cargo to the depths."
            ), False),
            ("🛠️ Harbor Repairs & Cargo", "Repair hull damage for 2 gold/HP at shipyards (`/ship repair`). Transfer goods between your inventory and hold (`/ship cargo`).", False),
            ("Commands", "`/ship buy` — Commission vessel\n`/ship info` — Inspect hull & cannons\n`/ship sail` — Navigate sea routes\n`/ship attack` — Fire broadsides\n`/ship repair` — Drydock repairs", False)
        ]
    },
    "crews": {
        "title": "🏴‍☠️ Pirate Crews, Politics & Mutinies",
        "description": "Band together with other players and autonomous AI crewmates under a pirate banner.",
        "fields": [
            ("⚓ Mixed Crews & Roles", "Crews feature real captains, navigators, gunners, and AI deckhands. Captains control the shared treasury and commission crew flagships.", False),
            ("🔥 Deterministic Mutiny Risk", (
                "Every crew has a dynamic **Mutiny Risk** rating based on:\n"
                "`Risk = (Avg Dissatisfaction × 1.2) + (100 - Avg Loyalty) × 0.5 - (Captain Authority × 0.4)`\n"
                "• If mutiny risk exceeds **75%**, a crew mutiny breaks out, stripping the captain of command!"
            ), False),
            ("💰 Treasury Ledger", "Crew gold is managed in an atomic sub-ledger. Members can deposit gold (`/crew deposit`) to fund expeditions and fleet purchases.", False),
            ("Commands", "`/crew info` — Inspect crew roster & morale\n`/crew join` — Enlist in a crew\n`/crew leave` — Abandon your crew\n`/crew deposit` — Donate gold to the treasury", False)
        ]
    },
    "businesses": {
        "title": "💼 Commercial Fronts, Smuggling & Forged Aliases",
        "description": "Run legitimate businesses or use them as fronts for high-profit black market smuggling.",
        "fields": [
            ("🏬 Business Ownership", "Operate taverns, warehouses, or trading posts. Run daily legal commerce (`/business operate`) for steady income and zero suspicion.", False),
            ("🎭 Forged Aliases & Shell Ownership", (
                "Criminals and pirates can forge civilian identities (`/alias forge`):\n"
                "• Register businesses under your fake identity so your real name never appears on government registries.\n"
                "• Beware: investigators can uncover paper trails and forge evidence if you get sloppy!"
            ), False),
            ("📦 Smuggling & Financial Anomalies", (
                "Smuggle contraband (`/business smuggle`) for huge profits.\n"
                "⚠️ High revenue spikes create **financial anomalies** that trigger Marine audits and inspections."
            ), False),
            ("Commands", "`/business info` — Inspect business revenue & suspicion\n`/business operate` — Legal daily trade\n`/business smuggle` — Illegal contraband run\n`/alias forge` — Create fake identity\n`/alias list` — View active forged papers", False)
        ]
    },
    "marines": {
        "title": "⚖️ Marine Justice, Evidence & AI Warrants",
        "description": "Join the 16th Marine Division to enforce maritime law, investigate cases, and arrest outlaws.",
        "fields": [
            ("📜 Statutory Laws", "The world enforces legal penal codes: Smuggling, Illegal Gambling, Falsified Identity, Bribery, Piracy, and Murder.", False),
            ("🔎 Evidence Dossier", "Detectives log physical contraband, financial anomalies, interrogation transcripts, and surveillance logs in case dockets.", False),
            ("🤖 AI Marine Commander Warrants", (
                "Submit warrant applications (`/case warrant`). Google Gemini acts as the Marine Commander:\n"
                "• Evaluates evidence against statutory legal standards.\n"
                "• Formally **APPROVES** or **DENIES** search and arrest warrants with legal reasoning."
            ), False),
            ("🤝 Bribery & Sting Operations", (
                "Suspects can attempt to bribe officers (`/bribe`).\n"
                "Marines can accept bribes, reject them, or launch **undercover sting operations** (*Operation Black Anchor*) with Internal Affairs."
            ), False),
            ("Commands", "`/case open` — Open docket\n`/case view` — View case dossier\n`/case evidence` — Log evidence\n`/case interrogate` — Question suspects\n`/case warrant` — Apply for search/arrest warrant\n`/bribe` — Attempt bribery or sting", False)
        ]
    },
    "combat": {
        "title": "⚔️ Combat, Weapons & Wanted Escalation",
        "description": "Engage in server-authoritative combat where every strike has life-or-death consequences.",
        "fields": [
            ("🗡️ Weaponry & Damage Invariants", (
                "• Cutlasses, Sabres, and Daggers inflict deterministic damage.\n"
                "• Armor reduces incoming blows.\n"
                "• 15% chance for critical strikes dealing 1.5× damage.\n"
                "• **Lethal Blows**: Reducing a target to 0 HP immediately triggers irreversible **Permadeath**."
            ), False),
            ("⭐ Wanted Level Escalation", (
                "Attacking or killing players increases your Marine Wanted Level (Levels 1–6+):\n"
                "• Level 1–2: Port sentry suspicion.\n"
                "• Level 3–5: Active arrest warrants and bounty hunters.\n"
                "• Level 6+: Marine Task Force **'Iron Tide'** is dispatched to hunt you down!"
            ), False),
            ("Commands", "`/combat attack <target>` — Attack another player in your current location", False)
        ]
    },
    "actions": {
        "title": "🤖 Freeform Actions (/act) & AI Context Engine",
        "description": "Perform any creative action not covered by predefined commands!",
        "fields": [
            ("💡 What is /act?", (
                "You can type `/act <freeform description>` (e.g. `'/act sneak through the warehouse window and pocket the ledger'`).\n"
                "The engine builds a strict, bounded context snapshot (location security, your inventory, active cases) and sends it to Google Gemini."
            ), False),
            ("🔒 Security & Prompt-Injection Defense", (
                "The AI is strictly an interpreter and reasoner. It proposes state changes through validated Pydantic schemas. "
                "Player input is quarantined within `<untrusted_player_action>` blocks—the AI can never invent gold or teleport state directly."
            ), False),
            ("Commands", "`/act <your action>` — Execute creative, contextual maneuvers", False)
        ]
    },
    "gambling": {
        "title": "🎲 Tavern Gambling & Dice",
        "description": "Step into The Crimson Parrot or The Black Skull Tavern to risk your doubloons at the tables.",
        "fields": [
            ("🎲 High-Low Dice (2d6)", (
                "Wager gold on the roll of two six-sided dice (`/gamble dice`):\n"
                "• **LOW (2–6)**: Pays 1:1.\n"
                "• **HIGH (8–12)**: Pays 1:1.\n"
                "• **SEVEN (7)**: The house hard roll! Pays 4:1."
            ), False),
            ("🕵️ Loaded Dice & House Security", "Attempting to use rigged dice carries high risk. If caught by tavern bouncers, your wager is confiscated and suspicion spikes.", False),
            ("Commands", "`/gamble dice <choice> <wager_amount>` — Bet at the dice table", False)
        ]
    },
    "cheatsheet": {
        "title": "📋 Complete Commands Quick-Reference",
        "description": "A quick reference of all 15 slash command groups available in Pirate Wars.",
        "fields": [
            ("👤 Player & World", "`/start` • `/profile` • `/inventory` • `/location` • `/status`", False),
            ("🏴‍☠️ Crews & Fleet", "`/crew info` • `/crew join` • `/crew leave` • `/crew deposit`\n`/ship buy` • `/ship info` • `/ship sail` • `/ship attack` • `/ship repair`", False),
            ("💰 Trade & Crime", "`/business info` • `/business operate` • `/business smuggle`\n`/alias forge` • `/alias list` • `/gamble dice`", False),
            ("⚖️ Law Enforcement", "`/case open` • `/case view` • `/case evidence` • `/case interrogate` • `/case warrant`", False),
            ("⚔️ Action & Combat", "`/act <action>` • `/combat attack <target>` • `/bribe <officer> <amount>`", False),
            ("⚙️ Admin & Simulation", "`/admin simulate_tick` • `/admin advance_time` • `/admin spawn_npc` • `/admin inspect_character` • `/admin list_ships`", False)
        ]
    }
}


class GuideSelect(discord.ui.Select):
    """Dropdown menu for selecting guide chapters."""

    def __init__(self):
        options = [
            discord.SelectOption(label="1. Overview & Golden Rules", value="overview", emoji="🧭", description="The core living simulation concept"),
            discord.SelectOption(label="2. Permadeath & Rebirth", value="lifecycle", emoji="☠️", description="One-life system, graveyard, and name reclamation"),
            discord.SelectOption(label="3. Ships & Naval Battles", value="ships", emoji="⛵", description="Ship classes, broadsides, and ocean sailing"),
            discord.SelectOption(label="4. Crews & Mutinies", value="crews", emoji="🏴‍☠️", description="Pirate crews, officer roles, and mutiny risk"),
            discord.SelectOption(label="5. Businesses & Aliases", value="businesses", emoji="💼", description="Fronts, shell companies, and smuggling"),
            discord.SelectOption(label="6. Marine Justice & Warrants", value="marines", emoji="⚖️", description="Detective cases, evidence, and AI warrants"),
            discord.SelectOption(label="7. Combat & Wanted Levels", value="combat", emoji="⚔️", description="Lethal combat, armor, and Task Force Iron Tide"),
            discord.SelectOption(label="8. Freeform Actions (/act)", value="actions", emoji="🤖", description="How Google Gemini interprets creative player moves"),
            discord.SelectOption(label="9. Tavern Gambling & Dice", value="gambling", emoji="🎲", description="High-Low dice wagering and loaded dice rules"),
            discord.SelectOption(label="10. Commands Cheat-Sheet", value="cheatsheet", emoji="📋", description="Complete directory of all 15 command groups")
        ]
        super().__init__(placeholder="📖 Select a guide topic to read...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_key = self.values[0]
        chapter = GUIDE_CHAPTERS.get(selected_key, GUIDE_CHAPTERS["overview"])

        embed = discord.Embed(
            title=chapter["title"],
            description=chapter["description"],
            color=discord.Color.gold()
        )
        for name, value, inline in chapter["fields"]:
            embed.add_field(name=name, value=value, inline=inline)

        embed.set_footer(text="Ginto's Pirate Wars Field Manual • Select another chapter below")
        await interaction.response.edit_message(embed=embed, view=self.view)


class GuideView(discord.ui.View):
    """Interactive container for the guide dropdown."""

    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(GuideSelect())


def build_initial_guide_embed() -> discord.Embed:
    chapter = GUIDE_CHAPTERS["overview"]
    embed = discord.Embed(
        title=chapter["title"],
        description=chapter["description"],
        color=discord.Color.gold()
    )
    for name, value, inline in chapter["fields"]:
        embed.add_field(name=name, value=value, inline=inline)
    embed.set_footer(text="Ginto's Pirate Wars Field Manual • Use the dropdown below to explore chapters")
    return embed


# --- Slash Commands ---

@app_commands.command(name="ginto", description="Open Ginto's Master Guidebook to the Pirate Wars persistent world.")
async def ginto_command(interaction: discord.Interaction):
    """Displays the master interactive player guide."""
    embed = build_initial_guide_embed()
    view = GuideView()
    await interaction.response.send_message(embed=embed, view=view)


@app_commands.command(name="help", description="Detailed player guide and system directory for Pirate Wars.")
async def help_command(interaction: discord.Interaction):
    """Alias for /ginto."""
    embed = build_initial_guide_embed()
    view = GuideView()
    await interaction.response.send_message(embed=embed, view=view)
