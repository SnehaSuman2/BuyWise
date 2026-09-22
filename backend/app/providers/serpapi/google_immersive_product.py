"""Every store's price for one Google Shopping product.

Google Shopping search returns a single merchant per product. The product's
own page lists every store, and that is what a price comparison is. SerpApi
exposes it as the Google Immersive Product engine, keyed by the token that came
with the search result; the older Google Product engine, keyed by product_id,
is the fallback and is what SearchApi offers.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.providers.base import NormalizedListing, ProviderResult, parse_price
from app.providers.search_client import SearchApiError, get_search_client
from app.providers.serpapi.common import (
    availability_from_text,
    condition_from_title,
    delivery_days_from_text,
    domain_of,
    extract_asin,
    rating_of,
    reviews_of,
    unwrap_google_redirect,
)
from app.providers.serpapi.google_product import GoogleProductProvider


def normalize_store(
    item: dict, product_id: str | None, *, provider: str
) -> NormalizedListing | None:
    name = item.get("name")
    link = unwrap_google_redirect(item.get("link"))
    price = parse_price(item.get("extracted_price")) or parse_price(item.get("price"))
    if not name or price is None:
        return None
    shipping = item.get("shipping_extracted")
    shipping_text = str(item.get("shipping") or "").lower()
    shipping_known = shipping is not None or "free" in shipping_text
    shipping_price = (
        float(shipping) if shipping is not None else (0.0 if "free" in shipping_text else None)
    )
    original = parse_price(item.get("extracted_original_price"))
    details = item.get("details_and_offers") or []
    details_text = " ".join(d.get("text", "") if isinstance(d, dict) else str(d) for d in details)
    identifiers = {}
    if product_id:
        identifiers["google_product_id"] = product_id
    asin = extract_asin(link)
    if asin:
        identifiers["asin"] = asin
    title = item.get("title") or name
    return NormalizedListing(
        title=title,
        url=link,
        price=price,
        original_price=original if original and original > price else None,
        currency="INR",
        retailer_name=name,
        retailer_domain=domain_of(link)
        if link and "google." not in (domain_of(link) or "")
        else None,
        shipping_price=shipping_price,
        shipping_known=shipping_known,
        delivery_text=details_text or None,
        delivery_days=delivery_days_from_text(details_text),
        availability=availability_from_text(details_text) if details_text else "in_stock",
        condition=condition_from_title(title),
        rating=rating_of(item.get("rating")),
        rating_count=reviews_of(item.get("reviews")),
        identifiers=identifiers,
        source_provider=provider,
        source_engine="google_immersive_product",
    )


class GoogleOffersEnricher:
    """One entry point: give it what the search result carried, get every store."""

    engine = "google_immersive_product"

    @property
    def name(self) -> str:
        return get_search_client().provider

    @property
    def enabled(self) -> bool:
        s = get_settings()
        return s.search_api_enabled and s.SERPAPI_ENABLE_GOOGLE_PRODUCT

    async def offers_for(
        self, *, token: str | None, product_id: str | None
    ) -> ProviderResult[NormalizedListing]:
        settings = get_settings()
        client = get_search_client()
        if client.provider == "serpapi" and token:
            try:
                data = await client.search(
                    self.engine,
                    {"page_token": token},
                    cache_ttl=settings.CACHE_TTL_OFFERS_SECONDS,
                )
            except SearchApiError as exc:
                return ProviderResult.failure(self.name, self.engine, str(exc))
            stores = (data.get("product_results") or {}).get("stores") or []
            items = [
                listing
                for listing in (
                    normalize_store(raw, product_id, provider=client.provider) for raw in stores
                )
                if listing
            ]
            return ProviderResult(
                items=items,
                provider=self.name,
                engine=self.engine,
                cached=data.get("_buywise_cached", False),
                stale=data.get("_buywise_stale", False),
            )
        if product_id:
            res = await GoogleProductProvider().get_product_details(product_id)
            if not res.ok or not res.items:
                return ProviderResult.failure(self.name, "google_product", res.error or "no data")
            return ProviderResult(
                items=res.items[0].offers,
                provider=self.name,
                engine="google_product",
                cached=res.cached,
                stale=res.stale,
            )
        return ProviderResult.failure(self.name, self.engine, "nothing to look up")
