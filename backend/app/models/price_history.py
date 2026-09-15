"""Price observations — every real price we have seen, with provenance."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDMixin, UUIDType


class PriceHistory(Base, UUIDMixin):
    __tablename__ = "price_history"
    __table_args__ = (
        Index("ix_price_history_product_observed", "product_id", "observed_at"),
        Index("ix_price_history_retailer_observed", "retailer_id", "observed_at"),
    )

    offer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("offers.id", ondelete="SET NULL"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("product_variants.id", ondelete="SET NULL")
    )
    retailer_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("retailers.id"), nullable=False
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, ForeignKey("sellers.id"))
    listed_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    estimated_final_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    availability: Mapped[str | None] = mapped_column(String(20))
    source_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    source_url: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    offer = relationship("Offer", back_populates="price_history")
