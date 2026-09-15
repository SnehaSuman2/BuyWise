"""SerpApi Amazon Product engine — product page details for an ASIN (identifiers, specs, buybox, sellers)."""

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
    rating_of,
    reviews_of,
    shipping_from_text,
)


def _first(d: dict, *keys):
    for k in keys:
        if d.get(k) not in (None, "", []):
            return d[k]
    return None


def normalize_amazon_product(data: dict, asin: str, amazon_domain: str) -> NormalizedProductDetails:
    product = data.get("product_results") or data.get("product") or data
    title = (product.get("title") or f"Amazon product {asin}").strip()
    specs: dict[str, str] = {}
    for section in ("specifications", "product_information", "details", "attributes"):
        raw = product.get(section)
        if isinstance(raw, dict):
            specs.update({str(k): str(v) for k, v in raw.items()})
        elif isinstance(raw, list):
            for row in raw:
                if isinstance(row, dict) and row.get("name"):
                    specs[str(row["name"])] = str(row.get("value", ""))
    identifiers = {"asin": asin}
    specs_lower = {k.lower().replace("_", " "): v for k, v in specs.items()}
    for key in ("gtin", "ean", "upc", "mpn", "model number", "item model number", "model"):
        val = specs_lower.get(key) or product.get(key.replace(" ", "_"))
        if val and str(val).strip():
            identifiers.setdefault(
                {
                    "ean": "gtin",
                    "upc": "gtin",
                    "model number": "mpn",
                    "item model number": "mpn",
                    "model": "mpn",
                }.get(key, key),
                str(val).strip(),
            )
    brand = (
        _first(product, "brand", "manufacturer") or specs.get("Brand") or specs.get("Manufacturer")
    )
    images = []
    for img in product.get("images") or []:
        link = img.get("link") if isinstance(img, dict) else img
        if link:
            images.append(link)
    if product.get("thumbnail"):
        images.insert(0, product["thumbnail"])

    offers: list[NormalizedListing] = []
    buybox = product.get("buybox") or product.get("buybox_winner") or {}
    price = (
        parse_price(buybox.get("price"))
        or parse_price(product.get("extracted_price"))
        or parse_price(product.get("price"))
    )
    if price:
        delivery = _first(buybox, "delivery", "fulfillment", "shipping") or _first(
            product, "delivery"
        )
        if isinstance(delivery, dict):
            delivery = " ".join(str(v) for v in delivery.values())
        if isinstance(delivery, list):
            delivery = " ".join(str(d) for d in delivery)
        delivery = delivery or ""
        shipping_price, shipping_known = shipping_from_text(delivery)
        if not shipping_known and (buybox.get("prime") or product.get("prime")):
            shipping_price, shipping_known = 0.0, True
        seller = buybox.get("seller") or buybox.get("sold_by") or product.get("seller")
        if isinstance(seller, dict):
            seller = seller.get("name")
        offers.append(
            NormalizedListing(
                title=title,
                url=f"https://www.{amazon_domain}/dp/{asin}",
                image_url=images[0] if images else None,
                price=price,
                original_price=parse_price(buybox.get("list_price"))
                or parse_price(product.get("list_price")),
                currency="INR",
                retailer_name="Amazon.in" if amazon_domain.endswith(".in") else "Amazon",
                retailer_domain=amazon_domain,
                seller_name=seller if isinstance(seller, str) else None,
                shipping_price=shipping_price,
                shipping_known=shipping_known,
                delivery_text=delivery or None,
                delivery_days=delivery_days_from_text(delivery),
                availability=availability_from_text(
                    str(buybox.get("availability") or product.get("availability") or delivery)
                )
                if (buybox or product)
                else "unknown",
                rating=rating_of(product.get("rating")),
                rating_count=reviews_of(product.get("reviews") or product.get("reviews_count")),
                identifiers=identifiers,
                source_provider="serpapi",
                source_engine="amazon_product",
            )
        )
    for other in product.get("other_sellers") or product.get("more_buying_choices") or []:
        p = parse_price(other.get("price"))
        if not p:
            continue
        ship_text = str(other.get("delivery") or other.get("shipping") or "")
        sp, sk = shipping_from_text(ship_text)
        offers.append(
            NormalizedListing(
                title=title,
                url=f"https://www.{amazon_domain}/dp/{asin}",
                price=p,
                currency="INR",
                retailer_name="Amazon.in",
                retailer_domain=amazon_domain,
                seller_name=(other.get("seller") or {}).get("name")
                if isinstance(other.get("seller"), dict)
                else other.get("seller"),
                shipping_price=sp,
                shipping_known=sk,
                delivery_text=ship_text or None,
                condition="used" if "used" in str(other.get("condition", "")).lower() else "new",
                identifiers=identifiers,
                source_provider="serpapi",
                source_engine="amazon_product",
            )
        )
    variants = []
    for v in product.get("variants") or product.get("variations") or []:
        if isinstance(v, dict):
            variants.append(
                {
                    "asin": v.get("asin"),
                    "title": v.get("title") or v.get("name"),
                    "attributes": {
                        k: v[k] for k in ("color", "size", "style", "pattern") if v.get(k)
                    },
                }
            )
    return NormalizedProductDetails(
        title=title,
        brand=brand,
        category=(product.get("categories") or [{}])[-1].get("name")
        if isinstance(product.get("categories"), list) and product.get("categories")
        else None,
        description=product.get("description")
        or " ".join(product.get("feature_bullets") or [])[:2000]
        or None,
        images=images[:8],
        specifications=specs,
        identifiers=identifiers,
        variants=variants,
        offers=offers,
        source_provider="serpapi",
        source_engine="amazon_product",
        source_url=f"https://www.{amazon_domain}/dp/{asin}",
    )


class AmazonProductProvider(ProductDetailsProvider):
    name = "serpapi"
    engine = "amazon_product"

    @property
    def enabled(self) -> bool:
        s = get_settings()
        return s.serpapi_enabled and s.SERPAPI_ENABLE_AMAZON_PRODUCT

    async def get_product_details(
        self, identifier: str
    ) -> ProviderResult[NormalizedProductDetails]:
        settings = get_settings()
        client = get_serpapi_client()
        params = {
            "asin": identifier,
            "amazon_domain": settings.SERPAPI_AMAZON_DOMAIN,
            "language": "en_IN",
        }
        try:
            data = await client.search(
                self.engine, params, cache_ttl=settings.CACHE_TTL_OFFERS_SECONDS
            )
        except SerpApiError as exc:
            return ProviderResult.failure(self.name, self.engine, str(exc))
        details = normalize_amazon_product(data, identifier, settings.SERPAPI_AMAZON_DOMAIN)
        return ProviderResult(
            items=[details],
            provider=self.name,
            engine=self.engine,
            cached=data.get("_buywise_cached", False),
        )
