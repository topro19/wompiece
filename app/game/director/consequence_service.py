from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.services.logger import logger
from app.game.director.relationship_service import relationship_service
from app.game.director.reputation_service import reputation_service
from app.game.director.thread_service import thread_service
from app.game.director.reward_service import reward_service
from app.game.director.opportunity_service import opportunity_engine
from app.game.director.director_models import RewardType, RewardGrant


class ActionConsequenceReport(BaseModel):
    """Encapsulates all world and character impacts resulting from an action."""
    character_id: str
    action_description: str
    outcome_summary: str
    relationship_shifts: List[Dict[str, Any]] = Field(default_factory=list)
    reputation_shifts: Dict[str, int] = Field(default_factory=dict)
    traits_recorded: Dict[str, int] = Field(default_factory=dict)
    threads_updated: List[str] = Field(default_factory=list)
    threads_merged: Optional[Dict[str, str]] = None
    rewards_granted: List[Dict[str, Any]] = Field(default_factory=list)
    new_opportunities: List[str] = Field(default_factory=list)


class ConsequenceService:
    """
    Executes the Living World Consequence Cascade:
    Player Choice -> Mechanical Outcome -> Relationship & Memory Shift ->
    Reputation & Trait Update -> Story Thread Progress -> Contextual Rewards ->
    New Opportunities Spawned.
    """

    async def apply_consequence_cascade(
        self,
        character_id: str,
        action_name: str,
        outcome_text: str,
        npc_target: Optional[str] = None,
        npc_delta_trust: int = 0,
        npc_delta_respect: int = 0,
        npc_delta_fear: int = 0,
        npc_delta_affection: int = 0,
        npc_memory_text: Optional[str] = None,
        npc_favor_earned: bool = False,
        npc_favor_reason: Optional[str] = None,
        reputation_changes: Optional[Dict[str, int]] = None,
        behavioral_traits: Optional[Dict[str, int]] = None,
        thread_id: Optional[str] = None,
        thread_advance_notes: Optional[str] = None,
        thread_new_fact: Optional[str] = None,
        thread_merge_target: Optional[str] = None,
        rewards: Optional[List[RewardGrant]] = None,
        completed_opportunity_id: Optional[str] = None,
        new_opportunity_data: Optional[Dict[str, Any]] = None
    ) -> ActionConsequenceReport:
        report = ActionConsequenceReport(
            character_id=character_id,
            action_description=action_name,
            outcome_summary=outcome_text
        )

        # 1. Update NPC Relationship & Memories
        if npc_target and any([npc_delta_trust, npc_delta_respect, npc_delta_fear, npc_delta_affection, npc_memory_text, npc_favor_earned]):
            rel = await relationship_service.adjust_relationship(
                character_id=character_id,
                npc_name=npc_target,
                trust_delta=npc_delta_trust,
                respect_delta=npc_delta_respect,
                fear_delta=npc_delta_fear,
                affection_delta=npc_delta_affection,
                memory_summary=npc_memory_text,
                favor_earned=npc_favor_earned
            )
            report.relationship_shifts.append({
                "npc": npc_target,
                "trust": rel.trust,
                "respect": rel.respect,
                "fear": rel.fear,
                "affection": rel.affection,
                "standing": rel.level.value,
                "favors": rel.favors_owed_to_player
            })

        if npc_target and npc_favor_earned and npc_favor_reason:
            await relationship_service.add_favor(
                character_id=character_id,
                npc_name=npc_target,
                favors=1,
                reason=npc_favor_reason
            )

        # 2. Update Multi-Dimensional Reputation & Behavioral Traits
        if reputation_changes:
            new_reps = await reputation_service.adjust_reputation(character_id, reputation_changes)
            report.reputation_shifts.update(new_reps)

        if behavioral_traits:
            recorded_traits = await reputation_service.record_action_traits(character_id, behavioral_traits)
            report.traits_recorded.update(recorded_traits)

        # 3. Advance or Merge Story Threads
        if thread_id and (thread_advance_notes or thread_new_fact):
            await thread_service.update_thread(
                thread_id=thread_id,
                new_fact=thread_new_fact,
                log_entry=thread_advance_notes
            )
            report.threads_updated.append(thread_id)

        if thread_id and thread_merge_target:
            merged = await thread_service.merge_threads(
                source_thread_id=thread_id,
                target_thread_id=thread_merge_target,
                merge_reason=thread_advance_notes or "The threads intertwine."
            )
            if merged:
                report.threads_merged = {
                    "source": thread_id,
                    "target": thread_merge_target
                }

        # 4. Complete Associated Opportunity
        if completed_opportunity_id:
            await opportunity_engine.complete_opportunity(
                character_id=character_id,
                opportunity_id=completed_opportunity_id,
                resolution_notes=outcome_text
            )

        # 5. Grant Contextual Non-Spam Rewards
        if rewards:
            grant_res = await reward_service.grant(
                character_id=character_id,
                rewards=rewards,
                reason=action_name,
                actor_npc_name=npc_target
            )
            report.rewards_granted.append(grant_res)

        # 6. Spawn Follow-up Opportunity if present
        if new_opportunity_data:
            opp = await opportunity_engine.create_opportunity(
                character_id=character_id,
                title=new_opportunity_data["title"],
                description=new_opportunity_data["description"],
                opp_type=new_opportunity_data.get("opp_type"),
                urgency=new_opportunity_data.get("urgency"),
                location_id=new_opportunity_data.get("location_id", "port_azure"),
                related_npc_name=new_opportunity_data.get("related_npc_name"),
                duration_minutes=new_opportunity_data.get("duration_minutes"),
                consequence_summary=new_opportunity_data.get("consequence_summary"),
                suggested_actions=new_opportunity_data.get("suggested_actions"),
                reward_preview=new_opportunity_data.get("reward_preview")
            )
            report.new_opportunities.append(opp.title)

        logger.info(f"[CONSEQUENCE CASCADE] Applied for {character_id} on action '{action_name}'.")
        return report


consequence_service = ConsequenceService()
