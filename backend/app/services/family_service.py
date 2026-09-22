"""One line, every variant, every store.

A search for "iPhone 17" used to answer with a grid of near-identical cards:
each colour Amazon sells is its own product, each carrying one offer. What the
shopper wants is one place that says: here are the storage sizes, here are the
colours, and here is every store's price for the one you pick, cheapest first.
That is a family: the products of one line, read together.

Nothing here is priced from outside. The "above the other stores" flag compares
an offer only with the other offers for the same variant.
"""

from __future__ import annotations

import re
import statistics
import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.catalog_models import SPECS_NOTE, catalog_model, storage_label
from app.models import Offer, Product
from app.models.trust import TrustScore
from app.schemas.family import FamilyOffer, FamilyVariant, ProductFamily
from app.services import catalog
from app.services.affiliate_service import go_url_for
from app.services.product_matcher import MatchType
from app.services.product_normalizer import NormalizedAttributes, extract_attributes, line_label

ABOVE_MARKET_RATIO = 1.35


@dataclass
class _Member:
    product: Product
    attrs: NormalizedAttributes


def _storage_order(storage: str | None) -> float:
    if not storage:
        return float("inf")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(GB|TB)", storage)
    if not m:
        return float("inf") - 1
    value = float(m.group(1))
    return value * 1024 if m.group(2) == "TB" else value


def is_family_member(attrs: NormalizedAttributes, line: str) -> bool:
    """A product of this line that is the product itself, not something sold
    around it."""
    return bool(
        attrs.line == line
        and not attrs.is_accessory
        and not attrs.is_rental
        and not attrs.is_service
        and not attrs.is_catalogue
    )


class FamilyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def products_for_line(
        self, line: str, seed_ids: set[uuid.UUID] | None = None
    ) -> list[_Member]:
        """Every product of the line the catalogue knows, plus the seeds."""
        # Rows carry their line since the column was added; older rows are found
        # by the family word in their name and checked the same way.
        family_word = re.match(r"[a-z]+", line)
        stmt = select(Product).where(Product.line == line)
        if family_word:
            stmt = select(Product).where(
                or_(Product.line == line, Product.name.ilike(f"%{family_word.group(0)}%"))
            )
        stmt = stmt.order_by(Product.updated_at.desc()).limit(300)
        rows = list((await self.db.execute(stmt)).scalars().all())
        found = {p.id for p in rows}
        missing = [pid for pid in (seed_ids or set()) if pid not in found]
        if missing:
            rows += list(
                (await self.db.execute(select(Product).where(Product.id.in_(missing))))
                .scalars()
                .all()
            )
        members = []
        for p in rows:
            attrs = extract_attributes(p.name, None, p.brand)
            if is_family_member(attrs, line):
                members.append(_Member(p, attrs))
        return members

    async def _trust_by_retailer(self, retailer_ids: set[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Latest stored retailer score each, in one query. Never gathers evidence."""
        if not retailer_ids:
            return {}
        rows = (
            await self.db.execute(
                select(TrustScore)
                .where(
                    TrustScore.retailer_id.in_(list(retailer_ids)),
                    TrustScore.seller_id.is_(None),
                )
                .order_by(TrustScore.calculated_at.desc())
            )
        ).scalars()
        out: dict[uuid.UUID, int] = {}
        for score in rows:
            if score.retailer_id not in out and score.overall_score is not None:
                out[score.retailer_id] = int(score.overall_score)
        return out

    async def build(
        self,
        line: str,
        *,
        seed_ids: set[uuid.UUID] | None = None,
        see_prices: bool = True,
        selected_storage: str | None = None,
        label: str | None = None,
    ) -> ProductFamily | None:
        members = await self.products_for_line(line, seed_ids)
        if not members:
            curated = catalog_model(line)
            if curated is None:
                return None
            sizes = [storage_label(gb) for gb in curated["specs"].get("storage_gb", [])]
            family = ProductFamily(
                line=line,
                label=curated["label"],
                brand=curated["brand"],
                curated=True,
                specs=curated["specs"],
                official_storages=sizes,
                official_colors=list(curated.get("colors", [])),
                released=curated.get("released"),
                specs_note=SPECS_NOTE,
                variants=[FamilyVariant(storage=s, label=s, official=True) for s in sizes],
                selected_storage=selected_storage if selected_storage in sizes else None,
            )
            return family if see_prices else self.withhold(family)
        by_id = {m.product.id: m for m in members}
        offers_by_product = await catalog.load_offers_many(self.db, set(by_id))
        exact: list[tuple[_Member, Offer]] = []
        for pid, offers in offers_by_product.items():
            for o in offers:
                if o.match_type == MatchType.EXACT.value and o.retailer is not None:
                    exact.append((by_id[pid], o))
        # Same self-referential rule as everywhere else: a price far below the
        # rest of the line is not a price for this line.
        new_prices = [
            float(o.estimated_final_price) for m, o in exact if (o.condition or "new") == "new"
        ]
        floor = catalog.implausible_price_floor(new_prices)
        if floor is not None:
            exact = [(m, o) for m, o in exact if float(o.estimated_final_price) >= floor]

        trust = await self._trust_by_retailer({o.retailer_id for _, o in exact})

        curated = catalog_model(line)
        official = [
            storage_label(gb) for gb in (curated or {}).get("specs", {}).get("storage_gb", [])
        ]
        buckets: dict[str | None, list[tuple[_Member, Offer]]] = {}
        # Every size the maker sells is listed, even before a store has been
        # seen for it; then whatever else the listings say.
        for size in official:
            buckets[size] = []
        for m, o in exact:
            buckets.setdefault(m.attrs.storage, []).append((m, o))
        for m in members:
            buckets.setdefault(m.attrs.storage, [])

        variants: list[FamilyVariant] = []
        for storage in sorted(buckets, key=_storage_order):
            pairs = buckets[storage]
            products = {m.product.id: m for m, _ in pairs} | {
                m.product.id: m for m in members if m.attrs.storage == storage
            }
            colors = sorted({m.attrs.color for m in products.values() if m.attrs.color})
            new_pairs = [(m, o) for m, o in pairs if (o.condition or "new") == "new"]
            typical = (
                statistics.median(float(o.estimated_final_price) for _, o in new_pairs)
                if len(new_pairs) >= 3
                else None
            )
            rows: list[FamilyOffer] = []
            for m, o in sorted(
                pairs,
                key=lambda mo: (
                    (mo[1].condition or "new") != "new",
                    float(mo[1].estimated_final_price),
                ),
            ):
                price = float(o.estimated_final_price)
                rows.append(
                    FamilyOffer(
                        offer_id=o.id,
                        product_id=m.product.id,
                        retailer_id=o.retailer_id,
                        retailer_name=o.retailer.name,
                        seller_name=o.seller.name if o.seller else None,
                        storage=storage,
                        color=m.attrs.color,
                        condition=o.condition or "new",
                        price=price,
                        listed_price=float(o.listed_price),
                        shipping_known=bool(o.shipping_known),
                        final_price_known=bool(o.final_price_known),
                        availability=o.availability or "unknown",
                        delivery_text=o.delivery_text,
                        delivery_days=o.delivery_days,
                        trust_score=trust.get(o.retailer_id),
                        go_url=go_url_for(o.id),
                        observed_at=o.observed_at,
                        is_demo=bool(o.is_demo),
                        above_market=bool(
                            typical
                            and (o.condition or "new") == "new"
                            and price > typical * ABOVE_MARKET_RATIO
                        ),
                    )
                )
            prices = [r.price for r in rows if r.condition == "new"] or [r.price for r in rows]
            variants.append(
                FamilyVariant(
                    storage=storage,
                    label=storage or "Listings not stating storage",
                    official=storage in official,
                    colors=colors,
                    product_ids=list(products),
                    offer_count=len(rows),
                    retailer_count=len({r.retailer_id for r in rows}),
                    lowest_price=min(prices) if prices else None,
                    highest_price=max(prices) if prices else None,
                    typical_price=typical,
                    offers=rows,
                )
            )

        all_rows = [r for v in variants for r in v.offers]
        total_retailers = len({r.retailer_id for r in all_rows})
        first = members[0]
        image = next((m.product.images[0] for m in members if m.product.images), None)
        family = ProductFamily(
            line=line,
            label=(curated or {}).get("label") or label or first.attrs.line_label or line,
            brand=(curated or {}).get("brand") or first.product.brand,
            image=image,
            curated=curated is not None,
            specs=(curated or {}).get("specs"),
            official_storages=official,
            official_colors=list((curated or {}).get("colors", [])),
            released=(curated or {}).get("released"),
            specs_note=SPECS_NOTE if curated else None,
            variants=variants,
            selected_storage=selected_storage
            if any(v.storage == selected_storage for v in variants)
            else None,
            total_offers=len(all_rows),
            total_retailers=total_retailers,
            product_count=len(members),
            is_demo=bool(all_rows) and all(r.is_demo for r in all_rows),
        )
        if see_prices:
            return family
        return self.withhold(family)

    @staticmethod
    def withhold(family: ProductFamily) -> ProductFamily:
        """Everything priced removed, on the server, for viewers without Pro."""
        sizes = sum(1 for v in family.variants if v.storage)
        hint = (
            f"Prices from {family.total_retailers} store{'s' if family.total_retailers != 1 else ''}"
            + (f" across {sizes} storage options" if sizes > 1 else "")
            + " with Pro"
        )
        return family.model_copy(
            update={
                "locked": True,
                "hint": hint,
                "variants": [
                    v.model_copy(
                        update={
                            "offers": [],
                            "lowest_price": None,
                            "highest_price": None,
                            "typical_price": None,
                        }
                    )
                    for v in family.variants
                ],
            }
        )


def family_for_query(query_text: str) -> tuple[str, str, str | None] | None:
    """(line token, label, storage) when a typed query names a product line."""
    attrs = extract_attributes(query_text or "")
    if not attrs.line or attrs.is_accessory or attrs.is_rental or attrs.is_service:
        return None
    return attrs.line, attrs.line_label or line_label(attrs.line, None, None), attrs.storage
