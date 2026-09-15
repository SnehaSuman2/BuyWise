"""Product schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import DataMeta


class MatchInfo(BaseModel):
    match_type: str
    confidence: float
    label: str
    reasons: list[str] = []


class ProductVariantResponse(BaseModel):
    id: UUID
    name: str | None = None
    storage: str | None = None
    ram: str | None = None
    color: str | None = None
    size: str | None = None
    configuration: str | None = None
    gtin: str | None = None
    asin: str | None = None
    mpn: str | None = None

    model_config = {"from_attributes": True}


class ProductResponse(BaseModel):
    id: UUID
    name: str
    brand: str | None = None
    model: str | None = None
    category: str | None = None
    description: str | None = None
    gtin: str | None = None
    sku: str | None = None
    mpn: str | None = None
    asin: str | None = None
    attributes: dict | None = None
    specifications: dict | None = None
    images: list[str] = []
    source_provider: str | None = None
    is_demo: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductDetail(ProductResponse):
    variants: list[ProductVariantResponse] = []
    lowest_price: float | None = None
    highest_price: float | None = None
    offer_count: int = 0
    exact_offer_count: int = 0
    average_rating: float | None = None
    rating_count: int | None = None
    meta: DataMeta | None = None


class ProductSearchResult(BaseModel):
    id: UUID
    name: str
    brand: str | None = None
    category: str | None = None
    image: str | None = None
    lowest_price: float | None = None
    highest_price: float | None = None
    offer_count: int = 0
    retailers: list[str] = []
    average_rating: float | None = None
    match: MatchInfo | None = None  # for URL/image searches: how well this matches the reference
    is_demo: bool = False
