"""Subscription, Payment and WebhookEvent models (Razorpay).

These tables are commercial records. Nothing in the trust engine reads them.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONType, TimestampMixin, UUIDMixin, UUIDType


class Subscription(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan: Mapped[str] = mapped_column(String(20), nullable=False)  # pro_monthly | pro_yearly
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # pending | active | past_due | cancelled | expired
    provider: Mapped[str] = mapped_column(String(20), default="razorpay", nullable=False)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(100), index=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription", lazy="noload")


class Payment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_order_id", name="uq_payment_provider_order"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("subscriptions.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(20), default="razorpay", nullable=False)
    provider_order_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    plan: Mapped[str] = mapped_column(String(20), nullable=False)
    period_days: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # smallest unit (paise)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="created", nullable=False
    )  # created | paid | failed | refunded
    signature_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_via: Mapped[str | None] = mapped_column(String(20))  # checkout | webhook
    failure_reason: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict | None] = mapped_column(
        JSONType, default=dict
    )  # provider payload, never contains secrets
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    subscription = relationship("Subscription", back_populates="payments")


class WebhookEvent(Base, UUIDMixin):
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)

    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    event_id: Mapped[str] = mapped_column(String(120), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONType)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_error: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
