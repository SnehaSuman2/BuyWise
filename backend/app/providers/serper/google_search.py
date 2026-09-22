"""Serper.dev Google web search → EvidenceItem.

Trust scoring and URL resolution both need plain web results. Without a second
source they stop the moment the first vendor's quota does, and every retailer
falls back to unrated.
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.providers.base import EvidenceItem, ProviderResult, WebSearchProvider
from app.providers.search_client import SearchApiError
from app.providers.serper.client import get_serper_client

logger = logging.getLogger(__name__)


class SerperWebSearchProvider(WebSearchProvider):
    name = "serper"
    engine = "google_search"

    @property
    def enabled(self) -> bool:
        return get_settings().serper_enabled

    async def search_web(
        self, query: str, *, max_results: int = 10
    ) -> ProviderResult[EvidenceItem]:
        settings = get_settings()
        client = get_serper_client()
        payload = {
            "q": query,
            "gl": settings.SERPAPI_COUNTRY,
            "hl": settings.SERPAPI_LANGUAGE,
            "num": min(max(max_results, 10), 20),
        }
        try:
            data = await client.post("search", payload, cache_ttl=settings.CACHE_TTL_SEARCH_SECONDS)
        except SearchApiError as exc:
            return ProviderResult.failure(self.name, self.engine, str(exc))
        items: list[EvidenceItem] = []
        for raw in data.get("organic") or []:
            if not isinstance(raw, dict):
                continue
            title = (raw.get("title") or "").strip()
            if not title:
                continue
            items.append(
                EvidenceItem(
                    source="google_search",
                    source_type="search_result",
                    url=raw.get("link"),
                    title=title,
                    snippet=raw.get("snippet"),
                    query=query,
                )
            )
        return ProviderResult(
            items=items[:max_results],
            provider=self.name,
            engine=self.engine,
            cached=data.get("_buywise_cached", False),
            stale=data.get("_buywise_stale", False),
        )
