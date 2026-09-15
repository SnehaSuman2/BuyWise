"""Recommendation engine: structured decision (deterministic) + optional AI explanation.

The AI only explains the structured result it is given. It cannot introduce
prices, retailers or scores that are not in the payload.
"""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.providers.llm import AIProviderError, get_llm_provider
from app.schemas.offer import OfferComparison
from app.schemas.price import PriceHistoryResponse
from app.schemas.recommendation import Recommendation, RecommendationSet
from app.services.offer_service import OfferService
from app.services.price_history_service import PriceHistoryService

logger = logging.getLogger(__name__)

EXPLAIN_SYSTEM = (
    "You are BuyWise, a shopping decision assistant for Indian shoppers. You will receive structured, verified data "
    "(offers, true prices, trust scores, price history signal). Write a short, plain-English explanation (max 120 words) of which "
    "retailer to buy from and why. Use ONLY numbers and names present in the data. If something is unknown, say it is unknown. "
    "Never invent prices, discounts, reviews, retailers or trust scores. Mention when data is demo data."
)


class RecommendationEngine:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.offers = OfferService(db)
        self.history = PriceHistoryService(db)

    def build(
        self, comparison: OfferComparison, history: PriceHistoryResponse | None
    ) -> list[Recommendation]:
        by_id = {o.id: o for o in comparison.offers}
        recs = []
        for pick in comparison.picks:
            o = by_id.get(pick.offer_id)
            if not o:
                continue
            recs.append(
                Recommendation(
                    category=pick.category,
                    product_id=comparison.product_id,
                    product_name=comparison.product_name,
                    offer_id=o.id,
                    retailer_id=o.retailer.id,
                    retailer_name=o.retailer.name,
                    seller_name=o.seller.name if o.seller else None,
                    price=o.price.estimated_final_price,
                    final_price_known=o.price.final_price_known,
                    trust_score=o.trust.score,
                    trust_risk=o.trust.risk_level,
                    price_status=history.signal.status if history else "UNKNOWN",
                    price_action=history.signal.action if history else "INSUFFICIENT_DATA",
                    match_label=o.match.label,
                    match_confidence=o.match.confidence,
                    reason=pick.reason,
                    confidence=pick.confidence,
                    go_url=o.go_url,
                    product_url=o.product_url,
                )
            )
        return recs

    async def explain(
        self,
        comparison: OfferComparison,
        history: PriceHistoryResponse | None,
        recs: list[Recommendation],
    ) -> tuple[str | None, str]:
        llm = get_llm_provider()
        if llm.is_demo or not recs:
            return None, llm.name
        payload = {
            "product": comparison.product_name,
            "data_mode": comparison.meta.data_mode,
            "recommendations": [
                {
                    "category": r.category,
                    "retailer": r.retailer_name,
                    "estimated_final_price_inr": r.price,
                    "final_price_known": r.final_price_known,
                    "trust_score": r.trust_score,
                    "trust_risk": r.trust_risk,
                    "match": r.match_label,
                }
                for r in recs
            ],
            "price_signal": history.signal.model_dump()
            if history
            else {"action": "INSUFFICIENT_DATA"},
            "price_stats": history.stats.model_dump() if history and history.stats else None,
        }
        try:
            text = await llm.complete(
                json.dumps(payload, default=str),
                system_prompt=EXPLAIN_SYSTEM,
                temperature=0.3,
                max_tokens=300,
            )
            return text.strip(), llm.name
        except AIProviderError as exc:
            logger.warning("AI explanation unavailable: %s", exc)
            return None, llm.name

    async def generate(
        self, product_id: uuid.UUID, *, with_ai: bool = True
    ) -> RecommendationSet | None:
        comparison = await self.offers.compare(product_id)
        if comparison is None:
            return None
        history = await self.history.get_history(product_id, 90)
        recs = self.build(comparison, history)
        explanation, provider = (
            (await self.explain(comparison, history, recs)) if with_ai else (None, "none")
        )
        if explanation is None and recs:
            best = recs[0]
            explanation = f"Buy from {best.retailer_name}: {best.reason} " + (
                history.signal.reasoning if history else ""
            )
        return RecommendationSet(
            product_id=product_id,
            product_name=comparison.product_name,
            recommendations=recs,
            ai_explanation=explanation,
            ai_provider=provider,
            meta=comparison.meta,
        )
