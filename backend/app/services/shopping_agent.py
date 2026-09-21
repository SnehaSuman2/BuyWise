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
    "Interpret Indian shorthand like '25k' as 25000 and '1.2 lakh' as 120000. "
    "product_query is the product the person means, with obvious typos corrected "
    "('ihpone 17' is 'iPhone 17') and every model number or generation kept "
    "('iPhone 17', 'Galaxy S25 Ultra', 'WH-1000XM5'). A model number is never a budget: "
    "only an amount of money is a budget. Leave out intent words such as 'should I buy', "
    "'right now', 'best place to buy'."
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
    intent.product_query = product_query_from(q, budget_match=m)
    return intent


# Whole phrases that state intent rather than name a product. Removed before words,
# so "right now" goes as a unit and "right" cannot survive as a product word.
_INTENT_PHRASES = (
    r"or should i wait",
    r"should i wait",
    r"should i buy",
    r"is it a good time to buy",
    r"good time to buy",
    r"is now a good time",
    r"right now",
    r"right time",
    r"best place to buy",
    r"cheapest place to buy",
    r"where should i buy",
    r"where to buy",
    r"where can i buy",
    r"price drop",
    r"buy now",
    r"find me",
    r"show me",
    r"less than",
    r"up to",
)
_INTENT_WORDS = (
    "best",
    "good",
    "top",
    "find",
    "recommend",
    "which",
    "what",
    "is",
    "the",
    "for",
    "a",
    "an",
    "me",
    "should",
    "i",
    "buy",
    "now",
    "where",
    "to",
    "under",
    "below",
    "upto",
    "within",
    "budget",
    "please",
    "cheapest",
    "trustworthy",
    "seller",
    "retailer",
    "wait",
    "or",
    "place",
    "time",
    "today",
    "currently",
    "worth",
    "it",
    "get",
    "of",
    "in",
    "at",
    "my",
    "can",
    "do",
    "want",
    "need",
    "looking",
    "purchase",
    "buying",
    "purchasing",
    "getting",
    "ordering",
)
# Product words a shopper types in a hurry. A token within one edit of one of these
# is taken to mean it ("ihpone" is "iphone"); anything longer than one edit is left alone.
_PRODUCT_WORDS = (
    "iphone",
    "ipad",
    "macbook",
    "airpods",
    "apple",
    "samsung",
    "galaxy",
    "pixel",
    "oneplus",
    "redmi",
    "xiaomi",
    "realme",
    "vivo",
    "oppo",
    "motorola",
    "nothing",
    "sony",
    "bose",
    "boat",
    "jbl",
    "dell",
    "lenovo",
    "asus",
    "acer",
    "playstation",
    "xbox",
    "kindle",
    "laptop",
    "phone",
    "headphones",
    "earbuds",
    "watch",
    "camera",
    "television",
    "refrigerator",
    "washing",
)


def _fix_typo(word: str) -> str | None:
    """Correct a product word typed in a hurry; drop an intent word typed in a hurry.

    "ihpone" becomes "iphone"; "rigth" (from "rigth now") is an intent word and goes.
    Returns None for a word to drop.
    """
    import difflib

    if word in _PRODUCT_WORDS or any(ch.isdigit() for ch in word):
        return word
    if len(word) >= 5:
        close = difflib.get_close_matches(word, _PRODUCT_WORDS, n=1, cutoff=0.8)
        if close:
            return close[0]
    if len(word) >= 4 and difflib.get_close_matches(
        word, _INTENT_WORDS + ("right", "should", "would"), n=1, cutoff=0.8
    ):
        return None
    return word


def product_query_from(q: str, budget_match: re.Match | None = None) -> str | None:
    """The product the shopper means, with intent words and the budget removed.

    Numbers are kept: "17" in "iphone 17" and "1000xm5" in "wh-1000xm5" are the
    product. The old version stripped every number as if it were money, which sent
    "iphone" to search and brought back every generation of iPhone. Only the budget
    phrase itself and amounts with a currency mark or a k/lakh suffix are removed.
    """
    text = q
    if budget_match:
        text = text[: budget_match.start()] + " " + text[budget_match.end() :]
    text = re.sub(r"(₹|rs\.?|inr)\s*[\d.,]+\s*(k|thousand|lakh|lac|l)?\b", " ", text)
    text = re.sub(r"\b[\d.,]+\s*(k|thousand|lakh|lac)\b", " ", text)
    for phrase in _INTENT_PHRASES:
        text = re.sub(rf"\b{phrase}\b", " ", text)
    text = re.sub(r"[^a-z0-9\-+ ]", " ", text)
    words = [w for w in text.split() if w not in _INTENT_WORDS]
    fixed = [_fix_typo(w) for w in words]
    cleaned = " ".join(w for w in fixed if w).strip()
    return cleaned or None


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
            from app.services.product_normalizer import extract_attributes

            llm_query = (data.get("product_query") or "").strip() or None
            product_query = llm_query or base.product_query
            # If the model dropped the generation the shopper typed, keep ours.
            if (
                llm_query
                and base.product_query
                and extract_attributes(base.product_query).model_tokens
                and not extract_attributes(llm_query).model_tokens
            ):
                product_query = base.product_query
            budget_max = float(data["budget_max"]) if data.get("budget_max") else base.budget_max
            if budget_max is not None and budget_max < 100:
                budget_max = base.budget_max  # a model number, not money
            return AgentIntent(
                kind=kind,
                product_query=product_query,
                budget_max=budget_max,
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
            asked = f' for "{intent.product_query}"' if intent.product_query else ""
            return (
                f"I couldn't find any listings{asked} right now. Try the exact product name "
                f"with its model, or paste a link to the product page."
            )
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
                    trust_text = (
                        f"trust {best.trust_score}/100"
                        if best.trust_score is not None
                        else "seller not yet rated"
                    )
                    line += f" — best overall from {best.retailer_name} at ₹{best.price:,.0f} ({trust_text})."
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
