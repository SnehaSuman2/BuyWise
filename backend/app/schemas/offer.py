"""Offer / true-price comparison schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import DataMeta
from app.schemas.product import MatchInfo
from app.schemas.retailer import RetailerResponse, SellerResponse


class TruePriceBreakdown(BaseModel):
    listed_price: float
    original_price: float | None = None
    discount_amount: float | None = None
    discount_percent: float | None = None
    shipping_price: float | None = None
    shipping_known: bool = False
    coupon_code: str | None = None
    coupon_amount: float | None = None
    estimated_final_price: float
    final_price_known: bool = False
    notes: list[str] = []


class TrustSummary(BaseModel):
    score: int | None = None
    risk_level: str = "unknown"
    confidence_level: str = "low"
    # verified | unverified | flagged — how much BuyWise actually knows about the seller.
    verification: str = "unverified"
    is_demo: bool = False


class OfferResponse(BaseModel):
    id: UUID
    product_id: UUID
    variant_id: UUID | None = None
    retailer: RetailerResponse
    seller: SellerResponse | None = None
    title: str | None = None
    product_url: str | None = None
    go_url: str  # BuyWise redirect (affiliate-aware, tracked)
    currency: str = "INR"
    price: TruePriceBreakdown
    availability: str = "unknown"
    delivery_days: int | None = None
    delivery_text: str | None = None
    cod_available: bool | None = None
    condition: str = "new"
    rating: float | None = None
    rating_count: int | None = None
    match: MatchInfo
    trust: TrustSummary
    source_provider: str
    source_engine: str | None = None
    observed_at: datetime
    is_demo: bool = False


class OfferPick(BaseModel):
    category: str  # BEST_OVERALL | CHEAPEST | SAFEST | BEST_VALUE | FASTEST
    offer_id: UUID
    retailer_name: str
    estimated_final_price: float
    trust_score: int | None = None
    reason: str
    confidence: float


class OfferComparison(BaseModel):
    product_id: UUID
    product_name: str
    total_offers: int
    exact_offers: int
    offers: list[OfferResponse] = []
    picks: list[OfferPick] = []
    lowest_final_price: float | None = None
    # The retailer-by-retailer comparison is part of Pro. For everyone else the
    # response carries the cheapest offer only, and says how much it is holding
    # back. Enforced here, on the server, never by the page hiding rows.
    locked: bool = False
    hidden_offers: int = 0
    hidden_retailers: int = 0
    meta: DataMeta
