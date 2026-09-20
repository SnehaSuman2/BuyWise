"""Google web search — organic results as evidence items (SerpApi or SearchApi)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import get_settings
from app.providers.base import EvidenceItem, ProviderResult, WebSearchProvider
from app.providers.search_client import SearchApiError, get_search_client


def _parse_date(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%b %d, %Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def normalize_organic_result(item: dict, query: str) -> EvidenceItem | None:
    title = item.get("title")
    link = item.get("link")
    if not title or not link:
        return None
    return EvidenceItem(
        source="google_search",
        source_type="search_result",
        url=link,
        title=title,
        snippet=item.get("snippet"),
        published_at=_parse_date(item.get("date")),
        query=query,
    )


class GoogleSearchProvider(WebSearchProvider):
    engine = "google"

    @property
    def name(self) -> str:
        return get_search_client().provider

    @property
    def enabled(self) -> bool:
        s = get_settings()
        return s.search_api_enabled and s.SERPAPI_ENABLE_GOOGLE_SEARCH

    async def search_web(
        self, query: str, *, max_results: int = 10
    ) -> ProviderResult[EvidenceItem]:
        settings = get_settings()
        client = get_search_client()
        params = {
            "q": query,
            "gl": settings.SERPAPI_COUNTRY,
            "hl": settings.SERPAPI_LANGUAGE,
            "num": min(max_results, 20),
        }
        try:
            data = await client.search(
                self.engine, params, cache_ttl=settings.CACHE_TTL_TRUST_SECONDS
            )
        except SearchApiError as exc:
            return ProviderResult.failure(self.name, self.engine, str(exc))
        items = []
        for raw in data.get("organic_results") or []:
            ev = normalize_organic_result(raw, query)
            if ev:
                items.append(ev)
        return ProviderResult(
            items=items[:max_results],
            provider=self.name,
            engine=self.engine,
            cached=data.get("_buywise_cached", False),
        )
