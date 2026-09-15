"""Subscription, payment and Razorpay webhook routes."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.models import User
from app.schemas.billing import (
    CreateOrderRequest,
    CreateOrderResponse,
    PaymentResponse,
    PlanInfo,
    SubscriptionResponse,
    VerifyPaymentRequest,
)
from app.services.subscription_service import SubscriptionService, plans

router = APIRouter(tags=["billing"])
settings = get_settings()


@router.get("/subscription/plans", response_model=list[PlanInfo])
async def list_plans():
    return plans()


@router.get("/subscription", response_model=SubscriptionResponse)
async def subscription_status(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await SubscriptionService(db).status(user)


@router.post("/subscription/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await SubscriptionService(db).cancel(user)


@router.post("/payments/create", response_model=CreateOrderResponse)
@limiter.limit("10/minute")
async def create_payment(
    request: Request,
    data: CreateOrderRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await SubscriptionService(db).create_order(user, data.plan)


@router.post("/payments/verify", response_model=SubscriptionResponse)
@limiter.limit("20/minute")
async def verify_payment(
    request: Request,
    data: VerifyPaymentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await SubscriptionService(db).verify_checkout(
        user, data.razorpay_order_id, data.razorpay_payment_id, data.razorpay_signature
    )


@router.get("/payments", response_model=list[PaymentResponse])
async def list_payments(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await SubscriptionService(db).payments_for(user.id)


@router.post("/webhooks/razorpay")
@limiter.limit("120/minute")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Razorpay webhook. Signature is verified against the raw body; events are idempotent by id."""
    if not settings.razorpay_webhooks_enabled:
        raise HTTPException(
            status_code=503, detail="Webhooks not configured (RAZORPAY_WEBHOOK_SECRET missing)"
        )
    raw = await request.body()
    if len(raw) > 512 * 1024:
        raise HTTPException(status_code=413, detail="Payload too large")
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    return await SubscriptionService(db).handle_webhook(
        raw,
        request.headers.get("x-razorpay-signature"),
        request.headers.get("x-razorpay-event-id"),
        payload,
    )
