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
        return {"providers": providers_used, "warnings": warnings, "stored": stored}

    async def compare(
        self, product_id: uuid.UUID, *, refresh: bool = False
    ) -> OfferComparison | None:
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
        is_thin = len(offers) < 2 and (age is None or age > thin_after)
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
        return OfferComparison(
            product_id=product.id,
            product_name=product.name,
            total_offers=len(responses),
            exact_offers=len(exact),
            offers=responses,
            picks=picks,
            lowest_final_price=min((r.price.estimated_final_price for r in exact), default=None),
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
                reason=f"Best balance of price (₹{best_value.price.estimated_final_price:,.0f}) and trust ({best_value.trust.score if best_value.trust.score is not None else 'n/a'}/100).",
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
            reason = "Cheapest offer and a strong trust score — no trade-off needed."
        elif diff > 0:
            reason = f"₹{diff:,.0f} more than the cheapest offer, but from a retailer with a higher trust score ({best_overall.trust.score}/100 vs {cheapest.trust.score if cheapest.trust.score is not None else 'n/a'}/100)."
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
