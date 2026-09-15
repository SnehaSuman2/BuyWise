"""Price history / buy-wait schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import DataMeta


class PricePoint(BaseModel):
    date: datetime
    price: float
    retailer_name: str | None = None


class PriceStatsResponse(BaseModel):
    current_price: float
    observations: int
    span_days: int
    average_7d: float | None = None
    average_30d: float | None = None
    average_90d: float | None = None
    historical_low: float | None = None
    historical_high: float | None = None
    percent_vs_average: float | None = None
    percent_vs_low: float | None = None
    trend: str = "unknown"
    volatility: float | None = None


class PriceSignalResponse(BaseModel):
    action: str
    status: str
    confidence: float
    confidence_level: str
    reasoning: str
    target_price: float | None = None
    evidence: list[str] = []


class PriceHistoryResponse(BaseModel):
    product_id: UUID
    product_name: str
    days_requested: int
    days_available: int
    history: list[PricePoint] = []
    stats: PriceStatsResponse | None = None
    signal: PriceSignalResponse
    message: str | None = None
    meta: DataMeta
