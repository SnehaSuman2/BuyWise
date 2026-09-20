"""Serves price history + buy/wait signal from stored observations only."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models import PriceHistory, Product
from app.schemas.common import DataMeta
from app.schemas.price import (
    PriceHistoryResponse,
    PricePoint,
    PriceSignalResponse,
    PriceStatsResponse,
)
from app.services.price_intelligence import (
    Observation,
    compute_stats,
    daily_minimums,
    evaluate_signal,
)


class PriceHistoryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def observations(self, product_id: uuid.UUID, days: int) -> list[PriceHistory]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = select(PriceHistory).where(
            PriceHistory.product_id == product_id, PriceHistory.observed_at >= since
        )
        if not self.settings.demo_mode:
            stmt = stmt.where(PriceHistory.is_demo.is_(False))
        stmt = stmt.options(selectinload(PriceHistory.offer)).order_by(
            PriceHistory.observed_at.asc()
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_history(
        self, product_id: uuid.UUID, days: int = 90, max_days: int | None = None
    ) -> PriceHistoryResponse | None:
        product = (
            await self.db.execute(select(Product).where(Product.id == product_id))
        ).scalar_one_or_none()
        if product is None:
            return None
        days = max(7, min(days, max_days or days))
        rows = await self.observations(product_id, days)
        obs = [
            Observation(
                r.observed_at.replace(tzinfo=r.observed_at.tzinfo or timezone.utc),
                float(r.estimated_final_price),
            )
            for r in rows
        ]
        stats = compute_stats(obs)
        signal = evaluate_signal(stats)
        series = daily_minimums(obs)
        is_demo = bool(rows) and all(r.is_demo for r in rows)
        message = None
        if not rows:
            message = "Price history unavailable for this product. BuyWise records prices each time the product is looked up or refreshed."
        elif signal.action == "INSUFFICIENT_DATA":
            first = min(o.observed_at for o in obs)
            message = (
                f"BuyWise has recorded {len(obs)} price observation(s) for this product "
                f"since {first.strftime('%d %b %Y')}. History builds each time the product "
                f"is looked up or refreshed; BuyWise never back-fills prices it did not see."
            )
        return PriceHistoryResponse(
            product_id=product.id,
            product_name=product.name,
            days_requested=days,
            days_available=stats.span_days if stats else 0,
            history=[PricePoint(date=o.observed_at, price=o.price) for o in series],
            stats=PriceStatsResponse(**stats.as_dict()) if stats else None,
            signal=PriceSignalResponse(**signal.as_dict()),
            message=message,
            meta=DataMeta(
                data_mode="demo" if is_demo else "live",
                is_demo=is_demo,
                providers=sorted({r.source_provider for r in rows}),
            ),
        )
