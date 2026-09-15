"""Trust models: evidence in, scores out.

Trust data is deliberately isolated from payments/affiliate models: there is no
foreign key or field linking commercial relationships to trust.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONType, TimestampMixin, UUIDMixin, UUIDType


class TrustEvidence(Base, UUIDMixin):
    """A single piece of evidence about a retailer or seller."""

    __tablename__ = "trust_evidence"
    __table_args__ = (Index("ix_trust_evidence_retailer_collected", "retailer_id", "collected_at"),)

    retailer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("retailers.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("sellers.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g. "google_search", "retailer_policy", "trustpilot", "community"
    source_type: Mapped[str] = mapped_column(
        String(40), nullable=False
    )  # search_result | policy | review_platform | community_report | verified_purchase
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(500))
    snippet: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    topic: Mapped[str] = mapped_column(
        String(40), nullable=False
    )  # returns | delivery | customer_service | authenticity | fraud | transparency | payment_security | general
    sentiment: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)  # -1..1
    severity: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0.5)  # 0..1
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0.5)  # 0..1
    extracted_claim: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # dedupe key
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    retailer = relationship("Retailer", back_populates="trust_evidence")


class TrustScore(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trust_scores"

    retailer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("retailers.id", ondelete="CASCADE"), index=True
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("sellers.id", ondelete="CASCADE"), index=True
    )
    overall_score: Mapped[int | None] = mapped_column(Integer)  # None when evidence is insufficient
    risk_level: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # low | medium | high | unknown
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    confidence_level: Mapped[str] = mapped_column(String(20), nullable=False)  # low | medium | high
    factors: Mapped[list | None] = mapped_column(
        JSONType, default=list
    )  # positive factors with scores
    concerns: Mapped[list | None] = mapped_column(JSONType, default=list)
    component_scores: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(20), default="1.0", nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    retailer = relationship("Retailer", back_populates="trust_scores")


class TrustEvent(Base, UUIDMixin, TimestampMixin):
    """Manually recorded notable events (e.g. regulatory action) — moderator-entered."""

    __tablename__ = "trust_events"

    retailer_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("retailers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[float | None] = mapped_column(Numeric(3, 2))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    retailer = relationship("Retailer", back_populates="trust_events")
