"""Seed demo data (only meaningful in demo mode). Run: python -m app.seed.demo_data

Creates curated retailers, demo products/offers and 90 days of clearly-labelled
demo price observations so the UI can be exercised without live providers.
Never creates demo users in production.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import async_session_factory, init_db_for_dev
from app.core.logging import configure_logging
from app.data.demo_catalog import DEMO_PRODUCTS, demo_offers_for, demo_price_series
from app.models import PriceHistory, Product, Retailer
from app.providers.base import NormalizedListing
from app.services import catalog
from app.services.price_engine import true_price_from_listing
from app.services.product_matcher import MatchResult, MatchType
from app.services.product_normalizer import extract_attributes
from app.services.trust_service import TrustService


async def seed(include_history: bool = True) -> None:
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("Refusing to seed demo data in production")
    if settings.DATABASE_URL.startswith("sqlite"):
        await init_db_for_dev()
    async with async_session_factory() as db:
        existing = (
            await db.execute(
                select(func.count()).select_from(Product).where(Product.is_demo.is_(True))
            )
        ).scalar_one()
        if existing:
            print(f"Demo products already present ({existing}). Skipping.")
            return
        print("Seeding demo catalog...")
        for p in DEMO_PRODUCTS:
            attrs = extract_attributes(p["title"], p["specs"], p["brand"])
            identifiers = {k: p[k] for k in ("gtin", "mpn") if p.get(k)} | {"demo_key": p["key"]}
            product = await catalog.upsert_product(
                db,
                p["title"],
                attrs=attrs,
                identifiers=identifiers,
                brand=p["brand"],
                category=p["category"],
                image_url=p["image"],
                specifications=p["specs"],
                source_provider="demo",
                is_demo=True,
            )
            variant = await catalog.primary_variant(db, product)
            for o in demo_offers_for(p):
                listing = NormalizedListing(
                    title=p["title"],
                    url=o["url"],
                    image_url=p["image"],
                    price=o["price"],
                    original_price=o["original_price"],
                    retailer_name=o["retailer_name"],
                    retailer_domain=o["retailer_domain"],
                    seller_name=o["seller_name"],
                    shipping_price=o["shipping_price"],
                    shipping_known=o["shipping_known"],
                    coupon_code=o["coupon_code"],
                    coupon_amount=o["coupon_amount"],
                    delivery_days=o["delivery_days"],
                    availability=o["availability"],
                    rating=o["rating"],
                    rating_count=o["rating_count"],
                    brand=p["brand"],
                    category=p["category"],
                    identifiers=identifiers,
                    source_provider="demo",
                    source_engine="demo_catalog",
                    is_demo=True,
                )
                tp = true_price_from_listing(listing)
                offer = await catalog.record_offer(
                    db,
                    product,
                    listing,
                    tp,
                    MatchResult(MatchType.EXACT, 0.97, ["Demo catalog listing"]),
                    variant=variant,
                )
                if include_history:
                    retailer = offer.retailer
                    for point in demo_price_series(p, 90)[:-1]:
                        db.add(
                            PriceHistory(
                                offer_id=offer.id,
                                product_id=product.id,
                                variant_id=variant.id if variant else None,
                                retailer_id=retailer.id,
                                seller_id=offer.seller_id,
                                listed_price=point["price"],
                                shipping_price=o["shipping_price"],
                                estimated_final_price=point["price"] + (o["shipping_price"] or 0),
                                currency="INR",
                                availability="in_stock",
                                source_provider="demo",
                                source_url=o["url"],
                                confidence=0.97,
                                observed_at=point["observed_at"],
                                is_demo=True,
                            )
                        )
        await db.flush()
        trust = TrustService(db)
        for retailer in (await db.execute(select(Retailer))).scalars().all():
            await trust.ensure_retailer_score(retailer, refresh=True)
        await db.commit()
        print(
            f"Seeded {len(DEMO_PRODUCTS)} demo products with offers, price history and trust scores (all labelled is_demo)."
        )


if __name__ == "__main__":
    configure_logging()
    asyncio.run(seed())
