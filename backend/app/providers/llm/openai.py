"""Client for any OpenAI-compatible chat API (no SDK dependency). Key is never logged.

Works unchanged against OpenAI, Groq, OpenRouter, Azure AI Foundry or a model you
host yourself: set OPENAI_BASE_URL, OPENAI_API_KEY and OPENAI_MODEL.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import get_settings
from app.core.http import request_with_retry
from app.providers.llm.base import AIProviderError, BaseLLMProvider

logger = logging.getLogger(__name__)
STATS = {"calls": 0, "failures": 0, "total_tokens": 0}


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self) -> None:
        s = get_settings()
        self.api_key = s.OPENAI_API_KEY
        self.base_url = s.OPENAI_BASE_URL.rstrip("/")
        self.model = s.OPENAI_MODEL
        self.embedding_model = s.OPENAI_EMBEDDING_MODEL

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def _chat(
        self, messages: list[dict], *, temperature: float, max_tokens: int, json_mode: bool
    ) -> str:
        if not self.enabled:
            raise AIProviderError("OPENAI_API_KEY not configured")
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        STATS["calls"] += 1
        try:
            resp = await request_with_retry(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=45.0,
                max_retries=1,
            )
        except Exception as exc:
            STATS["failures"] += 1
            raise AIProviderError(f"OpenAI request failed: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            STATS["failures"] += 1
            raise AIProviderError(f"OpenAI returned HTTP {resp.status_code}")
        data = resp.json()
        STATS["total_tokens"] += int((data.get("usage") or {}).get("total_tokens") or 0)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIProviderError("OpenAI returned an unexpected response") from exc

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return await self._chat(
            messages, temperature=temperature, max_tokens=max_tokens, json_mode=False
        )

    async def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (system_prompt or "") + "\nRespond with a single JSON object only.",
            }
        ]
        messages.append({"role": "user", "content": prompt})
        text = await self._chat(
            messages, temperature=temperature, max_tokens=max_tokens, json_mode=True
        )
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {"result": parsed}
        except json.JSONDecodeError as exc:
            raise AIProviderError("OpenAI returned invalid JSON") from exc

    async def embed(self, text: str) -> list[float]:
        if not self.enabled:
            raise AIProviderError("OPENAI_API_KEY not configured")
        resp = await request_with_retry(
            "POST",
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.embedding_model, "input": text[:8000]},
            timeout=30.0,
            max_retries=1,
        )
        if resp.status_code >= 400:
            raise AIProviderError(f"OpenAI embeddings returned HTTP {resp.status_code}")
        return resp.json()["data"][0]["embedding"]
