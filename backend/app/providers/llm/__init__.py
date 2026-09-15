"""AI providers."""

from app.core.config import get_settings
from app.providers.llm.base import AIProviderError, BaseLLMProvider
from app.providers.llm.demo import DemoLLMProvider
from app.providers.llm.openai import OpenAIProvider


def get_llm_provider() -> BaseLLMProvider:
    s = get_settings()
    if s.openai_enabled:
        return OpenAIProvider()
    return DemoLLMProvider()


__all__ = [
    "AIProviderError",
    "BaseLLMProvider",
    "DemoLLMProvider",
    "OpenAIProvider",
    "get_llm_provider",
]
