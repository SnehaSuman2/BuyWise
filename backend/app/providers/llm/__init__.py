"""AI providers."""

from app.core.config import get_settings
from app.providers.llm.base import AIProviderError, BaseLLMProvider
from app.providers.llm.demo import DemoLLMProvider
from app.providers.llm.gemini import GeminiProvider
from app.providers.llm.openai import OpenAIProvider


def get_llm_provider() -> BaseLLMProvider:
    """Pick the configured AI provider. Gemini first — it has a free tier."""
    s = get_settings()
    if s.gemini_enabled:
        return GeminiProvider()
    if s.openai_enabled:
        return OpenAIProvider()
    return DemoLLMProvider()


__all__ = [
    "AIProviderError",
    "BaseLLMProvider",
    "DemoLLMProvider",
    "GeminiProvider",
    "OpenAIProvider",
    "get_llm_provider",
]
