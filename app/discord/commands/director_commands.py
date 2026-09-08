import discord
from discord import app_commands
from typing import Optional

from app.services.character_service import character_service
from app.game.director.director_service import game_director
from app.game.director.discovery_service import discovery_service
from app.game.director.opportunity_service import opportunity_engine
from app.game.director.thread_service import thread_service
from app.game.director.relationship_service import relationship_service
from app.game.director.goal_service import goal_service
from app.game.director.director_models import OpportunityUrgency, GoalTier


class DiscoveryChoiceButton(discord.ui.Button):
    """Button representing a contextual branch choice during exploration."""
    def __init__(self, discovery_id: str, choice_id: str, label: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=label[:80], custom_id=f"disc_{discovery_id}_{choice_id}")
        self.discovery_id = discovery_id
        self.choice_id = choice_id

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        char = await character_service.get_active_character_by_user(user_id)
        if not char:
            await interaction.response.send_message("No active living character.", ephemeral=True)
            return

        result = await discovery_service.resolve_discovery_action(
            character_id=char.character_id,
            discovery_id=self.discovery_id,
            choice_id=self.choice_id
        )

        embed = discord.Embed(
            title="🔍 Discovery Resolved",
            description=result["outcome_text"],
            color=discord.Color.green()
        )
        if result.get("rewards"):
            embed.add_field(name="Rewards Granted", value="\n".join([f"• {r.get('description')}" for r in result["rewards"]]), inline=False)
        if result.get("merged_thread"):
            embed.add_field(name="⚠️ Story Threads Merged!", value=f"Threads connected: {result['merged_thread']}", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


class DiscoveryActionView(discord.ui.View):
    """View rendering choices for a newly discovered world element."""
    def __init__(self, discovery_id: str, choices: list):
        super().__init__(timeout=180)
        for c in choices[:5]:
            self.add_item(DiscoveryChoiceButton(discovery_id=discovery_id, choice_id=c.choice_id, label=c.label))


# --- Command Handlers ---

@app_commands.command(name="home", description="View your personalized Player Home Screen — current threads, opportunities, and people.")
async def home_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active character. Use `/start` first.", ephemeral=True)
        return

    briefing = await game_director.get_player_briefing(char.character_id, char.location_id)

    embed = discord.Embed(
        title=f"📜 Living Chronicle: {briefing.character_name}",
        description=(
            f"**Location:** {briefing.location_name} | **Faction:** {briefing.faction}\n"
            f"**Ambition:** {char.long_term_ambition or 'Make a name on the high seas.'}\n"
        ),
        color=discord.Color.gold()
    )

    # 1. Opportunities
    if briefing.immediate_opportunities:
        opp_lines = []
        for o in briefing.immediate_opportunities[:3]:
            urgency_icon = "🔥" if o.urgency == OpportunityUrgency.URGENT else "⚡"
            opp_lines.append(f"{urgency_icon} **{o.title}** [{o.urgency.value}]\n↳ *{o.description}*")
        embed.add_field(name="🎯 Immediate Opportunities", value="\n".join(opp_lines), inline=False)

    # 2. Active Threads
    if briefing.active_threads:
        thread_lines = []
        for t in briefing.active_threads[:3]:
            lead = t.unknown_questions[0] if t.unknown_questions else t.summary
            thread_lines.append(f"**{t.title}**\n↳ *Lead:* {lead}")
        embed.add_field(name="🧵 Living Story Threads", value="\n".join(thread_lines), inline=False)

    # 3. People You Know
    if briefing.known_people:
        people_lines = []
        for p in briefing.known_people[:4]:
            favors = f" ({p.favors_owed_to_player} favors owed to you)" if p.favors_owed_to_player > 0 else ""
            people_lines.append(f"• **{p.npc_name}**: Standing: *{p.level.value}*{favors}")
        embed.add_field(name="👥 People You Know", value="\n".join(people_lines), inline=True)

    # 4. Reputation Standing
    rep_text = ", ".join([f"{k}: {v}" for k, v in list(briefing.reputation_summary.items())[:4]])
    embed.add_field(name="⚖️ Reputation Standing", value=rep_text or "Neutral", inline=True)

    if briefing.rumors:
        rumor_lines = [f"• *\"{r.description}\"*" for r in briefing.rumors[:2]]
        embed.add_field(name="👂 Rumors on the Docks", value="\n".join(rumor_lines), inline=False)

    if briefing.world_updates:
        embed.add_field(name="⚠️ Recent City Developments", value="\n".join([f"• {u}" for u in briefing.world_updates[:2]]), inline=False)

    embed.set_footer(text="Use /opportunities, /threads, /people, or /explore to interact with the world.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.command(name="opportunities", description="Inspect all immediate, discoverable, and rumor opportunities.")
async def opportunities_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active character. Use `/start` first.", ephemeral=True)
        return

    opps = await opportunity_engine.list_active_opportunities(char.character_id, char.location_id)
    if not opps:
        await interaction.response.send_message("The docks are quiet at this exact moment. Try `/explore`.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎯 Active Opportunities",
        description="The world presents possibilities. Choose your path or leave them to unfold naturally.",
        color=discord.Color.dark_purple()
    )

    for o in opps[:6]:
        urgency_badge = f"[{o.urgency.value}]" if o.urgency == OpportunityUrgency.URGENT else ""
        embed.add_field(
            name=f"{o.title} {urgency_badge} — {o.opportunity_type.value}",
            value=f"{o.description}\n*Missed Consequence:* {o.consequence_summary}",
            inline=False
        )

    embed.set_footer(text="Respond to opportunities using /act or speaking with related NPCs.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.command(name="threads", description="View active story threads, known facts, and mysterious leads.")
async def threads_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active character. Use `/start` first.", ephemeral=True)
        return

    threads = await thread_service.list_active_threads()
    if not threads:
        await interaction.response.send_message("You are not currently entangled in any active story threads.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🧵 Active Story Threads",
        description="Threads are living mysteries. As you investigate, distinct cases may collide and merge.",
        color=discord.Color.blue()
    )

    for t in threads[:5]:
        facts = "\n".join([f"  • {f}" for f in t.known_facts[-3:]]) if t.known_facts else "  • No confirmed facts yet."
        lead = t.unknown_questions[0] if t.unknown_questions else t.summary
        embed.add_field(
            name=f"📖 {t.title} [{t.status.value}]",
            value=f"**Lead:** {lead}\n**Known Facts:**\n{facts}",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.command(name="people", description="Inspect your relationships, trust, respect, and favors owed with key NPCs.")
async def people_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active character. Use `/start` first.", ephemeral=True)
        return

    people = await relationship_service.list_relationships(char.character_id)
    if not people:
        await interaction.response.send_message("You haven't made any lasting impressions on the people of this port yet.", ephemeral=True)
        return

    embed = discord.Embed(
        title="👥 People You Know",
        description="Your reputation is personal. People remember every betrayal, kindness, and debt.",
        color=discord.Color.teal()
    )

    for p in people[:6]:
        last_mem = f"\n*Recent memory:* \"{p.memories[-1].summary}\"" if p.memories else ""

        embed.add_field(
            name=f"{p.npc_name} — Standing: {p.level.value}",
            value=(
                f"Trust: {p.trust:+d} | Respect: {p.respect:+d} | Fear: {p.fear:+d} | Affection: {p.affection:+d}\n"
                f"Favors owed to you: **{p.favors_owed_to_player}**"
                f"{last_mem}"
            ),
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.command(name="explore", description="Explore your surroundings for hidden opportunities, suspects, and curiosities.")
async def explore_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active character. Use `/start` first.", ephemeral=True)
        return

    discovery = await discovery_service.explore_location(char.character_id, char.location_id)

    embed = discord.Embed(
        title=f"🔎 Contextual Discovery: {discovery.title}",
        description=discovery.description,
        color=discord.Color.dark_gold()
    )
    embed.add_field(name="Category", value=discovery.discovery_type.value.capitalize(), inline=True)

    if discovery.choices:
        view = DiscoveryActionView(discovery_id=discovery.discovery_id, choices=discovery.choices)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.command(name="goals", description="Review your current Short-Term, Medium-Term, and Long-Term Ambitions.")
async def goals_command(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active character. Use `/start` first.", ephemeral=True)
        return

    goals = await goal_service.list_goals(char.character_id)
    if not goals:
        await goal_service.seed_initial_player_goals(char.character_id, char.faction.value)
        goals = await goal_service.list_goals(char.character_id)

    embed = discord.Embed(
        title=f"🎯 Ambitions & Goals: {char.name}",
        description="Direction without railroads. Pursue these objectives or chart your own course.",
        color=discord.Color.gold()
    )

    for tier in [GoalTier.SHORT_TERM, GoalTier.MEDIUM_TERM, GoalTier.LONG_TERM]:
        tier_goals = [g for g in goals if g.tier == tier]
        if tier_goals:
            lines = [f"• **{g.title}**\n  ↳ {g.description}" for g in tier_goals]
            embed.add_field(name=f"🏆 {tier.value.upper()}", value="\n".join(lines), inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)
