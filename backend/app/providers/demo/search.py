"""Demo product search / retailer search / product details / image search providers."""

from __future__ import annotations

from app.data.demo_catalog import DEMO_PRODUCTS, demo_offers_for
from app.providers.base import (
    ImageSearchProvider,
    NormalizedListing,
    NormalizedProductDetails,
    ProductDetailsProvider,
    ProductSearchProvider,
    ProviderResult,
    RetailerSearchProvider,
)


def _listing_from_offer(product: dict, offer: dict) -> NormalizedListing:
    return NormalizedListing(
        title=product["title"],
        url=offer["url"],
        image_url=product["image"],
        price=offer["price"],
        original_price=offer["original_price"],
        currency="INR",
        retailer_name=offer["retailer_name"],
        retailer_domain=offer["retailer_domain"],
        seller_name=offer["seller_name"],
        shipping_price=offer["shipping_price"],
        shipping_known=offer["shipping_known"],
        coupon_code=offer["coupon_code"],
        coupon_amount=offer["coupon_amount"],
        delivery_days=offer["delivery_days"],
        delivery_text=f"Delivery in {offer['delivery_days']} days",
        availability=offer["availability"],
        rating=offer["rating"],
        rating_count=offer["rating_count"],
        brand=product["brand"],
        category=product["category"],
        identifiers={k: product[k] for k in ("gtin", "mpn") if product.get(k)}
        | {"demo_key": product["key"]},
        source_provider="demo",
        source_engine="demo_catalog",
        is_demo=True,
    )


def _score(product: dict, query: str) -> float:
    q = query.lower()
    tokens = [t for t in q.replace(",", " ").split() if len(t) > 1]
    hay = f"{product['title']} {product['brand']} {product['model']} {product['category']} {' '.join(product['specs'].values())}".lower()
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t in hay)
    # category synonyms
    synonyms = {
        "headphone": "headphones",
        "headphones": "headphones",
        "earbuds": "headphones",
        "earphones": "headphones",
        "phone": "smartphones",
        "smartphone": "smartphones",
        "mobile": "smartphones",
        "laptop": "laptops",
        "keyboard": "keyboards",
        "mouse": "mice",
        "tv": "tvs",
        "television": "tvs",
        "watch": "smartwatches",
        "smartwatch": "smartwatches",
        "tablet": "tablets",
        "speaker": "speakers",
        "vacuum": "home appliances",
    }
    for t in tokens:
        if (
            synonyms.get(t.rstrip("s")) == product["category"].lower()
            or synonyms.get(t) == product["category"].lower()
        ):
            hits += 1.5
    return hits / (len(tokens) + 0.5)


class DemoProductSearchProvider(ProductSearchProvider):
    name = "demo"
    engine = "demo_catalog"
    is_demo = True

    async def search_products(
        self, query: str, *, max_results: int = 20, min_price=None, max_price=None
    ) -> ProviderResult[NormalizedListing]:
        scored = sorted(((_score(p, query), p) for p in DEMO_PRODUCTS), key=lambda x: -x[0])
        items: list[NormalizedListing] = []
        for score, product in scored:
            if score <= 0.2:
                continue
            for offer in demo_offers_for(product):
                if min_price is not None and offer["price"] < min_price:
                    continue
                if max_price is not None and offer["price"] > max_price:
                    continue
                items.append(_listing_from_offer(product, offer))
            if len(items) >= max_results * 3:
                break
        return ProviderResult(items=items, provider=self.name, engine=self.engine, is_demo=True)


class DemoRetailerSearchProvider(RetailerSearchProvider):
    name = "demo"
    engine = "demo_amazon"
    retailer_slug = "amazon-india"
    is_demo = True

    async def search_retailer(
        self, query: str, *, max_results: int = 10
    ) -> ProviderResult[NormalizedListing]:
        inner = await DemoProductSearchProvider().search_products(
            query, max_results=max_results * 4
        )
        items = [i for i in inner.items if i.retailer_domain == "amazon.in"][:max_results]
        return ProviderResult(items=items, provider=self.name, engine=self.engine, is_demo=True)


class DemoProductDetailsProvider(ProductDetailsProvider):
    name = "demo"
    engine = "demo_product"
    is_demo = True

    async def get_product_details(
        self, identifier: str
    ) -> ProviderResult[NormalizedProductDetails]:
        product = next(
            (
                p
                for p in DEMO_PRODUCTS
                if p["key"] == identifier
                or p.get("mpn") == identifier
                or p.get("gtin") == identifier
            ),
            None,
        )
        if not product:
            return ProviderResult.failure(self.name, self.engine, "Demo product not found")
        details = NormalizedProductDetails(
            title=product["title"],
            brand=product["brand"],
            model=product["model"],
            category=product["category"],
            images=[product["image"]],
            specifications=product["specs"],
            identifiers={k: product[k] for k in ("gtin", "mpn") if product.get(k)}
            | {"demo_key": product["key"]},
            offers=[_listing_from_offer(product, o) for o in demo_offers_for(product)],
            source_provider="demo",
            source_engine=self.engine,
            is_demo=True,
        )
        return ProviderResult(items=[details], provider=self.name, engine=self.engine, is_demo=True)


class DemoImageSearchProvider(ImageSearchProvider):
    name = "demo"
    engine = "demo_lens"
    is_demo = True

    async def search_by_image(self, image_url: str) -> ProviderResult[NormalizedListing]:
        # Without a real vision API we cannot identify the image. Return a clearly labelled demo set.
        items = []
        for product in DEMO_PRODUCTS[:3]:
            for offer in demo_offers_for(product)[:2]:
                items.append(_listing_from_offer(product, offer))
        return ProviderResult(items=items, provider=self.name, engine=self.engine, is_demo=True)
