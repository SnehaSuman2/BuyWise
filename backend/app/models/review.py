"""Review and ReviewAnalysis models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONType, TimestampMixin, UUIDMixin, UUIDType


class Review(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "reviews"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    retailer_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, ForeignKey("retailers.id"))
    source: Mapped[str | None] = mapped_column(String(50))
    source_url: Mapped[str | None] = mapped_column(Text)
    reviewer_name: Mapped[str | None] = mapped_column(String(200))
    rating: Mapped[float | None] = mapped_column(Numeric(2, 1))
    title: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text)
    is_verified_purchase: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    helpful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product = relationship("Product", back_populates="reviews")


class ReviewAnalysis(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "review_analysis"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    total_reviews: Mapped[int | None] = mapped_column(Integer)
    average_rating: Mapped[float | None] = mapped_column(Numeric(2, 1))
    positive_themes: Mapped[list | None] = mapped_column(JSONType, default=list)
    negative_themes: Mapped[list | None] = mapped_column(JSONType, default=list)
    quality_score: Mapped[int | None] = mapped_column(Integer)
    delivery_score: Mapped[int | None] = mapped_column(Integer)
    packaging_score: Mapped[int | None] = mapped_column(Integer)
    authenticity_score: Mapped[int | None] = mapped_column(Integer)
    service_score: Mapped[int | None] = mapped_column(Integer)
    suspicious_pattern_detected: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    suspicious_signals: Mapped[list | None] = mapped_column(JSONType)
    summary: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    provider: Mapped[str | None] = mapped_column(String(50))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product = relationship("Product", back_populates="review_analysis")
