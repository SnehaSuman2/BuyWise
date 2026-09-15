"""SerpApi Amazon Search engine (amazon.in) → NormalizedListing."""

from __future__ import annotations

from app.core.config import get_settings
from app.providers.base import (
    NormalizedListing,
    ProviderResult,
    RetailerSearchProvider,
    parse_price,
)
from app.providers.serpapi.client import SerpApiError, get_serpapi_client
from app.providers.serpapi.common import (
    availability_from_text,
    delivery_days_from_text,
    rating_of,
    reviews_of,
    shipping_from_text,
)


def normalize_amazon_result(item: dict, amazon_domain: str) -> NormalizedListing | None:
    title = (item.get("title") or "").strip()
    asin = item.get("asin")
    if not title or not asin:
        return None
    price = parse_price(item.get("extracted_price")) or parse_price(item.get("price"))
    original = (
        parse_price(item.get("extracted_old_price"))
        or parse_price(item.get("old_price"))
        or parse_price(item.get("list_price"))
    )
    link = item.get("link") or item.get("link_clean") or f"https://www.{amazon_domain}/dp/{asin}"
    delivery = item.get("delivery")
    if isinstance(delivery, list):
        delivery = " ".join(str(d) for d in delivery)
    delivery = delivery or ""
    shipping_price, shipping_known = shipping_from_text(delivery)
    if not shipping_known and item.get("prime"):
        shipping_price, shipping_known = 0.0, True  # Prime-eligible listings ship free on amazon.in
    return NormalizedListing(
        title=title,
        url=link,
        image_url=item.get("thumbnail"),
        price=price,
        original_price=original if original and price and original > price else None,
        currency="INR",
        retailer_name="Amazon.in" if amazon_domain.endswith(".in") else "Amazon",
        retailer_domain=amazon_domain,
        shipping_price=shipping_price,
        shipping_known=shipping_known,
        delivery_text=delivery or None,
        delivery_days=delivery_days_from_text(delivery),
        availability=availability_from_text(delivery)
        if delivery
        else ("in_stock" if price else "unknown"),
        rating=rating_of(item.get("rating")),
        rating_count=reviews_of(item.get("reviews")),
        identifiers={"asin": asin},
        source_provider="serpapi",
        source_engine="amazon",
    )


class AmazonSearchProvider(RetailerSearchProvider):
    name = "serpapi"
    engine = "amazon"
    retailer_slug = "amazon-india"

    @property
    def enabled(self) -> bool:
        s = get_settings()
        return s.serpapi_enabled and s.SERPAPI_ENABLE_AMAZON_SEARCH

    async def search_retailer(
        self, query: str, *, max_results: int = 10
    ) -> ProviderResult[NormalizedListing]:
        settings = get_settings()
        client = get_serpapi_client()
        params = {"k": query, "amazon_domain": settings.SERPAPI_AMAZON_DOMAIN, "language": "en_IN"}
        try:
            data = await client.search(
                self.engine, params, cache_ttl=settings.CACHE_TTL_SEARCH_SECONDS
            )
        except SerpApiError as exc:
            return ProviderResult.failure(self.name, self.engine, str(exc))
        items = []
        for raw in data.get("organic_results") or []:
            if raw.get("sponsored"):
                continue  # sponsored placements never influence our data
            listing = normalize_amazon_result(raw, settings.SERPAPI_AMAZON_DOMAIN)
            if listing:
                items.append(listing)
        return ProviderResult(
            items=items[:max_results],
            provider=self.name,
            engine=self.engine,
            cached=data.get("_buywise_cached", False),
        )
