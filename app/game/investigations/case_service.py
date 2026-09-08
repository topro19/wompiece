import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.database.connection import db_manager
from app.game.investigations.case_models import MarineCase, CaseStatus, Evidence, EvidenceType, InterrogationRecord, Warrant
from app.game.laws.laws_registry import laws_service
from app.ai.providers.gemini_provider import gemini_provider
from app.ai.schemas.marine_schemas import MarineHeadDecision
from app.game.events.event_bus import event_bus, WorldEvent
from app.game.events.event_types import EventType, EventVisibility
from app.config.settings import settings
from app.services.logger import logger


class InvestigationService:
    """Service governing criminal investigations, evidence custody, interrogations, and AI Marine Head warrants."""

    async def get_case(self, case_id: str) -> Optional[MarineCase]:
        db = db_manager.db
        doc = await db.cases.find_one({"_id": case_id})
        return MarineCase(**doc) if doc else None

    async def get_case_by_number(self, case_number: int) -> Optional[MarineCase]:
        db = db_manager.db
        doc = await db.cases.find_one({"case_number": case_number})
        return MarineCase(**doc) if doc else None

    async def open_case(
        self,
        assigned_marine_id: str,
        title: str,
        location_id: str,
        suspect_ids: Optional[List[str]] = None,
        suspect_names: Optional[List[str]] = None
    ) -> MarineCase:
        db = db_manager.db

        marine_doc = await db.characters.find_one({"_id": assigned_marine_id})
        marine_name = marine_doc.get("name", "Marine Investigator") if marine_doc else "Marine Investigator"

        # Auto-increment case number
        count = await db.cases.count_documents({})
        case_number = 1000 + count + 1

        now_str = datetime.now(timezone.utc).strftime("%H:%M")

        case = MarineCase(
            case_number=case_number,
            title=title.strip(),
            location_id=location_id,
            assigned_marine_id=assigned_marine_id,
            assigned_marine_name=marine_name,
            suspect_ids=suspect_ids or [],
            suspect_names=suspect_names or [],
            timeline=[f"{now_str} — Case opened by {marine_name} at {location_id}."]
        )

        await db.cases.insert_one(case.to_mongo())

        await event_bus.publish(WorldEvent(
            event_type=EventType.CASE_OPENED,
            actor_id=assigned_marine_id,
            location_id=location_id,
            visibility=EventVisibility.CASE_RESTRICTED,
            state_delta={
                "case_id": case.case_id,
                "case_number": case.case_number,
                "title": case.title
            },
            related_case_id=case.case_id
        ))

        logger.info(f"Opened CASE #{case.case_number} '{case.title}' assigned to {marine_name}.")
        return case

    async def add_evidence(
        self,
        case_id: str,
        evidence_type: EvidenceType,
        title: str,
        description: str,
        source: str,
        location_id: str,
        discovered_by_id: str,
        reliability: int = 85
    ) -> Evidence:
        db = db_manager.db
        case = await self.get_case(case_id)
        if not case:
            raise ValueError(f"Case {case_id} not found.")

        evidence = Evidence(
            case_id=case_id,
            evidence_type=evidence_type,
            title=title.strip(),
            description=description.strip(),
            source=source.strip(),
            location_id=location_id,
            discovered_by_id=discovered_by_id,
            reliability=reliability
        )

        await db.evidence.insert_one(evidence.to_mongo())

        now_str = datetime.now(timezone.utc).strftime("%H:%M")
        timeline_entry = f"{now_str} — Evidence logged: {evidence.title} ({evidence.evidence_type.value})."

        await db.cases.update_one(
            {"_id": case_id},
            {
                "$push": {
                    "evidence_ids": evidence.evidence_id,
                    "timeline": timeline_entry
                },
                "$set": {"status": CaseStatus.UNDER_INVESTIGATION.value}
            }
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.EVIDENCE_DISCOVERED,
            actor_id=discovered_by_id,
            location_id=location_id,
            visibility=EventVisibility.CASE_RESTRICTED,
            state_delta={
                "evidence_id": evidence.evidence_id,
                "title": evidence.title,
                "type": evidence.evidence_type.value
            },
            related_case_id=case_id
        ))

        logger.info(f"Logged evidence '{evidence.title}' to Case #{case.case_number}.")
        return evidence

    async def log_interrogation(
        self,
        case_id: str,
        marine_id: str,
        marine_name: str,
        subject_id: str,
        subject_name: str,
        dialogue_log: List[Dict[str, str]],
        summary: str
    ) -> InterrogationRecord:
        db = db_manager.db
        case = await self.get_case(case_id)
        if not case:
            raise ValueError(f"Case {case_id} not found.")

        record = InterrogationRecord(
            case_id=case_id,
            marine_id=marine_id,
            marine_name=marine_name,
            subject_id=subject_id,
            subject_name=subject_name,
            dialogue_log=dialogue_log,
            summary=summary
        )
        await db.interrogations.insert_one(record.to_mongo())

        # Automatically create Testimony evidence piece
        await self.add_evidence(
            case_id=case_id,
            evidence_type=EvidenceType.TESTIMONY,
            title=f"Interrogation Testimony: {subject_name}",
            description=summary,
            source=subject_name,
            location_id=case.location_id,
            discovered_by_id=marine_id
        )

        now_str = datetime.now(timezone.utc).strftime("%H:%M")
        await db.cases.update_one(
            {"_id": case_id},
            {"$push": {"timeline": f"{now_str} — Interrogated {subject_name}."}}
        )

        return record

    async def request_warrant_review(
        self,
        case_id: str,
        requesting_marine_id: str,
        target_id: str,
        target_name: str,
        statute_id: str,
        requested_action: str
    ) -> Warrant:
        """
        Gathers verified evidence bundle and submits petition to the AI Marine Head.
        The AI evaluates statutory legal requirements, and the deterministic engine authorizes the result.
        """
        db = db_manager.db
        case = await self.get_case(case_id)
        if not case:
            raise ValueError(f"Case {case_id} not found.")

        law = laws_service.get_law(statute_id)
        if not law:
            raise ValueError(f"Statutory law '{statute_id}' does not exist in legal code.")

        if requested_action not in law.permitted_penalties:
            raise ValueError(
                f"Action '{requested_action}' is not legally authorized under statute '{law.title}'. "
                f"Permitted penalties: {', '.join(law.permitted_penalties)}"
            )

        # Retrieve all evidence for this case
        evidence_cursor = db.evidence.find({"case_id": case_id})
        evidence_docs = await evidence_cursor.to_list(length=50)

        evidence_text = "\n".join([
            f"- [{e['evidence_type']}] {e['title']}: {e['description']} (Source: {e['source']}, Reliability: {e['reliability']}%)"
            for e in evidence_docs
        ]) if evidence_docs else "No physical or documentary evidence logged."

        system_instruction = (
            "You are Fleet Admiral Bartholomew, authoritative AI Commander of the Colonial Marines.\n"
            "You review warrant and raid petitions strictly against statutory law and evidence thresholds.\n"
            "You do NOT invent laws. If evidence is insufficient or contradictory, you DENY or REQUEST_MORE_EVIDENCE.\n"
            "If documented proof links the suspect to the crime, you AUTHORIZE the specific requested action."
        )

        prompt = (
            f"=== CASE PETITION FOR REVIEW ===\n"
            f"Case: #{case.case_number} — {case.title}\n"
            f"Statute Cited: {law.title} (Severity: {law.severity}/5)\n"
            f"Required Proof Elements: {', '.join(law.evidence_requirements)}\n"
            f"Requested Action: {requested_action}\n"
            f"Target Subject: {target_name} ({target_id})\n\n"
            f"=== LOGGED CASE EVIDENCE ===\n"
            f"{evidence_text}\n\n"
            f"Evaluate whether the evidence meets the legal threshold for {requested_action}. Output MarineHeadDecision."
        )

        decision: MarineHeadDecision = await gemini_provider.structured_output(
            prompt=prompt,
            schema=MarineHeadDecision,
            system_instruction=system_instruction,
            model=settings.GEMINI_MODEL_REASONING
        )

        warrant = Warrant(
            case_id=case_id,
            target_id=target_id,
            target_name=target_name,
            statute_id=statute_id,
            requested_action=requested_action,
            status=decision.decision,
            ai_verdict=decision.model_dump()
        )

        await db.warrants.insert_one(warrant.to_mongo())

        now_str = datetime.now(timezone.utc).strftime("%H:%M")
        timeline_entry = (
            f"{now_str} — Warrant for {requested_action} on {target_name}: {decision.decision} "
            f"(Reason: {decision.reason})"
        )

        new_status = CaseStatus.RAID_AUTHORIZED.value if decision.decision == "AUTHORIZED" else CaseStatus.WARRANT_REQUESTED.value
        await db.cases.update_one(
            {"_id": case_id},
            {
                "$push": {
                    "warrant_ids": warrant.warrant_id,
                    "timeline": timeline_entry
                },
                "$set": {"status": new_status}
            }
        )

        await event_bus.publish(WorldEvent(
            event_type=EventType.WARRANT_DECISION,
            actor_id=requesting_marine_id,
            target_ids=[target_id],
            location_id=case.location_id,
            visibility=EventVisibility.CASE_RESTRICTED,
            state_delta={
                "warrant_id": warrant.warrant_id,
                "decision": decision.decision,
                "reason": decision.reason,
                "requested_action": requested_action
            },
            related_case_id=case_id
        ))

        logger.info(f"Marine Head evaluated Warrant #{warrant.warrant_id[:8]} -> {decision.decision}")
        return warrant


investigation_service = InvestigationService()
