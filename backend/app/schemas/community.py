"""Community report schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CommunityReportCreate(BaseModel):
    product_id: UUID | None = None
    retailer_id: UUID | None = None
    seller_id: UUID | None = None
    report_type: str = Field(..., pattern="^(purchase|delivery|return|refund|authenticity|seller)$")
    title: str | None = Field(None, max_length=200)
    body: str = Field(..., min_length=20, max_length=4000)
    rating: float | None = Field(None, ge=1, le=5)
    order_reference: str | None = Field(
        None, max_length=100, description="Order id used only for verification; stored hashed"
    )


class CommunityReportResponse(BaseModel):
    id: UUID
    username: str | None = None
    product_id: UUID | None = None
    retailer_id: UUID | None = None
    seller_id: UUID | None = None
    report_type: str
    title: str | None = None
    body: str
    rating: float | None = None
    verification_status: str
    moderation_status: str
    flag_count: int = 0
    helpful_count: int = 0
    is_demo: bool = False
    created_at: datetime


class ReportFlagCreate(BaseModel):
    reason: str = Field(..., min_length=5, max_length=300)


class ModerationAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|hide|verify|reject_verification)$")
    note: str | None = Field(None, max_length=500)
