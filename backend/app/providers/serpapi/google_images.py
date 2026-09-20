"""SerpApi Google Images engine (Phase 3) — image results for a product query."""

from __future__ import annotations

from app.core.config import get_settings
from app.providers.base import NormalizedListing, ProductSearchProvider, ProviderResult
from app.providers.serpapi.client import SerpApiError, get_serpapi_client
from app.providers.serpapi.common import domain_of


class GoogleImagesProvider(ProductSearchProvider):
    name = "serpapi"
    engine = "google_images"

    @property
    def enabled(self) -> bool:
        s = get_settings()
        return s.search_api_enabled and s.SERPAPI_ENABLE_GOOGLE_IMAGES

    async def search_products(
        self, query: str, *, max_results: int = 20, min_price=None, max_price=None
    ) -> ProviderResult[NormalizedListing]:
        settings = get_settings()
        client = get_serpapi_client()
        params = {"q": query, "gl": settings.SERPAPI_COUNTRY, "hl": settings.SERPAPI_LANGUAGE}
        try:
            data = await client.search(
                self.engine, params, cache_ttl=settings.CACHE_TTL_SEARCH_SECONDS
            )
        except SerpApiError as exc:
            return ProviderResult.failure(self.name, self.engine, str(exc))
        items = []
        for raw in data.get("images_results") or []:
            if not raw.get("title"):
                continue
            items.append(
                NormalizedListing(
                    title=raw["title"],
                    url=raw.get("link"),
                    image_url=raw.get("original") or raw.get("thumbnail"),
                    retailer_name=raw.get("source"),
                    retailer_domain=domain_of(raw.get("link")),
                    source_provider="serpapi",
                    source_engine=self.engine,
                )
            )
        return ProviderResult(
            items=items[:max_results],
            provider=self.name,
            engine=self.engine,
            cached=data.get("_buywise_cached", False),
        )
