import discord
from discord import app_commands
from typing import Optional, List
import re
import time

from app.game.models.character import Faction
from app.services.character_service import character_service
from app.game.world.location import location_service
from app.game.world.time import world_time_service
from app.game.npcs.npc_models import WorldNPC, NPCFaction
from app.game.npcs.npc_encounter_service import npc_encounter_service, LocationAtmosphere, NPCApproach
from app.game.npcs.npc_interaction_service import npc_interaction_service, NPCInteractionResult
from app.services.logger import logger


# --- Living World UI & Multi-Turn Conversation Engine ---

def build_conversation_embed(npc: WorldNPC, res: NPCInteractionResult, player_action_label: str, clock_str: Optional[str] = None) -> discord.Embed:
    """Builds a constructive conversation embed showing player input, NPC response, and relationship state."""
    icon = "⚓" if npc.is_marine else ("🏴‍☠️" if npc.is_pirate else ("🛒" if npc.faction == NPCFaction.MERCHANT else "👤"))
    color = discord.Color.green() if res.trust_delta >= 0 else discord.Color.orange()

    embed = discord.Embed(
        title=f"{icon} Conversation with {res.npc_name}",
        description=(
            f"**You:** *\"{player_action_label}\"*\n\n"
            f"**{res.npc_name} ({res.npc_role}):**\n"
            f"{res.dialogue}"
        ),
        color=color
    )
    embed.add_field(name="Standing", value=f"**{res.relationship_standing}**", inline=True)
    if res.trust_delta or res.respect_delta:
        embed.add_field(name="Bond Shift", value=f"Trust: `{res.trust_delta:+d}` | Respect: `{res.respect_delta:+d}`", inline=True)
    if res.rewards_granted:
        embed.add_field(name="🎁 Outcomes", value="\n".join([f"• {r}" for r in res.rewards_granted]), inline=False)
    
    footer_text = f"🕒 In-Game Time: {clock_str}" if clock_str else ""
    if res.memory_logged:
        footer_text = f"{footer_text} • Memory: \"{res.memory_logged}\"" if footer_text else f"Memory preserved: \"{res.memory_logged}\""
    embed.set_footer(text=footer_text or "Type custom speech or choose an option below")
    return embed



class NPCSpeechModal(discord.ui.Modal):
    """Modal allowing the player to input custom freeform speech or action to the NPC."""
    def __init__(self, npc: WorldNPC, parent_view: Optional[discord.ui.View] = None):
        clean_name = re.sub(r'[^a-zA-Z0-9 ]', '', npc.name).strip()[:25] or "NPC"
        super().__init__(title=f"Speak with {clean_name}")
        self.npc = npc
        self.parent_view = parent_view

        self.speech_input = discord.ui.TextInput(
            label="What do you say or do?",
            placeholder="e.g. 'I'm looking for work on the docks.' or 'What's the word on the Marine cutter?'",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=300,
            custom_id="player_custom_speech_text"
        )
        self.add_item(self.speech_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        char = await character_service.get_active_character_by_user(user_id)
        if not char:
            await interaction.followup.send("No active living character.", ephemeral=True)
            return

        speech_text = self.speech_input.value.strip()

        try:
            res = await npc_interaction_service.interact(
                character_id=char.character_id,
                npc_id=self.npc.npc_id,
                action_type="CUSTOM_SPEECH",
                player_speech=speech_text
            )

            clock = await world_time_service.get_world_time()
            clock_str = world_time_service.format_clock(clock)
            embed = build_conversation_embed(self.npc, res, player_action_label=speech_text, clock_str=clock_str)
            new_view = NPCActionsView(self.npc)

            try:
                await interaction.edit_original_response(embed=embed, view=new_view)
            except Exception:
                await interaction.followup.send(embed=embed, view=new_view, ephemeral=True)
        except Exception as e:
            logger.error(f"Error submitting custom speech: {e}", exc_info=True)
            await interaction.followup.send(f"⚠️ Speech failed: {e}", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.error(f"Error in NPCSpeechModal: {error}", exc_info=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"⚠️ Dialogue error: {error}", ephemeral=True)
            else:
                await interaction.followup.send(f"⚠️ Dialogue error: {error}", ephemeral=True)
        except Exception:
            pass


class OpenSpeechModalButton(discord.ui.Button):
    """Button triggering the custom speech modal."""
    def __init__(self, npc: WorldNPC, row: int = 0):
        super().__init__(style=discord.ButtonStyle.primary, label="Say / Do Something", emoji="✍️", row=row)
        self.npc = npc

    async def callback(self, interaction: discord.Interaction):
        try:
            modal = NPCSpeechModal(npc=self.npc, parent_view=self.view)
            await interaction.response.send_modal(modal)
        except Exception as e:
            logger.error(f"Failed to open NPC speech modal: {e}", exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"⚠️ Could not open speech window: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"⚠️ Could not open speech window: {e}", ephemeral=True)
            except Exception:
                pass


class NPCOptionButton(discord.ui.Button):
    """Button triggering a preset action while keeping the conversation view active."""
    def __init__(self, npc: WorldNPC, action_type: str, label: str, emoji: str, style: discord.ButtonStyle, row: int = 0):
        super().__init__(style=style, label=label, emoji=emoji, row=row)
        self.npc = npc
        self.action_type = action_type
        self.button_label = label

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        char = await character_service.get_active_character_by_user(user_id)
        if not char:
            await interaction.followup.send("No active character.", ephemeral=True)
            return

        try:
            res = await npc_interaction_service.interact(
                character_id=char.character_id,
                npc_id=self.npc.npc_id,
                action_type=self.action_type
            )

            clock = await world_time_service.get_world_time()
            clock_str = world_time_service.format_clock(clock)
            embed = build_conversation_embed(self.npc, res, player_action_label=f"[{self.button_label}]", clock_str=clock_str)
            new_view = NPCActionsView(self.npc)
            try:
                await interaction.edit_original_response(embed=embed, view=new_view)
            except Exception:
                await interaction.followup.send(embed=embed, view=new_view, ephemeral=True)
        except Exception as e:
            logger.error(f"Error executing NPC option: {e}", exc_info=True)
            await interaction.followup.send(f"⚠️ Interaction failed: {e}", ephemeral=True)


class NPCLeaveButton(discord.ui.Button):
    """Gracefully steps away from the conversation."""
    def __init__(self, npc: WorldNPC, row: int = 2):
        super().__init__(style=discord.ButtonStyle.secondary, label="Step Away / Leave", emoji="👋", row=row)
        self.npc = npc

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"Farewell: {self.npc.name}",
            description=f"You nod to {self.npc.name} and step back into the district street.",
            color=discord.Color.dark_grey()
        )
        await interaction.response.edit_message(embed=embed, view=None)


class NPCActionsView(discord.ui.View):
    """View providing both custom natural-language input and persistent preset options."""
    def __init__(self, npc: WorldNPC):
        super().__init__(timeout=300)
        self.npc = npc

        # Row 0: Custom Speech & Rumors
        self.add_item(OpenSpeechModalButton(npc, row=0))
        self.add_item(NPCOptionButton(npc, "ASK_RUMORS", "Inquire for Rumors", "📜", discord.ButtonStyle.secondary, row=0))

        # Row 1: Work / Jobs & Recruitment
        self.add_item(NPCOptionButton(npc, "ASK_WORK", "Inquire for Work / Jobs", "💼", discord.ButtonStyle.secondary, row=1))
        self.add_item(NPCOptionButton(npc, "RECRUIT", "Recruit to Crew", "🤝", discord.ButtonStyle.success, row=1))

        # Row 2: Bribe & Leave
        self.add_item(NPCOptionButton(npc, "BRIBE_50", "Offer Bribe (50 Gold)", "💰", discord.ButtonStyle.secondary, row=2))
        self.add_item(NPCLeaveButton(npc, row=2))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.error(f"Error in NPCActionsView on item {item}: {error}", exc_info=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"⚠️ Interaction error: {error}", ephemeral=True)
            else:
                await interaction.followup.send(f"⚠️ Interaction error: {error}", ephemeral=True)
        except Exception:
            pass


class NPCSelectMenu(discord.ui.Select):
    """Dropdown menu allowing the player to select an NPC present in the district."""
    def __init__(self, npcs: List[WorldNPC]):
        options = []
        for npc in npcs[:25]:
            emoji = "⚓" if npc.is_marine else ("🏴‍☠️" if npc.is_pirate else ("🛒" if npc.faction == NPCFaction.MERCHANT else "👤"))
            desc = f"{npc.role_title} • {npc.current_activity[:50]}"
            options.append(discord.SelectOption(
                label=npc.name[:100],
                value=npc.npc_id,
                description=desc[:100],
                emoji=emoji
            ))
        super().__init__(
            placeholder="👥 Select someone to approach or interact with...",
            min_values=1,
            max_values=1,
            options=options
        )
        self._npc_map = {n.npc_id: n for n in npcs}

    async def callback(self, interaction: discord.Interaction):
        chosen_id = self.values[0]
        chosen_npc = self._npc_map.get(chosen_id)
        if not chosen_npc:
            await interaction.response.send_message("NPC not found.", ephemeral=True)
            return

        view = NPCActionsView(chosen_npc)
        icon = "⚓" if chosen_npc.is_marine else ("🏴‍☠️" if chosen_npc.is_pirate else ("🛒" if chosen_npc.faction == NPCFaction.MERCHANT else "👤"))
        embed = discord.Embed(
            title=f"{icon} Approached: {chosen_npc.name}",
            description=(
                f"**Role:** {chosen_npc.role_title}\n"
                f"**Current Action:** *{chosen_npc.current_activity}*\n"
                f"**Personality:** {', '.join(chosen_npc.personality)}\n"
                f"**Purse:** {chosen_npc.wealth} Gold\n\n"
                f"Choose how you wish to engage with them, or use **[✍️ Say / Do Something]** to speak naturally:"
            ),
            color=discord.Color.teal()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class NPCApproachButton(discord.ui.Button):
    """Button representing one of the direct reaction choices for an approaching NPC."""
    def __init__(self, npc: WorldNPC, action_label: str):
        super().__init__(style=discord.ButtonStyle.primary, label=action_label[:80], emoji="⚡")
        self.npc = npc
        self.action_label = action_label

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        char = await character_service.get_active_character_by_user(user_id)
        if not char:
            await interaction.followup.send("No active character.", ephemeral=True)
            return

        try:
            res = await npc_interaction_service.interact(
                character_id=char.character_id,
                npc_id=self.npc.npc_id,
                action_type=self.action_label,
                player_speech=self.action_label
            )

            # Continue the conversation by attaching the full NPCActionsView
            clock = await world_time_service.get_world_time()
            clock_str = world_time_service.format_clock(clock)
            view = NPCActionsView(self.npc)
            embed = build_conversation_embed(self.npc, res, player_action_label=self.action_label, clock_str=clock_str)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in approach callback: {e}", exc_info=True)
            await interaction.followup.send(f"⚠️ Action failed: {e}", ephemeral=True)


class TravelButton(discord.ui.Button):
    """Button triggering authoritative movement to an adjacent location."""
    def __init__(self, target_id: str, label: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=f"Go to: {label}", emoji="🚶", custom_id=f"travel_{target_id}")
        self.target_id = target_id

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        char = await character_service.get_active_character_by_user(user_id)
        if not char:
            await interaction.response.send_message("You do not have an active living character. Use `/start` first.", ephemeral=True)
            return

        try:
            dest = await character_service.move_character(char.character_id, self.target_id)
            embed, view = await build_living_location_display(
                location_id=dest.location_id,
                character_id=char.character_id,
                is_arrival=True
            )
            await interaction.response.edit_message(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Travel failed: {e}", exc_info=True)
            await interaction.response.send_message(f"Travel failed: {str(e)}", ephemeral=True)


class LivingLocationView(discord.ui.View):
    """View rendering living interactions: NPC dropdown, approach actions, and travel routes."""
    def __init__(self, atmosphere: LocationAtmosphere, current_location_id: str):
        super().__init__(timeout=180)

        # 1. NPC Select Menu (Row 0)
        if atmosphere.present_npcs:
            self.add_item(NPCSelectMenu(atmosphere.present_npcs))

        # 2. Approaching NPC Quick Action Buttons (Row 1)
        if atmosphere.approaching_npc:
            # Find the actual NPC object for approach buttons
            approaching_obj = next((n for n in atmosphere.present_npcs if n.npc_id == atmosphere.approaching_npc.npc_id), None)
            if approaching_obj:
                for act in atmosphere.approaching_npc.available_actions[:3]:
                    self.add_item(NPCApproachButton(
                        npc=approaching_obj,
                        action_label=act
                    ))

        # 3. Movement Destinations
        destinations = location_service.get_destinations(current_location_id)
        for dest in destinations:
            if not dest.is_sea_zone:
                self.add_item(TravelButton(target_id=dest.location_id, label=dest.name.split(" - ")[-1]))


async def build_living_location_display(location_id: str, character_id: str, is_arrival: bool = False):
    """Constructs the rich atmospheric embed and interactive view for a living location."""
    atmosphere = await npc_encounter_service.get_location_atmosphere(location_id, character_id)
    loc = location_service.get_location(location_id)
    clock = await world_time_service.get_world_time()
    clock_str = world_time_service.format_clock(clock)

    title_prefix = "⚓ Arrived at:" if is_arrival else "📍"
    embed = discord.Embed(
        title=f"{title_prefix} {loc.name if loc else location_id}",
        description=f"{loc.description if loc else ''}\n\n*{atmosphere.ambient_overview}*",
        color=discord.Color.green() if is_arrival else discord.Color.gold()
    )
    embed.add_field(name="Island", value=atmosphere.island, inline=True)
    embed.add_field(name="Security Rating", value=f"{'⭐' * atmosphere.security_level} (Level {atmosphere.security_level})", inline=True)
    embed.add_field(name="Facilities", value=", ".join(loc.facilities) if loc and loc.facilities else "None", inline=False)

    # In-Game Clock & Period
    period_info = world_time_service.get_period_info(clock)
    am_pm = "AM" if clock.hour < 12 else "PM"
    disp_hour = clock.hour % 12
    if disp_hour == 0:
        disp_hour = 12
    time_display = f"{disp_hour:02d}:{clock.minute:02d} {am_pm}"

    embed.add_field(
        name=f"🕒 In-Game Clock: Day {clock.day} • {time_display} ({period_info['icon']} {period_info['period']})",
        value=(
            f"**Weather:** `{clock.weather}` | **Tide:** `{clock.tide}`\n"
            f"*{period_info['atmosphere']}*\n"
            f"🧭 **Town Routine:** {period_info['npc_routine']}"
        ),
        inline=False
    )

    # 1. Active Scenes
    if atmosphere.active_scenes:
        scene_lines = []
        for s in atmosphere.active_scenes:
            scene_lines.append(f"• **{s.title}**\n  ↳ *{s.description}*")
        embed.add_field(name="🎭 Ongoing Scenes in this District", value="\n".join(scene_lines), inline=False)

    # 2. Present Living NPCs
    if atmosphere.present_npcs:
        npc_lines = []
        for n in atmosphere.present_npcs[:6]:
            icon = "⚓" if n.is_marine else ("🏴‍☠️" if n.is_pirate else ("🛒" if n.faction == NPCFaction.MERCHANT else "👤"))
            npc_lines.append(f"• {icon} **{n.name}** ({n.role_title}) — *{n.current_activity}*")
        if len(atmosphere.present_npcs) > 6:
            npc_lines.append(f"*...and {len(atmosphere.present_npcs) - 6} other townspeople.*")
        embed.add_field(name="👥 People Present Right Now", value="\n".join(npc_lines), inline=False)
    else:
        embed.add_field(name="👥 People Present", value="*The streets are momentarily deserted.*", inline=False)

    # 3. Dynamic NPC Approach Callout
    if atmosphere.approaching_npc:
        app = atmosphere.approaching_npc
        embed.add_field(
            name=f"⚡ {app.npc_name} ({app.npc_role}) approaches you!",
            value=f"{app.dialogue}\n*Use the reaction buttons below to respond immediately!*",
            inline=False
        )

    embed.set_footer(text=f"{clock_str} | Select an NPC below or choose an action to interact")
    view = LivingLocationView(atmosphere=atmosphere, current_location_id=location_id)
    return embed, view


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

        from app.game.director.director_service import game_director
        await game_director.initialize_player_world(char.character_id, char.location_id, char.faction.value)

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
                f"🌟 **The Living World is Active**: The port around you is alive with opportunities, mysteries, and persistent NPCs.\n"
                f"Type `/location` to see who is around you, or `/explore` to inspect your surroundings.\n\n"
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
    await interaction.response.defer(ephemeral=True)
    try:
        user_id = str(interaction.user.id)
        char = await character_service.get_active_character_by_user(user_id)

        if not char:
            await interaction.followup.send(
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

        from app.game.director.reputation_service import reputation_service
        reps = await reputation_service.get_all_reputations(char.character_id)
        rep_strings = []
        for f, v in reps.items():
            standing = reputation_service.get_reputation_title(v)
            rep_strings.append(f"• **{f}**: {standing} ({v:+d})")

        embed.add_field(name="⚖️ Reputations", value="\n".join(rep_strings) if rep_strings else "Neutral", inline=False)
        if char.long_term_ambition:
            embed.add_field(name="👑 Long-Term Ambition", value=char.long_term_ambition, inline=False)
        if char.behavioral_traits:
            traits_str = ", ".join([f"{k.capitalize()} ({v:+d})" for k, v in char.behavioral_traits.items()])
            embed.add_field(name="🎭 Behavioral Traits", value=traits_str or "None recorded yet.", inline=False)

        embed.set_footer(text="Authoritative State Record | Check /location to interact with the world around you")
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        logger.error(f"Error in profile_command: {e}", exc_info=True)
        await interaction.followup.send(f"⚠️ Error loading profile dossier: {e}", ephemeral=True)


@app_commands.command(name="inventory", description="Inspect your personal inventory and equipment.")
async def inventory_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        user_id = str(interaction.user.id)
        char = await character_service.get_active_character_by_user(user_id)

        if not char:
            await interaction.followup.send("No active living character found. Use `/start`.", ephemeral=True)
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

        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        logger.error(f"Error in inventory_command: {e}", exc_info=True)
        await interaction.followup.send(f"⚠️ Error loading inventory: {e}", ephemeral=True)


@app_commands.command(name="location", description="Inspect your current living surroundings, ongoing scenes, people present, and routes.")
async def location_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        user_id = str(interaction.user.id)
        char = await character_service.get_active_character_by_user(user_id)

        if not char:
            await interaction.followup.send("No active living character found. Use `/start`.", ephemeral=True)
            return

        embed, view = await build_living_location_display(
            location_id=char.location_id,
            character_id=char.character_id,
            is_arrival=False
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    except Exception as e:
        logger.error(f"Error in location_command: {e}", exc_info=True)
        await interaction.followup.send(f"⚠️ Error loading location: {e}", ephemeral=True)


@app_commands.command(name="time", description="Check the current in-game world clock, period of day, weather, tide, and routine phase.")
async def time_command(interaction: discord.Interaction):
    """Authoritative in-game world clock query."""
    await interaction.response.defer(ephemeral=False)
    try:
        clock = await world_time_service.get_world_time()
        period_info = world_time_service.get_period_info(clock)
        am_pm = "AM" if clock.hour < 12 else "PM"
        disp_hour = clock.hour % 12
        if disp_hour == 0:
            disp_hour = 12
        time_12h = f"{disp_hour:02d}:{clock.minute:02d} {am_pm}"
        time_24h = f"{clock.hour:02d}:{clock.minute:02d}"

        color = discord.Color.gold() if period_info["period"] in ["Morning", "Afternoon"] else discord.Color.dark_purple()
        embed = discord.Embed(
            title=f"🕒 In-Game World Clock — {period_info['icon']} {period_info['period']}",
            description=f"*{period_info['atmosphere']}*",
            color=color
        )
        embed.add_field(name="📅 In-Game Date", value=f"**Day {clock.day}**", inline=True)
        embed.add_field(name="⏰ Time of Day", value=f"**{time_12h}** (`{time_24h}`)", inline=True)
        embed.add_field(name="🌅 Period", value=f"{period_info['icon']} {period_info['period']}", inline=True)
        embed.add_field(name="⛅ Current Weather", value=f"`{clock.weather}`", inline=True)
        embed.add_field(name="🌊 Ocean Tide", value=f"`{clock.tide}`", inline=True)
        embed.add_field(name="🧭 District Routine Phase", value=period_info['npc_routine'], inline=False)
        embed.set_footer(text="World time advances deterministically via the simulation clock.")

        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"Error in time_command: {e}", exc_info=True)
        await interaction.followup.send(f"⚠️ Error loading in-game clock: {e}", ephemeral=True)


@app_commands.command(name="clock", description="Check the current in-game world clock, period of day, weather, and tides.")
async def clock_command(interaction: discord.Interaction):
    """Alias for /time."""
    await time_command.callback(interaction)

