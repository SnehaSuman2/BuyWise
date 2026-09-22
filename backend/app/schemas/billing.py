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
    # Worked out on the server so the page never does arithmetic on prices and
    # never shows a saving that is not real.
    monthly_equivalent_inr: float | None = None
    savings_percent: int | None = None
    is_best_value: bool = False


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
    # Deliberately not a pattern listing the plan ids: one drifted out of date the
    # moment a plan was added and the new plan was rejected here rather than
    # anywhere obvious. plans() is the single source of truth, and
    # subscription_service.plan_by_id rejects anything it does not contain.
    plan: str = Field(..., min_length=1, max_length=40)


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
