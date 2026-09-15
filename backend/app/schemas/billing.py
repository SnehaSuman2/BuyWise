"""Subscription / payment schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PlanInfo(BaseModel):
    id: str
    name: str
    price_inr: int
    period_days: int
    features: list[str]


class SubscriptionResponse(BaseModel):
    plan: str
    status: str
    is_pro: bool
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    limits: dict
    usage: dict
    payments_enabled: bool


class CreateOrderRequest(BaseModel):
    plan: str = Field(..., pattern="^(pro_monthly|pro_yearly)$")


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    key_id: str
    plan: str
    name: str
    description: str
    prefill: dict


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str = Field(..., max_length=100)
    razorpay_payment_id: str = Field(..., max_length=100)
    razorpay_signature: str = Field(..., max_length=200)


class PaymentResponse(BaseModel):
    id: UUID
    provider_order_id: str
    provider_payment_id: str | None = None
    plan: str
    amount: int
    currency: str
    status: str
    paid_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
