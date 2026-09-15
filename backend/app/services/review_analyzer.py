"""Review intelligence: summarises stored reviews when there are enough real ones.

Reviews are only analysed when they exist in the database (community reports or
imported review evidence). No review text is ever fabricated.
"""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Review
from app.providers.llm import AIProviderError, get_llm_provider
from app.schemas.common import DataMeta
from app.schemas.review import ReviewAnalysisResponse, ReviewTheme

logger = logging.getLogger(__name__)
MIN_REVIEWS = 5


class ReviewAnalyzer:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def analyze(self, product_id: uuid.UUID) -> ReviewAnalysisResponse:
        stmt = select(Review).where(Review.product_id == product_id)
        if not self.settings.demo_mode:
            stmt = stmt.where(Review.is_demo.is_(False))
        reviews = (await self.db.execute(stmt.limit(100))).scalars().all()
        is_demo = bool(reviews) and all(r.is_demo for r in reviews)
        meta = DataMeta(
            data_mode="demo" if is_demo else "live",
            is_demo=is_demo,
            providers=sorted({r.source or "unknown" for r in reviews}),
        )
        if len(reviews) < MIN_REVIEWS:
            return ReviewAnalysisResponse(
                product_id=product_id,
                total_reviews=len(reviews),
                available=False,
                message=f"Review intelligence needs at least {MIN_REVIEWS} reviews; BuyWise has {len(reviews)} for this product.",
                meta=meta,
            )
        ratings = [float(r.rating) for r in reviews if r.rating]
        avg = round(sum(ratings) / len(ratings), 1) if ratings else None
        llm = get_llm_provider()
        if llm.is_demo:
            pos = [r for r in reviews if r.rating and float(r.rating) >= 4]
            neg = [r for r in reviews if r.rating and float(r.rating) <= 2]
            return ReviewAnalysisResponse(
                product_id=product_id,
                total_reviews=len(reviews),
                average_rating=avg,
                positive_themes=[
                    ReviewTheme(
                        theme="Positive ratings",
                        count=len(pos),
                        sentiment="positive",
                        examples=[(r.title or r.body or "")[:100] for r in pos[:3]],
                    )
                ],
                negative_themes=[
                    ReviewTheme(
                        theme="Negative ratings",
                        count=len(neg),
                        sentiment="negative",
                        examples=[(r.title or r.body or "")[:100] for r in neg[:3]],
                    )
                ],
                summary=None,
                confidence=0.4,
                available=True,
                message="AI theme extraction requires an AI provider; showing rating counts only.",
                meta=meta,
            )
        payload = [
            {
                "rating": float(r.rating) if r.rating else None,
                "title": r.title,
                "body": (r.body or "")[:400],
            }
            for r in reviews[:60]
        ]
        try:
            data = await llm.complete_json(
                json.dumps(payload),
                system_prompt="Summarise these product reviews. Return JSON: {summary, positive_themes:[{theme,count,examples[]}], negative_themes:[...]}. Use only the reviews given.",
                max_tokens=700,
            )
        except AIProviderError as exc:
            logger.warning("Review analysis unavailable: %s", exc)
            return ReviewAnalysisResponse(
                product_id=product_id,
                total_reviews=len(reviews),
                average_rating=avg,
                available=False,
                message="AI provider temporarily unavailable.",
                meta=meta,
            )
        return ReviewAnalysisResponse(
            product_id=product_id,
            total_reviews=len(reviews),
            average_rating=avg,
            positive_themes=[
                ReviewTheme(
                    theme=str(t.get("theme")),
                    count=int(t.get("count", 0)),
                    sentiment="positive",
                    examples=[str(e) for e in t.get("examples", [])][:3],
                )
                for t in data.get("positive_themes", [])[:6]
            ],
            negative_themes=[
                ReviewTheme(
                    theme=str(t.get("theme")),
                    count=int(t.get("count", 0)),
                    sentiment="negative",
                    examples=[str(e) for e in t.get("examples", [])][:3],
                )
                for t in data.get("negative_themes", [])[:6]
            ],
            summary=str(data.get("summary", ""))[:1000] or None,
            confidence=0.7,
            available=True,
            meta=meta,
        )
