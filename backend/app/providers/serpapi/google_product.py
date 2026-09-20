"""SerpApi Google Product engine — offers from many sellers for one Google product id.

This is the most direct way to get the *same* product listed at several Indian
retailers, including base price + shipping (true price) where Google shows it.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.providers.base import (
    NormalizedListing,
    NormalizedProductDetails,
    ProductDetailsProvider,
    ProviderResult,
    parse_price,
)
from app.providers.serpapi.client import SerpApiError, get_serpapi_client
from app.providers.serpapi.common import (
    availability_from_text,
    delivery_days_from_text,
    domain_of,
    extract_asin,
    rating_of,
    reviews_of,
    unwrap_google_redirect,
)


def normalize_seller(item: dict, product_id: str) -> NormalizedListing | None:
    name = item.get("name") or item.get("seller") or item.get("source")
    link = unwrap_google_redirect(item.get("link") or item.get("direct_link"))
    base = parse_price(item.get("base_price"))
    total = parse_price(item.get("total_price"))
    additional = item.get("additional_price") or {}
    shipping = parse_price(additional.get("shipping")) if isinstance(additional, dict) else None
    shipping_known = False
    if isinstance(additional, dict) and "shipping" in additional:
        raw_ship = str(additional.get("shipping", "")).lower()
        if "free" in raw_ship or shipping is not None:
            shipping = shipping or 0.0
            shipping_known = True
    if base is None and total is None:
        return None
    if base is None and total is not None:
        base = total - (shipping or 0)
    details = item.get("details_and_offers") or []
    details_text = " ".join(d.get("text", "") if isinstance(d, dict) else str(d) for d in details)
    identifiers = {"google_product_id": product_id}
    asin = extract_asin(link)
    if asin:
        identifiers["asin"] = asin
    return NormalizedListing(
        title=item.get("title") or name or "Offer",
        url=link,
        price=base,
        currency="INR",
        retailer_name=name,
        retailer_domain=domain_of(link)
        if link and "google." not in (domain_of(link) or "")
        else None,
        shipping_price=shipping,
        shipping_known=shipping_known,
        delivery_text=details_text or None,
        delivery_days=delivery_days_from_text(details_text),
        availability=availability_from_text(details_text) if details_text else "in_stock",
        rating=rating_of(item.get("rating")),
        rating_count=reviews_of(item.get("reviews")),
        identifiers=identifiers,
        source_provider="serpapi",
        source_engine="google_product",
    )


class GoogleProductProvider(ProductDetailsProvider):
    name = "serpapi"
    engine = "google_product"

    @property
    def enabled(self) -> bool:
        s = get_settings()
        return s.search_api_enabled and s.SERPAPI_ENABLE_GOOGLE_PRODUCT

    async def get_product_details(
        self, identifier: str
    ) -> ProviderResult[NormalizedProductDetails]:
        settings = get_settings()
        client = get_serpapi_client()
        params = {
            "product_id": identifier,
            "gl": settings.SERPAPI_COUNTRY,
            "hl": settings.SERPAPI_LANGUAGE,
            "offers": "1",
        }
        try:
            data = await client.search(
                self.engine, params, cache_ttl=settings.CACHE_TTL_OFFERS_SECONDS
            )
        except SerpApiError as exc:
            return ProviderResult.failure(self.name, self.engine, str(exc))
        product = data.get("product_results") or {}
        sellers = data.get("sellers_results") or {}
        offers = []
        for raw in sellers.get("online_sellers") or []:
            listing = normalize_seller(raw, identifier)
            if listing:
                offers.append(listing)
        specs = {}
        for spec in product.get("specs") or []:
            if isinstance(spec, dict) and spec.get("name"):
                specs[str(spec["name"])] = str(spec.get("value", ""))
        details = NormalizedProductDetails(
            title=product.get("title") or f"Google product {identifier}",
            description=product.get("description"),
            images=[
                m.get("link")
                for m in (product.get("media") or [])
                if isinstance(m, dict) and m.get("link")
            ][:6],
            specifications=specs,
            identifiers={"google_product_id": identifier},
            offers=offers,
            source_provider="serpapi",
            source_engine=self.engine,
        )
        return ProviderResult(
            items=[details],
            provider=self.name,
            engine=self.engine,
            cached=data.get("_buywise_cached", False),
        )
