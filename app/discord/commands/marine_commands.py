import discord
from discord import app_commands
from typing import Optional
from app.services.character_service import character_service
from app.game.models.character import Faction
from app.game.investigations.case_service import investigation_service
from app.game.investigations.case_models import EvidenceType
from app.game.actions.action_engine import action_engine


class CaseGroup(app_commands.Group):
    """Commands for Marine detective work, evidence management, and warrant petitions."""
    def __init__(self):
        super().__init__(name="case", description="Marine detective case management and evidence tracking.")


case_group = CaseGroup()


@case_group.command(name="open", description="Open an official Marine criminal investigation docket.")
@app_commands.describe(
    title="Case title (e.g. 'Smuggling ring at The Golden Anchor')",
    location_id="Location of investigation (e.g. 'port_azure_docks')"
)
async def case_open_command(interaction: discord.Interaction, title: str, location_id: str = "port_azure_docks"):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active living character found.", ephemeral=True)
        return

    if char.faction != Faction.MARINE:
        await interaction.response.send_message("Only commissioned Marine officers can open official cases.", ephemeral=True)
        return

    try:
        case = await investigation_service.open_case(
            assigned_marine_id=char.character_id,
            title=title,
            location_id=location_id
        )
        embed = discord.Embed(
            title=f"⚖️ CASE #{case.case_number} OPENED",
            description=f"**Title:** {case.title}\n**Jurisdiction:** `{case.location_id}`\n**Lead Investigator:** {case.assigned_marine_name}",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Naval Intelligence Docket System")
        await interaction.response.send_message(embed=embed, ephemeral=False)
    except Exception as e:
        await interaction.response.send_message(f"Failed to open case: {str(e)}", ephemeral=True)


@case_group.command(name="view", description="Inspect the full dossier, evidence list, and timeline of an active case.")
@app_commands.describe(case_number="The numerical case ID (e.g. 1001)")
async def case_view_command(interaction: discord.Interaction, case_number: int):
    case = await investigation_service.get_case_by_number(case_number)
    if not case:
        await interaction.response.send_message(f"Case #{case_number} not found.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"📂 CASE #{case.case_number}: {case.title}",
        description=f"Status: `{case.status.value}` | Priority: `{case.priority}`\nLead Investigator: **{case.assigned_marine_name}**",
        color=discord.Color.dark_blue()
    )

    embed.add_field(name="Location", value=case.location_id, inline=True)
    embed.add_field(name="Logged Evidence Count", value=str(len(case.evidence_ids)), inline=True)
    embed.add_field(name="Pending/Active Warrants", value=str(len(case.warrant_ids)), inline=True)

    # Timeline excerpt
    timeline_str = "\n".join(case.timeline[-6:]) if case.timeline else "No events recorded."
    embed.add_field(name="Recent Timeline", value=timeline_str, inline=False)
    embed.set_footer(text="Marine Restricted Clearance")

    await interaction.response.send_message(embed=embed, ephemeral=True)


@case_group.command(name="evidence", description="Log physical, documentary, or observational evidence into a case file.")
@app_commands.describe(
    case_number="The target case number",
    evidence_type="Type of evidence discovered",
    title="Brief title of the evidence",
    description="Detailed description of the clue"
)
@app_commands.choices(evidence_type=[
    app_commands.Choice(name="Document / Ledger Discrepancy", value="DOCUMENT"),
    app_commands.Choice(name="Visual Observation / Surveillance", value="OBSERVATION"),
    app_commands.Choice(name="Contraband Sample", value="CONTRABAND_SAMPLE"),
    app_commands.Choice(name="Financial Ledger Anomaly", value="TRANSACTION_ANOMALY"),
    app_commands.Choice(name="Identity Match / Alias Link", value="IDENTITY_MATCH")
])
async def case_evidence_command(
    interaction: discord.Interaction,
    case_number: int,
    evidence_type: app_commands.Choice[str],
    title: str,
    description: str
):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char or char.faction != Faction.MARINE:
        await interaction.response.send_message("Only authorized Marines can log case evidence.", ephemeral=True)
        return

    case = await investigation_service.get_case_by_number(case_number)
    if not case:
        await interaction.response.send_message(f"Case #{case_number} not found.", ephemeral=True)
        return

    try:
        ev = await investigation_service.add_evidence(
            case_id=case.case_id,
            evidence_type=EvidenceType(evidence_type.value),
            title=title,
            description=description,
            source=f"Investigator {char.name}",
            location_id=char.location_id,
            discovered_by_id=char.character_id
        )
        embed = discord.Embed(
            title=f"🔍 Evidence Attached to Case #{case.case_number}",
            description=f"**[{ev.evidence_type.value}]** {ev.title}\n{ev.description}",
            color=discord.Color.teal()
        )
        embed.set_footer(text=f"Logged into chain of custody by {char.name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to log evidence: {str(e)}", ephemeral=True)


@case_group.command(name="interrogate", description="Question a suspect or witness and log the official transcript as testimony.")
@app_commands.describe(
    case_number="Active case number",
    subject_name="Name of person being questioned",
    dialogue="The questions and answers exchanged"
)
async def case_interrogate_command(
    interaction: discord.Interaction,
    case_number: int,
    subject_name: str,
    dialogue: str
):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char or char.faction != Faction.MARINE:
        await interaction.response.send_message("Only Marines have interrogation authority.", ephemeral=True)
        return

    case = await investigation_service.get_case_by_number(case_number)
    if not case:
        await interaction.response.send_message(f"Case #{case_number} not found.", ephemeral=True)
        return

    try:
        rec = await investigation_service.log_interrogation(
            case_id=case.case_id,
            marine_id=char.character_id,
            marine_name=char.name,
            subject_id=subject_name.lower().replace(" ", "_"),
            subject_name=subject_name,
            dialogue_log=[{"speaker": char.name, "text": dialogue}],
            summary=f"Official statement provided during investigation of Case #{case.case_number}."
        )
        embed = discord.Embed(
            title=f"🎙️ Interrogation Transcript Filed: {subject_name}",
            description=f"**Case:** #{case.case_number}\n**Interrogator:** {char.name}\n\n**Record:**\n*{dialogue}*",
            color=discord.Color.dark_purple()
        )
        embed.set_footer(text="Converted to sworn testimony evidence.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Interrogation logging failed: {str(e)}", ephemeral=True)


@case_group.command(name="warrant", description="Petition the AI Marine Head to review case evidence and issue a search or raid warrant.")
@app_commands.describe(
    case_number="Active case number",
    target_name="The suspect or establishment to be searched/raided",
    statute_id="The statutory violation cited",
    action="The specific legal action requested"
)
@app_commands.choices(
    statute_id=[
        app_commands.Choice(name="Anti-Smuggling Act Sec. 14", value="SMUGGLING"),
        app_commands.Choice(name="Gaming Regulation Ordinance Sec. 4", value="ILLEGAL_GAMBLING"),
        app_commands.Choice(name="Imperial Registry Fraud Statute Sec. 22", value="FALSIFIED_IDENTITY"),
        app_commands.Choice(name="Maritime Security (Piracy) Sec. 1", value="PIRACY")
    ],
    action=[
        app_commands.Choice(name="Search Warrant (Inspect premises & ledger)", value="SEARCH_WARRANT"),
        app_commands.Choice(name="Raid Warrant (Armed naval seizure)", value="RAID_WARRANT"),
        app_commands.Choice(name="Detention (Holding cell custody)", value="DETENTION")
    ]
)
async def case_warrant_command(
    interaction: discord.Interaction,
    case_number: int,
    target_name: str,
    statute_id: app_commands.Choice[str],
    action: app_commands.Choice[str]
):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char or char.faction != Faction.MARINE:
        await interaction.response.send_message("Only Marines can petition for warrants.", ephemeral=True)
        return

    case = await investigation_service.get_case_by_number(case_number)
    if not case:
        await interaction.response.send_message(f"Case #{case_number} not found.", ephemeral=True)
        return

    # Defer response as AI evaluation is being run
    await interaction.response.defer(ephemeral=False)

    try:
        warrant = await investigation_service.request_warrant_review(
            case_id=case.case_id,
            requesting_marine_id=char.character_id,
            target_id=target_name.lower().replace(" ", "_"),
            target_name=target_name,
            statute_id=statute_id.value,
            requested_action=action.value
        )

        verdict = warrant.ai_verdict or {}
        decision = warrant.status
        is_authorized = decision == "AUTHORIZED"

        embed = discord.Embed(
            title=f"⚖️ AI Marine Head Verdict: Warrant Petition for {target_name}",
            description=(
                f"**Reviewing Authority:** {warrant.reviewed_by}\n"
                f"**Statute Cited:** {statute_id.name}\n"
                f"**Requested Action:** `{warrant.requested_action}`\n\n"
                f"**DECISION:** {'🟢 AUTHORIZED' if is_authorized else ('🔴 DENIED' if decision == 'DENIED' else '🟡 REQUEST MORE EVIDENCE')}\n"
                f"**Legal Rationale:** {verdict.get('reason', 'N/A')}\n"
            ),
            color=discord.Color.green() if is_authorized else discord.Color.red()
        )

        if verdict.get("required_evidence"):
            embed.add_field(
                name="Missing Required Elements",
                value="\n".join(f"• {req}" for req in verdict["required_evidence"]),
                inline=False
            )

        embed.set_footer(text=f"Warrant ID: {warrant.warrant_id[:8]}")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"Warrant evaluation failed: {str(e)}")


@app_commands.command(name="act", description="Describe a freeform contextual action or attempt in natural language.")
@app_commands.describe(action_description="Describe what your character attempts to do")
async def freeform_action_command(interaction: discord.Interaction, action_description: str):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active living character found. Use `/start`.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    try:
        res = await action_engine.resolve_freeform_action(
            character_id=char.character_id,
            untrusted_action_text=action_description
        )

        outcome_color = discord.Color.green() if res["success"] else discord.Color.red()
        embed = discord.Embed(
            title=f"⚔️ Action Resolution: {char.name}",
            description=f"**Attempted:** *\"{action_description}\"*\n\n**Outcome:** `{res['outcome']}`\n\n{res['narrative']}",
            color=outcome_color
        )

        if res.get("state_deltas"):
            details = [f"• **{k.replace('_', ' ').title()}:** {v}" for k, v in res["state_deltas"].items()]
            embed.add_field(name="Consequences & State Mutations", value="\n".join(details), inline=False)

        embed.set_footer(text="Deterministic Rule Engine & Gemini Evaluation")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"Action failed to resolve: {str(e)}")


@app_commands.command(name="bribe", description="Attempt to secretly bribe a Marine officer. (Ephemeral & Discreet)")
@app_commands.describe(
    marine_name="Name of the Marine officer",
    amount="Amount of gold to offer",
    reason="What favor or silence you are requesting"
)
async def bribe_command(interaction: discord.Interaction, marine_name: str, amount: int, reason: str):
    user_id = str(interaction.user.id)
    char = await character_service.get_active_character_by_user(user_id)
    if not char:
        await interaction.response.send_message("No active character found.", ephemeral=True)
        return

    if char.wealth < amount:
        await interaction.response.send_message("Insufficient funds to offer this bribe.", ephemeral=True)
        return

    from app.database.connection import db_manager
    from app.game.investigations.corruption_service import corruption_service

    db = db_manager.db
    target_marine = await db.characters.find_one({
        "name": {"$regex": f"^{marine_name.strip()}$", "$options": "i"},
        "faction": Faction.MARINE.value,
        "status": "ALIVE"
    })
    if not target_marine:
        await interaction.response.send_message(f"Marine officer '{marine_name}' not found.", ephemeral=True)
        return

    try:
        res = await corruption_service.attempt_bribe(
            briber_character_id=char.character_id,
            target_marine_id=target_marine["_id"],
            amount=amount,
            reason=reason
        )

        embed = discord.Embed(
            title="🤫 Clandestine Transaction",
            description=f"You passed **{amount} Gold** to {target_marine['name']}.\n\n*{res['message']}*",
            color=discord.Color.dark_magenta()
        )
        embed.set_footer(text="Private & Ephemeral (Never leaked to public chat)")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Bribe failed: {str(e)}", ephemeral=True)
