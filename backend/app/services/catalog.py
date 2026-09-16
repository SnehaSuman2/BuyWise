"""Catalog persistence: retailers, sellers, products, variants, offers and price observations.

All writes go through here so provenance and demo labelling are consistent.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.retailers import resolve_retailer, slugify
from app.models import (
    Offer,
    PriceHistory,
    Product,
    ProductVariant,
    Retailer,
    ReviewAnalysis,
    Seller,
)
from app.providers.base import NormalizedListing
from app.services.price_engine import TruePrice
from app.services.product_matcher import MatchResult, MatchType
from app.services.product_normalizer import NormalizedAttributes, canonical_key, extract_attributes


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def clean_identifiers(identifiers: dict | None) -> dict[str, str]:
    out = {}
    for k, v in (identifiers or {}).items():
        if v and k in ("gtin", "asin", "mpn", "sku", "google_product_id", "demo_key"):
            out[k] = str(v).strip()
    return out


async def get_or_create_retailer(
    db: AsyncSession, name: str | None, domain: str | None, is_demo: bool = False
) -> Retailer:
    curated = resolve_retailer(name, domain)
    if curated:
        result = await db.execute(select(Retailer).where(Retailer.slug == curated["slug"]))
        retailer = result.scalar_one_or_none()
        if retailer is None:
            retailer = Retailer(
                name=curated["name"],
                slug=curated["slug"],
                domain=curated["domain"],
                website_url=curated.get("website_url"),
                is_marketplace=curated.get("is_marketplace", False),
                is_curated=True,
                policies=curated.get("policies", {}),
                is_demo=False,
            )
            db.add(retailer)
            await db.flush()
        else:
            # The registry file is the source of truth for curated retailers. Without
            # this, policy facts added to the registry never reach rows created earlier,
            # and their trust scores silently keep using stale facts.
            retailer.is_curated = True
            if retailer.policies != curated.get("policies", {}):
                retailer.policies = curated.get("policies", {})
        return retailer
    display = (name or domain or "Unknown retailer").strip()
    slug = slugify(domain or display)
    result = await db.execute(select(Retailer).where(Retailer.slug == slug))
    retailer = result.scalar_one_or_none()
    if retailer is None:
        retailer = Retailer(
            name=display[:200],
            slug=slug,
            domain=domain,
            website_url=f"https://{domain}" if domain else None,
            is_marketplace=False,
            is_curated=False,
            policies={},
            is_demo=is_demo,
        )
        db.add(retailer)
        await db.flush()
    return retailer


async def get_or_create_seller(
    db: AsyncSession, retailer: Retailer, name: str | None, listing: NormalizedListing | None = None
) -> Seller | None:
    if not name:
        return None
    name = name.strip()[:300]
    result = await db.execute(
        select(Seller).where(Seller.retailer_id == retailer.id, Seller.name == name)
    )
    seller = result.scalar_one_or_none()
    if seller is None:
        seller = Seller(
            retailer_id=retailer.id,
            name=name,
            source_provider=listing.source_provider if listing else None,
            is_demo=bool(listing and listing.is_demo),
        )
        db.add(seller)
        await db.flush()
    return seller


async def find_product_by_identifiers(
    db: AsyncSession, identifiers: dict[str, str]
) -> Product | None:
    for key, column in (("gtin", Product.gtin), ("asin", Product.asin), ("mpn", Product.mpn)):
        val = identifiers.get(key)
        if val:
            result = await db.execute(select(Product).where(column == val).limit(1))
            product = result.scalar_one_or_none()
            if product:
                return product
    return None


async def upsert_product(
    db: AsyncSession,
    title: str,
    *,
    attrs: NormalizedAttributes | None = None,
    identifiers: dict | None = None,
    brand: str | None = None,
    category: str | None = None,
    image_url: str | None = None,
    description: str | None = None,
    specifications: dict | None = None,
    source_provider: str = "unknown",
    source_url: str | None = None,
    is_demo: bool = False,
) -> Product:
    identifiers = clean_identifiers(identifiers)
    attrs = attrs or extract_attributes(title, specifications, brand)
    key = canonical_key(attrs, identifiers)

    async def _find_existing() -> Product | None:
        result = await db.execute(select(Product).where(Product.canonical_key == key))
        found = result.scalar_one_or_none()
        if found is None:
            found = await find_product_by_identifiers(db, identifiers)
        return found

    product = await _find_existing()
    created = False
    if product is None:
        # Two concurrent requests (e.g. a duplicate double-fetch, or two users searching
        # the same brand-new product at once) can race to insert the same canonical_key.
        # Insert inside a SAVEPOINT so a unique-constraint conflict only rolls back this
        # attempt rather than the whole request, then fall back to whichever row won.
        try:
            async with db.begin_nested():
                product = Product(
                    name=title[:500],
                    brand=(brand or (attrs.brand.title() if attrs.brand else None)),
                    model=attrs.model,
                    category=category,
                    description=description,
                    gtin=identifiers.get("gtin"),
                    sku=identifiers.get("sku"),
                    mpn=identifiers.get("mpn"),
                    asin=identifiers.get("asin"),
                    attributes=attrs.as_dict(),
                    specifications=specifications or {},
                    images=[image_url] if image_url else [],
                    normalized_name=attrs.clean_title[:500],
                    canonical_key=key,
                    source_provider=source_provider,
                    source_url=source_url,
                    is_demo=is_demo,
                )
                db.add(product)
                await db.flush()
                variant = ProductVariant(
                    product_id=product.id,
                    name=title[:500],
                    storage=attrs.storage,
                    ram=attrs.ram,
                    color=attrs.color,
                    size=attrs.size,
                    gtin=identifiers.get("gtin"),
                    asin=identifiers.get("asin"),
                    mpn=identifiers.get("mpn"),
                    sku=identifiers.get("sku"),
                    canonical_key=f"v:{key}",
                    additional_specs={},
                )
                db.add(variant)
                await db.flush()
            created = True
        except IntegrityError:
            product = await _find_existing()
            if product is None:
                raise  # conflict was on something else entirely — a real error
    if not created:
        # enrich missing fields without overwriting known data
        if image_url and not product.images:
            product.images = [image_url]
        for field, val in (
            ("gtin", identifiers.get("gtin")),
            ("asin", identifiers.get("asin")),
            ("mpn", identifiers.get("mpn")),
        ):
            if val and not getattr(product, field):
                setattr(product, field, val)
        if description and not product.description:
            product.description = description[:5000]
        if specifications and not product.specifications:
            product.specifications = specifications
        if category and not product.category:
            product.category = category
        if is_demo is False and product.is_demo:
            product.is_demo = False
    return product


async def primary_variant(db: AsyncSession, product: Product) -> ProductVariant | None:
    result = await db.execute(
        select(ProductVariant)
        .where(ProductVariant.product_id == product.id)
        .order_by(ProductVariant.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def record_offer(
    db: AsyncSession,
    product: Product,
    listing: NormalizedListing,
    true_price: TruePrice,
    match: MatchResult,
    *,
    variant: ProductVariant | None = None,
) -> Offer:
    retailer = await get_or_create_retailer(
        db, listing.retailer_name, listing.retailer_domain, is_demo=listing.is_demo
    )
    seller = await get_or_create_seller(db, retailer, listing.seller_name, listing)
    observed = listing.observed_at or utcnow()
    stmt = select(Offer).where(Offer.product_id == product.id, Offer.retailer_id == retailer.id)
    stmt = (
        stmt.where(Offer.seller_id == seller.id)
        if seller
        else stmt.where(Offer.seller_id.is_(None))
    )
    if listing.condition:
        stmt = stmt.where(Offer.condition == listing.condition)
    result = await db.execute(stmt.limit(1))
    offer = result.scalar_one_or_none()
    values = dict(
        variant_id=variant.id if variant else None,
        seller_id=seller.id if seller else None,
        title=listing.title[:500],
        product_url=listing.url,
        external_id=listing.identifiers.get("asin") or listing.identifiers.get("google_product_id"),
        currency=listing.currency or "INR",
        listed_price=true_price.listed_price,
        original_price=true_price.original_price,
        shipping_price=true_price.shipping_price,
        shipping_known=true_price.shipping_known,
        discount_amount=true_price.discount_amount,
        coupon_code=true_price.coupon_code,
        coupon_amount=true_price.coupon_amount,
        estimated_final_price=true_price.estimated_final_price,
        final_price_known=true_price.final_price_known,
        availability=listing.availability or "unknown",
        delivery_days=listing.delivery_days,
        delivery_text=(listing.delivery_text or "")[:200] or None,
        condition=listing.condition or "new",
        rating=listing.rating,
        rating_count=listing.rating_count,
        match_type=match.match_type.value,
        match_confidence=match.confidence,
        match_reasons=match.reasons,
        source_provider=listing.source_provider,
        source_engine=listing.source_engine,
        observed_at=observed,
        is_active=True,
        is_demo=listing.is_demo,
    )
    if offer is None:
        offer = Offer(product_id=product.id, retailer_id=retailer.id, **values)
        offer.retailer = retailer  # assign relationships explicitly so no lazy load is needed later
        offer.seller = seller
        db.add(offer)
        await db.flush()
    else:
        for k, v in values.items():
            setattr(offer, k, v)
        offer.retailer = retailer
        offer.seller = seller
    # Only record price observations for listings we are confident are the same product.
    if match.match_type == MatchType.EXACT and match.confidence >= 0.7:
        db.add(
            PriceHistory(
                offer_id=offer.id,
                product_id=product.id,
                variant_id=variant.id if variant else None,
                retailer_id=retailer.id,
                seller_id=seller.id if seller else None,
                listed_price=true_price.listed_price,
                shipping_price=true_price.shipping_price,
                estimated_final_price=true_price.estimated_final_price,
                currency=listing.currency or "INR",
                availability=listing.availability,
                source_provider=listing.source_provider,
                source_url=listing.url,
                confidence=match.confidence,
                observed_at=observed,
                is_demo=listing.is_demo,
            )
        )
    return offer


async def store_review_insights(db: AsyncSession, product: Product, insights) -> None:
    """Persist retailer-aggregated review themes as this product's review analysis.

    These counts come from the retailer's own aggregation over its full review corpus,
    so they are recorded as observed facts with provenance rather than as an AI summary.
    """
    if insights is None or not (insights.themes or insights.summary):
        return

    positive, negative = [], []
    for theme in insights.themes:
        entry = {
            "theme": theme.theme,
            "count": theme.total_mentions,
            "positive": theme.positive_mentions,
            "negative": theme.negative_mentions,
            "summary": theme.summary,
            "examples": theme.examples,
        }
        # "mixed" themes are the honest cons: enough people raised the issue that it is
        # worth surfacing, even though others were satisfied.
        if theme.sentiment == "positive" and theme.positive_mentions >= theme.negative_mentions:
            entry["sentiment"] = "positive"
            positive.append(entry)
        else:
            entry["sentiment"] = "negative" if theme.sentiment == "negative" else "mixed"
            negative.append(entry)

    positive.sort(key=lambda t: -t["count"])
    negative.sort(key=lambda t: -t["negative"])

    existing = (
        await db.execute(
            select(ReviewAnalysis)
            .where(ReviewAnalysis.product_id == product.id)
            .order_by(ReviewAnalysis.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    values = dict(
        total_reviews=insights.total_reviews,
        average_rating=insights.average_rating,
        positive_themes=positive,
        negative_themes=negative,
        summary=insights.summary,
        confidence=0.8,
        provider=insights.source,
        is_demo=False,
    )
    if existing is None:
        db.add(ReviewAnalysis(product_id=product.id, **values))
    else:
        for k, v in values.items():
            setattr(existing, k, v)
    await db.flush()


async def load_product(db: AsyncSession, product_id: uuid.UUID) -> Product | None:
    result = await db.execute(select(Product).where(Product.id == product_id))
    return result.scalar_one_or_none()


async def load_offers(
    db: AsyncSession, product_id: uuid.UUID, *, include_demo: bool = True
) -> list[Offer]:
    stmt = select(Offer).where(Offer.product_id == product_id, Offer.is_active.is_(True))
    if not include_demo:
        stmt = stmt.where(Offer.is_demo.is_(False))
    result = await db.execute(stmt.order_by(Offer.estimated_final_price.asc()))
    return list(result.scalars().unique().all())
