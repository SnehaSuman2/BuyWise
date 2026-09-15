"""Retailer and seller schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class SellerResponse(BaseModel):
    id: UUID
    name: str
    external_id: str | None = None
    rating: float | None = None
    rating_count: int | None = None
    is_demo: bool = False

    model_config = {"from_attributes": True}


class RetailerResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    domain: str | None = None
    website_url: str | None = None
    logo_url: str | None = None
    description: str | None = None
    country: str = "IN"
    is_marketplace: bool = False
    is_curated: bool = False
    is_demo: bool = False

    model_config = {"from_attributes": True}


class RetailerDetail(RetailerResponse):
    policies: dict | None = None
    trust_score: int | None = None
    risk_level: str | None = None
    total_offers: int = 0
