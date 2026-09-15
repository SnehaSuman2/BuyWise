"""AI provider abstraction. The application never depends on a specific vendor."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AIProviderError(Exception):
    pass


class BaseLLMProvider(ABC):
    name: str = "base"
    is_demo: bool = False

    @property
    def enabled(self) -> bool:
        return True

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> str: ...

    @abstractmethod
    async def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...
