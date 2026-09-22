"""Try one AI provider, then another.

A free tier that runs out should degrade to the next provider, not to no AI at
all. Gemini's free allowance caps daily; an OpenAI-compatible endpoint (Groq,
OpenRouter, Azure, a self-hosted model) configured alongside it takes over for
the rest of the day and hands back automatically when the cap resets.
"""

from __future__ import annotations

import logging
from typing import Any

from app.providers.llm.base import AIProviderError, BaseLLMProvider

logger = logging.getLogger(__name__)


class FallbackLLMProvider(BaseLLMProvider):
    def __init__(self, primary: BaseLLMProvider, secondary: BaseLLMProvider) -> None:
        self.primary = primary
        self.secondary = secondary

    @property
    def name(self) -> str:
        return f"{self.primary.name}+{self.secondary.name}"

    @property
    def is_demo(self) -> bool:
        return self.primary.is_demo and self.secondary.is_demo

    @property
    def enabled(self) -> bool:
        return self.primary.enabled or self.secondary.enabled

    async def _either(self, method: str, *args, **kwargs):
        try:
            return await getattr(self.primary, method)(*args, **kwargs)
        except AIProviderError as exc:
            logger.warning(
                "%s unavailable (%s); trying %s", self.primary.name, exc, self.secondary.name
            )
            return await getattr(self.secondary, method)(*args, **kwargs)

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> str:
        return await self._either(
            "complete", prompt, system_prompt, temperature=temperature, max_tokens=max_tokens
        )

    async def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        return await self._either(
            "complete_json", prompt, system_prompt, temperature=temperature, max_tokens=max_tokens
        )

    async def embed(self, text: str) -> list[float]:
        return await self._either("embed", text)
