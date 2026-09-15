"""AI Shopping Agent — orchestration and reasoning layer over structured tools.

Flow: intent extraction → tools (search, offers, price history, trust) → recommendation
engine → explanation. The LLM (when configured) parses intent and explains the
structured result; it is never the source of any price, retailer or score.
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.data.retailers import resolve_retailer
from app.models import Retailer
from app.providers.llm import AIProviderError, get_llm_provider
from app.schemas.common import DataMeta
from app.schemas.recommendation import AgentIntent, AgentProductResult, AgentResponse
from app.schemas.search import SearchRequest
from app.services.recommendation_engine import RecommendationEngine
from app.services.search_service import SearchService
from app.services.trust_service import TrustService

logger = logging.getLogger(__name__)

INTENT_SYSTEM = (
    "Extract shopping intent from the user's message as JSON with keys: kind (product_search|compare|where_to_buy|buy_timing|seller_trust|unknown), "
    "product_query (string or null), budget_max (number in INR or null), budget_min, brands (list), features (list), compare_items (list), retailer (string or null), priority (price|trust|speed|value|null). "
    "Interpret Indian shorthand like '25k' as 25000 and '1.2 lakh' as 120000."
)
ANSWER_SYSTEM = (
    "You are BuyWise's shopping agent. Answer the user's question using ONLY the structured data provided. Be concise (max 160 words), "
    "use rupee amounts exactly as given, name the retailer for each recommendation, mention trust scores and the buy/wait signal when present. "
    "If data is missing or marked demo, say so plainly. Never invent products, prices, discounts, reviews or scores."
)

_MONEY_RE = re.compile(r"(?:₹|rs\.?|inr)?\s*(\d+(?:[.,]\d+)?)\s*(k|thousand|lakh|lac|l)?\b", re.I)


def _parse_money(text: str) -> float | None:
    m = _MONEY_RE.search(text)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    if unit in ("k", "thousand"):
        num *= 1000
    elif unit in ("lakh", "lac", "l"):
        num *= 100000
    return num if num >= 100 else None


def heuristic_intent(query: str) -> AgentIntent:
    q = query.lower().strip()
    intent = AgentIntent(kind="product_search")
    budget = None
    m = re.search(
        r"(?:under|below|less than|upto|up to|within|max(?:imum)?)\s*(₹|rs\.?|inr)?\s*([\d.,]+\s*(?:k|thousand|lakh|lac|l)?)",
        q,
    )
    if m:
        budget = _parse_money(m.group(2))
    intent.budget_max = budget
    for b in (
        "apple",
        "samsung",
        "sony",
        "bose",
        "oneplus",
        "google",
        "dell",
        "hp",
        "lenovo",
        "asus",
        "acer",
        "boat",
        "jbl",
        "lg",
        "xiaomi",
        "redmi",
        "realme",
        "vivo",
        "oppo",
        "nothing",
        "motorola",
        "logitech",
        "keychron",
    ):
        if re.search(rf"\b{b}\b", q):
            intent.brands.append(b)
    if " vs " in q or " versus " in q or q.startswith("compare "):
        intent.kind = "compare"
        parts = re.split(r"\s+vs\.?\s+|\s+versus\s+|,| and ", re.sub(r"^compare\s+", "", q))
        intent.compare_items = [
            p.strip(" ?.") for p in parts if p.strip(" ?.") and len(p.strip()) > 2
        ][:3]
    elif any(
        k in q
        for k in (
            "trustworthy",
            "trust",
            "legit",
            "safe to buy",
            "reliable seller",
            "is this seller",
            "scam",
        )
    ):
        intent.kind = "seller_trust"
    elif any(
        k in q for k in ("buy now", "should i buy", "wait", "good time", "price drop", "right time")
    ):
        intent.kind = "buy_timing"
    elif any(
        k in q
        for k in ("where should i buy", "where to buy", "best place to buy", "cheapest place")
    ):
        intent.kind = "where_to_buy"
    if any(k in q for k in ("cheapest", "lowest price", "budget")):
        intent.priority = "price"
    elif any(k in q for k in ("safest", "trusted", "reliable")):
        intent.priority = "trust"
    elif any(k in q for k in ("fastest", "quick delivery", "tomorrow")):
        intent.priority = "speed"
    for name in (
        "amazon",
        "flipkart",
        "croma",
        "reliance digital",
        "tata cliq",
        "vijay sales",
        "jiomart",
        "myntra",
        "ajio",
        "nykaa",
    ):
        if name in q:
            intent.retailer = name
            break
    cleaned = re.sub(
        r"\b(best|good|top|find me|find|show me|recommend|which|what|is|the|for|a|an|me|should|i|buy|now|where|to|under|below|less than|upto|up to|within|budget|please|cheapest|trustworthy|seller|retailer|now)\b",
        " ",
        q,
    )
    cleaned = re.sub(r"(₹|rs\.?|inr)?\s*[\d.,]+\s*(k|thousand|lakh|lac|l)?\b", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9\- ]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    intent.product_query = cleaned or None
    return intent


class ShoppingAgent:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.llm = get_llm_provider()
        self.search = SearchService(db)
        self.recommender = RecommendationEngine(db)
        self.trust = TrustService(db)

    async def extract_intent(self, query: str) -> AgentIntent:
        base = heuristic_intent(query)
        if self.llm.is_demo:
            return base
        try:
            data = await self.llm.complete_json(
                query, system_prompt=INTENT_SYSTEM, temperature=0.0, max_tokens=300
            )
            kind = (
                data.get("kind")
                if data.get("kind")
                in (
                    "product_search",
                    "compare",
                    "where_to_buy",
                    "buy_timing",
                    "seller_trust",
                    "unknown",
                )
                else base.kind
            )
            return AgentIntent(
                kind=kind,
                product_query=data.get("product_query") or base.product_query,
                budget_max=float(data["budget_max"]) if data.get("budget_max") else base.budget_max,
                budget_min=float(data["budget_min"]) if data.get("budget_min") else None,
                brands=[str(b).lower() for b in data.get("brands") or []] or base.brands,
                features=[str(f) for f in data.get("features") or []],
                compare_items=[str(c) for c in data.get("compare_items") or []]
                or base.compare_items,
                retailer=data.get("retailer") or base.retailer,
                priority=data.get("priority") or base.priority,
            )
        except (AIProviderError, ValueError, TypeError) as exc:
            logger.warning("Intent extraction fell back to heuristics: %s", exc)
            return base

    async def _retailer_trust(self, name: str) -> dict | None:
        curated = resolve_retailer(name, None)
        slug = curated["slug"] if curated else None
        retailer = None
        if slug:
            retailer = (
                await self.db.execute(select(Retailer).where(Retailer.slug == slug))
            ).scalar_one_or_none()
        if retailer is None:
            from app.services.catalog import get_or_create_retailer

            retailer = await get_or_create_retailer(
                self.db,
                curated["name"] if curated else name,
                curated["domain"] if curated else None,
            )
        trust = await self.trust.get_retailer_trust(retailer.id, include_evidence=True)
        return trust.model_dump(mode="json") if trust else None

    async def process(
        self, query: str, user_id: uuid.UUID | None = None, product_id: uuid.UUID | None = None
    ) -> AgentResponse:
        intent = await self.extract_intent(query)
        products: list[AgentProductResult] = []
        trust_payload = None
        price_signal = None
        warnings: list[str] = []
        providers: list[str] = []
        is_demo = self.settings.demo_mode

        if intent.kind == "seller_trust" and intent.retailer:
            trust_payload = await self._retailer_trust(intent.retailer)
            if trust_payload:
                is_demo = is_demo or trust_payload.get("meta", {}).get("is_demo", False)

        queries = (
            intent.compare_items
            if intent.kind == "compare" and intent.compare_items
            else ([intent.product_query] if intent.product_query else [])
        )
        if product_id and not queries:
            rec = await self.recommender.generate(product_id)
            if rec:
                from app.services.catalog import load_offers, load_product

                p = await load_product(self.db, product_id)
                offers = await load_offers(self.db, product_id)
                from app.schemas.product import ProductSearchResult

                if p:
                    products.append(
                        AgentProductResult(
                            product=ProductSearchResult(
                                id=p.id,
                                name=p.name,
                                brand=p.brand,
                                category=p.category,
                                image=(p.images or [None])[0],
                                lowest_price=rec.recommendations[0].price
                                if rec.recommendations
                                else None,
                                offer_count=len(offers),
                                is_demo=p.is_demo,
                            ),
                            recommendations=rec,
                        )
                    )
                    history = await self.recommender.history.get_history(product_id, 90)
                    price_signal = history.signal.model_dump() if history else None
        for q in queries[:3]:
            try:
                result = await self.search.search(
                    SearchRequest(
                        query=q,
                        max_price=intent.budget_max,
                        min_price=intent.budget_min,
                        page_size=5,
                    ),
                    user_id,
                )
            except ValueError as exc:
                warnings.append(str(exc))
                continue
            providers += result.meta.providers
            warnings += result.meta.warnings
            is_demo = is_demo or result.meta.is_demo
            top = result.results[: (1 if intent.kind == "compare" else 3)]
            for item in top:
                rec = await self.recommender.generate(item.id, with_ai=False)
                products.append(AgentProductResult(product=item, recommendations=rec))
            if intent.kind in ("buy_timing", "where_to_buy") and top:
                history = await self.recommender.history.get_history(top[0].id, 90)
                price_signal = history.signal.model_dump() if history else None

        answer = await self._compose_answer(
            query, intent, products, trust_payload, price_signal, is_demo
        )
        return AgentResponse(
            query=query,
            intent=intent,
            answer=answer,
            products=products,
            trust=trust_payload,
            price_signal=price_signal,
            ai_provider=self.llm.name,
            meta=DataMeta(
                data_mode="demo" if is_demo else "live",
                is_demo=is_demo,
                providers=sorted(set(providers)),
                warnings=warnings,
            ),
        )

    async def _compose_answer(
        self,
        query: str,
        intent: AgentIntent,
        products: list[AgentProductResult],
        trust: dict | None,
        price_signal: dict | None,
        is_demo: bool,
    ) -> str:
        facts = {
            "question": query,
            "intent": intent.model_dump(),
            "data_mode": "demo" if is_demo else "live",
            "products": [
                {
                    "name": p.product.name,
                    "lowest_estimated_final_price_inr": p.product.lowest_price,
                    "retailers": p.product.retailers,
                    "recommendations": [
                        {
                            "category": r.category,
                            "retailer": r.retailer_name,
                            "price_inr": r.price,
                            "final_price_known": r.final_price_known,
                            "trust_score": r.trust_score,
                            "trust_risk": r.trust_risk,
                            "reason": r.reason,
                        }
                        for r in (p.recommendations.recommendations if p.recommendations else [])
                    ],
                }
                for p in products
            ],
            "retailer_trust": {
                k: trust[k]
                for k in ("subject_name", "score", "risk_level", "confidence_level", "explanation")
                if trust and k in trust
            }
            if trust
            else None,
            "price_signal": price_signal,
        }
        if not self.llm.is_demo:
            try:
                return (
                    await self.llm.complete(
                        json.dumps(facts, default=str),
                        system_prompt=ANSWER_SYSTEM,
                        temperature=0.3,
                        max_tokens=400,
                    )
                ).strip()
            except AIProviderError as exc:
                logger.warning("Agent answer fell back to template: %s", exc)
        return self._template_answer(intent, products, trust, price_signal, is_demo)

    @staticmethod
    def _template_answer(
        intent: AgentIntent,
        products: list[AgentProductResult],
        trust: dict | None,
        price_signal: dict | None,
        is_demo: bool,
    ) -> str:
        lines: list[str] = []
        if trust:
            score = trust.get("score")
            lines.append(
                f"{trust.get('subject_name')}: BuyWise Trust Score {score if score is not None else 'not available'}/100, risk {trust.get('risk_level')}, confidence {trust.get('confidence_level')}. {trust.get('explanation', '')}"
            )
        if not products and not trust:
            return "I couldn't find matching products for that request. Try a more specific product name or a different budget."
        if products:
            lines.append(
                f"I found {len(products)} option{'s' if len(products) != 1 else ''}"
                + (f" under ₹{intent.budget_max:,.0f}" if intent.budget_max else "")
                + ":"
            )
            for i, p in enumerate(products, 1):
                best = next(
                    (
                        r
                        for r in (p.recommendations.recommendations if p.recommendations else [])
                        if r.category == "BEST_OVERALL"
                    ),
                    None,
                )
                cheapest = next(
                    (
                        r
                        for r in (p.recommendations.recommendations if p.recommendations else [])
                        if r.category == "CHEAPEST"
                    ),
                    None,
                )
                line = f"{i}. {p.product.name}"
                if best:
                    line += f" — best overall from {best.retailer_name} at ₹{best.price:,.0f} (trust {best.trust_score if best.trust_score is not None else 'n/a'}/100)."
                    if cheapest and cheapest.offer_id != best.offer_id:
                        line += f" Cheapest is {cheapest.retailer_name} at ₹{cheapest.price:,.0f}."
                    if not best.final_price_known:
                        line += " Final price may vary at checkout."
                elif p.product.lowest_price:
                    line += f" — from ₹{p.product.lowest_price:,.0f}."
                lines.append(line)
        if price_signal:
            lines.append(
                f"Price timing: {price_signal.get('action', '').replace('_', ' ')} — {price_signal.get('reasoning', '')}"
            )
        if is_demo:
            lines.append(
                "Note: this answer uses DEMO DATA because live data providers are not configured."
            )
        return "\n".join(lines)
