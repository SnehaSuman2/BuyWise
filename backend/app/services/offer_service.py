"""Offer comparison for a product: refresh (cost-aware), true price, trust, match, picks."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Offer, Product
from app.providers import registry
from app.schemas.common import DataMeta
from app.schemas.offer import (
    OfferComparison,
    OfferPick,
    OfferResponse,
    TruePriceBreakdown,
    TrustSummary,
)
from app.schemas.product import MatchInfo
from app.schemas.retailer import RetailerResponse, SellerResponse
from app.services import catalog
from app.services.affiliate_service import go_url_for
from app.services.market_filter import filter_to_market
from app.services.price_engine import compute_true_price, true_price_from_listing
from app.services.product_matcher import Candidate, MatchResult, MatchType, match_products
from app.services.product_normalizer import search_query_for
from app.services.trust_service import FLAGGED, TrustService, verification_status

logger = logging.getLogger(__name__)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class OfferService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.trust = TrustService(db)

    async def refresh_offers(self, product: Product) -> dict:
        """Fetch fresh listings for a product and store matched offers. Returns provider meta."""
        providers_used, warnings, listings = [], [], []
        reference = Candidate(
            product.name,
            catalog.clean_identifiers(
                {"gtin": product.gtin, "asin": product.asin, "mpn": product.mpn}
            ),
            product.brand,
            product.specifications,
        )
        if product.asin:
            provider = registry.amazon_product_provider()
            res = await provider.get_product_details(product.asin)
            providers_used.append(f"{provider.name}:{provider.engine}")
            if res.ok and res.items:
                listings.extend(res.items[0].offers)
                await catalog.store_review_insights(self.db, product, res.items[0].review_insights)
            else:
                warnings.append("Amazon data temporarily unavailable.")
        query = search_query_for(product.name, product.brand, product.specifications)
        for provider in registry.product_search_providers():
            res = await provider.search_products(query, max_results=30)
            providers_used.append(f"{provider.name}:{provider.engine}")
            if res.ok:
                listings.extend(res.items)
                break
            warnings.append(f"{provider.engine} temporarily unavailable.")
        # Same market guard as search: never persist an offer from a merchant that
        # doesn't sell into India.
        listings, excluded_count, excluded_names = filter_to_market(listings)
        if excluded_count:
            warnings.append(
                f"Excluded {excluded_count} offer(s) from outside India "
                f"({', '.join(excluded_names[:4])})."
            )
        # Every store's price from Google for this exact product, when the search
        # result carried the handle for it. This is what turns one offer into a
        # comparison.
        google_offers, providers_g, warnings_g = await self.google_offers(product)
        listings.extend(google_offers)
        providers_used += providers_g
        warnings += warnings_g
        cache = catalog.PersistCache()
        variant = await catalog.primary_variant(self.db, product, cache=cache)
        stored = 0
        for listing in listings:
            if not listing.price:
                continue
            match = match_products(
                reference,
                Candidate(
                    listing.title, catalog.clean_identifiers(listing.identifiers), listing.brand
                ),
            )
            if match.match_type == MatchType.UNKNOWN:
                continue
            tp = true_price_from_listing(listing)
            if tp:
                await catalog.record_offer(
                    self.db, product, listing, tp, match, variant=variant, cache=cache
                )
                stored += 1
        await catalog.flush_pending(self.db, cache)
        attrs = dict(product.attributes or {})
        attrs["enriched_at"] = datetime.now(timezone.utc).isoformat()
        product.attributes = attrs
        return {"providers": providers_used, "warnings": warnings, "stored": stored}

    async def google_offers(self, product: Product) -> tuple[list, list[str], list[str]]:
        """Listings from every store Google knows for this product, or none."""
        enricher = registry.offers_enricher()
        attrs = product.attributes or {}
        token = attrs.get("enrichment_token")
        product_id = attrs.get("google_product_id")
        if enricher is None or not (token or product_id):
            return [], [], []
        res = await enricher.offers_for(token=token, product_id=product_id)
        providers = [f"{enricher.name}:{res.engine or enricher.engine}"]
        if not res.ok:
            return [], providers, [f"Store prices from Google unavailable ({res.error})."]
        return list(res.items), providers, []

    @staticmethod
    async def enrich_in_own_session(product_id: uuid.UUID, force: bool = False) -> bool:
        """enrich_if_thin with a session of its own, so it can outlive the request
        that started it. Used by search to time-box the wait for store lookups."""
        from app.core.database import async_session_factory

        async with async_session_factory() as session:
            product = await catalog.load_product(session, product_id)
            if product is None:
                return False
            ok = await OfferService(session).enrich_if_thin(product, force=force)
            await session.commit()
            return ok

    @staticmethod
    def enrichment_attempted_recently(attrs: dict, within: timedelta) -> bool:
        """Whether a store lookup for this product started within the interval.

        A lookup that fails, or is still running, must not make every later
        search for the product wait the full time-box again.
        """
        raw = (attrs or {}).get("enrich_attempted_at")
        if not raw:
            return False
        try:
            attempted = datetime.fromisoformat(raw)
        except ValueError:
            return False
        return datetime.now(timezone.utc) - _aware(attempted) < within

    @staticmethod
    def mark_enrichment_attempt(product: Product) -> None:
        attrs = dict(product.attributes or {})
        attrs["enrich_attempted_at"] = datetime.now(timezone.utc).isoformat()
        product.attributes = attrs

    def can_enrich(self, attrs: dict) -> bool:
        """A product Google flagged that has not been enriched or tried lately."""
        attrs = attrs or {}
        if attrs.get("enriched_at"):
            return False
        if not (attrs.get("enrichment_token") or attrs.get("google_product_id")):
            return False
        retry_after = timedelta(seconds=self.settings.OFFER_THIN_REFRESH_SECONDS)
        return not self.enrichment_attempted_recently(attrs, retry_after)

    async def enrich_if_thin(self, product: Product, force: bool = False) -> bool:
        """First sight of a product that Google says several stores sell: fetch them.

        Returns True when a refresh ran. With force, a recent attempt does not
        stop it: the search that marked the attempt is the one asking.
        """
        offers = await catalog.load_offers(self.db, product.id)
        attrs = product.attributes or {}
        if len(offers) >= 2 or attrs.get("enriched_at"):
            return False
        if not (attrs.get("enrichment_token") or attrs.get("google_product_id")):
            return False
        if not force and not self.can_enrich(attrs):
            return False
        self.mark_enrichment_attempt(product)
        try:
            await self.refresh_offers(product)
        except Exception as exc:  # never let enrichment break a page
            logger.warning("Enrichment failed for %s: %s", product.id, type(exc).__name__)
            return False
        return True

    async def compare(
        self,
        product_id: uuid.UUID,
        *,
        refresh: bool = False,
        full: bool = True,
        prices: bool = True,
    ) -> OfferComparison | None:
        """The comparison for a product.

        With full=False (a visitor without Pro) the result keeps only the cheapest
        exact offer and reports how many offers and retailers it is holding back.
        The ranking still runs over everything so lowest_final_price is honest.
        """
        product = await catalog.load_product(self.db, product_id)
        if product is None:
            return None
        offers = await catalog.load_offers(self.db, product_id)
        warnings: list[str] = []
        providers: list[str] = []
        stale_after = timedelta(seconds=self.settings.OFFER_REFRESH_SECONDS)
        thin_after = timedelta(seconds=self.settings.OFFER_THIN_REFRESH_SECONDS)
        newest = max((_aware(o.observed_at) for o in offers), default=None)
        age = None if newest is None else datetime.now(timezone.utc) - newest
        is_stale = newest is None or age > stale_after
        # One offer is not a comparison. A product that arrived with a single offer
        # (a photo match, a pasted link) is refreshed sooner so the page can compare,
        # still no more than once per OFFER_THIN_REFRESH_SECONDS.
        attrs = product.attributes or {}
        # A thin product Google flagged as sold by several stores is enriched on its
        # first view; other thin products wait for the interval so a page view cannot
        # spend vendor calls on something with nothing more to find.
        can_enrich_now = self.can_enrich(attrs)
        is_thin = len(offers) < 2 and (age is None or age > thin_after or can_enrich_now)
        if refresh or ((is_stale or is_thin) and not (self.settings.demo_mode and offers)):
            try:
                meta = await self.refresh_offers(product)
                providers += meta["providers"]
                warnings += meta["warnings"]
                offers = await catalog.load_offers(self.db, product_id)
            except Exception as exc:
                logger.warning("Offer refresh failed for %s: %s", product_id, type(exc).__name__)
                warnings.append("Live offer refresh failed; showing last known offers.")
        retired = await catalog.deactivate_implausible_offers(self.db, product)
        if retired:
            offers = await catalog.load_offers(self.db, product_id)
            warnings.append(
                f"Hid {retired} offer(s) priced far below this product's other offers "
                f"(likely spam or a mismatched listing)."
            )
        trust_map = await self.trust.trust_summaries({o.retailer_id for o in offers})
        responses = [self._offer_response(o, trust_map.get(o.retailer_id)) for o in offers]

        # A merchant assessed with enough confidence and found to be high risk is
        # withheld entirely — showing it with a warning would still put a cheap,
        # untrustworthy price at the top of the comparison.
        flagged = [r for r in responses if r.trust.verification == FLAGGED]
        if flagged:
            responses = [r for r in responses if r.trust.verification != FLAGGED]
            names = sorted({r.retailer.name for r in flagged})
            warnings.append(
                f"Hid {len(flagged)} offer(s) from merchants BuyWise assessed as high "
                f"risk ({', '.join(names[:3])})."
            )

        exact = [r for r in responses if r.match.match_type == MatchType.EXACT.value]
        picks = self.rank(exact)
        is_demo = bool(offers) and all(o.is_demo for o in offers)
        lowest = min((r.price.estimated_final_price for r in exact), default=None)
        locked, hidden_offers, hidden_retailers = False, 0, 0
        if not prices and responses:
            # Nothing priced leaves the server: not even the cheapest offer.
            hidden_offers = len(responses)
            hidden_retailers = len({r.retailer.id for r in responses})
            responses, picks, locked, lowest = [], [], True, None
        elif not full and responses:
            cheapest = min(exact or responses, key=lambda r: r.price.estimated_final_price)
            hidden_offers = len(responses) - 1
            hidden_retailers = len({r.retailer.id for r in responses} - {cheapest.retailer.id})
            responses = [cheapest]
            picks = []
            locked = True
        return OfferComparison(
            product_id=product.id,
            product_name=product.name,
            total_offers=len(responses) + hidden_offers,
            exact_offers=len(exact),
            offers=responses,
            picks=picks,
            lowest_final_price=lowest,
            locked=locked,
            hidden_offers=hidden_offers,
            hidden_retailers=hidden_retailers,
            meta=DataMeta(
                data_mode="demo"
                if is_demo
                else ("mixed" if any(o.is_demo for o in offers) else "live"),
                is_demo=is_demo,
                providers=sorted(set(providers) | {o.source_provider for o in offers}),
                warnings=warnings,
            ),
        )

    def _offer_response(self, o: Offer, trust_entry: tuple | None) -> OfferResponse:
        retailer, trust = trust_entry if trust_entry else (None, None)
        tp = compute_true_price(
            float(o.listed_price),
            original_price=float(o.original_price) if o.original_price else None,
            shipping_price=float(o.shipping_price) if o.shipping_price is not None else None,
            shipping_known=o.shipping_known,
            coupon_code=o.coupon_code,
            coupon_amount=float(o.coupon_amount) if o.coupon_amount else None,
        )
        return OfferResponse(
            id=o.id,
            product_id=o.product_id,
            variant_id=o.variant_id,
            retailer=RetailerResponse.model_validate(o.retailer),
            seller=SellerResponse.model_validate(o.seller) if o.seller else None,
            title=o.title,
            product_url=o.product_url,
            go_url=go_url_for(o.id),
            currency=o.currency,
            price=TruePriceBreakdown(**tp.as_dict()),
            availability=o.availability,
            delivery_days=o.delivery_days,
            delivery_text=o.delivery_text,
            cod_available=o.cod_available,
            condition=o.condition,
            rating=float(o.rating) if o.rating else None,
            rating_count=o.rating_count,
            match=MatchInfo(
                match_type=o.match_type,
                confidence=float(o.match_confidence),
                label=MatchResult(MatchType(o.match_type), float(o.match_confidence)).label,
                reasons=o.match_reasons or [],
            ),
            trust=TrustSummary(
                score=trust.overall_score if trust else None,
                risk_level=trust.risk_level if trust else "unknown",
                confidence_level=trust.confidence_level if trust else "low",
                verification=verification_status(retailer, trust),
                is_demo=trust.is_demo if trust else False,
            ),
            source_provider=o.source_provider,
            source_engine=o.source_engine,
            observed_at=o.observed_at,
            is_demo=o.is_demo,
        )

    @staticmethod
    def rank(offers: list[OfferResponse]) -> list[OfferPick]:
        """Deterministic picks. Trust and price only — affiliate status is not an input."""
        available = [
            o for o in offers if o.availability != "out_of_stock" and o.condition == "new"
        ] or offers
        if not available:
            return []
        picks: list[OfferPick] = []
        prices = [o.price.estimated_final_price for o in available]
        lo, hi = min(prices), max(prices)

        def price_score(o: OfferResponse) -> float:
            return 100.0 if hi == lo else 100.0 * (hi - o.price.estimated_final_price) / (hi - lo)

        def trust_val(o: OfferResponse) -> float:
            return float(o.trust.score) if o.trust.score is not None else 50.0

        cheapest = min(available, key=lambda o: o.price.estimated_final_price)
        picks.append(
            OfferPick(
                category="CHEAPEST",
                offer_id=cheapest.id,
                retailer_name=cheapest.retailer.name,
                estimated_final_price=cheapest.price.estimated_final_price,
                trust_score=cheapest.trust.score,
                confidence=0.9 if cheapest.price.final_price_known else 0.7,
                reason=f"Lowest estimated final price at ₹{cheapest.price.estimated_final_price:,.0f}"
                + ("" if cheapest.price.final_price_known else " (shipping/coupons not confirmed)")
                + ".",
            )
        )
        with_trust = [o for o in available if o.trust.score is not None]
        if with_trust:
            safest = max(with_trust, key=lambda o: (trust_val(o), -o.price.estimated_final_price))
            picks.append(
                OfferPick(
                    category="SAFEST",
                    offer_id=safest.id,
                    retailer_name=safest.retailer.name,
                    estimated_final_price=safest.price.estimated_final_price,
                    trust_score=safest.trust.score,
                    confidence=0.85 if safest.trust.confidence_level == "high" else 0.6,
                    reason=f"Highest BuyWise Trust Score ({safest.trust.score}/100, {safest.trust.risk_level} risk) among available offers.",
                )
            )
        with_delivery = [o for o in available if o.delivery_days is not None]
        if with_delivery:
            fastest = min(
                with_delivery, key=lambda o: (o.delivery_days, o.price.estimated_final_price)
            )
            picks.append(
                OfferPick(
                    category="FASTEST",
                    offer_id=fastest.id,
                    retailer_name=fastest.retailer.name,
                    estimated_final_price=fastest.price.estimated_final_price,
                    trust_score=fastest.trust.score,
                    confidence=0.7,
                    reason=f"Fastest stated delivery ({fastest.delivery_days} day{'s' if fastest.delivery_days != 1 else ''}); delivery times vary by pincode.",
                )
            )
        best_value = max(available, key=lambda o: 0.6 * price_score(o) + 0.4 * trust_val(o))
        picks.append(
            OfferPick(
                category="BEST_VALUE",
                offer_id=best_value.id,
                retailer_name=best_value.retailer.name,
                estimated_final_price=best_value.price.estimated_final_price,
                trust_score=best_value.trust.score,
                confidence=0.75,
                reason=(
                    f"Best balance of price (₹{best_value.price.estimated_final_price:,.0f}) "
                    + (
                        f"and trust ({best_value.trust.score}/100)."
                        if best_value.trust.score is not None
                        else "and what is known about the seller (not yet rated)."
                    )
                ),
            )
        )
        best_overall = max(
            available,
            key=lambda o: (
                0.45 * price_score(o)
                + 0.4 * trust_val(o)
                + 0.15 * (100 - min(o.delivery_days or 5, 10) * 10)
                + (5 if o.match.confidence >= 0.9 else 0)
            ),
        )
        diff = best_overall.price.estimated_final_price - cheapest.price.estimated_final_price
        if best_overall.id == cheapest.id:
            if best_overall.trust.score is None:
                reason = (
                    "Cheapest offer. BuyWise has not rated this seller yet, so check the "
                    "seller before buying."
                )
            elif best_overall.trust.score >= 60:
                reason = "Cheapest offer and a strong trust score — no trade-off needed."
            else:
                reason = (
                    f"Cheapest offer, from a retailer with a trust score of "
                    f"{best_overall.trust.score}/100."
                )
        elif diff > 0:
            cheapest_trust = (
                f"{cheapest.trust.score}/100"
                if cheapest.trust.score is not None
                else "a seller not yet rated"
            )
            reason = (
                f"₹{diff:,.0f} more than the cheapest offer, but from a retailer with a "
                f"higher trust score ({best_overall.trust.score}/100 vs {cheapest_trust})."
            )
        else:
            reason = "Best combination of price, trust and delivery."
        picks.insert(
            0,
            OfferPick(
                category="BEST_OVERALL",
                offer_id=best_overall.id,
                retailer_name=best_overall.retailer.name,
                estimated_final_price=best_overall.price.estimated_final_price,
                trust_score=best_overall.trust.score,
                confidence=0.8 if best_overall.trust.score is not None else 0.55,
                reason=reason,
            ),
        )
        return picks
