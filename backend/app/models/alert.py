"""PriceAlert and Notification models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONType, SoftDeleteMixin, TimestampMixin, UUIDMixin, UUIDType


class PriceAlert(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "price_alerts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("product_variants.id", ondelete="SET NULL")
    )
    alert_type: Mapped[str] = mapped_column(
        String(20), default="target_price", nullable=False
    )  # target_price | percent_drop
    target_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    drop_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    baseline_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2)
    )  # price when the alert was created
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    current_lowest_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trigger_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notification_method: Mapped[str] = mapped_column(String(20), default="email", nullable=False)

    user = relationship("User", back_populates="price_alerts")
    product = relationship("Product", back_populates="price_alerts", lazy="joined")


class Notification(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("price_alerts.id", ondelete="SET NULL")
    )
    channel: Mapped[str] = mapped_column(String(20), default="email", nullable=False)
    kind: Mapped[str] = mapped_column(
        String(40), nullable=False
    )  # price_alert | subscription | system
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending | sent | failed | skipped
    provider: Mapped[str | None] = mapped_column(String(40))
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict | None] = mapped_column(JSONType, default=dict)
