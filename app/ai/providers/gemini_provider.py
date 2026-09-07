import os
from typing import Type, TypeVar, Optional
from pydantic import BaseModel
from app.config.settings import settings
from app.ai.providers.base import AIProvider
from app.services.logger import logger

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

T = TypeVar("T", bound=BaseModel)


class GeminiAIProvider(AIProvider):
    """Google Gemini AI implementation using official google-genai SDK with graceful fallback."""

    def __init__(self):
        self._client = None
        if genai and settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_gemini_api_key_here":
            try:
                self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
                logger.info("Initialized Google Gemini AI client.")
            except Exception as e:
                logger.warning(f"Could not initialize Google Gemini client ({e}). Operating in deterministic heuristic mode.")

    async def structured_output(
        self,
        prompt: str,
        schema: Type[T],
        system_instruction: str = "",
        model: Optional[str] = None
    ) -> T:
        primary_model = model or settings.GEMINI_MODEL_FAST
        candidate_models = [primary_model]
        for fallback_m in ["gemini-3.6-flash", "gemini-flash-latest", "gemini-3.5-flash-lite"]:
            if fallback_m not in candidate_models:
                candidate_models.append(fallback_m)

        if self._client:
            last_err = None
            for candidate in candidate_models:
                try:
                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=0.2
                    )
                    response = self._client.models.generate_content(
                        model=candidate,
                        contents=prompt,
                        config=config
                    )
                    return schema.model_validate_json(response.text)
                except Exception as e:
                    last_err = e
                    continue
            logger.error(f"Gemini API structured output error across all models: {last_err}. Falling back to deterministic resolver.")

        # Deterministic Heuristic Fallback
        return self._heuristic_fallback(prompt, schema)

    async def generate_prose(
        self,
        prompt: str,
        system_instruction: str = "",
        model: Optional[str] = None
    ) -> str:
        primary_model = model or settings.GEMINI_MODEL_FAST
        candidate_models = [primary_model, "gemini-3.6-flash", "gemini-flash-latest", "gemini-3.5-flash-lite"]

        if self._client:
            for candidate in candidate_models:
                try:
                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.7
                    )
                    response = self._client.models.generate_content(
                        model=candidate,
                        contents=prompt,
                        config=config
                    )
                    return response.text
                except Exception as e:
                    continue

        return "The ocean winds howl across the docks as waves crash against the weathered wooden pilings."

    def _heuristic_fallback(self, prompt: str, schema: Type[T]) -> T:
        """Provides consistent deterministic structured outputs when running offline or without active API key."""
        schema_name = schema.__name__
        prompt_lower = prompt.lower()

        if schema_name == "ActionProposal":
            # Determine action feasibility heuristically
            is_feasible = True
            rejection = None
            if any(k in prompt_lower for k in ["teleport", "impossible", "god", "moon", "1,000,000", "10,000,000", "grant this character"]):
                is_feasible = False
                rejection = "Action defies physical and world law constraints."

            action_type = "EXPLORE"
            difficulty = "MODERATE"
            chance = 70
            gold = 0
            items_summary = None
            health_delta = 0
            wanted_delta = 0
            rep_faction = None
            rep_delta = 0
            narrative = "You assess your surroundings and take action amidst the bustling colonial harbor."

            if not is_feasible:
                outcome = "FAILURE"
                narrative = rejection
            elif any(k in prompt_lower for k in ["job", "work", "labor", "hire", "employment", "earn", "unload", "haul", "clean"]):
                action_type = "LABOR_WORK"
                difficulty = "EASY"
                chance = 85
                outcome = "SUCCESS"
                gold = 35
                rep_faction = "merchant"
                rep_delta = 2
                narrative = "You find honest day labor at the harbor docks, sweating under the afternoon sun hauling heavy cargo crates. The dockmaster tosses you 35 Gold for your efforts."
            elif any(k in prompt_lower for k in ["steal", "pocket", "pilfer", "pickpocket", "rob", "loot"]):
                action_type = "CRIME_STEAL"
                difficulty = "HARD"
                chance = 50
                outcome = "PARTIAL_SUCCESS"
                gold = 75
                wanted_delta = 1
                rep_faction = "pirate"
                rep_delta = 3
                narrative = "You slip through the harbor shadows and deftly cut a fat merchant's purse strings, slipping away with 75 Gold before anyone notices."
            elif any(k in prompt_lower for k in ["betray", "informant", "snitch", "sabotage", "treason", "leak"]):
                action_type = "BETRAY"
                difficulty = "HARD"
                chance = 55
                outcome = "SUCCESS"
                rep_faction = "marine"
                rep_delta = 5
                narrative = "You quietly make your way to the Marine liaison and whisper confidential movements of your pirate crew."
            elif "smuggle" in prompt_lower:
                action_type = "SMUGGLE"
                difficulty = "HARD"
                chance = 55
                outcome = "SUCCESS"
                gold = 120
                rep_faction = "pirate"
                rep_delta = 2
                narrative = "You sneak contraband past sleepy dock sentries and deliver the goods to a shadowy contact."
            elif "observe" in prompt_lower or "examine" in prompt_lower or "look" in prompt_lower:
                action_type = "EXAMINE"
                difficulty = "TRIVIAL"
                chance = 95
                outcome = "SUCCESS"
                narrative = "You survey the surroundings with sharp eyes, noting the guard patrols and ship moorings."
            else:
                outcome = "SUCCESS"

            return schema(
                intent=f"Player attempts to execute {action_type.lower()}",
                action_type=action_type,
                difficulty_level=difficulty,
                success_chance_percent=chance,
                target=None,
                feasible=is_feasible,
                rejection_reason=rejection,
                proposed_outcome=outcome,
                reward_gold=gold,
                reward_items_summary=items_summary,
                health_change=health_delta,
                wanted_level_change=wanted_delta,
                reputation_faction=rep_faction,
                reputation_change=rep_delta,
                narrative=narrative
            )

        elif schema_name == "NPCReaction":
            attitude = 0
            tell = "Eyes narrow calculatingly."
            dialogue = "What business do ye have here, matey?"
            if "hostile" in prompt_lower or "threat" in prompt_lower:
                attitude = -5
                dialogue = "Watch your tongue before I feed it to the sharks."
                tell = "Hand drifts slowly toward cutlass pommel."
            elif "friend" in prompt_lower or "bribe" in prompt_lower:
                attitude = 4
                dialogue = "Now you're speaking a language an honest sailor can appreciate."

            return schema(
                npc_name="Simulated Character",
                dialogue=dialogue,
                internal_thought="Assessing whether this stranger is a Marine informant or an ally.",
                attitude_delta=attitude,
                body_language_tell=tell,
                action_taken=None
            )

        elif schema_name == "MarineHeadDecision":
            # Real evidence present if not the empty placeholder string
            has_real_evidence = (
                "no physical or documentary evidence logged" not in prompt_lower
                and ("contraband" in prompt_lower or "anomaly" in prompt_lower or "unmanifested" in prompt_lower)
            )

            if has_real_evidence:
                return schema(
                    decision="AUTHORIZED",
                    confidence=0.88,
                    reason="Documented evidence and financial anomalies meet statutory threshold for search and warrant execution.",
                    statute_analyzed="Anti-Smuggling Act Sec. 14",
                    required_evidence=[],
                    authorized_actions=["SEARCH", "RAID"]
                )
            else:
                return schema(
                    decision="REQUEST_MORE_EVIDENCE",
                    confidence=0.45,
                    reason="Insufficient prima facie evidence linking suspect to the alleged crime. Testimony alone requires corroborating records.",
                    statute_analyzed="Marine Procedural Code Sec. 9",
                    required_evidence=["Financial ledger audit", "Contraband manifest or physical sample"],
                    authorized_actions=[]
                )

        raise ValueError(f"No heuristic fallback defined for schema {schema_name}")


gemini_provider = GeminiAIProvider()
