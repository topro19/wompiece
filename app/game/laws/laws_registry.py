from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class GameLaw(BaseModel):
    """Authoritative statutory statute in the colonial and naval legal code."""
    law_id: str
    title: str
    description: str
    severity: int = Field(ge=1, le=5)  # 1: Fine/Citation, 5: Capital/Execution
    evidence_requirements: List[str]
    permitted_penalties: List[str]  # e.g. ["CITATION", "SEARCH_WARRANT", "RAID_WARRANT", "DETENTION", "EXECUTION"]
    jurisdiction: str = "Azure Colonial Waters"
    authorization_required: bool = True


STATUTORY_LAWS: Dict[str, GameLaw] = {
    "SMUGGLING": GameLaw(
        law_id="SMUGGLING",
        title="Colonial Anti-Smuggling Act Sec. 14",
        description="The illicit importation, concealment, or liquidation of unmanifested contraband or stolen cargo.",
        severity=3,
        evidence_requirements=["Financial ledger anomaly", "Contraband physical sample", "Eyewitness testimony"],
        permitted_penalties=["SEARCH_WARRANT", "CARGO_SEIZURE", "RAID_WARRANT"],
        authorization_required=True
    ),
    "ILLEGAL_GAMBLING": GameLaw(
        law_id="ILLEGAL_GAMBLING",
        title="Gaming Regulation Ordinance Sec. 4",
        description="Operating unauthorized dice tables, loaded games, or unlicensed betting parlors.",
        severity=2,
        evidence_requirements=["Customer complaints", "Unlicensed table observation", "Confiscated loaded dice"],
        permitted_penalties=["FINE", "SEARCH_WARRANT", "CLOSURE_ORDER"],
        authorization_required=True
    ),
    "FALSIFIED_IDENTITY": GameLaw(
        law_id="FALSIFIED_IDENTITY",
        title="Imperial Registry Fraud Statute Sec. 22",
        description="Procuring or operating commercial businesses under forged civilian documentation to mask criminal history.",
        severity=4,
        evidence_requirements=["Discrepancy in baptismal/port records", "Linked criminal aliases", "Handwriting match"],
        permitted_penalties=["ARREST_WARRANT", "ASSET_FREEZE", "DETENTION"],
        authorization_required=True
    ),
    "BRIBERY": GameLaw(
        law_id="BRIBERY",
        title="Marine Public Integrity Code Sec. 7",
        description="Offering or accepting coin, valuables, or favors to influence naval patrols or dismiss evidence.",
        severity=4,
        evidence_requirements=["Recorded ledger transaction", "Undercover agent testimony", "Audio/transcript record"],
        permitted_penalties=["INTERNAL_AFFAIRS_INVESTIGATION", "STRIPPING_OF_RANK", "ARREST_WARRANT"],
        authorization_required=True
    ),
    "PIRACY": GameLaw(
        law_id="PIRACY",
        title="High Seas Maritime Security Code Sec. 1",
        description="Armed assault on commercial vessels, flying pirate colors, or mutinous rebellion against colonial authority.",
        severity=5,
        evidence_requirements=["Naval sighting", "Bounty poster confirmation", "Armed resistance against Marine vessel"],
        permitted_penalties=["LETHAL_ENGAGEMENT", "VESSEL_SINKING", "SUMMARY_EXECUTION"],
        authorization_required=True
    )
}


class LawsService:
    def get_law(self, law_id: str) -> Optional[GameLaw]:
        return STATUTORY_LAWS.get(law_id.upper())

    def get_all_laws(self) -> List[GameLaw]:
        return list(STATUTORY_LAWS.values())


laws_service = LawsService()
