"""BuyWise Pro subscriptions via Razorpay.

- Orders are created server-side; the amount comes from config, never the client.
- Checkout success is verified with the payment signature AND (when reachable)
  by fetching the payment from Razorpay to confirm status/amount.
- Webhooks are verified against the raw body and deduplicated by event id.
- Subscription activation only happens after server-side verification.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Payment, PriceAlert, SavedProduct, Subscription, User, WebhookEvent
from app.providers.payments.razorpay import (
    RazorpayClient,
    RazorpayError,
    verify_payment_signature,
    verify_webhook_signature,
)
from app.schemas.billing import CreateOrderResponse, PlanInfo, SubscriptionResponse

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def plans() -> list[PlanInfo]:
    s = get_settings()
    features_pro = [
        f"Up to {s.PRO_MAX_ALERTS} price alerts",
        f"Up to {s.PRO_MAX_SAVED_PRODUCTS} saved products",
        f"{s.PRO_HISTORY_DAYS}-day price history",
        "Deeper trust reports with evidence",
        "Priority AI shopping agent",
    ]
    return [
        PlanInfo(
            id="free",
            name="Free",
            price_inr=0,
            period_days=0,
            features=[
                f"Up to {s.FREE_MAX_ALERTS} price alerts",
                f"Up to {s.FREE_MAX_SAVED_PRODUCTS} saved products",
                f"{s.FREE_HISTORY_DAYS}-day price history",
                "AI shopping agent",
            ],
        ),
        PlanInfo(
            id="pro_monthly",
            name="Pro Monthly",
            price_inr=s.PRO_MONTHLY_PRICE_INR,
            period_days=30,
            features=features_pro,
        ),
        PlanInfo(
            id="pro_yearly",
            name="Pro Yearly",
            price_inr=s.PRO_YEARLY_PRICE_INR,
            period_days=365,
            features=features_pro + ["2 months free vs monthly"],
        ),
    ]


def plan_by_id(plan_id: str) -> PlanInfo:
    for p in plans():
        if p.id == plan_id:
            return p
    raise HTTPException(status_code=400, detail="Unknown plan")


class SubscriptionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.client = RazorpayClient()

    # ------------------------------------------------------------ status
    async def active_subscription(self, user_id: uuid.UUID) -> Subscription | None:
        rows = (
            (
                await self.db.execute(
                    select(Subscription)
                    .where(Subscription.user_id == user_id, Subscription.status == "active")
                    .order_by(Subscription.current_period_end.desc())
                )
            )
            .scalars()
            .all()
        )
        for sub in rows:
            if sub.current_period_end and _aware(sub.current_period_end) > _now():
                return sub
            sub.status = "expired"
        return None

    async def sync_user_plan(self, user: User) -> None:
        sub = await self.active_subscription(user.id)
        user.plan = "pro" if sub else "free"

    async def status(self, user: User) -> SubscriptionResponse:
        sub = await self.active_subscription(user.id)
        await self.sync_user_plan(user)
        s = self.settings
        alerts = (
            await self.db.execute(
                select(func.count())
                .select_from(PriceAlert)
                .where(
                    PriceAlert.user_id == user.id,
                    PriceAlert.is_active.is_(True),
                    PriceAlert.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        saved = (
            await self.db.execute(
                select(func.count())
                .select_from(SavedProduct)
                .where(SavedProduct.user_id == user.id)
            )
        ).scalar_one()
        pro = user.plan == "pro"
        return SubscriptionResponse(
            plan=sub.plan if sub else "free",
            status=sub.status if sub else "none",
            is_pro=pro,
            current_period_end=sub.current_period_end if sub else None,
            cancel_at_period_end=sub.cancel_at_period_end if sub else False,
            limits={
                "alerts": s.PRO_MAX_ALERTS if pro else s.FREE_MAX_ALERTS,
                "saved_products": s.PRO_MAX_SAVED_PRODUCTS if pro else s.FREE_MAX_SAVED_PRODUCTS,
                "history_days": s.PRO_HISTORY_DAYS if pro else s.FREE_HISTORY_DAYS,
            },
            usage={"alerts": alerts, "saved_products": saved},
            payments_enabled=s.razorpay_enabled,
        )

    # ------------------------------------------------------------ checkout
    async def create_order(self, user: User, plan_id: str) -> CreateOrderResponse:
        if not self.settings.razorpay_enabled:
            raise HTTPException(
                status_code=503,
                detail="Payments are not configured yet (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET missing).",
            )
        plan = plan_by_id(plan_id)
        if plan.price_inr <= 0:
            raise HTTPException(status_code=400, detail="This plan is free")
        amount = plan.price_inr * 100
        receipt = f"bw_{uuid.uuid4().hex[:20]}"
        try:
            order = await self.client.create_order(
                amount, "INR", receipt, {"user_id": str(user.id), "plan": plan.id}
            )
        except RazorpayError as exc:
            logger.error("Razorpay order creation failed: %s", exc)
            raise HTTPException(status_code=502, detail="Could not create payment order") from exc
        payment = Payment(
            user_id=user.id,
            provider="razorpay",
            provider_order_id=order["id"],
            plan=plan.id,
            period_days=plan.period_days,
            amount=amount,
            currency="INR",
            status="created",
            raw={"receipt": receipt},
        )
        self.db.add(payment)
        await self.db.flush()
        return CreateOrderResponse(
            order_id=order["id"],
            amount=amount,
            currency="INR",
            key_id=self.settings.RAZORPAY_KEY_ID,
            plan=plan.id,
            name="BuyWise Pro",
            description=plan.name,
            prefill={"email": user.email, "name": user.display_name or user.username},
        )

    async def verify_checkout(
        self, user: User, order_id: str, payment_id: str, signature: str
    ) -> SubscriptionResponse:
        payment = (
            await self.db.execute(
                select(Payment).where(
                    Payment.provider == "razorpay", Payment.provider_order_id == order_id
                )
            )
        ).scalar_one_or_none()
        if payment is None or payment.user_id != user.id:
            raise HTTPException(status_code=404, detail="Order not found")
        if payment.status == "paid":
            return await self.status(user)  # idempotent
        if not verify_payment_signature(
            order_id, payment_id, signature, self.settings.RAZORPAY_KEY_SECRET
        ):
            payment.status = "failed"
            payment.failure_reason = "signature_mismatch"
            raise HTTPException(status_code=400, detail="Payment signature verification failed")
        # Second check straight from Razorpay (status + amount). If unreachable, the webhook will confirm later.
        try:
            remote = await self.client.fetch_payment(payment_id)
            if (
                remote.get("order_id") != order_id
                or int(remote.get("amount", 0)) != payment.amount
                or remote.get("status") not in ("captured", "authorized")
            ):
                payment.status = "failed"
                payment.failure_reason = f"remote_status_{remote.get('status')}"
                raise HTTPException(
                    status_code=400, detail="Payment could not be confirmed with Razorpay"
                )
            payment.raw = {
                **(payment.raw or {}),
                "method": remote.get("method"),
                "status": remote.get("status"),
            }
        except RazorpayError as exc:
            logger.warning("Razorpay fetch_payment failed (will rely on webhook): %s", exc)
        await self._mark_paid(payment, payment_id, via="checkout")
        return await self.status(user)

    async def _mark_paid(self, payment: Payment, payment_id: str, *, via: str) -> None:
        if payment.status == "paid":
            return
        payment.status = "paid"
        payment.provider_payment_id = payment_id
        payment.signature_verified = True
        payment.verified_via = via
        payment.paid_at = _now()
        await self._activate(payment)

    async def _activate(self, payment: Payment) -> Subscription:
        user = (await self.db.execute(select(User).where(User.id == payment.user_id))).scalar_one()
        current = await self.active_subscription(user.id)
        start = (
            _aware(current.current_period_end)
            if current and current.plan == payment.plan
            else _now()
        )
        end = start + timedelta(days=payment.period_days)
        if current and current.plan == payment.plan:
            current.current_period_end = end
            current.status = "active"
            current.cancel_at_period_end = False
            sub = current
        else:
            if current:
                current.status = "cancelled"
                current.cancelled_at = _now()
            sub = Subscription(
                user_id=user.id,
                plan=payment.plan,
                status="active",
                provider="razorpay",
                current_period_start=_now(),
                current_period_end=end,
            )
            self.db.add(sub)
            await self.db.flush()
        payment.subscription_id = sub.id
        user.plan = "pro"
        return sub

    async def cancel(self, user: User) -> SubscriptionResponse:
        sub = await self.active_subscription(user.id)
        if sub is None:
            raise HTTPException(status_code=404, detail="No active subscription")
        sub.cancel_at_period_end = True
        sub.cancelled_at = _now()
        return await self.status(user)

    async def payments_for(self, user_id: uuid.UUID) -> list[Payment]:
        return list(
            (
                await self.db.execute(
                    select(Payment)
                    .where(Payment.user_id == user_id)
                    .order_by(Payment.created_at.desc())
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )

    # ------------------------------------------------------------ webhooks
    async def handle_webhook(
        self, raw_body: bytes, signature: str | None, event_id: str | None, payload: dict
    ) -> dict:
        valid = verify_webhook_signature(
            raw_body, signature or "", self.settings.RAZORPAY_WEBHOOK_SECRET
        )
        event_type = str(payload.get("event") or "unknown")
        event_id = (
            event_id or f"noid_{uuid.uuid5(uuid.NAMESPACE_URL, raw_body.decode('utf-8', 'ignore'))}"
        )
        record = WebhookEvent(
            provider="razorpay",
            event_id=event_id,
            event_type=event_type,
            signature_valid=valid,
            payload=payload if valid else {"rejected": True},
            received_at=_now(),
        )
        self.db.add(record)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            logger.info("Duplicate Razorpay webhook %s ignored", event_id)
            return {"status": "duplicate"}
        if not valid:
            record.processing_error = "invalid signature"
            record.processed_at = _now()
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
        try:
            result = await self._process_event(event_type, payload)
            record.processed_at = _now()
            return {"status": "processed", **result}
        except Exception as exc:
            record.processing_error = f"{type(exc).__name__}: {exc}"[:500]
            record.processed_at = _now()
            logger.exception("Webhook processing failed for %s", event_id)
            return {"status": "error"}

    async def _process_event(self, event_type: str, payload: dict) -> dict:
        entity = ((payload.get("payload") or {}).get("payment") or {}).get("entity") or {}
        order_id = entity.get("order_id")
        payment_id = entity.get("id")
        if event_type in ("payment.captured", "order.paid") and order_id:
            payment = (
                await self.db.execute(
                    select(Payment).where(
                        Payment.provider == "razorpay", Payment.provider_order_id == order_id
                    )
                )
            ).scalar_one_or_none()
            if payment is None:
                return {"note": "unknown order"}
            if int(entity.get("amount", payment.amount)) != payment.amount:
                payment.failure_reason = "amount_mismatch"
                return {"note": "amount mismatch"}
            payment.raw = {
                **(payment.raw or {}),
                "method": entity.get("method"),
                "webhook": event_type,
            }
            await self._mark_paid(
                payment, payment_id or payment.provider_payment_id or "", via="webhook"
            )
            return {"payment": str(payment.id), "activated": True}
        if event_type == "payment.failed" and order_id:
            payment = (
                await self.db.execute(
                    select(Payment).where(
                        Payment.provider == "razorpay", Payment.provider_order_id == order_id
                    )
                )
            ).scalar_one_or_none()
            if payment and payment.status != "paid":
                payment.status = "failed"
                payment.failure_reason = (
                    entity.get("error_description") or entity.get("error_code") or "failed"
                )[:500]
            return {"payment": str(payment.id) if payment else None, "failed": True}
        if event_type.startswith("subscription."):
            # Razorpay Subscriptions (recurring) — recorded for audit; period passes are the V1 model.
            return {"note": f"{event_type} recorded"}
        return {"note": "ignored"}
