"""Serper.dev Google Lens → NormalizedListing.

Photo search otherwise stops dead when the first vendor's quota does. These are
visual look-alikes, never confirmed matches, and the search layer labels them
as such regardless of which vendor found them.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.providers.base import ImageSearchProvider, NormalizedListing, ProviderResult, parse_price
from app.providers.search_client import SearchApiError
from app.providers.serpapi.common import domain_of
from app.providers.serper.client import get_serper_client
from app.providers.serper.google_shopping import _first


def normalize_serper_lens(item: dict) -> NormalizedListing | None:
    title = str(_first(item, "title", "name") or "").strip()
    if not title:
        return None
    raw_price = _first(item, "price", "priceRaw", "extracted_price")
    price = parse_price(raw_price.get("value") if isinstance(raw_price, dict) else raw_price)
    link = _first(item, "link", "url")
    return NormalizedListing(
        title=title,
        url=link,
        image_url=_first(item, "imageUrl", "thumbnail", "thumbnailUrl"),
        price=price,
        currency="INR",
        retailer_name=_first(item, "source", "seller", "domain"),
        retailer_domain=domain_of(link),
        availability="unknown",
        source_provider="serper",
        source_engine="google_lens",
    )


class SerperLensProvider(ImageSearchProvider):
    name = "serper"
    engine = "google_lens"

    @property
    def enabled(self) -> bool:
        return get_settings().serper_enabled

    async def search_by_image(self, image_url: str) -> ProviderResult[NormalizedListing]:
        settings = get_settings()
        client = get_serper_client()
        payload = {
            "url": image_url,
            "gl": settings.SERPAPI_COUNTRY,
            "hl": settings.SERPAPI_LANGUAGE,
        }
        try:
            data = await client.post("lens", payload, cache_ttl=settings.CACHE_TTL_SEARCH_SECONDS)
        except SearchApiError as exc:
            return ProviderResult.failure(self.name, self.engine, str(exc))
        raw_items = data.get("organic") or data.get("visual_matches") or data.get("shopping") or []
        items = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            listing = normalize_serper_lens(raw)
            if listing:
                items.append(listing)
        return ProviderResult(
            items=items,
            provider=self.name,
            engine=self.engine,
            cached=data.get("_buywise_cached", False),
            stale=data.get("_buywise_stale", False),
        )
