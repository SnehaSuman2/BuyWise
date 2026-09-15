"""Review analysis schemas (kept for the review intelligence feature)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import DataMeta


class ReviewTheme(BaseModel):
    theme: str
    count: int
    sentiment: str
    examples: list[str] = []


class ReviewAnalysisResponse(BaseModel):
    product_id: UUID
    total_reviews: int = 0
    average_rating: float | None = None
    positive_themes: list[ReviewTheme] = []
    negative_themes: list[ReviewTheme] = []
    summary: str | None = None
    confidence: float | None = None
    available: bool = False
    message: str | None = None
    meta: DataMeta
