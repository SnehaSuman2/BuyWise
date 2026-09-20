"""SerpApi Google Reverse Image engine (Phase 3) — pages containing a matching image."""

from __future__ import annotations

from app.core.config import get_settings
from app.providers.base import ImageSearchProvider, NormalizedListing, ProviderResult
from app.providers.serpapi.client import SerpApiError, get_serpapi_client
from app.providers.serpapi.common import domain_of


class GoogleReverseImageProvider(ImageSearchProvider):
    name = "serpapi"
    engine = "google_reverse_image"

    @property
    def enabled(self) -> bool:
        s = get_settings()
        return s.search_api_enabled and s.SERPAPI_ENABLE_GOOGLE_REVERSE_IMAGE

    async def search_by_image(self, image_url: str) -> ProviderResult[NormalizedListing]:
        settings = get_settings()
        client = get_serpapi_client()
        params = {
            "image_url": image_url,
            "gl": settings.SERPAPI_COUNTRY,
            "hl": settings.SERPAPI_LANGUAGE,
        }
        try:
            data = await client.search(
                self.engine, params, cache_ttl=settings.CACHE_TTL_SEARCH_SECONDS
            )
        except SerpApiError as exc:
            return ProviderResult.failure(self.name, self.engine, str(exc))
        items = []
        for raw in data.get("image_results") or []:
            if not raw.get("title"):
                continue
            items.append(
                NormalizedListing(
                    title=raw["title"],
                    url=raw.get("link"),
                    image_url=raw.get("thumbnail"),
                    retailer_name=raw.get("source"),
                    retailer_domain=domain_of(raw.get("link")),
                    snippet=raw.get("snippet"),
                    source_provider="serpapi",
                    source_engine=self.engine,
                )
            )
        return ProviderResult(
            items=items[:30],
            provider=self.name,
            engine=self.engine,
            cached=data.get("_buywise_cached", False),
        )
