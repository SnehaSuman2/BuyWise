"""Offer model — one listing of a product (variant) at a retailer, optionally via a marketplace seller."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONType, TimestampMixin, UUIDMixin, UUIDType


class Offer(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "offers"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("product_variants.id", ondelete="SET NULL"), index=True
    )
    retailer_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("retailers.id"), nullable=False, index=True
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, ForeignKey("sellers.id"))

    title: Mapped[str | None] = mapped_column(String(500))
    product_url: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(200))  # ASIN / product_id at the source
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)

    # --- True price components. None means UNKNOWN, never assumed. ---
    listed_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    original_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2)
    )  # MRP / strike-through if shown
    shipping_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    shipping_known: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    discount_amount: Mapped[float | None] = mapped_column(
        Numeric(10, 2)
    )  # original - listed when both known
    coupon_code: Mapped[str | None] = mapped_column(String(100))
    coupon_amount: Mapped[float | None] = mapped_column(Numeric(10, 2))
    estimated_final_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    final_price_known: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    availability: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    delivery_days: Mapped[int | None] = mapped_column(Integer)
    delivery_text: Mapped[str | None] = mapped_column(String(200))
    cod_available: Mapped[bool | None] = mapped_column(Boolean)
    condition: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2))
    rating_count: Mapped[int | None] = mapped_column(Integer)

    # --- Matching (how confident we are this listing is the product) ---
    match_type: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    match_confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0, nullable=False)
    match_reasons: Mapped[list | None] = mapped_column(JSONType, default=list)

    # --- Provenance ---
    source_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    source_engine: Mapped[str | None] = mapped_column(String(50))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product = relationship("Product", back_populates="offers")
    retailer = relationship("Retailer", back_populates="offers", lazy="joined")
    seller = relationship("Seller", back_populates="offers", lazy="joined")
    price_history = relationship("PriceHistory", back_populates="offer", lazy="noload")
