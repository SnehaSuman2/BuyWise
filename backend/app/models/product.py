"""Product and ProductVariant models (normalized, provider-independent)."""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONType, TimestampMixin, UUIDMixin, UUIDType


class Product(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(200), index=True)
    model: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(200), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    # Identifiers (any may be unknown)
    gtin: Mapped[str | None] = mapped_column(String(20), index=True)
    sku: Mapped[str | None] = mapped_column(String(100), index=True)
    mpn: Mapped[str | None] = mapped_column(String(100), index=True)
    asin: Mapped[str | None] = mapped_column(String(20), index=True)
    # Normalized attributes extracted from title/specs: storage, ram, color, size, generation...
    attributes: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    specifications: Mapped[dict | None] = mapped_column(JSONType, default=dict)
    images: Mapped[list | None] = mapped_column(JSONType, default=list)
    normalized_name: Mapped[str | None] = mapped_column(String(500), index=True)
    # The product line as the normaliser names it ("iphone17"): what joins a
    # listing to its curated model and its family page.
    line: Mapped[str | None] = mapped_column(String(60), index=True)
    # Deterministic key used to avoid duplicate products (brand+model+variant attrs).
    canonical_key: Mapped[str | None] = mapped_column(String(300), unique=True, index=True)
    # Provenance
    source_provider: Mapped[str | None] = mapped_column(String(50))
    source_url: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    variants = relationship(
        "ProductVariant", back_populates="product", lazy="selectin", cascade="all, delete-orphan"
    )
    offers = relationship("Offer", back_populates="product", lazy="noload")
    reviews = relationship("Review", back_populates="product", lazy="noload")
    review_analysis = relationship("ReviewAnalysis", back_populates="product", lazy="noload")
    price_alerts = relationship("PriceAlert", back_populates="product", lazy="noload")
    community_reports = relationship("CommunityReport", back_populates="product", lazy="noload")


class ProductVariant(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "product_variants"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(500))
    storage: Mapped[str | None] = mapped_column(String(30))
    ram: Mapped[str | None] = mapped_column(String(30))
    color: Mapped[str | None] = mapped_column(String(60))
    size: Mapped[str | None] = mapped_column(String(60))
    configuration: Mapped[str | None] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(20), default="IN")
    gtin: Mapped[str | None] = mapped_column(String(20), index=True)
    sku: Mapped[str | None] = mapped_column(String(100))
    mpn: Mapped[str | None] = mapped_column(String(100))
    asin: Mapped[str | None] = mapped_column(String(20), index=True)
    canonical_key: Mapped[str | None] = mapped_column(String(300), unique=True)
    additional_specs: Mapped[dict | None] = mapped_column(JSONType, default=dict)

    product = relationship("Product", back_populates="variants")
