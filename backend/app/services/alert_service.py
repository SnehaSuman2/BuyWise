"""Price alerts: CRUD with plan limits, and the background checker."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Offer, PriceAlert, Product, User
from app.schemas.alert import AlertCreate, AlertResponse
from app.services.notification_service import NotificationService
from app.services.product_matcher import MatchType

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AlertService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def current_lowest(self, product_id: uuid.UUID) -> float | None:
        stmt = select(func.min(Offer.estimated_final_price)).where(
            Offer.product_id == product_id,
            Offer.is_active.is_(True),
            Offer.match_type == MatchType.EXACT.value,
            Offer.availability != "out_of_stock",
        )
        if not self.settings.demo_mode:
            stmt = stmt.where(Offer.is_demo.is_(False))
        val = (await self.db.execute(stmt)).scalar_one_or_none()
        return float(val) if val is not None else None

    async def _limit(self, user: User) -> int:
        from app.services.subscription_service import entitlements_for

        return (await entitlements_for(self.db, user)).alerts

    async def create(self, user: User, data: AlertCreate) -> AlertResponse:
        product = (
            await self.db.execute(select(Product).where(Product.id == data.product_id))
        ).scalar_one_or_none()
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        active = (
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
        if active >= await self._limit(user):
            raise HTTPException(
                status_code=402,
                detail=f"Alert limit reached for your plan ({await self._limit(user)}). Upgrade to BuyWise Pro for more alerts.",
            )
        current = await self.current_lowest(product.id)
        alert = PriceAlert(
            user_id=user.id,
            product_id=product.id,
            alert_type=data.alert_type,
            target_price=data.target_price,
            drop_percent=data.drop_percent,
            baseline_price=current,
            current_lowest_price=current,
            notification_method=data.notification_method,
        )
        self.db.add(alert)
        await self.db.flush()
        return self._response(alert, product)

    async def list_for_user(self, user_id: uuid.UUID) -> list[AlertResponse]:
        rows = (
            (
                await self.db.execute(
                    select(PriceAlert)
                    .where(PriceAlert.user_id == user_id, PriceAlert.deleted_at.is_(None))
                    .order_by(PriceAlert.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return [self._response(a, a.product) for a in rows]

    async def delete(self, alert_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        alert = (
            await self.db.execute(
                select(PriceAlert).where(
                    PriceAlert.id == alert_id,
                    PriceAlert.user_id == user_id,
                    PriceAlert.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if alert is None:
            return False
        alert.deleted_at = _now()
        alert.is_active = False
        return True

    async def toggle(self, alert_id: uuid.UUID, user_id: uuid.UUID, active: bool) -> AlertResponse:
        alert = (
            await self.db.execute(
                select(PriceAlert).where(
                    PriceAlert.id == alert_id,
                    PriceAlert.user_id == user_id,
                    PriceAlert.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        alert.is_active = active
        if active:
            alert.is_triggered = False
        return self._response(alert, alert.product)

    @staticmethod
    def _response(alert: PriceAlert, product: Product | None) -> AlertResponse:
        return AlertResponse(
            id=alert.id,
            product_id=alert.product_id,
            product_name=product.name if product else None,
            product_image=(product.images or [None])[0] if product else None,
            alert_type=alert.alert_type,
            target_price=float(alert.target_price) if alert.target_price else None,
            drop_percent=float(alert.drop_percent) if alert.drop_percent else None,
            baseline_price=float(alert.baseline_price) if alert.baseline_price else None,
            currency=alert.currency,
            current_lowest_price=float(alert.current_lowest_price)
            if alert.current_lowest_price
            else None,
            is_active=alert.is_active,
            is_triggered=alert.is_triggered,
            triggered_at=alert.triggered_at,
            trigger_count=alert.trigger_count,
            last_checked_at=alert.last_checked_at,
            notification_method=alert.notification_method,
            created_at=alert.created_at,
        )

    @staticmethod
    def should_trigger(alert: PriceAlert, current: float) -> bool:
        if alert.alert_type == "target_price" and alert.target_price is not None:
            return current <= float(alert.target_price)
        if (
            alert.alert_type == "percent_drop"
            and alert.drop_percent is not None
            and alert.baseline_price
        ):
            return current <= float(alert.baseline_price) * (1 - float(alert.drop_percent) / 100)
        return False

    async def check_all(self, *, notify: bool = True, cooldown_hours: int = 24) -> dict:
        """Evaluate every active alert against the latest stored offers (no external API calls here)."""
        rows = (
            (
                await self.db.execute(
                    select(PriceAlert).where(
                        PriceAlert.is_active.is_(True), PriceAlert.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        notifier = NotificationService(self.db)
        checked = triggered = notified = 0
        for alert in rows:
            checked += 1
            current = await self.current_lowest(alert.product_id)
            alert.last_checked_at = _now()
            if current is None:
                continue
            alert.current_lowest_price = current
            if not self.should_trigger(alert, current):
                continue
            recently = alert.last_notified_at and (
                _now()
                - alert.last_notified_at.replace(
                    tzinfo=alert.last_notified_at.tzinfo or timezone.utc
                )
            ) < timedelta(hours=cooldown_hours)
            alert.is_triggered = True
            alert.triggered_at = _now()
            alert.trigger_count += 1
            triggered += 1
            if notify and not recently and alert.notification_method == "email":
                user = (
                    await self.db.execute(select(User).where(User.id == alert.user_id))
                ).scalar_one_or_none()
                product = alert.product
                if user and product:
                    goal = (
                        f"₹{float(alert.target_price):,.0f}"
                        if alert.alert_type == "target_price"
                        else f"a {float(alert.drop_percent):.0f}% drop"
                    )
                    app_url = self.settings.NEXT_PUBLIC_APP_URL.rstrip("/")
                    body = (
                        f"Good news — {product.name} is now ₹{current:,.0f} (your alert: {goal}).\n\n"
                        f"See offers and trust scores: {app_url}/product/{product.id}\n\nManage alerts: {app_url}/alerts\n\n— BuyWise"
                    )
                    await notifier.notify(
                        user,
                        kind="price_alert",
                        subject=f"Price alert: {product.name[:60]} is ₹{current:,.0f}",
                        body=body,
                        alert_id=alert.id,
                        payload={"current_price": current},
                    )
                    alert.last_notified_at = _now()
                    notified += 1
        return {"checked": checked, "triggered": triggered, "notified": notified}
