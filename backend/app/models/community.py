"""Community reports (user-submitted purchase experiences) and moderation flags."""

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
from app.models.base import TimestampMixin, UUIDMixin, UUIDType


class CommunityReport(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "community_reports"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    retailer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("retailers.id", ondelete="SET NULL"), index=True
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("sellers.id", ondelete="SET NULL")
    )
    report_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # purchase | delivery | return | refund | authenticity | seller
    title: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[float | None] = mapped_column(Numeric(2, 1))
    order_reference_hash: Mapped[str | None] = mapped_column(
        String(64)
    )  # hashed order id for verification, never raw
    verification_status: Mapped[str] = mapped_column(
        String(20), default="unverified", nullable=False
    )  # unverified | pending | verified | rejected
    moderation_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending | approved | rejected | hidden
    moderation_note: Mapped[str | None] = mapped_column(Text)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    flag_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="community_reports")
    product = relationship("Product", back_populates="community_reports")
    retailer = relationship("Retailer", back_populates="community_reports")


class ReportFlag(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "report_flags"
    __table_args__ = (UniqueConstraint("report_id", "user_id", name="uq_report_flag_user"),)

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("community_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
