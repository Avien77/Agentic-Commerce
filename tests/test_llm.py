"""The shared LLM client: model routing, the quota fallback, and schemas Gemini accepts."""

import pytest
from google import genai
from google.genai import _transformers

from src.agents.consumer import IntentExtraction
from src.agents.merchant import FlagReasons
from src.llm import LLM, LLMError, make_llm, provider_for
from src.pipeline import ExtractionBatch


def test_provider_and_model_choice(cfg, monkeypatch):
    assert provider_for("gemini-3.8-flash") == "gemini"
    assert provider_for("openai/gpt-oss-20b") == "groq"
    assert provider_for("rules") == "offline"
    monkeypatch.delenv("AGENTIC_LLM")
    llm = make_llm(cfg)
    assert llm.model == "gemini-3.8-flash" and llm.fallback.model == "gemini-3.5-flash-lite"
    monkeypatch.setenv("AGENTIC_LLM", "small")
    assert make_llm(cfg).provider == "groq"


@pytest.mark.parametrize("schema", [IntentExtraction, ExtractionBatch, FlagReasons])
def test_structured_output_schemas_convert_for_gemini(schema):
    """Gemini's schema subset has no exclusiveMinimum (Field(gt=...)) and no extra keys."""
    api = genai.Client(api_key="not-used")._api_client
    assert _transformers.t_schema(api, schema) is not None


class QuotaLLM(LLM):
    def _with_retries(self, system, prompt, schema):
        raise LLMError(f"{self.model}: rate limit or daily quota reached")


def test_quota_exhaustion_moves_to_the_fallback(tmp_path):
    backup = QuotaLLM(model="rules", cache_dir=None)
    backup.provider = "offline"  # answers from the offline handlers
    main = QuotaLLM(model="gemini-3.8-flash", cache_dir=str(tmp_path), fallback=backup)
    out = main.json(tag="intent", system="", prompt="<request>Mewtwo under $50</request>",
                    schema=IntentExtraction)  # fmt: skip
    assert out.budget == 50.0 and backup.calls and not main.calls
