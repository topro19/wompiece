import pytest
from app.game.models.character import Faction
from app.services.character_service import character_service
from app.game.investigations.case_service import investigation_service
from app.game.investigations.case_models import EvidenceType, CaseStatus


@pytest.mark.asyncio
async def test_case_creation_and_evidence_timeline(test_db):
    """Verify Marine case opening, evidence logging, and chronological timeline preservation."""
    marine = await character_service.create_character(
        user_id="marine_user_1",
        name="Lieutenant Vance",
        faction=Faction.MARINE
    )

    case = await investigation_service.open_case(
        assigned_marine_id=marine.character_id,
        title="Illicit Contraband at Azure Docks",
        location_id="port_azure_docks"
    )

    assert case.case_number >= 1000
    assert case.assigned_marine_name == "Lieutenant Vance"
    assert len(case.timeline) >= 1

    # Log documentary evidence
    ev1 = await investigation_service.add_evidence(
        case_id=case.case_id,
        evidence_type=EvidenceType.TRANSACTION_ANOMALY,
        title="Unmanifested Gold Transfer",
        description="A payment of 500 gold made to an unregistered offshore cargo sloop.",
        source="Port Azure Customs Ledger",
        location_id="port_azure_docks",
        discovered_by_id=marine.character_id
    )

    assert ev1.title == "Unmanifested Gold Transfer"
    reloaded_case = await investigation_service.get_case(case.case_id)
    assert ev1.evidence_id in reloaded_case.evidence_ids
    assert reloaded_case.status == CaseStatus.UNDER_INVESTIGATION


@pytest.mark.asyncio
async def test_marine_interrogation_and_testimony(test_db):
    """Verify player interrogation creates immutable transcript records and testimony evidence."""
    marine = await character_service.create_character(
        user_id="marine_user_2",
        name="Sergeant Cross",
        faction=Faction.MARINE
    )
    suspect = await character_service.create_character(
        user_id="pirate_user_2",
        name="One-Eyed Pete",
        faction=Faction.PIRATE
    )

    case = await investigation_service.open_case(
        assigned_marine_id=marine.character_id,
        title="Questioning of One-Eyed Pete",
        location_id="marine_headquarters"
    )

    record = await investigation_service.log_interrogation(
        case_id=case.case_id,
        marine_id=marine.character_id,
        marine_name=marine.name,
        subject_id=suspect.character_id,
        subject_name=suspect.name,
        dialogue_log=[
            {"speaker": marine.name, "text": "Who ordered the crates unloaded at midnight?"},
            {"speaker": suspect.name, "text": "I was only drinking ale at The Golden Anchor, sir."}
        ],
        summary="Suspect claims to have been drinking at The Golden Anchor during the smuggling run."
    )

    assert record.subject_name == "One-Eyed Pete"
    assert len(record.dialogue_log) == 2

    # Verify testimony evidence created
    reloaded_case = await investigation_service.get_case(case.case_id)
    assert len(reloaded_case.evidence_ids) >= 1


@pytest.mark.asyncio
async def test_ai_marine_head_warrant_evaluation(test_db):
    """Verify AI Marine Head evaluates evidence strictly against statutory law thresholds."""
    marine = await character_service.create_character(
        user_id="marine_user_3",
        name="Commander Sterling",
        faction=Faction.MARINE
    )

    case = await investigation_service.open_case(
        assigned_marine_id=marine.character_id,
        title="Smuggling at The Golden Anchor",
        location_id="port_azure_docks"
    )

    # 1. Petition WITHOUT evidence -> Expected: REQUEST_MORE_EVIDENCE
    warrant_empty = await investigation_service.request_warrant_review(
        case_id=case.case_id,
        requesting_marine_id=marine.character_id,
        target_id="the_golden_anchor",
        target_name="The Golden Anchor",
        statute_id="SMUGGLING",
        requested_action="SEARCH_WARRANT"
    )
    assert warrant_empty.status in ["REQUEST_MORE_EVIDENCE", "DENIED"]

    # 2. Add required evidence (smuggling contraband + financial ledger anomaly)
    await investigation_service.add_evidence(
        case_id=case.case_id,
        evidence_type=EvidenceType.CONTRABAND_SAMPLE,
        title="Crate of Smuggled Firearms",
        description="Unmarked naval muskets found hidden beneath barrels of salted fish.",
        source="Harbor Patrol Inspection",
        location_id="port_azure_docks",
        discovered_by_id=marine.character_id
    )
    await investigation_service.add_evidence(
        case_id=case.case_id,
        evidence_type=EvidenceType.TRANSACTION_ANOMALY,
        title="Smuggling Revenue Spike",
        description="Commercial revenue exceeded standard tavern customer intake by 400%.",
        source="Colonial Revenue Bureau",
        location_id="port_azure_docks",
        discovered_by_id=marine.character_id
    )

    # 3. Petition WITH evidence -> Expected: AUTHORIZED
    warrant_approved = await investigation_service.request_warrant_review(
        case_id=case.case_id,
        requesting_marine_id=marine.character_id,
        target_id="the_golden_anchor",
        target_name="The Golden Anchor",
        statute_id="SMUGGLING",
        requested_action="SEARCH_WARRANT"
    )
    assert warrant_approved.status == "AUTHORIZED"
    assert warrant_approved.ai_verdict["confidence"] > 0.7
