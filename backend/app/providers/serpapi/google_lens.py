"""SerpApi Google Lens engine — visual matches for a public image URL."""

from __future__ import annotations

from app.core.config import get_settings
from app.providers.base import ImageSearchProvider, NormalizedListing, ProviderResult, parse_price
from app.providers.serpapi.client import SerpApiError, get_serpapi_client
from app.providers.serpapi.common import domain_of


def normalize_visual_match(item: dict) -> NormalizedListing | None:
    title = item.get("title")
    if not title:
        return None
    price_info = item.get("price") or {}
    price = (
        parse_price(price_info.get("extracted_value"))
        if isinstance(price_info, dict)
        else parse_price(price_info)
    )
    currency = (price_info.get("currency") if isinstance(price_info, dict) else None) or "INR"
    link = item.get("link")
    return NormalizedListing(
        title=title,
        url=link,
        image_url=item.get("thumbnail"),
        price=price,
        currency="INR" if currency in ("₹", "INR", "Rs") else currency,
        retailer_name=item.get("source"),
        retailer_domain=domain_of(link),
        availability="unknown",
        source_provider="serpapi",
        source_engine="google_lens",
    )


class GoogleLensProvider(ImageSearchProvider):
    name = "serpapi"
    engine = "google_lens"

    @property
    def enabled(self) -> bool:
        s = get_settings()
        return s.serpapi_enabled and s.SERPAPI_ENABLE_GOOGLE_LENS

    async def search_by_image(self, image_url: str) -> ProviderResult[NormalizedListing]:
        settings = get_settings()
        client = get_serpapi_client()
        params = {
            "url": image_url,
            "country": settings.SERPAPI_COUNTRY,
            "hl": settings.SERPAPI_LANGUAGE,
        }
        try:
            data = await client.search(
                self.engine, params, cache_ttl=settings.CACHE_TTL_SEARCH_SECONDS
            )
        except SerpApiError as exc:
            return ProviderResult.failure(self.name, self.engine, str(exc))
        items = []
        for raw in data.get("visual_matches") or []:
            listing = normalize_visual_match(raw)
            if listing:
                items.append(listing)
        return ProviderResult(
            items=items[:30],
            provider=self.name,
            engine=self.engine,
            cached=data.get("_buywise_cached", False),
        )
