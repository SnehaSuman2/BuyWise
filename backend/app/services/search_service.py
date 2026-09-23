"""Search orchestration: text / URL / image → normalized listings → grouped products → persisted.

Routing (minimum API calls):
  text  : Google Shopping (→ Bing Shopping fallback) ; Amazon Search only if fewer than 3 results
  url   : detect retailer → Amazon Product (ASIN) or slug-derived query → Google Shopping
  image : Google Lens → grouped listings
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.http import UnsafeURLError, validate_public_http_url
from app.data.retailers import resolve_retailer
from app.models import Product, Search
from app.providers import registry
from app.providers.base import NormalizedListing, ProviderResult
from app.providers.serpapi.common import condition_from_title, extract_asin
from app.schemas.common import DataMeta
from app.schemas.product import MatchInfo, ProductSearchResult
from app.schemas.search import SearchRequest, SearchResponse
from app.services import catalog
from app.services.market_filter import filter_to_market
from app.services.price_engine import true_price_from_listing
from app.services.product_matcher import Candidate, MatchResult, MatchType, match_products
from app.services.product_normalizer import (
    KNOWN_BRANDS,
    PRODUCT_LINE_BRANDS,
    extract_attributes,
    search_query_for,
)

logger = logging.getLogger(__name__)


# Store lookups still running after their search answered. Tests drain this;
# in production the tasks simply finish and write to the database.
BACKGROUND_TASKS: dict[asyncio.Task, object] = {}


async def drain_background_tasks() -> None:
    while BACKGROUND_TASKS:
        await asyncio.gather(*list(BACKGROUND_TASKS), return_exceptions=True)


@dataclass
class ListingGroup:
    reference: Candidate
    listings: list[tuple[NormalizedListing, MatchResult]] = field(default_factory=list)
    product: Product | None = None
    reference_match: MatchResult | None = None  # vs an external reference (URL/image)

    @property
    def title(self) -> str:
        return self.reference.title


def group_listings(
    listings: list[NormalizedListing], min_confidence: float = 0.75
) -> list[ListingGroup]:
    """Cluster listings into products using the matcher (exact matches join a group)."""
    groups: list[ListingGroup] = []
    for listing in listings:
        # Providers do not all flag condition; the title is where Indian resellers say
        # "Refurbished". Normalise it here so every provider's listings group alike.
        listing.condition = condition_from_title(listing.title, listing.condition or "new")
        cand = Candidate(
            listing.title, catalog.clean_identifiers(listing.identifiers), listing.brand
        )
        best: tuple[ListingGroup, MatchResult] | None = None
        for group in groups:
            # A refurbished or used listing is not the same product as a sealed one,
            # however identical the title. It gets its own group, and so its own
            # card and price, instead of becoming a "cheapest offer" for the new one.
            if listing.condition != (group.listings[0][0].condition or "new"):
                continue
            res = match_products(group.reference, cand)
            if res.match_type == MatchType.EXACT and res.confidence >= min_confidence:
                if best is None or res.confidence > best[1].confidence:
                    best = (group, res)
        if best:
            group, res = best
            group.listings.append((listing, res))
            # prefer a reference that carries hard identifiers
            if not group.reference.identifiers and cand.identifiers:
                group.reference = cand
        else:
            groups.append(
                ListingGroup(
                    reference=cand,
                    listings=[(listing, MatchResult(MatchType.EXACT, 1.0, ["Reference listing"]))],
                )
            )
    return groups


def filter_accessories(listings: list, query_text: str | None) -> tuple[list, int]:
    """Drop accessory listings unless the shopper asked for an accessory.

    A ₹999 skin sitting beside ₹22,000 headphones reads as a suspiciously cheap
    version of the product, even when correctly separated into its own entry.
    Someone who wants one can say so ("WH-1000XM5 skins"), and then they are kept.

    Returns (kept, dropped_count).
    """
    query_attrs = extract_attributes(query_text or "")
    if query_attrs.is_accessory:
        return listings, 0

    kept, dropped = [], 0
    for listing in listings:
        if extract_attributes(listing.title, None, listing.brand).is_accessory:
            dropped += 1
        else:
            kept.append(listing)
    return kept, dropped


def filter_rentals(listings: list, query_text: str | None) -> tuple[list, int]:
    """Drop rental listings unless the shopper is looking to rent.

    A rental price ("₹573 on rent") is not a price for owning the product. Left in,
    it can become the cheapest figure shown for something nobody can actually buy
    at that price. Returns (kept, dropped_count).
    """
    query_attrs = extract_attributes(query_text or "")
    if query_attrs.is_rental:
        return listings, 0

    kept, dropped = [], 0
    for listing in listings:
        if extract_attributes(listing.title, None, listing.brand).is_rental:
            dropped += 1
        else:
            kept.append(listing)
    return kept, dropped


def filter_services(listings: list, query_text: str | None) -> tuple[list, int]:
    """Drop services sold under a product's name (unlocks, activations, repairs)
    and catalogue-style listings that name every model at once, unless the
    shopper asked for one. Neither is a price for the product."""
    query_attrs = extract_attributes(query_text or "")
    kept, dropped = [], 0
    for listing in listings:
        a = extract_attributes(listing.title, None, listing.brand)
        if (a.is_service and not query_attrs.is_service) or a.is_catalogue:
            dropped += 1
        else:
            kept.append(listing)
    return kept, dropped


def filter_implausible_price_outliers(listings: list) -> tuple[list, int]:
    """Drop a listing priced far below others that are almost certainly the same
    device line, even when they never join the same product group.

    group_listings() only merges listings that reach 75% match confidence, and a
    bare title ("Apple iPhone 17 Pro") loses confidence against a fuller one
    ("Apple iPhone 17 Pro 512GB Silver MG8K4HN/A") for stating no variant details —
    exactly the gap a spam or mismatched listing hides in. A real case: a ₹148
    "Apple iPhone 17 Pro" from Meesho sat alone, ungrouped, beside genuine listings
    of the same phone above ₹1,20,000 — never compared against them because it
    never joined their group.

    This checks price plausibility on its own, before grouping, clustered only by
    the model's line token (so "iPhone 17 Pro" and "iPhone 17 Pro Max" are never
    compared against each other — they are different products with legitimately
    different prices). The comparison is entirely self-referential, against other
    listings identified as the same line in this same search, so no external price
    data is assumed. A cluster needs at least 3 priced listings before anything is
    checked, so one early or unusual listing cannot become "the family" on its own,
    and the bar — a fifth of the median — sits far below any ordinary discount.
    """
    families: dict[str, list] = {}
    unclustered = []
    for listing in listings:
        tokens = extract_attributes(listing.title, None, listing.brand).model_tokens
        if tokens and listing.price:
            families.setdefault(tokens[0], []).append(listing)
        else:
            unclustered.append(listing)

    kept = list(unclustered)
    dropped = 0
    for family in families.values():
        floor = catalog.implausible_price_floor([listing.price for listing in family])
        if floor is None:
            kept.extend(family)
            continue
        for listing in family:
            if listing.price < floor:
                dropped += 1
            else:
                kept.append(listing)
    return kept, dropped


def hide_non_product_cards(
    results: list[ProductSearchResult], query_text: str | None
) -> tuple[list[ProductSearchResult], int]:
    """Hide product rows whose own name is a spare part or a rental.

    Fresh listings with such titles never reach the results any more, but rows
    created by earlier searches keep their original names. Unless the shopper asked
    for an accessory or a rental, those rows are not products either.
    """
    q = extract_attributes(query_text or "")
    kept, hidden = [], 0
    for r in results:
        a = extract_attributes(r.name, None, r.brand)
        if (
            (a.is_accessory and not q.is_accessory)
            or (a.is_rental and not q.is_rental)
            or (a.is_service and not q.is_service)
            or a.is_catalogue
        ):
            hidden += 1
        else:
            kept.append(r)
    return kept, hidden


def hide_implausible_results(
    results: list[ProductSearchResult],
) -> tuple[list[ProductSearchResult], int]:
    """Drop result cards whose price is implausible against their model family.

    A product whose only stored offers are spam (a ₹6,607 "iPhone 17 Pro Max" from
    a case maker) has nothing inside itself to compare against, so the per-product
    check cannot touch it. Across the result set it does have neighbours: the other
    products of the same line. Same rule, same floor, keyed by the line token.
    """
    families: dict[str, list[ProductSearchResult]] = {}
    for r in results:
        tokens = extract_attributes(r.name, None, r.brand).model_tokens
        if tokens and r.lowest_price:
            families.setdefault(tokens[0], []).append(r)
    hidden: set = set()
    for family in families.values():
        floor = catalog.implausible_price_floor([r.lowest_price for r in family])
        if floor is None:
            continue
        hidden.update(r.id for r in family if r.lowest_price < floor)
    return [r for r in results if r.id not in hidden], len(hidden)


def query_from_url(url: str) -> str:
    """Derive a search query from a retailer product URL slug."""
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    candidates = [
        s for s in segments if len(s) > 12 and "-" in s and not re.fullmatch(r"[A-Za-z0-9]{10,}", s)
    ]
    slug = max(candidates, key=len) if candidates else (segments[0] if segments else "")
    slug = re.sub(
        r"\b(p|dp|product|itm[a-z0-9]+|buy|online)\b",
        " ",
        slug.replace("-", " ").replace("_", " "),
        flags=re.I,
    )
    return re.sub(r"\s+", " ", slug).strip()[:120]


class SearchService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    # ------------------------------------------------------------ public
    async def search(
        self, request: SearchRequest, user_id: uuid.UUID | None = None, user=None
    ) -> SearchResponse:
        started = time.perf_counter()
        from app.services.subscription_service import entitlements_for

        # Read entitlements now: enrichment commits mid-request, which expires the
        # user instance, and an async session will not lazily refresh it later.
        see_prices = (await entitlements_for(self.db, user)).see_prices
        warnings: list[str] = []
        providers_used: list[str] = []
        cached = False
        detected_retailer = None
        reference: Candidate | None = None
        reference_product_id: str | None = None
        ref_product: Product | None = None
        unavailable_reason: str | None = None

        if request.url:
            query_type = "url"
            try:
                url = validate_public_http_url(request.url)
            except UnsafeURLError as exc:
                raise ValueError(str(exc)) from exc
            listings, reference, detected_retailer, ref_product, meta = await self._search_by_url(
                url
            )
            providers_used += meta["providers"]
            warnings += meta["warnings"]
            cached = meta["cached"]
            if ref_product is not None:
                reference_product_id = str(ref_product.id)
            query_text = reference.title if reference else url
        elif request.image_url or request.image_base64:
            query_type = "image"
            image_url = request.image_url
            if not image_url and request.image_base64:
                image_url = await self._store_uploaded_image(request.image_base64)
                if image_url is None:
                    warnings.append(
                        "Image uploads need a publicly reachable API_PUBLIC_URL for Google Lens; using demo results."
                    )
            listings, reference, meta = await self._search_by_image(image_url or "")
            providers_used += meta["providers"]
            warnings += meta["warnings"]
            cached = meta["cached"]
            query_text = reference.title if reference else "image search"
            warnings.append(
                "Photo results are visual look-alikes found by image search, not confirmed "
                "matches. If your photo is a screenshot of a product page, paste that "
                "page's link instead to get the exact product."
            )
        else:
            query_type = "text"
            query_text = (request.query or "").strip()
            if not query_text:
                raise ValueError("Provide a query, url or image")
            listings, meta = await self._search_text(
                query_text, request.min_price, request.max_price
            )
            providers_used += meta["providers"]
            warnings += meta["warnings"]
            cached = meta["cached"]
            unavailable_reason = meta.get("unavailable")

        providers_ms = int((time.perf_counter() - started) * 1000)

        # Keep only merchants that actually sell into India before anything is grouped,
        # matched or persisted — a foreign listing's converted price is not a price the
        # shopper can pay, and it would otherwise become a "cheapest" pick.
        # A listing that names no merchant at all cannot be bought from, trusted or
        # compared, so it is not a result. It would otherwise appear as "Unknown
        # retailer" and could even become the cheapest pick.
        listings = [l for l in listings if (l.retailer_name or l.retailer_domain)]
        listings, excluded_count, excluded_names = filter_to_market(listings)
        if excluded_count:
            shown = ", ".join(excluded_names[:4])
            more = f" and {len(excluded_names) - 4} more" if len(excluded_names) > 4 else ""
            warnings.append(
                f"Excluded {excluded_count} listing(s) from outside India ({shown}{more})."
            )

        # Accessories for the product are not the product. Unless the shopper asked for
        # one, keep them out of the result set entirely rather than listing them beside
        # the real item at a fraction of the price.
        accessory_query = reference.title if reference is not None else query_text
        listings, dropped_accessories = filter_accessories(listings, accessory_query)
        if dropped_accessories:
            warnings.append(
                f"Hid {dropped_accessories} accessory listing(s) (cases, skins, straps). "
                f"Add the accessory name to your search to see them."
            )
        listings, dropped_rentals = filter_rentals(listings, accessory_query)
        if dropped_rentals:
            warnings.append(f"Hid {dropped_rentals} rental listing(s) — not a purchase price.")
        listings, dropped_services = filter_services(listings, accessory_query)
        if dropped_services:
            warnings.append(
                f"Hid {dropped_services} listing(s) that are services or catalogue "
                f"entries, not the product."
            )

        listings, dropped_implausible = filter_implausible_price_outliers(listings)
        if dropped_implausible:
            warnings.append(
                f"Hid {dropped_implausible} listing(s) priced far below the rest for the "
                f"same product (likely spam or a mismatched listing)."
            )

        groups = group_listings(listings)
        if reference is not None:
            for g in groups:
                g.reference_match = match_products(reference, g.reference)
            if query_type == "image":
                # The anchor is a visual look-alike, not a product the shopper named.
                # Nothing matched against it can honestly be called exact.
                for g in groups:
                    m = g.reference_match
                    if m.match_type == MatchType.EXACT:
                        g.reference_match = MatchResult(
                            MatchType.SIMILAR,
                            min(m.confidence, 0.7),
                            ["Looks like your photo; verify the product before buying"]
                            + [r for r in m.reasons if r != "Reference listing"],
                        )
            groups.sort(
                key=lambda g: (
                    -(g.reference_match.match_type == MatchType.EXACT),
                    -g.reference_match.confidence,
                )
            )
        elif query_type == "text":
            groups, hidden_models = self._filter_to_named_model(groups, query_text)
            if hidden_models:
                warnings.append(
                    f"Hid {hidden_models} product(s) that are a different model from the "
                    f"one you searched for."
                )

        persist_started = time.perf_counter()
        results = await self._persist_groups(groups, query_type, reference_product=ref_product)
        persist_ms = int((time.perf_counter() - persist_started) * 1000)
        if not results and unavailable_reason and query_type == "text":
            # The vendor is down or out of quota. Answer from what the catalogue
            # already knows rather than showing nothing, and say so plainly.
            results = await self._catalog_fallback(query_text)
            if results:
                warnings = [w for w in warnings if not w.startswith("Live retailer search")]
                warnings.append(
                    "Live retailer search is temporarily unavailable. Showing products "
                    "BuyWise has seen before; prices may be out of date."
                )
        # If the URL flow produced a reference product not represented in results, put it first.
        if reference_product_id and all(str(r.id) != reference_product_id for r in results):
            ref = await catalog.load_product(self.db, uuid.UUID(reference_product_id))
            if ref:
                results.insert(0, await self._result_for_product(ref, None))

        before = {r.id: r.offer_count for r in results}
        results = await self._enrich_top(results)
        if any(r.offer_count > before.get(r.id, 0) for r in results):
            enricher = registry.offers_enricher()
            if enricher is not None:
                providers_used.append(f"{enricher.name}:{enricher.engine}")
        results, hidden_non_products = hide_non_product_cards(results, accessory_query)
        if hidden_non_products:
            warnings.append(
                f"Hid {hidden_non_products} accessory or rental product(s) recorded earlier."
            )
        results, hidden_cards = hide_implausible_results(results)
        if hidden_cards:
            warnings.append(
                f"Hid {hidden_cards} product(s) whose only prices are far below the rest "
                f"of the same model (likely spam or mismatched listings)."
            )
        results = self._sort(results, request.sort_by)
        family = None
        catalog_page = None
        catalog_filters = None
        if query_type == "text":
            family = await self._family_for(query_text, results, see_prices)
            if family is None:
                catalog_page, catalog_filters = await self._catalog_for(query_text, see_prices)
        if not see_prices:
            results = self.withhold_prices(results)
        total = len(results)
        start = (request.page - 1) * request.page_size
        page_results = results[start : start + request.page_size]
        is_demo = any(l.is_demo for l in listings) if listings else self.settings.demo_mode
        data_mode = (
            "demo"
            if is_demo and all(l.is_demo for l in listings)
            else ("mixed" if is_demo else "live")
        )

        self.db.add(
            Search(
                user_id=user_id,
                query_text=query_text[:1000],
                query_type=query_type,
                query_url=request.url,
                results_count=total,
                filters={"min_price": request.min_price, "max_price": request.max_price},
                data_mode=data_mode,
                providers_used=providers_used,
                cache_hit=cached,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        )
        return SearchResponse(
            query=query_text,
            query_type=query_type,
            detected_retailer=detected_retailer,
            reference_product_id=reference_product_id,
            total_results=total,
            page=request.page,
            page_size=request.page_size,
            results=page_results,
            family=family,
            catalog=catalog_page,
            catalog_filters=catalog_filters,
            meta=DataMeta(
                data_mode=data_mode,
                is_demo=is_demo,
                providers=sorted(set(providers_used)),
                cached=cached,
                warnings=warnings,
                timings={
                    "providers_ms": providers_ms,
                    "persist_ms": persist_ms,
                    "total_ms": int((time.perf_counter() - started) * 1000),
                },
            ),
        )

    # ------------------------------------------------------------ routing
    async def _search_text(
        self, query: str, min_price, max_price
    ) -> tuple[list[NormalizedListing], dict]:
        providers_used, warnings, listings, cached = [], [], [], False
        failures: list[str] = []
        stale = False
        # Google Shopping and Amazon, together, every time. Amazon used to be asked
        # only when Google returned almost nothing, so most products arrived with a
        # single offer. Its listings carry clean titles and ASINs, which is what
        # lets the same product from two stores recognise itself.
        shopping = [
            (p, p.search_products(query, max_results=40, min_price=min_price, max_price=max_price))
            for p in registry.product_search_providers()
        ]
        amazon = [
            (p, p.search_retailer(query, max_results=10))
            for p in registry.retailer_search_providers()
        ]
        results = await asyncio.gather(*[c for _, c in shopping + amazon], return_exceptions=True)
        # One source failing while another answers is not news the shopper can act
        # on, and saying so on a page full of results only makes the site look
        # broken. These are held back unless nothing was found at all.
        soft_warnings: list[str] = []
        for (provider, _), res in zip(shopping + amazon, results, strict=True):
            providers_used.append(f"{provider.name}:{provider.engine}")
            if isinstance(res, BaseException):
                soft_warnings.append(f"{provider.engine} temporarily unavailable.")
                failures.append(f"{provider.engine}: {type(res).__name__}")
                continue
            cached = cached or res.cached
            stale = stale or res.stale
            if not res.ok:
                soft_warnings.append(f"{provider.engine} temporarily unavailable.")
                failures.append(res.error or provider.engine)
                continue
            listings.extend(res.items)
        priced = [l for l in listings if l.price]
        # Price bounds are applied here for every vendor; only SerpApi's Google
        # Shopping engine can filter server-side, and even then not exactly.
        if min_price is not None:
            priced = [l for l in priced if l.price >= min_price]
        if max_price is not None:
            priced = [l for l in priced if l.price <= max_price]
        if not priced:
            warnings.extend(soft_warnings)
        unavailable = None
        if not priced and failures and not listings:
            unavailable = "; ".join(str(f) for f in failures)[:200]
            warnings = [
                "Live retailer search is temporarily unavailable (search provider quota "
                "or credentials). Results may be incomplete."
            ]
        if stale:
            warnings.append(
                "Live search is temporarily unavailable, so these are the most recent "
                "results BuyWise has. Prices may have changed since."
            )
        return priced, {
            "providers": providers_used,
            "warnings": warnings,
            "cached": cached,
            "unavailable": unavailable,
        }

    async def _search_by_url(self, url: str):
        providers_used, warnings, listings, cached = [], [], [], False
        parsed = urlparse(url)
        curated = resolve_retailer(None, parsed.hostname)
        detected = curated["name"] if curated else (parsed.hostname or None)
        reference: Candidate | None = None
        ref_product: Product | None = None
        asin = extract_asin(url) if curated and curated["slug"] == "amazon-india" else None

        if asin:
            provider = registry.amazon_product_provider()
            res = await provider.get_product_details(asin)
            providers_used.append(f"{provider.name}:{provider.engine}")
            cached = res.cached
            if res.ok and res.items:
                details = res.items[0]
                reference = Candidate(
                    details.title,
                    catalog.clean_identifiers(details.identifiers),
                    details.brand,
                    details.specifications,
                )
                ref_product = await catalog.upsert_product(
                    self.db,
                    details.title,
                    attrs=reference.attrs,
                    identifiers=details.identifiers,
                    brand=details.brand,
                    category=details.category,
                    image_urls=list(details.images or []),
                    description=details.description,
                    specifications=details.specifications,
                    source_provider=details.source_provider,
                    source_url=details.source_url,
                    is_demo=details.is_demo,
                )
                await catalog.store_review_insights(self.db, ref_product, details.review_insights)
                variant = await catalog.primary_variant(self.db, ref_product)
                for offer in details.offers:
                    tp = true_price_from_listing(offer)
                    if tp:
                        await catalog.record_offer(
                            self.db,
                            ref_product,
                            offer,
                            tp,
                            MatchResult(MatchType.EXACT, 0.98, ["Product page listing (ASIN)"]),
                            variant=variant,
                        )
                listings.extend(details.offers)
            else:
                warnings.append(
                    "Amazon product details unavailable; searching by URL text instead."
                )
        if reference is None:
            query = query_from_url(url)
            if not query:
                raise ValueError("Could not extract a product from that URL")
            reference = Candidate(query)
        text_listings, meta = await self._search_text(self._fanout_query(reference), None, None)
        listings.extend(text_listings)
        providers_used += meta["providers"]
        warnings += meta["warnings"]
        cached = cached or meta["cached"]
        return (
            listings,
            reference,
            detected,
            ref_product,
            {"providers": providers_used, "warnings": warnings, "cached": cached},
        )

    @staticmethod
    def _fanout_query(reference: Candidate) -> str:
        return search_query_for(reference.title, reference.brand, reference.specs)

    @staticmethod
    def _filter_to_named_model(groups: list[ListingGroup], query_text: str):
        """Drop result groups for a different model than the one the shopper named.

        "iPhone 17" used to return iPhone 13, 15 and 16 as well, because to a token
        similarity they are the same words. When the query carries a model or
        generation, groups whose model conflicts are removed rather than ranked
        lower: a different model is not an answer to that question at any price.
        Queries without a model ("wireless headphones") are left alone.
        """
        query_ref = Candidate(query_text)
        if not query_ref.attrs.model_tokens:
            return groups, 0
        q = query_ref.attrs
        # The query's brand is only trusted when it is a brand we know, not the
        # first word of a model name ("pixaplay 35").
        q_brand = (
            q.brand
            if q.brand and (q.brand in KNOWN_BRANDS or q.brand in PRODUCT_LINE_BRANDS.values())
            else None
        )
        kept, hidden = [], 0
        for g in groups:
            ref = g.reference.attrs
            # A different family or generation is a different product: "iPhone
            # Air" or "Galaxy S25 Ultra" is no answer to "iPhone 17", however the
            # words overlap. A different tier of the same generation (17 Pro) is
            # a sibling and stays, as its own card.
            if q.line_family and ref.line_family:
                if ref.line_family != q.line_family or (
                    q.line_number and ref.line_number != q.line_number
                ):
                    hidden += 1
                    continue
            if q_brand and ref.brand and ref.brand != q_brand:
                hidden += 1
                continue
            m = match_products(query_ref, g.reference)
            conflicting = m.match_type == MatchType.UNKNOWN or any(
                r.startswith(("Model code differs", "Generation differs")) for r in m.reasons
            )
            if conflicting:
                hidden += 1
                continue
            g.reference_match = m
            kept.append(g)
        kept.sort(
            key=lambda g: (
                -(g.reference_match.match_type == MatchType.EXACT),
                -g.reference_match.confidence,
            )
        )
        # The badge on a card is for URL and photo searches, where the shopper gave
        # a specific product to match against. For a typed query it is noise.
        for g in kept:
            g.reference_match = None
        return kept, hidden

    async def _enrich_top(self, results: list[ProductSearchResult]) -> list[ProductSearchResult]:
        """Ask Google for every store's price on the first few products it flagged as
        sold by several stores and that arrived with one offer. Bounded by
        SEARCH_ENRICH_LIMIT, one vendor call each, run together."""
        from app.services.offer_service import OfferService

        limit = self.settings.SEARCH_ENRICH_LIMIT
        if limit <= 0 or registry.offers_enricher() is None:
            return results
        candidates = []
        snapshot = getattr(self, "_persisted_attrs", {})
        products = getattr(self, "_persisted_products", {})
        offer_service = OfferService(self.db)
        for r in results:
            if len(candidates) >= limit:
                break
            if r.offer_count > 1:
                continue
            attrs = snapshot.get(r.id)
            if attrs is None:
                product = await catalog.load_product(self.db, r.id)
                attrs = (product.attributes if product else None) or {}
            if attrs.get("multiple_sources") and offer_service.can_enrich(attrs):
                candidates.append((r, r.id))
        if not candidates:
            return results
        # Mark the attempt before committing: the lookups run whether or not this
        # search waits for them, and the next search for these products must not
        # wait the whole time-box again for a lookup that is slow or failing.
        for _, pid in candidates:
            product = products.get(pid) or await catalog.load_product(self.db, pid)
            if product is not None:
                OfferService.mark_enrichment_attempt(product)
        # Each lookup runs in its own session so it can finish after this request
        # has answered. The search waits a few seconds for whatever completes and
        # merges that; the rest lands on the product page when it is opened.
        # Commit first: a product created moments ago in this session does not
        # exist yet for a session of its own.
        pending_ids = list(candidates)
        await self.db.commit()
        tasks = {
            asyncio.create_task(OfferService.enrich_in_own_session(pid, force=True)): r
            for r, pid in pending_ids
        }
        BACKGROUND_TASKS.update(tasks)
        done, pending = await asyncio.wait(tasks, timeout=self.settings.SEARCH_ENRICH_WAIT_SECONDS)
        for t in done:
            BACKGROUND_TASKS.pop(t, None)
        for t in pending:
            t.add_done_callback(lambda t: BACKGROUND_TASKS.pop(t, None))
        refreshed = {
            tasks[t].id for t in done if not t.cancelled() and t.exception() is None and t.result()
        }
        if not refreshed:
            return results
        self.db.expire_all()
        rebuilt = []
        for r in results:
            if r.id in refreshed:
                product = await catalog.load_product(self.db, r.id)
                rebuilt.append(await self._result_for_product(product, None) if product else r)
                if rebuilt[-1] is not r:
                    rebuilt[-1].match = r.match
            else:
                rebuilt.append(r)
        return rebuilt

    @staticmethod
    def withhold_prices(results: list[ProductSearchResult]) -> list[ProductSearchResult]:
        """Strip everything priced from result cards for viewers without Pro."""
        out = []
        for r in results:
            hint = (
                f"Prices at {len(r.retailers)} stores"
                if len(r.retailers) > 1
                else "Price available"
            )
            out.append(
                r.model_copy(
                    update={
                        "lowest_price": None,
                        "highest_price": None,
                        "offer_count": 0,
                        "retailers": [],
                        "locked": True,
                        "hint": hint + " with Pro",
                    }
                )
            )
        return out

    async def _family_for(
        self, query_text: str, results: list[ProductSearchResult], see_prices: bool
    ):
        """The line's variants and stores in one view, when the query names a line."""
        from app.services.family_service import FamilyService, family_for_query

        named = family_for_query(query_text)
        if named is None:
            return None
        line, label, storage = named
        try:
            return await FamilyService(self.db).build(
                line,
                seed_ids={r.id for r in results},
                see_prices=see_prices,
                selected_storage=storage,
                label=label,
            )
        except Exception as exc:  # the cards still answer; the family is extra
            logger.warning("Family view failed for %s: %s", line, type(exc).__name__)
            return None

    async def _catalog_for(self, query_text: str, see_prices: bool):
        """Curated models filtered by what the query asked for, when it browses
        a category rather than naming a product."""
        from app.services.catalog_browse import CatalogBrowser, catalog_for_query

        named = catalog_for_query(query_text)
        if named is None:
            return None, None
        category, filters = named
        try:
            page = await CatalogBrowser(self.db).page(
                category,
                see_prices=see_prices,
                brands=filters.get("brands") or None,
                ram_gb=filters.get("ram_gb"),
                storage_gb=filters.get("storage_gb"),
                min_price=filters.get("min_price"),
                max_price=filters.get("max_price"),
                sort="price_asc"
                if (filters.get("max_price") or filters.get("min_price"))
                else "newest",
            )
        except Exception as exc:  # the cards still answer; the catalogue is extra
            logger.warning("Catalogue view failed for %r: %s", query_text, type(exc).__name__)
            return None, None
        return page, filters

    async def _catalog_fallback(self, query_text: str) -> list[ProductSearchResult]:
        from sqlalchemy import select

        words = [w for w in re.findall(r"[a-z0-9]+", query_text.lower()) if len(w) > 1][:6]
        if not words:
            return []
        stmt = select(Product)
        for w in words:
            stmt = stmt.where(Product.name.ilike(f"%{w}%"))
        stmt = stmt.order_by(Product.updated_at.desc()).limit(24)
        products = (await self.db.execute(stmt)).scalars().all()
        return [await self._result_for_product(p, None) for p in products]

    async def _search_by_image(
        self, image_url: str
    ) -> tuple[list[NormalizedListing], Candidate | None, dict]:
        providers_used, warnings, listings, cached = [], [], [], False
        for provider in registry.image_search_providers():
            res: ProviderResult = await provider.search_by_image(image_url)
            providers_used.append(f"{provider.name}:{provider.engine}")
            cached = cached or res.cached
            if not res.ok:
                warnings.append("Image search temporarily unavailable.")
                continue
            listings.extend(res.items)
            if listings:
                break
        priced = [l for l in listings if l.price]
        best = (priced or listings)[0] if listings else None
        reference = None
        if best is not None:
            reference = Candidate(
                best.title, catalog.clean_identifiers(best.identifiers), best.brand
            )
            # Lens returns look-alikes at whichever store it saw them, usually one.
            # The same item at other stores comes from a text search on the best
            # match's title, so a photo gives a comparison and not a single price.
            text_listings, meta = await self._search_text(
                search_query_for(best.title, best.brand), None, None
            )
            providers_used += meta["providers"]
            warnings += meta["warnings"]
            cached = cached or meta["cached"]
            priced = priced + text_listings
        return (
            priced,
            reference,
            {"providers": providers_used, "warnings": warnings, "cached": cached},
        )

    async def _store_uploaded_image(self, image_base64: str) -> str | None:
        """Persist an uploaded image so Google Lens can fetch it. Requires a public API_PUBLIC_URL."""
        from pathlib import Path

        settings = self.settings
        public_url = settings.api_public_url
        if public_url.startswith(("http://localhost", "http://127.")):
            return None
        try:
            raw = base64.b64decode(image_base64.split(",")[-1], validate=True)
        except Exception as exc:
            raise ValueError("Invalid image data") from exc
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("Image too large (max 5MB)")
        if not (raw.startswith(b"\xff\xd8") or raw.startswith(b"\x89PNG") or raw[:4] == b"RIFF"):
            raise ValueError("Only JPEG, PNG or WebP images are supported")
        ext = (
            "jpg"
            if raw.startswith(b"\xff\xd8")
            else "png"
            if raw.startswith(b"\x89PNG")
            else "webp"
        )
        name = f"{uuid.uuid4().hex}.{ext}"
        upload_dir = Path(__file__).resolve().parent.parent.parent / "uploads"
        upload_dir.mkdir(exist_ok=True)
        (upload_dir / name).write_bytes(raw)
        return f"{public_url}/uploads/{name}"

    # ------------------------------------------------------------ persistence
    async def _persist_groups(
        self,
        groups: list[ListingGroup],
        query_type: str,
        reference_product: Product | None = None,
    ) -> list[ProductSearchResult]:
        seen: dict[uuid.UUID, ListingGroup] = {}
        cache = catalog.PersistCache()
        groups = groups[:24]

        # Everything this batch might already have, in a handful of queries: the
        # products by key and identifier, and the retailers by slug.
        wanted = []
        group_identifiers: dict[int, dict] = {}
        for group in groups:
            identifiers = dict(group.reference.identifiers)
            for listing, _ in group.listings:
                for k, v in catalog.clean_identifiers(listing.identifiers).items():
                    identifiers.setdefault(k, v)
            group_identifiers[id(group)] = identifiers
            ref_listing = group.listings[0][0]
            wanted.append(
                catalog.product_key_for(
                    group.reference.attrs,
                    catalog.clean_identifiers(identifiers),
                    ref_listing.condition or "new",
                )
            )
        prefetched = await catalog.prefetch_products(self.db, wanted)
        listings_flat = [listing for group in groups for listing, _ in group.listings]
        await catalog.preload_retailers(self.db, listings_flat, cache)
        await catalog.preload_sellers(self.db, listings_flat, cache)

        # New products are added without flushing and written in one statement
        # inside a savepoint. If another request inserted one of them meanwhile,
        # the savepoint rolls back and the batch is redone one product at a time,
        # which finds whichever row won.
        try:
            async with self.db.begin_nested():
                planned = await self._upsert_groups(
                    groups, group_identifiers, reference_product, prefetched, deferred=True
                )
                await self.db.flush()
        except IntegrityError:
            logger.info("Product batch conflicted with a concurrent insert; retrying singly")
            prefetched = await catalog.prefetch_products(self.db, wanted)
            planned = await self._upsert_groups(
                groups, group_identifiers, reference_product, prefetched, deferred=False
            )
        # Snapshots for the enrichment step: after the commit it triggers, these
        # instances are expired and cannot be read without a lazy refresh.
        self._persisted_attrs = {p.id: dict(p.attributes or {}) for _, p, _ in planned}
        self._persisted_products = {p.id: p for _, p, _ in planned}
        await self._record_offers(planned, cache, seen)
        return await self._results_for(seen)

    async def _upsert_groups(
        self,
        groups: list[ListingGroup],
        group_identifiers: dict[int, dict],
        reference_product: Product | None,
        prefetched: catalog.Prefetched,
        *,
        deferred: bool,
    ) -> list[tuple[ListingGroup, Product, bool]]:
        planned: list[tuple[ListingGroup, Product, bool]] = []
        for group in groups:
            ref_listing = group.listings[0][0]
            identifiers = group_identifiers[id(group)]
            attached = (
                reference_product is not None
                and group.reference_match is not None
                and group.reference_match.match_type == MatchType.EXACT
                and group.reference_match.confidence >= 0.8
            )
            if attached:
                # A link search found this same product at another retailer. Its
                # listings are offers on the referenced product, not a new product:
                # that is the whole point of pasting a link. Only exact matches
                # attach; a different variant stays its own product so a 128 GB
                # price is never shown against a 256 GB link.
                product = reference_product
            else:
                product = await catalog.upsert_product(
                    self.db,
                    group.title,
                    attrs=group.reference.attrs,
                    identifiers=identifiers,
                    brand=ref_listing.brand,
                    category=ref_listing.category,
                    image_urls=[l.image_url for l, _ in group.listings if l.image_url],
                    source_provider=ref_listing.source_provider,
                    source_url=ref_listing.url,
                    is_demo=all(l.is_demo for l, _ in group.listings),
                    condition=ref_listing.condition or "new",
                    prefetched=prefetched,
                    defer_create=deferred,
                    extra_attributes={
                        "multiple_sources": any(l.multiple_sources for l, _ in group.listings),
                        "enrichment_token": next(
                            (l.enrichment_token for l, _ in group.listings if l.enrichment_token),
                            None,
                        ),
                        "google_product_id": identifiers.get("google_product_id"),
                    },
                )
            group.product = product
            planned.append((group, product, attached))
        return planned

    async def _record_offers(
        self,
        planned: list[tuple[ListingGroup, Product, bool]],
        cache: catalog.PersistCache,
        seen: dict[uuid.UUID, ListingGroup],
    ) -> None:
        # Every product's variant and existing offers in two queries, then the
        # offers themselves with one flush for all of them and one for their price
        # observations. This was one to four queries per listing before, and at
        # ~50ms per round trip from the API host that was most of the search time.
        await catalog.preload_for_products(self.db, {p.id for _, p, _ in planned}, cache)
        for group, product, attached in planned:
            variant = await catalog.primary_variant(self.db, product, cache=cache)
            for listing, match in group.listings:
                tp = true_price_from_listing(listing)
                if tp:
                    await catalog.record_offer(
                        self.db,
                        product,
                        listing,
                        tp,
                        group.reference_match if attached else match,
                        variant=variant,
                        cache=cache,
                    )
            # Several listing groups can resolve to the same stored product (a group
            # whose title differs but whose identifiers/canonical key match an existing
            # row). Record it once, keeping the first group for match attribution.
            if product.id not in seen:
                seen[product.id] = group
        await catalog.flush_pending(self.db, cache)

    async def _results_for(self, seen: dict[uuid.UUID, ListingGroup]) -> list[ProductSearchResult]:
        # Build results only after every group is persisted, so offer counts and price
        # ranges reflect all offers rather than however many existed mid-loop. Offers
        # recorded before today's filters existed are retired here if implausible.
        results: list[ProductSearchResult] = []
        offers_by_product = await catalog.load_offers_many(self.db, set(seen))
        to_purge: list[tuple[Product, catalog.Retirement]] = []
        for product_id, group in seen.items():
            product = group.product  # created or loaded above in this same session
            if product is None:
                continue
            offers = offers_by_product.get(product_id, [])
            retirement = catalog.retire_implausible_offers(product, offers)
            if retirement.retired or retirement.floor is not None:
                to_purge.append((product, retirement))
            results.append(
                await self._result_for_product(product, group, offers=retirement.remaining)
            )
        if to_purge:
            purged = await catalog.purge_implausible_history_many(self.db, to_purge)
            if purged or any(r.retired for _, r in to_purge):
                await self.db.flush()
        return results

    async def _result_for_product(
        self,
        product: Product,
        group: ListingGroup | None,
        offers: list | None = None,
    ) -> ProductSearchResult:
        if offers is None:
            offers = await catalog.load_offers(self.db, product.id)
        exact = [o for o in offers if o.match_type == MatchType.EXACT.value]
        prices = [float(o.estimated_final_price) for o in exact] or [
            float(o.estimated_final_price) for o in offers
        ]
        ratings = [(float(o.rating), o.rating_count or 1) for o in offers if o.rating]
        avg_rating = (
            round(sum(r * n for r, n in ratings) / sum(n for _, n in ratings), 1)
            if ratings
            else None
        )
        match = None
        if group is not None and group.reference_match is not None:
            m = group.reference_match
            match = MatchInfo(
                match_type=m.match_type.value,
                confidence=m.confidence,
                label=m.label,
                reasons=m.reasons,
            )
        return ProductSearchResult(
            id=product.id,
            name=product.name,
            brand=product.brand,
            category=product.category,
            image=(product.images or [None])[0],
            lowest_price=min(prices) if prices else None,
            highest_price=max(prices) if prices else None,
            offer_count=len(offers),
            retailers=sorted({o.retailer.name for o in offers if o.retailer}),
            average_rating=avg_rating,
            match=match,
            is_demo=product.is_demo or all(o.is_demo for o in offers)
            if offers
            else product.is_demo,
        )

    @staticmethod
    def _sort(results: list[ProductSearchResult], sort_by: str | None) -> list[ProductSearchResult]:
        if sort_by == "price_asc":
            return sorted(results, key=lambda r: r.lowest_price or float("inf"))
        if sort_by == "price_desc":
            return sorted(results, key=lambda r: -(r.lowest_price or 0))
        if sort_by == "rating":
            return sorted(results, key=lambda r: -(r.average_rating or 0))
        return results
