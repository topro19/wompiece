import pytest
from pydantic import BaseModel
from unittest.mock import MagicMock, patch
from app.config.settings import settings
from app.ai.providers.gemini_provider import GeminiAIProvider


class MockOutputSchema(BaseModel):
    status: str
    code: int


@pytest.mark.asyncio
async def test_allowed_models_configuration():
    """Ensure that the 4 specified models and heavy/basic tiers are configured."""
    expected_models = [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemma-4-26b-a4b-it",
        "gemma-4-31b-it",
    ]
    assert set(settings.AI_FALLBACK_MODELS) == set(expected_models)
    assert settings.GEMINI_MODEL_HEAVY == "gemini-3.5-flash-lite"
    assert "gemma" in settings.GEMINI_MODEL_BASIC


@pytest.mark.asyncio
async def test_candidate_models_filtering():
    """Ensure candidate models prioritize Gemma for basic tasks and Gemini for heavy tasks."""
    provider = GeminiAIProvider()
    
    # When requesting a Gemma model (basic/frequent task), Gemma models come first
    candidates_gemma = provider._build_candidate_models("gemma-4-26b-a4b-it")
    assert candidates_gemma[0] == "gemma-4-26b-a4b-it"
    assert "gemma" in candidates_gemma[1]
    assert set(candidates_gemma) == set(settings.AI_FALLBACK_MODELS)
    
    # When requesting Gemini 3.5 (heavy/main task), Gemini models come first
    candidates_heavy = provider._build_candidate_models("gemini-3.5-flash-lite")
    assert candidates_heavy[0] == "gemini-3.5-flash-lite"
    assert candidates_heavy[1] == "gemini-3.1-flash-lite"
    assert set(candidates_heavy) == set(settings.AI_FALLBACK_MODELS)

    # When requesting an unauthorized model (e.g. gemini-3.6-flash), it must be ignored
    candidates_unauth = provider._build_candidate_models("gemini-3.6-flash")
    assert "gemini-3.6-flash" not in candidates_unauth
    assert set(candidates_unauth) == set(settings.AI_FALLBACK_MODELS)


@pytest.mark.asyncio
async def test_multi_model_failover_execution():
    """Ensure that if the first model fails with quota/rate limit error, the second model is tried seamlessly."""
    provider = GeminiAIProvider()
    mock_client = MagicMock()
    provider._client = mock_client

    call_order = []

    def mock_generate(model, contents, config):
        call_order.append(model)
        if model == "gemini-3.5-flash-lite":
            raise Exception("429 Quota Exceeded")
        mock_res = MagicMock()
        mock_res.text = '{"status": "ok", "code": 200}'
        return mock_res

    mock_client.models.generate_content.side_effect = mock_generate

    result = await provider.structured_output(
        prompt="Test failover",
        schema=MockOutputSchema,
        model=settings.GEMINI_MODEL_HEAVY
    )

    assert result.status == "ok"
    assert result.code == 200
    # First model was tried and failed, second model succeeded
    assert call_order == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
