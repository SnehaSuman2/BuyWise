"""Price alert schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AlertCreate(BaseModel):
    product_id: UUID
    alert_type: str = Field("target_price", pattern="^(target_price|percent_drop)$")
    target_price: float | None = Field(None, gt=0)
    drop_percent: float | None = Field(None, gt=0, le=90)
    notification_method: str = Field("email", pattern="^(email|none)$")

    @model_validator(mode="after")
    def _check(self):
        if self.alert_type == "target_price" and not self.target_price:
            raise ValueError("target_price is required for target_price alerts")
        if self.alert_type == "percent_drop" and not self.drop_percent:
            raise ValueError("drop_percent is required for percent_drop alerts")
        return self


class AlertResponse(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str | None = None
    product_image: str | None = None
    alert_type: str
    target_price: float | None = None
    drop_percent: float | None = None
    baseline_price: float | None = None
    currency: str = "INR"
    current_lowest_price: float | None = None
    is_active: bool = True
    is_triggered: bool = False
    triggered_at: datetime | None = None
    trigger_count: int = 0
    last_checked_at: datetime | None = None
    notification_method: str = "email"
    created_at: datetime


class NotificationResponse(BaseModel):
    id: UUID
    kind: str
    channel: str
    subject: str
    body: str
    status: str
    sent_at: datetime | None = None
    read_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
