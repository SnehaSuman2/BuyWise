"""Search orchestration: text / URL / image → normalized listings → grouped products → persisted.

Routing (minimum API calls):
  text  : Google Shopping (→ Bing Shopping fallback) ; Amazon Search only if fewer than 3 results
  url   : detect retailer → Amazon Product (ASIN) or slug-derived query → Google Shopping
  image : Google Lens → grouped listings
"""

from __future__ import annotations

import base64
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.http import UnsafeURLError, validate_public_http_url
from app.data.retailers import resolve_retailer
from app.models import Product, Search
from app.providers import registry
from app.providers.base import NormalizedListing, ProviderResult
from app.providers.serpapi.common import extract_asin
from app.schemas.common import DataMeta
from app.schemas.product import MatchInfo, ProductSearchResult
from app.schemas.search import SearchRequest, SearchResponse
from app.services import catalog
from app.services.market_filter import filter_to_market
from app.services.price_engine import true_price_from_listing
from app.services.product_matcher import Candidate, MatchResult, MatchType, match_products
from app.services.product_normalizer import extract_attributes

logger = logging.getLogger(__name__)


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
        cand = Candidate(
            listing.title, catalog.clean_identifiers(listing.identifiers), listing.brand
        )
        best: tuple[ListingGroup, MatchResult] | None = None
        for group in groups:
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
        if (a.is_accessory and not q.is_accessory) or (a.is_rental and not q.is_rental):
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
        self, request: SearchRequest, user_id: uuid.UUID | None = None
    ) -> SearchResponse:
        started = time.perf_counter()
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
            listings, meta = await self._search_by_image(image_url or "")
            providers_used += meta["providers"]
            warnings += meta["warnings"]
            cached = meta["cached"]
            query_text = "image search"
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

        results = await self._persist_groups(groups, query_type, reference_product=ref_product)
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
            meta=DataMeta(
                data_mode=data_mode,
                is_demo=is_demo,
                providers=sorted(set(providers_used)),
                cached=cached,
                warnings=warnings,
            ),
        )

    # ------------------------------------------------------------ routing
    async def _search_text(
        self, query: str, min_price, max_price
    ) -> tuple[list[NormalizedListing], dict]:
        providers_used, warnings, listings, cached = [], [], [], False
        failures: list[str] = []
        for provider in registry.product_search_providers():
            res = await provider.search_products(
                query, max_results=40, min_price=min_price, max_price=max_price
            )
            providers_used.append(f"{provider.name}:{provider.engine}")
            cached = cached or res.cached
            if not res.ok:
                warnings.append(f"{provider.engine} temporarily unavailable.")
                failures.append(res.error or provider.engine)
                continue
            listings.extend(res.items)
            if len(listings) >= 5:
                break
        if len(listings) < 3:
            for provider in registry.retailer_search_providers():
                res = await provider.search_retailer(query, max_results=10)
                providers_used.append(f"{provider.name}:{provider.engine}")
                cached = cached or res.cached
                if res.ok:
                    listings.extend(res.items)
                else:
                    warnings.append("Amazon data temporarily unavailable.")
                    failures.append(res.error or "amazon")
        priced = [l for l in listings if l.price]
        # Price bounds are applied here for every vendor; only SerpApi's Google
        # Shopping engine can filter server-side, and even then not exactly.
        if min_price is not None:
            priced = [l for l in priced if l.price >= min_price]
        if max_price is not None:
            priced = [l for l in priced if l.price <= max_price]
        unavailable = None
        if not priced and failures and not listings:
            unavailable = "; ".join(str(f) for f in failures)[:200]
            warnings = [
                "Live retailer search is temporarily unavailable (search provider quota "
                "or credentials). Results may be incomplete."
            ]
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
                    image_url=details.images[0] if details.images else None,
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
        """A short query for finding the referenced product at other retailers.

        A retailer's own title ("Apple iPhone 16 (128 GB) - Black, 6.1-inch Super
        Retina XDR, A18 chip...") is far too specific for a marketplace search and
        returns little or nothing from other stores. Brand, model and storage are
        what identify the product; the rest is dropped.
        """
        attrs = reference.attrs
        # A literal model code in the title ("wh-1000xm5") is the best possible
        # query on its own: "sony wh-1000xm5" found eight stores where the first
        # eight words of Amazon's title ("... best active noise cancelling wireless
        # bluetooth") found one. Line tokens like "iphone17" are squashed forms
        # that never appear literally, so they fall through to the title head.
        codes = sorted(
            (t for t in attrs.model_tokens if t in attrs.clean_title),
            key=lambda t: ("-" not in t, -len(t)),  # hyphenated, then longest, first
        )
        if codes:
            query = f"{attrs.brand} {codes[0]}" if attrs.brand else codes[0]
        else:
            head = re.split(r"\s[-|,(]\s*|\(", attrs.clean_title, maxsplit=1)[0].strip()
            query = " ".join(head.split()[:8])
            if attrs.brand and attrs.brand not in query:
                query = f"{attrs.brand} {query}"
        if attrs.storage and attrs.storage.lower() not in query.replace(" ", "").lower():
            query = f"{query} {attrs.storage.lower()}"
        return query.strip().lower() or reference.title

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
        kept, hidden = [], 0
        for g in groups:
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

    async def _search_by_image(self, image_url: str) -> tuple[list[NormalizedListing], dict]:
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
        if listings and not priced:
            # Lens matches often lack prices: run a text search using the best-matching title.
            text_listings, meta = await self._search_text(listings[0].title, None, None)
            providers_used += meta["providers"]
            warnings += meta["warnings"]
            priced = text_listings
        return priced, {"providers": providers_used, "warnings": warnings, "cached": cached}

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
        results: list[ProductSearchResult] = []
        seen: dict[uuid.UUID, ListingGroup] = {}
        cache = catalog.PersistCache()
        for group in groups[:24]:
            ref_listing = group.listings[0][0]
            identifiers = dict(group.reference.identifiers)
            for listing, _ in group.listings:
                for k, v in catalog.clean_identifiers(listing.identifiers).items():
                    identifiers.setdefault(k, v)
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
                    image_url=next((l.image_url for l, _ in group.listings if l.image_url), None),
                    source_provider=ref_listing.source_provider,
                    source_url=ref_listing.url,
                    is_demo=all(l.is_demo for l, _ in group.listings),
                )
            group.product = product
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

        # Build results only after every group is persisted, so offer counts and price
        # ranges reflect all offers rather than however many existed mid-loop. Offers
        # recorded before today's filters existed are retired here if implausible.
        for product_id, group in seen.items():
            product = group.product  # created or loaded above in this same session
            if product is not None:
                await catalog.deactivate_implausible_offers(self.db, product)
                results.append(await self._result_for_product(product, group))
        return results

    async def _result_for_product(
        self, product: Product, group: ListingGroup | None
    ) -> ProductSearchResult:
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
