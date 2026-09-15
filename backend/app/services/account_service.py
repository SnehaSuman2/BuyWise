"""Account: dashboard, saved products, preferences, deletion."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import (
    Notification,
    PriceAlert,
    Product,
    RefreshSession,
    SavedProduct,
    Search,
    Subscription,
    User,
)
from app.services.auth_service import AuthService
from app.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


class AccountService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def saved_products(self, user: User) -> list[dict]:
        rows = (
            (
                await self.db.execute(
                    select(SavedProduct)
                    .where(SavedProduct.user_id == user.id)
                    .order_by(SavedProduct.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        out = []
        from app.services.alert_service import AlertService

        alerts = AlertService(self.db)
        for r in rows:
            p = r.product
            out.append(
                {
                    "id": str(r.id),
                    "product_id": str(p.id),
                    "name": p.name,
                    "image": (p.images or [None])[0],
                    "brand": p.brand,
                    "note": r.note,
                    "lowest_price": await alerts.current_lowest(p.id),
                    "is_demo": p.is_demo,
                    "saved_at": r.created_at,
                }
            )
        return out

    async def save_product(self, user: User, product_id: uuid.UUID, note: str | None) -> dict:
        product = (
            await self.db.execute(select(Product).where(Product.id == product_id))
        ).scalar_one_or_none()
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        limit = (
            self.settings.PRO_MAX_SAVED_PRODUCTS
            if user.plan == "pro"
            else self.settings.FREE_MAX_SAVED_PRODUCTS
        )
        existing = (
            await self.db.execute(
                select(SavedProduct).where(
                    SavedProduct.user_id == user.id, SavedProduct.product_id == product_id
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.note = note
            return {"id": str(existing.id), "product_id": str(product_id), "already_saved": True}
        count = (
            await self.db.execute(
                select(func.count())
                .select_from(SavedProduct)
                .where(SavedProduct.user_id == user.id)
            )
        ).scalar_one()
        if count >= limit:
            raise HTTPException(
                status_code=402,
                detail=f"Saved product limit reached ({limit}). Upgrade to BuyWise Pro for more.",
            )
        row = SavedProduct(user_id=user.id, product_id=product_id, note=note)
        self.db.add(row)
        await self.db.flush()
        return {"id": str(row.id), "product_id": str(product_id), "already_saved": False}

    async def unsave_product(self, user: User, product_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            delete(SavedProduct).where(
                SavedProduct.user_id == user.id, SavedProduct.product_id == product_id
            )
        )
        return result.rowcount > 0

    async def dashboard(self, user: User) -> dict:
        subs = SubscriptionService(self.db)
        status = await subs.status(user)
        alerts = (
            (
                await self.db.execute(
                    select(PriceAlert)
                    .where(PriceAlert.user_id == user.id, PriceAlert.deleted_at.is_(None))
                    .order_by(PriceAlert.created_at.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        searches = (
            (
                await self.db.execute(
                    select(Search)
                    .where(Search.user_id == user.id)
                    .order_by(Search.created_at.desc())
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )
        notifications = (
            (
                await self.db.execute(
                    select(Notification)
                    .where(Notification.user_id == user.id)
                    .order_by(Notification.created_at.desc())
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )
        payments = await subs.payments_for(user.id)
        drops = [a for a in alerts if a.is_triggered]
        return {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "display_name": user.display_name,
                "plan": user.plan,
                "role": user.role,
                "auth_provider": user.auth_provider,
                "notification_preferences": user.notification_preferences or {"email": True},
            },
            "subscription": status.model_dump(mode="json"),
            "saved_products": await self.saved_products(user),
            "alerts": [
                {
                    "id": str(a.id),
                    "product_id": str(a.product_id),
                    "product_name": a.product.name if a.product else None,
                    "alert_type": a.alert_type,
                    "target_price": float(a.target_price) if a.target_price else None,
                    "drop_percent": float(a.drop_percent) if a.drop_percent else None,
                    "current_lowest_price": float(a.current_lowest_price)
                    if a.current_lowest_price
                    else None,
                    "is_active": a.is_active,
                    "is_triggered": a.is_triggered,
                    "triggered_at": a.triggered_at,
                }
                for a in alerts
            ],
            "price_drops": [
                {
                    "alert_id": str(a.id),
                    "product_id": str(a.product_id),
                    "product_name": a.product.name if a.product else None,
                    "current_lowest_price": float(a.current_lowest_price)
                    if a.current_lowest_price
                    else None,
                    "triggered_at": a.triggered_at,
                }
                for a in drops
            ],
            "recent_searches": [
                {
                    "id": str(s.id),
                    "query": s.query_text,
                    "type": s.query_type,
                    "results": s.results_count,
                    "at": s.created_at,
                }
                for s in searches
            ],
            "notifications": [
                {
                    "id": str(n.id),
                    "kind": n.kind,
                    "subject": n.subject,
                    "status": n.status,
                    "created_at": n.created_at,
                    "read_at": n.read_at,
                }
                for n in notifications
            ],
            "payments": [
                {
                    "id": str(p.id),
                    "plan": p.plan,
                    "amount": p.amount,
                    "currency": p.currency,
                    "status": p.status,
                    "paid_at": p.paid_at,
                    "created_at": p.created_at,
                    "order_id": p.provider_order_id,
                }
                for p in payments
            ],
        }

    async def update_profile(
        self, user: User, display_name: str | None, prefs: dict | None
    ) -> User:
        if display_name is not None:
            user.display_name = display_name.strip()[:100] or user.username
        if prefs is not None:
            allowed = {
                k: bool(v)
                for k, v in prefs.items()
                if k in ("email", "price_alerts", "product_updates", "marketing")
            }
            user.notification_preferences = {**(user.notification_preferences or {}), **allowed}
        return user

    async def delete_account(self, user: User) -> None:
        """Soft-delete + anonymise personal data, revoke sessions, cancel subscription and alerts.

        Payment records are retained (anonymised link) for accounting obligations.
        """
        now = datetime.now(timezone.utc)
        auth = AuthService(self.db)
        await auth.logout_all(user)
        await self.db.execute(delete(SavedProduct).where(SavedProduct.user_id == user.id))
        alerts = (
            (await self.db.execute(select(PriceAlert).where(PriceAlert.user_id == user.id)))
            .scalars()
            .all()
        )
        for a in alerts:
            a.is_active = False
            a.deleted_at = now
        subs = (
            (
                await self.db.execute(
                    select(Subscription).where(
                        Subscription.user_id == user.id, Subscription.status == "active"
                    )
                )
            )
            .scalars()
            .all()
        )
        for s in subs:
            s.status = "cancelled"
            s.cancelled_at = now
        await self.db.execute(delete(RefreshSession).where(RefreshSession.user_id == user.id))
        searches = (
            (await self.db.execute(select(Search).where(Search.user_id == user.id))).scalars().all()
        )
        for s in searches:
            s.user_id = None
        anon = f"deleted-{uuid.uuid4().hex[:12]}"
        user.email = f"{anon}@deleted.buywise.invalid"
        user.username = anon
        user.display_name = "Deleted user"
        user.avatar_url = None
        user.password_hash = None
        user.google_sub = None
        user.notification_preferences = {}
        user.is_active = False
        user.plan = "free"
        user.deleted_at = now
        logger.info("Account deleted and anonymised: user_id=%s", user.id)
