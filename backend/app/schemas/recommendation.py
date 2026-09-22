"""Recommendation / agent schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import DataMeta
from app.schemas.product import ProductSearchResult


class Recommendation(BaseModel):
    category: str  # BEST_OVERALL | CHEAPEST | SAFEST | BEST_VALUE | FASTEST
    product_id: UUID
    product_name: str
    offer_id: UUID
    retailer_id: UUID
    retailer_name: str
    seller_name: str | None = None
    price: float
    final_price_known: bool
    trust_score: int | None = None
    trust_risk: str = "unknown"
    price_status: str = "UNKNOWN"
    price_action: str = "INSUFFICIENT_DATA"
    match_label: str
    match_confidence: float
    reason: str
    confidence: float
    go_url: str
    product_url: str | None = None


class RecommendationSet(BaseModel):
    product_id: UUID
    product_name: str
    recommendations: list[Recommendation] = []
    locked: bool = False  # picks are part of Pro; see OfferComparison.locked
    ai_explanation: str | None = None
    ai_provider: str | None = None
    meta: DataMeta


class AgentRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    product_id: UUID | None = None


class AgentIntent(BaseModel):
    kind: str  # product_search | compare | where_to_buy | buy_timing | seller_trust | unknown
    product_query: str | None = None
    budget_max: float | None = None
    budget_min: float | None = None
    brands: list[str] = []
    features: list[str] = []
    compare_items: list[str] = []
    retailer: str | None = None
    priority: str | None = None  # price | trust | speed | value


class AgentProductResult(BaseModel):
    product: ProductSearchResult
    recommendations: RecommendationSet | None = None


class AgentResponse(BaseModel):
    query: str
    intent: AgentIntent
    answer: str
    products: list[AgentProductResult] = []
    trust: dict | None = None
    price_signal: dict | None = None
    ai_provider: str
    meta: DataMeta
