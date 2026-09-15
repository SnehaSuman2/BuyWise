"""Demo AI provider — deterministic, no network. Used when no AI key is configured.

It never invents product data: the callers pass structured facts and the demo
provider simply echoes them into plain-language templates.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any

from app.providers.llm.base import BaseLLMProvider


class DemoLLMProvider(BaseLLMProvider):
    name = "demo"
    is_demo = True

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> str:
        return "AI explanations are running in demo mode (no AI provider configured). The structured recommendation above is computed from the data shown."

    async def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        # Callers that need JSON in demo mode use their own heuristic fallbacks; return an explicit marker.
        return {"is_demo": True, "unsupported": True}

    async def embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).hexdigest()
        rng = random.Random(h)
        return [rng.gauss(0, 1) for _ in range(256)]

    @staticmethod
    def describe(payload: dict) -> str:
        return json.dumps(payload, default=str)[:200]
