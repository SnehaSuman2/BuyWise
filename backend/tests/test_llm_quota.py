"""Gemini quota exhaustion is remembered instead of retried on every question."""

import pytest

from app.core.config import get_settings
from app.providers.llm import gemini as g


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.headers = {}

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_quota_429_blocks_further_calls(monkeypatch):
    monkeypatch.setattr(get_settings(), "GEMINI_API_KEY", "k")
    monkeypatch.setattr(g, "_quota_blocked_until", 0.0)
    calls = []

    async def fake_request(method, url, **kwargs):
        calls.append(url)
        return FakeResponse(
            429, {"error": {"message": "You exceeded your current quota, please check your plan"}}
        )

    monkeypatch.setattr(g, "request_with_retry", fake_request)
    provider = g.GeminiProvider()
    with pytest.raises(g.AIProviderError):
        await provider.complete("hi", system_prompt=None, temperature=0, max_tokens=50)
    assert g.quota_blocked()
    with pytest.raises(g.AIProviderError):
        await provider.complete("hi again", system_prompt=None, temperature=0, max_tokens=50)
    assert len(calls) == 1  # the second question never reached Google
    monkeypatch.setattr(g, "_quota_blocked_until", 0.0)
