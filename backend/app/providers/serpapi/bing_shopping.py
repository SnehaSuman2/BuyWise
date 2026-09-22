"""SerpApi Bing Shopping engine (Phase 3) → NormalizedListing."""

from __future__ import annotations

from app.core.config import get_settings
from app.providers.base import NormalizedListing, ProductSearchProvider, ProviderResult, parse_price
from app.providers.serpapi.client import SerpApiError, get_serpapi_client
from app.providers.serpapi.common import domain_of, rating_of, reviews_of, shipping_from_text


class BingShoppingProvider(ProductSearchProvider):
    name = "serpapi"
    engine = "bing_shopping"

    @property
    def enabled(self) -> bool:
        s = get_settings()
        return s.search_api_enabled and s.SERPAPI_ENABLE_BING_SHOPPING

    async def search_products(
        self, query: str, *, max_results: int = 20, min_price=None, max_price=None
    ) -> ProviderResult[NormalizedListing]:
        settings = get_settings()
        client = get_serpapi_client()
        params = {"q": query, "cc": settings.SERPAPI_COUNTRY.upper(), "mkt": "en-IN"}
        try:
            data = await client.search(
                self.engine, params, cache_ttl=settings.CACHE_TTL_SEARCH_SECONDS
            )
        except SerpApiError as exc:
            return ProviderResult.failure(self.name, self.engine, str(exc))
        items = []
        for raw in data.get("shopping_results") or []:
            if not raw.get("title"):
                continue
            shipping_price, shipping_known = shipping_from_text(
                raw.get("shipping") or raw.get("delivery")
            )
            items.append(
                NormalizedListing(
                    title=raw["title"],
                    url=raw.get("link"),
                    image_url=raw.get("thumbnail"),
                    price=parse_price(raw.get("extracted_price")) or parse_price(raw.get("price")),
                    original_price=parse_price(raw.get("extracted_old_price"))
                    or parse_price(raw.get("old_price")),
                    retailer_name=raw.get("seller") or raw.get("source"),
                    retailer_domain=domain_of(raw.get("link")),
                    shipping_price=shipping_price,
                    shipping_known=shipping_known,
                    rating=rating_of(raw.get("rating")),
                    rating_count=reviews_of(raw.get("reviews")),
                    source_provider="serpapi",
                    source_engine=self.engine,
                )
            )
        return ProviderResult(
            items=items[:max_results],
            provider=self.name,
            engine=self.engine,
            cached=data.get("_buywise_cached", False),
            stale=data.get("_buywise_stale", False),
        )
