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
        model_name = model or settings.GEMINI_MODEL_FAST

        if self._client:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.2
                )
                response = self._client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config
                )
                return schema.model_validate_json(response.text)
            except Exception as e:
                logger.error(f"Gemini API structured output error: {e}. Falling back to deterministic resolver.")

        # Deterministic Heuristic Fallback
        return self._heuristic_fallback(prompt, schema)

    async def generate_prose(
        self,
        prompt: str,
        system_instruction: str = "",
        model: Optional[str] = None
    ) -> str:
        model_name = model or settings.GEMINI_MODEL_FAST

        if self._client:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7
                )
                response = self._client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config
                )
                return response.text
            except Exception as e:
                logger.error(f"Gemini API text generation error: {e}.")

        return "The ocean winds howl across the docks as waves crash against the weathered wooden pilings."

    def _heuristic_fallback(self, prompt: str, schema: Type[T]) -> T:
        """Provides consistent deterministic structured outputs when running offline or without active API key."""
        schema_name = schema.__name__
        prompt_lower = prompt.lower()

        if schema_name == "ActionProposal":
            # Determine action feasibility heuristically
            is_feasible = True
            rejection = None
            if "teleport" in prompt_lower or "impossible" in prompt_lower or "god" in prompt_lower or "moon" in prompt_lower:
                is_feasible = False
                rejection = "Action defies physical and world law constraints."

            action_type = "FREEFORM"
            if "steal" in prompt_lower:
                action_type = "STEAL"
            elif "betray" in prompt_lower:
                action_type = "BETRAY"
            elif "smuggle" in prompt_lower:
                action_type = "SMUGGLE"
            elif "observe" in prompt_lower or "examine" in prompt_lower:
                action_type = "EXAMINE"

            outcome = "SUCCESS" if is_feasible else "FAILURE"
            if "sneak" in prompt_lower or "steal" in prompt_lower or "betray" in prompt_lower:
                outcome = "PARTIAL_SUCCESS"

            return schema(
                intent=f"Player attempts to execute {action_type.lower()}",
                action_type=action_type,
                target=None,
                parameters={},
                feasible=is_feasible,
                rejection_reason=rejection,
                proposed_outcome=outcome,
                narrative="You move cautiously into position, assessing the surrounding guards and shadows.",
                requested_state_changes=[]
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
