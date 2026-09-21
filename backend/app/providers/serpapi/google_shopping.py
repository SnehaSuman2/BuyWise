"""Google Shopping engine → NormalizedListing (SerpApi or SearchApi transport)."""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.providers.base import NormalizedListing, ProductSearchProvider, ProviderResult, parse_price
from app.providers.search_client import SearchApiError, get_search_client
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

logger = logging.getLogger(__name__)


def normalize_shopping_result(
    item: dict, *, engine: str = "google_shopping", provider: str = "serpapi"
) -> NormalizedListing | None:
    title = (item.get("title") or "").strip()
    if not title:
        return None
    price = parse_price(item.get("extracted_price")) or parse_price(item.get("price"))
    original = parse_price(item.get("extracted_old_price")) or parse_price(item.get("old_price"))
    link = unwrap_google_redirect(item.get("link") or item.get("product_link"))
    delivery = item.get("delivery") or ""
    if isinstance(delivery, list):
        delivery = " ".join(str(d) for d in delivery)
    extensions = item.get("extensions") or []
    ext_text = " ".join(str(e) for e in extensions)
    shipping_price, shipping_known = shipping_from_text(delivery or ext_text)
    identifiers: dict[str, str] = {}
    if item.get("product_id"):
        identifiers["google_product_id"] = str(item["product_id"])
    asin = extract_asin(link)
    if asin:
        identifiers["asin"] = asin
    condition = "new"
    if (
        item.get("second_hand_condition")
        or "refurbished" in ext_text.lower()
        or "used" in ext_text.lower()
    ):
        condition = "used"
    condition = condition_from_title(title, condition)
    return NormalizedListing(
        title=title,
        url=link,
        image_url=item.get("thumbnail"),
        price=price,
        original_price=original if original and price and original > price else None,
        currency="INR",
        # SerpApi names the merchant "source"; SearchApi names it "seller".
        retailer_name=item.get("source") or item.get("seller"),
        retailer_domain=domain_of(link)
        if link and "google." not in (domain_of(link) or "")
        else None,
        shipping_price=shipping_price,
        shipping_known=shipping_known,
        delivery_text=delivery or None,
        delivery_days=delivery_days_from_text(delivery),
        availability=availability_from_text(delivery, ext_text)
        if (delivery or ext_text)
        else ("in_stock" if price else "unknown"),
        condition=condition,
        rating=rating_of(item.get("rating")),
        rating_count=reviews_of(item.get("reviews")),
        snippet=item.get("snippet"),
        identifiers=identifiers,
        source_provider=provider,
        source_engine=engine,
    )


class GoogleShoppingProvider(ProductSearchProvider):
    engine = "google_shopping"

    @property
    def name(self) -> str:
        return get_search_client().provider

    @property
    def enabled(self) -> bool:
        s = get_settings()
        return s.search_api_enabled and s.SERPAPI_ENABLE_GOOGLE_SHOPPING

    async def search_products(
        self, query: str, *, max_results: int = 20, min_price=None, max_price=None
    ) -> ProviderResult[NormalizedListing]:
        settings = get_settings()
        client = get_search_client()
        params: dict = {
            "q": query,
            "gl": settings.SERPAPI_COUNTRY,
            "hl": settings.SERPAPI_LANGUAGE,
            "location": "India",
        }
        if client.provider == "serpapi":
            params["num"] = min(max(max_results, 10), 40)
            # Google Shopping price filters (tbs), SerpApi only; the search layer
            # applies the same bounds locally for every vendor.
            tbs = []
            if min_price is not None:
                tbs.append(f"ppr_min:{int(min_price)}")
            if max_price is not None:
                tbs.append(f"ppr_max:{int(max_price)}")
            if tbs:
                params["tbs"] = "mr:1,price:1," + ",".join(tbs)
        try:
            data = await client.search(
                self.engine, params, cache_ttl=settings.CACHE_TTL_SEARCH_SECONDS
            )
        except SearchApiError as exc:
            return ProviderResult.failure(self.name, self.engine, str(exc))
        items = []
        for raw in (data.get("shopping_results") or []) + (
            data.get("inline_shopping_results") or []
        ):
            listing = normalize_shopping_result(raw, provider=client.provider)
            if listing:
                items.append(listing)
        return ProviderResult(
            items=items[:max_results],
            provider=self.name,
            engine=self.engine,
            cached=data.get("_buywise_cached", False),
        )
