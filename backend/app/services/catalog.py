"""Catalog persistence: retailers, sellers, products, variants, offers and price observations.

All writes go through here so provenance and demo labelling are consistent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import and_, delete, or_, select
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


@dataclass
class PersistCache:
    """Per-request memo for the lookups that persisting a search repeats.

    A search persists around sixty listings across two dozen products, and each
    listing used to cost its own retailer lookup, seller lookup, variant lookup and
    existing-offer lookup: several hundred round trips to the database, which from
    the API host is the bulk of a thirty-second search. Retailers, sellers and
    variants repeat constantly within one search, and a product's existing offers
    can be read once. Nothing here outlives the request.
    """

    retailers: dict[str, Retailer] = field(default_factory=dict)
    sellers: dict[tuple[uuid.UUID, str], Seller] = field(default_factory=dict)
    variants: dict[uuid.UUID, ProductVariant | None] = field(default_factory=dict)
    offers: dict[uuid.UUID, dict[tuple, Offer]] = field(default_factory=dict)
    # Price observations for offers created in this request. A new offer has no id
    # until the session flushes, so these are written by flush_pending() after one
    # flush for all new offers, instead of one flush per offer.
    pending_history: list[tuple[Offer, dict]] = field(default_factory=list)
    # Retailer slugs and (retailer, seller name) pairs already looked up for this
    # request, found or not. A miss here is a row that does not exist, so it is
    # created without asking the database again.
    known_retailer_slugs: set[str] = field(default_factory=set)
    known_sellers: set[tuple[uuid.UUID, str]] = field(default_factory=set)


async def preload_for_products(
    db: AsyncSession, product_ids: set[uuid.UUID], cache: PersistCache
) -> None:
    """Load every product's primary variant and existing offers in two queries."""
    ids = [i for i in product_ids if i not in cache.variants or i not in cache.offers]
    if not ids:
        return
    variants = (
        (
            await db.execute(
                select(ProductVariant)
                .where(ProductVariant.product_id.in_(ids))
                .order_by(ProductVariant.created_at)
            )
        )
        .scalars()
        .all()
    )
    for pid in ids:
        cache.variants.setdefault(pid, None)
        cache.offers.setdefault(pid, {})
    for v in variants:
        if cache.variants.get(v.product_id) is None:
            cache.variants[v.product_id] = v
    offers = (
        (await db.execute(select(Offer).where(Offer.product_id.in_(ids)))).scalars().unique().all()
    )
    for o in offers:
        cache.offers[o.product_id][(o.retailer_id, o.seller_id, o.condition or "new")] = o


async def flush_pending(db: AsyncSession, cache: PersistCache) -> None:
    """One flush for every new offer, then their price observations, then one more."""
    await db.flush()
    for offer, history in cache.pending_history:
        db.add(PriceHistory(offer_id=offer.id, **history))
    cache.pending_history.clear()
    await db.flush()


async def load_offers_many(
    db: AsyncSession, product_ids: set[uuid.UUID]
) -> dict[uuid.UUID, list[Offer]]:
    """Active offers for many products in one query, cheapest first per product."""
    out: dict[uuid.UUID, list[Offer]] = {pid: [] for pid in product_ids}
    if not product_ids:
        return out
    rows = (
        (
            await db.execute(
                select(Offer)
                .where(Offer.product_id.in_(list(product_ids)), Offer.is_active.is_(True))
                .order_by(Offer.estimated_final_price.asc())
            )
        )
        .scalars()
        .unique()
        .all()
    )
    for o in rows:
        out.setdefault(o.product_id, []).append(o)
    return out


async def get_or_create_retailer(
    db: AsyncSession,
    name: str | None,
    domain: str | None,
    is_demo: bool = False,
    cache: PersistCache | None = None,
) -> Retailer:
    curated = resolve_retailer(name, domain)
    cache_key = (
        curated["slug"] if curated else slugify(domain or (name or "Unknown retailer").strip())
    )
    if cache is not None and cache_key in cache.retailers:
        return cache.retailers[cache_key]
    if cache is not None and cache_key in cache.known_retailer_slugs:
        # Preloaded and absent: create it without another round trip. The id is
        # client-generated, so offers can reference it before any flush.
        retailer = _new_retailer(name, domain, is_demo, curated)
        db.add(retailer)
        cache.retailers[cache_key] = retailer
        return retailer
    retailer = await _get_or_create_retailer(db, name, domain, is_demo, curated)
    if cache is not None:
        cache.retailers[cache_key] = retailer
    return retailer


def _new_retailer(name: str | None, domain: str | None, is_demo: bool, curated) -> Retailer:
    if curated:
        return Retailer(
            id=uuid.uuid4(),
            name=curated["name"],
            slug=curated["slug"],
            domain=curated["domain"],
            website_url=curated.get("website_url"),
            is_marketplace=curated.get("is_marketplace", False),
            is_curated=True,
            policies=curated.get("policies", {}),
            is_demo=False,
        )
    display = (name or domain or "Unknown retailer").strip()
    return Retailer(
        id=uuid.uuid4(),
        name=display[:200],
        slug=slugify(domain or display),
        domain=domain,
        website_url=f"https://{domain}" if domain else None,
        is_marketplace=False,
        is_curated=False,
        policies={},
        is_demo=is_demo,
    )


async def _get_or_create_retailer(
    db: AsyncSession, name: str | None, domain: str | None, is_demo: bool, curated
) -> Retailer:
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
    db: AsyncSession,
    retailer: Retailer,
    name: str | None,
    listing: NormalizedListing | None = None,
    cache: PersistCache | None = None,
) -> Seller | None:
    if not name:
        return None
    name = name.strip()[:300]
    if cache is not None and (retailer.id, name) in cache.sellers:
        return cache.sellers[(retailer.id, name)]
    known_absent = cache is not None and (retailer.id, name) in cache.known_sellers
    seller = None
    if not known_absent:
        result = await db.execute(
            select(Seller).where(Seller.retailer_id == retailer.id, Seller.name == name)
        )
        seller = result.scalar_one_or_none()
    if seller is None:
        seller = Seller(
            id=uuid.uuid4(),
            retailer_id=retailer.id,
            name=name,
            source_provider=listing.source_provider if listing else None,
            is_demo=bool(listing and listing.is_demo),
        )
        db.add(seller)
        if cache is None:
            await db.flush()
    if cache is not None:
        cache.sellers[(retailer.id, name)] = seller
    return seller


def product_key_for(
    attrs: NormalizedAttributes, identifiers: dict, condition: str = "new"
) -> tuple[str, dict]:
    """The canonical key and identifiers a product is stored under.

    One rule, used both when a product is written and when a batch of them is
    looked up beforehand, so the two can never disagree. A used or refurbished
    item is its own product: it shares the sealed item's key and often its ASIN.
    """
    key = canonical_key(attrs, identifiers)
    if condition != "new":
        return f"{key}:{condition}", {}
    return key, identifiers


@dataclass
class Prefetched:
    """Existing products for a batch of keys and identifiers, from two queries.

    Persisting a search used to look every product up one at a time: a query by
    key and up to three by identifier, each a round trip. For two dozen products
    that was most of the time a search spent writing.
    """

    by_key: dict[str, Product] = field(default_factory=dict)
    by_ident: dict[tuple[str, str], Product] = field(default_factory=dict)

    def remember(self, product: Product, key: str, identifiers: dict) -> None:
        """A product created for this batch; later groups with its key reuse it."""
        self.by_key[key] = product
        for kind in ("gtin", "asin", "mpn"):
            val = identifiers.get(kind)
            if val:
                self.by_ident.setdefault((kind, val), product)

    def find(self, key: str, identifiers: dict) -> Product | None:
        if key in self.by_key:
            return self.by_key[key]
        for kind in ("gtin", "asin", "mpn"):
            val = identifiers.get(kind)
            if val and (kind, val) in self.by_ident:
                return self.by_ident[(kind, val)]
        return None


async def prefetch_products(db: AsyncSession, wanted: list[tuple[str, dict]]) -> Prefetched:
    out = Prefetched()
    keys = {k for k, _ in wanted if k}
    if keys:
        rows = (await db.execute(select(Product).where(Product.canonical_key.in_(keys)))).scalars()
        for row in rows:
            out.by_key[row.canonical_key] = row
    idents = {
        (kind, ids[kind]) for _, ids in wanted for kind in ("gtin", "asin", "mpn") if ids.get(kind)
    }
    if idents:
        clauses = []
        for kind in ("gtin", "asin", "mpn"):
            values = [v for k, v in idents if k == kind]
            if values:
                clauses.append(getattr(Product, kind).in_(values))
        rows = (await db.execute(select(Product).where(or_(*clauses)))).scalars()
        for row in rows:
            for kind in ("gtin", "asin", "mpn"):
                val = getattr(row, kind)
                if val:
                    out.by_ident.setdefault((kind, val), row)
    return out


async def preload_retailers(db: AsyncSession, listings, cache: PersistCache) -> None:
    """Load every retailer a batch of listings names, in one query."""
    slugs: dict[str, dict | None] = {}
    for listing in listings:
        curated = resolve_retailer(listing.retailer_name, listing.retailer_domain)
        slug = (
            curated["slug"]
            if curated
            else slugify(
                listing.retailer_domain or (listing.retailer_name or "Unknown retailer").strip()
            )
        )
        slugs.setdefault(slug, curated)
    missing = [slug for slug in slugs if slug not in cache.retailers]
    cache.known_retailer_slugs.update(missing)
    if not missing:
        return
    rows = (await db.execute(select(Retailer).where(Retailer.slug.in_(missing)))).scalars()
    for retailer in rows:
        curated = slugs.get(retailer.slug)
        if curated:
            # The registry stays the source of truth for curated retailers.
            retailer.is_curated = True
            if retailer.policies != curated.get("policies", {}):
                retailer.policies = curated.get("policies", {})
        cache.retailers[retailer.slug] = retailer


async def preload_sellers(db: AsyncSession, listings, cache: PersistCache) -> None:
    """Load every seller a batch of listings names, in one query.

    Runs after preload_retailers: a seller belongs to a retailer, and a retailer
    that does not exist yet has no sellers to load.
    """
    wanted: set[tuple[uuid.UUID, str]] = set()
    for listing in listings:
        if not listing.seller_name:
            continue
        curated = resolve_retailer(listing.retailer_name, listing.retailer_domain)
        slug = (
            curated["slug"]
            if curated
            else slugify(
                listing.retailer_domain or (listing.retailer_name or "Unknown retailer").strip()
            )
        )
        retailer = cache.retailers.get(slug)
        if retailer is not None:
            wanted.add((retailer.id, listing.seller_name.strip()[:300]))
    wanted -= set(cache.sellers)
    cache.known_sellers.update(wanted)
    if not wanted:
        return
    retailer_ids = {rid for rid, _ in wanted}
    names = {name for _, name in wanted}
    rows = (
        await db.execute(
            select(Seller).where(Seller.retailer_id.in_(retailer_ids), Seller.name.in_(names))
        )
    ).scalars()
    for seller in rows:
        if (seller.retailer_id, seller.name) in wanted:
            cache.sellers[(seller.retailer_id, seller.name)] = seller


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
    condition: str = "new",
    extra_attributes: dict | None = None,
    prefetched: Prefetched | None = None,
    defer_create: bool = False,
) -> Product:
    """Find or create the product a listing group belongs to.

    With defer_create, the prefetched batch is the only lookup and a new product
    is added to the session without flushing: the caller flushes the whole batch
    once, inside a savepoint, and retries one product at a time if another
    request inserted one of them first.
    """
    identifiers = clean_identifiers(identifiers)
    attrs = attrs or extract_attributes(title, specifications, brand)
    key, identifiers = product_key_for(attrs, identifiers, condition)

    async def _find_existing() -> Product | None:
        if prefetched is not None:
            found = prefetched.find(key, identifiers)
            if found is not None or defer_create:
                return found
        result = await db.execute(select(Product).where(Product.canonical_key == key))
        found = result.scalar_one_or_none()
        if found is None:
            found = await find_product_by_identifiers(db, identifiers)
        return found

    def _new_product() -> Product:
        return Product(
            id=uuid.uuid4(),
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

    def _new_variant(product: Product) -> ProductVariant:
        return ProductVariant(
            id=uuid.uuid4(),
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

    product = await _find_existing()
    created = False
    if product is None and defer_create and prefetched is not None:
        product = _new_product()
        product.variants = [_new_variant(product)]
        db.add(product)
        prefetched.remember(product, key, identifiers)
        created = True
    elif product is None:
        # Two concurrent requests (e.g. a duplicate double-fetch, or two users searching
        # the same brand-new product at once) can race to insert the same canonical_key.
        # Insert inside a SAVEPOINT so a unique-constraint conflict only rolls back this
        # attempt rather than the whole request, then fall back to whichever row won.
        try:
            async with db.begin_nested():
                product = _new_product()
                db.add(product)
                await db.flush()
                db.add(_new_variant(product))
                await db.flush()
            created = True
        except IntegrityError:
            product = await _find_existing()
            if product is None:
                raise  # conflict was on something else entirely — a real error
    if extra_attributes:
        merged = dict(product.attributes or {})
        merged.update({k: v for k, v in extra_attributes.items() if v not in (None, "", False)})
        if merged != (product.attributes or {}):
            product.attributes = merged
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


async def primary_variant(
    db: AsyncSession, product: Product, cache: PersistCache | None = None
) -> ProductVariant | None:
    if cache is not None and product.id in cache.variants:
        return cache.variants[product.id]
    result = await db.execute(
        select(ProductVariant)
        .where(ProductVariant.product_id == product.id)
        .order_by(ProductVariant.created_at)
        .limit(1)
    )
    variant = result.scalar_one_or_none()
    if cache is not None:
        cache.variants[product.id] = variant
    return variant


async def record_offer(
    db: AsyncSession,
    product: Product,
    listing: NormalizedListing,
    true_price: TruePrice,
    match: MatchResult,
    *,
    variant: ProductVariant | None = None,
    cache: PersistCache | None = None,
) -> Offer:
    retailer = await get_or_create_retailer(
        db, listing.retailer_name, listing.retailer_domain, is_demo=listing.is_demo, cache=cache
    )
    seller = await get_or_create_seller(db, retailer, listing.seller_name, listing, cache=cache)
    observed = listing.observed_at or utcnow()
    condition = listing.condition or "new"
    offer_key = (retailer.id, seller.id if seller else None, condition)
    if cache is not None:
        # One read of the product's offers serves every listing for it in this request.
        if product.id not in cache.offers:
            rows = (
                (await db.execute(select(Offer).where(Offer.product_id == product.id)))
                .scalars()
                .all()
            )
            cache.offers[product.id] = {
                (o.retailer_id, o.seller_id, o.condition or "new"): o for o in rows
            }
        offer = cache.offers[product.id].get(offer_key)
    else:
        stmt = select(Offer).where(Offer.product_id == product.id, Offer.retailer_id == retailer.id)
        stmt = (
            stmt.where(Offer.seller_id == seller.id)
            if seller
            else stmt.where(Offer.seller_id.is_(None))
        )
        stmt = stmt.where(Offer.condition == condition)
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
        if cache is None:
            await db.flush()
        else:
            cache.offers.setdefault(product.id, {})[offer_key] = offer
    else:
        for k, v in values.items():
            setattr(offer, k, v)
        offer.retailer = retailer
        offer.seller = seller
    # Only record price observations for listings we are confident are the same product.
    if match.match_type == MatchType.EXACT and match.confidence >= 0.7:
        history = dict(
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
        if cache is not None:
            cache.pending_history.append((offer, history))
        else:
            db.add(PriceHistory(offer_id=offer.id, **history))
    return offer


def implausible_price_floor(prices: list[float]) -> float | None:
    """The price below which a listing is not plausibly the same item as the rest.

    Reference is the upper quartile of the prices, not the median: spam is cheap and
    genuine listings sit at the top, so when spam makes up half of a small family the
    median is itself a spam price (seen live: ₹273, ₹6,607 and ₹2,12,923 for one
    phone gave a median of ₹6,607 and the ₹6,607 case survived). Needs at least
    three prices; the floor is a fifth of the reference, far below any real discount.
    """
    priced = sorted(p for p in prices if p and p > 0)
    if len(priced) < 3:
        return None
    reference = priced[min(len(priced) - 1, (len(priced) * 3) // 4)]
    return reference * 0.2


@dataclass
class Retirement:
    remaining: list[Offer]
    retired: list[Offer]
    floor: float | None


def retire_implausible_offers(product: Product, offers: list[Offer]) -> Retirement:
    """Mark implausible offers inactive on the given list.

    Pure over the objects it is given, so a caller that already holds a product's
    offers pays no query. See deactivate_implausible_offers for the rule.
    """
    product_attrs = extract_attributes(product.name)
    remaining, retired = [], []
    for offer in offers:
        title_attrs = extract_attributes(offer.title or "")
        if (title_attrs.is_accessory and not product_attrs.is_accessory) or title_attrs.is_rental:
            offer.is_active = False
            retired.append(offer)
        else:
            remaining.append(offer)
    exact = [o for o in remaining if o.match_type == MatchType.EXACT.value]
    basis = exact if len(exact) >= 3 else remaining
    floor = implausible_price_floor([float(o.estimated_final_price) for o in basis])
    if floor is None:
        return Retirement(remaining, retired, None)
    kept = []
    for offer in remaining:
        if float(offer.estimated_final_price) < floor:
            offer.is_active = False
            retired.append(offer)
        else:
            kept.append(offer)
    return Retirement(kept, retired, floor)


async def purge_implausible_history_many(
    db: AsyncSession, items: list[tuple[Product, Retirement]]
) -> int:
    """purge_implausible_history for many products in one statement."""
    clauses = []
    for product, retirement in items:
        conditions = []
        if retirement.retired:
            conditions.append(PriceHistory.offer_id.in_([o.id for o in retirement.retired]))
        if retirement.floor is not None:
            conditions.append(PriceHistory.estimated_final_price < retirement.floor)
        if conditions:
            clauses.append(and_(PriceHistory.product_id == product.id, or_(*conditions)))
    if not clauses:
        return 0
    result = await db.execute(delete(PriceHistory).where(or_(*clauses)))
    return int(result.rowcount or 0)


async def purge_implausible_history(
    db: AsyncSession, product: Product, retirement: Retirement
) -> int:
    """Remove price observations that were never observations of this product.

    An offer retired as a spare part, a rental or an implausible price recorded
    observations while it was believed to be the product, and the history card
    reads observations, not offers: a ₹273 "iPhone 17 Pro Max" kept showing as the
    product's current lowest price a day after its offer was retired. Its rows go,
    along with any older row below the same self-referential floor, so history
    already on record heals the same way offers do. Returns rows removed.
    """
    conditions = []
    if retirement.retired:
        conditions.append(PriceHistory.offer_id.in_([o.id for o in retirement.retired]))
    if retirement.floor is not None:
        conditions.append(PriceHistory.estimated_final_price < retirement.floor)
    if not conditions:
        return 0
    result = await db.execute(
        delete(PriceHistory).where(PriceHistory.product_id == product.id, or_(*conditions))
    )
    return int(result.rowcount or 0)


async def deactivate_implausible_offers(db: AsyncSession, product: Product) -> int:
    """Retire stored offers priced far below this product's other offers, or whose
    own listing title is a spare part or a rental.

    Filtering fresh listings cannot remove an offer that was recorded before the
    filter existed, and such an offer keeps setting the product's lowest price for
    ever. This applies the same self-referential rule to what is already on record,
    every time the product is persisted or viewed, so the catalogue heals itself.
    Exact-match offers are the reference when there are enough of them; nothing is
    deleted, only marked inactive. Returns the number retired.
    """
    offers = await load_offers(db, product.id)
    retirement = retire_implausible_offers(product, offers)
    purged = await purge_implausible_history(db, product, retirement)
    if retirement.retired or purged:
        await db.flush()
    return len(retirement.retired)


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
