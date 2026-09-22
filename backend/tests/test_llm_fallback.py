"""A capped free tier must fall through to the other provider, not to no AI."""

import pytest

from app.core.config import get_settings
from app.providers.llm import FallbackLLMProvider, get_llm_provider
from app.providers.llm.base import AIProviderError, BaseLLMProvider


class Boom(BaseLLMProvider):
    name = "boom"

    def __init__(self):
        self.calls = 0

    async def complete(self, prompt, system_prompt=None, temperature=0.4, max_tokens=1200):
        self.calls += 1
        raise AIProviderError("quota exhausted")

    async def complete_json(self, prompt, system_prompt=None, temperature=0.1, max_tokens=1200):
        self.calls += 1
        raise AIProviderError("quota exhausted")

    async def embed(self, text):
        raise AIProviderError("quota exhausted")


class Works(BaseLLMProvider):
    name = "works"

    def __init__(self):
        self.calls = 0

    async def complete(self, prompt, system_prompt=None, temperature=0.4, max_tokens=1200):
        self.calls += 1
        return "an answer"

    async def complete_json(self, prompt, system_prompt=None, temperature=0.1, max_tokens=1200):
        self.calls += 1
        return {"ok": True}

    async def embed(self, text):
        self.calls += 1
        return [0.0]


@pytest.mark.asyncio
async def test_secondary_answers_when_the_primary_is_out_of_quota():
    primary, secondary = Boom(), Works()
    provider = FallbackLLMProvider(primary, secondary)
    assert await provider.complete("hi") == "an answer"
    assert await provider.complete_json("hi") == {"ok": True}
    assert await provider.embed("hi") == [0.0]
    assert primary.calls == 2 and secondary.calls == 3
    assert provider.name == "boom+works" and provider.enabled


@pytest.mark.asyncio
async def test_both_failing_still_raises_so_callers_use_their_template():
    provider = FallbackLLMProvider(Boom(), Boom())
    with pytest.raises(AIProviderError):
        await provider.complete("hi")


def test_factory_chains_only_when_both_are_configured(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "AI_PROVIDER", "auto")
    monkeypatch.setattr(s, "GEMINI_API_KEY", "g")
    monkeypatch.setattr(s, "OPENAI_API_KEY", "")
    assert get_llm_provider().name == "gemini"
    monkeypatch.setattr(s, "OPENAI_API_KEY", "o")
    assert get_llm_provider().name == "gemini+openai"
    monkeypatch.setattr(s, "GEMINI_API_KEY", "")
    assert get_llm_provider().name == "openai"


def test_openai_client_points_at_the_configured_endpoint(monkeypatch):
    from app.providers.llm.openai import OpenAIProvider

    s = get_settings()
    monkeypatch.setattr(s, "OPENAI_API_KEY", "k")
    monkeypatch.setattr(s, "OPENAI_BASE_URL", "https://api.groq.com/openai/v1/")
    assert OpenAIProvider().base_url == "https://api.groq.com/openai/v1"
