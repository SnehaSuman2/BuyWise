"""Affiliate click tracking. Commercial data — isolated from trust and ranking."""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin, UUIDType


class AffiliateClick(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "affiliate_clicks"

    offer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("offers.id", ondelete="SET NULL"), index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    retailer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("retailers.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL")
    )
    destination_url: Mapped[str] = mapped_column(Text, nullable=False)
    affiliate_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    program: Mapped[str | None] = mapped_column(String(50))
    ip_hash: Mapped[str | None] = mapped_column(String(64))  # hashed, never the raw IP
    user_agent: Mapped[str | None] = mapped_column(String(300))
    referer: Mapped[str | None] = mapped_column(String(500))
