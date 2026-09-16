"""Google Gemini provider (HTTPS API, no SDK dependency).

Gemini has a genuinely free tier, which is why this exists alongside OpenAI. The
key is never logged — see core.logging redaction.

API reference: https://ai.google.dev/api/generate-content
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

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
MIN_OUTPUT_TOKENS = 2048


class GeminiProvider(BaseLLMProvider):
    name = "gemini"

    def __init__(self) -> None:
        s = get_settings()
        self.api_key = s.GEMINI_API_KEY
        self.model = s.GEMINI_MODEL
        self.embedding_model = s.GEMINI_EMBEDDING_MODEL

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def _generate(
        self,
        prompt: str,
        system_prompt: str | None,
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        if not self.enabled:
            raise AIProviderError("GEMINI_API_KEY not configured")

        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                # Gemini 3.x spends part of maxOutputTokens on internal reasoning before
                # emitting any text, so a caller's modest limit can return an empty or
                # truncated reply. Floor the budget so the visible answer still fits;
                # callers' limits remain the upper bound when they ask for more.
                "maxOutputTokens": max(max_tokens, MIN_OUTPUT_TOKENS),
            },
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"

        STATS["calls"] += 1
        try:
            resp = await request_with_retry(
                "POST",
                f"{API_ROOT}/models/{self.model}:generateContent",
                headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
                json=body,
                timeout=45.0,
                max_retries=1,
            )
        except Exception as exc:
            STATS["failures"] += 1
            raise AIProviderError(f"Gemini request failed: {type(exc).__name__}") from exc

        if resp.status_code >= 400:
            STATS["failures"] += 1
            detail = ""
            try:
                detail = (resp.json().get("error") or {}).get("message", "")[:200]
            except ValueError:
                pass
            if resp.status_code == 404 and "no longer available" in detail:
                raise AIProviderError(
                    f"Gemini model '{self.model}' has been retired. {detail} "
                    "Set GEMINI_MODEL to a current model."
                )
            raise AIProviderError(f"Gemini returned HTTP {resp.status_code}: {detail}")

        data = resp.json()
        usage = data.get("usageMetadata") or {}
        STATS["total_tokens"] += int(usage.get("totalTokenCount") or 0)

        candidates = data.get("candidates") or []
        if not candidates:
            # Safety filters can return no candidate at all.
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise AIProviderError(f"Gemini returned no candidates{f' ({reason})' if reason else ''}")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        if not text:
            raise AIProviderError("Gemini returned an empty response")
        return text

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> str:
        return await self._generate(
            prompt, system_prompt, temperature=temperature, max_tokens=max_tokens, json_mode=False
        )

    async def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        system = (system_prompt or "") + "\nRespond with a single JSON object only."
        text = await self._generate(
            prompt, system, temperature=temperature, max_tokens=max_tokens, json_mode=True
        )
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIProviderError("Gemini returned invalid JSON") from exc
        return parsed if isinstance(parsed, dict) else {"result": parsed}

    async def embed(self, text: str) -> list[float]:
        if not self.enabled:
            raise AIProviderError("GEMINI_API_KEY not configured")
        resp = await request_with_retry(
            "POST",
            f"{API_ROOT}/models/{self.embedding_model}:embedContent",
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            json={
                "model": f"models/{self.embedding_model}",
                "content": {"parts": [{"text": text[:8000]}]},
            },
            timeout=30.0,
            max_retries=1,
        )
        if resp.status_code >= 400:
            raise AIProviderError(f"Gemini embeddings returned HTTP {resp.status_code}")
        return (resp.json().get("embedding") or {}).get("values") or []
