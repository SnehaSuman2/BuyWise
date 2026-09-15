"""User, refresh session and saved product models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONType, SoftDeleteMixin, TimestampMixin, UUIDMixin, UUIDType


class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # null for Google-only accounts
    display_name: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    auth_provider: Mapped[str] = mapped_column(String(20), default="password", nullable=False)
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), default="user", nullable=False
    )  # user | moderator | admin
    plan: Mapped[str] = mapped_column(String(20), default="free", nullable=False)  # free | pro
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notification_preferences: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    searches = relationship("Search", back_populates="user", lazy="noload")
    price_alerts = relationship("PriceAlert", back_populates="user", lazy="noload")
    community_reports = relationship("CommunityReport", back_populates="user", lazy="noload")
    saved_products = relationship("SavedProduct", back_populates="user", lazy="noload")
    subscriptions = relationship("Subscription", back_populates="user", lazy="noload")


class RefreshSession(Base, UUIDMixin):
    """A refresh token issued to a user; revoked on rotation, logout or deletion."""

    __tablename__ = "refresh_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SavedProduct(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "saved_products"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_saved_product_user_product"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(String(500))

    user = relationship("User", back_populates="saved_products")
    product = relationship("Product", lazy="joined")
