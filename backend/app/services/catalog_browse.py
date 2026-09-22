"""Category browsing: curated models, filtered by their specifications, with
what the catalogue currently knows about their prices."""

from __future__ import annotations

import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.catalog_models import CATALOG_MODELS, CATEGORIES, SPECS_NOTE, models_for_category
from app.models import Offer, Product
from app.schemas.catalog import CatalogFacets, CatalogModelCard, CatalogPage, FacetValue
from app.services import catalog
from app.services.product_matcher import MatchType


class CatalogBrowser:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _live_figures(self, lines: list[str]) -> tuple[dict, dict]:
        """(lowest plausible new price, stores, offers) per line, and an image per line."""
        rows = (
            await self.db.execute(
                select(Product.line, Product.images, Offer.estimated_final_price, Offer.retailer_id)
                .join(Offer, Offer.product_id == Product.id)
                .where(
                    Product.line.in_(lines),
                    Offer.is_active.is_(True),
                    Offer.match_type == MatchType.EXACT.value,
                    Offer.condition == "new",
                )
            )
        ).all()
        prices: dict[str, list[float]] = {}
        retailers: dict[str, set] = {}
        images: dict[str, str] = {}
        for line, imgs, price, retailer_id in rows:
            prices.setdefault(line, []).append(float(price))
            retailers.setdefault(line, set()).add(retailer_id)
            if imgs and line not in images:
                images[line] = imgs[0]
        figures = {}
        for line, values in prices.items():
            floor = catalog.implausible_price_floor(values)
            kept = [v for v in values if floor is None or v >= floor]
            figures[line] = (min(kept) if kept else None, len(retailers[line]), len(kept))
        # A line with products but no offers yet still has an image to show.
        missing = [ln for ln in lines if ln not in images]
        if missing:
            for line, imgs in (
                await self.db.execute(
                    select(Product.line, Product.images).where(Product.line.in_(missing))
                )
            ).all():
                if imgs and line not in images:
                    images[line] = imgs[0]
        return figures, images

    async def page(
        self,
        category: str,
        *,
        see_prices: bool,
        brands: list[str] | None = None,
        ram_gb: list[int] | None = None,
        storage_gb: list[int] | None = None,
        min_screen: float | None = None,
        max_screen: float | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        sort: str = "newest",
    ) -> CatalogPage | None:
        if category not in CATEGORIES:
            return None
        models = models_for_category(category)
        figures, images = await self._live_figures([m["line"] for m in models])

        def matches(m: dict) -> bool:
            sp = m["specs"]
            if brands and m["brand"].lower() not in {b.lower() for b in brands}:
                return False
            if ram_gb and not set(sp.get("ram_gb") or []) & set(ram_gb):
                return False
            if storage_gb and not set(sp.get("storage_gb") or []) & set(storage_gb):
                return False
            if min_screen is not None and (sp.get("display_in") or 0) < min_screen:
                return False
            if max_screen is not None and (sp.get("display_in") or 0) > max_screen:
                return False
            if see_prices and (min_price is not None or max_price is not None):
                low = figures.get(m["line"], (None, 0, 0))[0]
                if low is None:
                    return False
                if min_price is not None and low < min_price:
                    return False
                if max_price is not None and low > max_price:
                    return False
            return True

        chosen = [m for m in models if matches(m)]
        cards = []
        for m in chosen:
            low, stores, offers = figures.get(m["line"], (None, 0, 0))
            cards.append(
                CatalogModelCard(
                    line=m["line"],
                    label=m["label"],
                    brand=m["brand"],
                    category=m["category"],
                    released=m.get("released"),
                    specs=m["specs"],
                    colors=m.get("colors", []),
                    image=images.get(m["line"]),
                    lowest_price=low if see_prices else None,
                    store_count=stores,
                    offer_count=offers if see_prices else 0,
                    locked=not see_prices,
                )
            )
        if sort == "price_asc":
            cards.sort(key=lambda c: (c.lowest_price is None, c.lowest_price or 0))
        elif sort == "price_desc":
            cards.sort(key=lambda c: (c.lowest_price is None, -(c.lowest_price or 0)))
        elif sort == "name":
            cards.sort(key=lambda c: c.label.lower())
        else:
            cards.sort(key=lambda c: c.released or "", reverse=True)

        # Facets count over the whole category, so a filter never hides its options.
        brand_counts = Counter(m["brand"] for m in models)
        ram_counts = Counter(r for m in models for r in (m["specs"].get("ram_gb") or []))
        storage_counts = Counter(g for m in models for g in m["specs"].get("storage_gb", []))
        facets = CatalogFacets(
            brands=[FacetValue(value=b, count=n) for b, n in sorted(brand_counts.items())],
            ram_gb=[FacetValue(value=str(r), count=n) for r, n in sorted(ram_counts.items())],
            storage_gb=[
                FacetValue(value=str(g), count=n) for g, n in sorted(storage_counts.items())
            ],
        )
        return CatalogPage(
            category=category,
            title=CATEGORIES[category],
            total=len(cards),
            models=cards,
            facets=facets,
            locked=not see_prices,
            specs_note=SPECS_NOTE,
        )


# Words that mean "show me the category", and family words that mean a brand.
_CATEGORY_WORDS = {
    "phone": "phones",
    "phones": "phones",
    "smartphone": "phones",
    "smartphones": "phones",
    "mobile": "phones",
    "mobiles": "phones",
}
_FAMILY_BRANDS = {
    "iphone": "Apple",
    "iphones": "Apple",
    "galaxy": "Samsung",
    "pixel": "Google",
    "redmi": "Xiaomi",
    "poco": "POCO",
    "nord": "OnePlus",
    "iqoo": "iQOO",
}
_MONEY = r"(?:rs\.?|₹|inr)?\s*(\d[\d,]*)\s*(k|thousand)?"
_MAX_RE = re.compile(rf"\b(?:under|below|upto|up to|less than|within|max|maximum)\s*{_MONEY}", re.I)
_MIN_RE = re.compile(rf"\b(?:above|over|more than|from|min|minimum|starting)\s*{_MONEY}", re.I)
_BETWEEN_RE = re.compile(rf"\b(?:between)\s*{_MONEY}\s*(?:and|to|-)\s*{_MONEY}", re.I)
_RAM_RE = re.compile(r"\b(\d{1,2})\s*gb\s*ram\b", re.I)
_STORAGE_RE = re.compile(r"\b(\d{2,4})\s*(gb|tb)\b(?!\s*ram)", re.I)


def _rupees(num: str, unit: str | None) -> float:
    value = float(num.replace(",", ""))
    return value * 1000 if unit else value


def catalog_for_query(query: str) -> tuple[str, dict] | None:
    """(category, filters) when a typed query browses a category rather than
    naming one product: "phone under 20000", "samsung 8gb ram", "iphone".

    Returns None for anything else, including a query that names a line
    ("iphone 17"), which the family view answers instead.
    """
    from app.services.product_normalizer import extract_attributes

    if extract_attributes(query or "").line:
        return None
    text = (query or "").lower()
    words = set(re.findall(r"[a-z0-9+]+", text))
    category = next((_CATEGORY_WORDS[w] for w in words if w in _CATEGORY_WORDS), None)
    brands = {m["brand"] for m in CATALOG_MODELS if m["brand"].lower() in words}
    brands |= {_FAMILY_BRANDS[w] for w in words if w in _FAMILY_BRANDS}
    if category is None and brands:
        category = "phones"
    if category is None:
        return None
    filters: dict = {"brands": sorted(brands)}
    between = _BETWEEN_RE.search(text)
    if between:
        lo, lo_unit, hi, hi_unit = between.groups()
        filters["min_price"], filters["max_price"] = _rupees(lo, lo_unit), _rupees(hi, hi_unit)
    else:
        if m := _MAX_RE.search(text):
            filters["max_price"] = _rupees(m.group(1), m.group(2))
        if m := _MIN_RE.search(text):
            filters["min_price"] = _rupees(m.group(1), m.group(2))
    if m := _RAM_RE.search(text):
        filters["ram_gb"] = [int(m.group(1))]
    storages = [
        int(float(n) * (1024 if u.lower() == "tb" else 1))
        for n, u in _STORAGE_RE.findall(text)
        if not (filters.get("ram_gb") and int(n) in filters["ram_gb"])
    ]
    if storages:
        filters["storage_gb"] = storages
    return category, filters
