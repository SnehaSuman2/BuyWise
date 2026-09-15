"""Retailer and Seller models. A retailer (Amazon) is not the same as a seller (a marketplace merchant)."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONType, TimestampMixin, UUIDMixin, UUIDType


class Retailer(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "retailers"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), index=True)
    website_url: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(10), default="IN", nullable=False)
    is_marketplace: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Curated = BuyWise has reviewed and recorded this retailer's public policies.
    is_curated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Public policy facts with source URLs: {"returns_window_days": 7, "cod": true, "source_url": "..."}.
    policies: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    sellers = relationship("Seller", back_populates="retailer", lazy="noload")
    offers = relationship("Offer", back_populates="retailer", lazy="noload")
    trust_scores = relationship("TrustScore", back_populates="retailer", lazy="noload")
    trust_events = relationship("TrustEvent", back_populates="retailer", lazy="noload")
    trust_evidence = relationship("TrustEvidence", back_populates="retailer", lazy="noload")
    community_reports = relationship("CommunityReport", back_populates="retailer", lazy="noload")


class Seller(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sellers"
    __table_args__ = (UniqueConstraint("retailer_id", "name", name="uq_seller_retailer_name"),)

    retailer_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("retailers.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(200))
    profile_url: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2))
    rating_count: Mapped[int | None] = mapped_column(Integer)
    source_provider: Mapped[str | None] = mapped_column(String(50))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    retailer = relationship("Retailer", back_populates="sellers")
    offers = relationship("Offer", back_populates="seller", lazy="noload")
