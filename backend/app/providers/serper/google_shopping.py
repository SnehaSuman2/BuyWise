"""Serper.dev Google Shopping → NormalizedListing."""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.providers.base import NormalizedListing, ProductSearchProvider, ProviderResult, parse_price
from app.providers.search_client import SearchApiError
from app.providers.serpapi.common import (
    availability_from_text,
    condition_from_title,
    delivery_days_from_text,
    domain_of,
    extract_asin,
    rating_of,
    reviews_of,
    shipping_from_text,
    unwrap_google_redirect,
)
from app.providers.serper.client import get_serper_client

logger = logging.getLogger(__name__)


def _first(item: dict, *names):
    """The first of several possible field names that carries a value.

    Serper's field names differ from SerpApi's and have changed before, so each
    value is looked up under every spelling seen rather than one.
    """
    for n in names:
        v = item.get(n)
        if v not in (None, "", []):
            return v
    return None


def normalize_serper_shopping(item: dict) -> NormalizedListing | None:
    title = str(_first(item, "title", "name") or "").strip()
    if not title:
        return None
    price = parse_price(_first(item, "price", "extracted_price", "priceRaw"))
    original = parse_price(_first(item, "originalPrice", "oldPrice", "old_price"))
    link = unwrap_google_redirect(_first(item, "link", "productLink", "url"))
    delivery = _first(item, "delivery", "shipping", "deliveryText") or ""
    if isinstance(delivery, list):
        delivery = " ".join(str(d) for d in delivery)
    delivery = str(delivery)
    shipping_price, shipping_known = shipping_from_text(delivery)

    identifiers: dict[str, str] = {}
    product_id = _first(item, "productId", "product_id")
    if product_id:
        identifiers["google_product_id"] = str(product_id)
    asin = extract_asin(link)
    if asin:
        identifiers["asin"] = asin

    # "offers": how many merchants Google knows for this product. More than one
    # is the same signal SerpApi's multiple_sources carries, and it is what marks
    # a product worth asking about every store.
    offer_count = _first(item, "offers", "offerCount", "offers_count")
    try:
        several = int(str(offer_count).strip()) > 1
    except (TypeError, ValueError):
        several = False

    return NormalizedListing(
        title=title,
        url=link,
        image_url=_first(item, "imageUrl", "thumbnail", "image"),
        price=price,
        original_price=original if original and price and original > price else None,
        currency="INR",
        retailer_name=_first(item, "source", "seller", "merchant", "store"),
        retailer_domain=domain_of(link)
        if link and "google." not in (domain_of(link) or "")
        else None,
        shipping_price=shipping_price,
        shipping_known=shipping_known,
        delivery_text=delivery or None,
        delivery_days=delivery_days_from_text(delivery),
        availability=availability_from_text(delivery, "")
        if delivery
        else ("in_stock" if price else "unknown"),
        condition=condition_from_title(title, "new"),
        rating=rating_of(_first(item, "rating", "ratingValue")),
        rating_count=reviews_of(_first(item, "ratingCount", "reviews", "reviewCount")),
        identifiers=identifiers,
        source_provider="serper",
        source_engine="google_shopping",
        multiple_sources=several,
        # Serper has no immersive-product token. Store lookups for these products
        # go through the Google product id instead, when an enricher is available.
        enrichment_token=None,
    )


class SerperShoppingProvider(ProductSearchProvider):
    name = "serper"
    engine = "google_shopping"

    @property
    def enabled(self) -> bool:
        return get_settings().serper_enabled

    async def search_products(
        self, query: str, *, max_results: int = 20, min_price=None, max_price=None
    ) -> ProviderResult[NormalizedListing]:
        settings = get_settings()
        client = get_serper_client()
        payload = {
            "q": query,
            "gl": settings.SERPAPI_COUNTRY,
            "hl": settings.SERPAPI_LANGUAGE,
            "location": "India",
            "num": min(max(max_results, 10), 40),
        }
        try:
            data = await client.post(
                "shopping", payload, cache_ttl=settings.CACHE_TTL_SEARCH_SECONDS
            )
        except SearchApiError as exc:
            return ProviderResult.failure(self.name, self.engine, str(exc))
        raw_items = data.get("shopping") or data.get("shopping_results") or []
        items = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            listing = normalize_serper_shopping(raw)
            if listing:
                items.append(listing)
        return ProviderResult(
            items=items[:max_results],
            provider=self.name,
            engine=self.engine,
            cached=data.get("_buywise_cached", False),
            stale=data.get("_buywise_stale", False),
        )
