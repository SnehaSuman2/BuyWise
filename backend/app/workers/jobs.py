"""Background job implementations (async). Run via Celery tasks or inline (`python -m app.workers.run_jobs`)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import JobRun, PriceAlert, Product, RefreshSession, Retailer, SavedProduct, Search
from app.services.alert_service import AlertService
from app.services.offer_service import OfferService
from app.services.trust_service import TrustService

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _tracked_products(db: AsyncSession, limit: int) -> list[Product]:
    """Products with active alerts or saved by users — refreshed first, oldest observation first."""
    alert_ids = select(PriceAlert.product_id).where(
        PriceAlert.is_active.is_(True), PriceAlert.deleted_at.is_(None)
    )
    saved_ids = select(SavedProduct.product_id)
    stmt = (
        select(Product)
        .where(Product.id.in_(alert_ids) | Product.id.in_(saved_ids))
        .order_by(Product.updated_at.asc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def refresh_prices(db: AsyncSession, limit: int = 50) -> dict:
    """Refresh offers/prices for tracked products (bounded to respect API budgets)."""
    settings = get_settings()
    products = await _tracked_products(db, limit)
    service = OfferService(db)
    refreshed = failed = 0
    for product in products:
        try:
            await service.refresh_offers(product)
            product.updated_at = _now()
            refreshed += 1
        except Exception as exc:
            failed += 1
            logger.warning("Price refresh failed for %s: %s", product.id, type(exc).__name__)
    return {
        "tracked": len(products),
        "refreshed": refreshed,
        "failed": failed,
        "data_mode": settings.data_mode,
    }


async def check_alerts(db: AsyncSession) -> dict:
    return await AlertService(db).check_all(notify=True)


async def refresh_trust(db: AsyncSession, limit: int = 20) -> dict:
    """Refresh trust evidence for retailers with the oldest scores."""
    retailers = list(
        (await db.execute(select(Retailer).order_by(Retailer.updated_at.asc()).limit(limit)))
        .scalars()
        .all()
    )
    service = TrustService(db)
    done = failed = 0
    for r in retailers:
        try:
            await service.ensure_retailer_score(r, refresh=True)
            r.updated_at = _now()
            done += 1
        except Exception as exc:
            failed += 1
            logger.warning("Trust refresh failed for %s: %s", r.slug, type(exc).__name__)
    return {"retailers": len(retailers), "refreshed": done, "failed": failed}


async def cleanup(db: AsyncSession) -> dict:
    cutoff_sessions = _now()
    expired = await db.execute(
        delete(RefreshSession).where(
            (RefreshSession.expires_at < cutoff_sessions) | (RefreshSession.revoked_at.is_not(None))
        )
    )
    old_searches = await db.execute(
        delete(Search).where(
            Search.user_id.is_(None), Search.created_at < _now() - timedelta(days=30)
        )
    )
    old_jobs = await db.execute(
        delete(JobRun).where(JobRun.started_at < _now() - timedelta(days=30))
    )
    return {
        "sessions_deleted": expired.rowcount,
        "anonymous_searches_deleted": old_searches.rowcount,
        "job_runs_deleted": old_jobs.rowcount,
    }


async def assess_new_retailers(db: AsyncSession, limit: int = 10) -> dict:
    """Gather trust evidence for merchants that appeared in results but were never
    assessed, so they can graduate from "unverified" to a real score — or be flagged.

    This is what lets a small Indian retailer earn its way into results on evidence
    rather than by paying for placement. Bounded per run because each retailer costs
    several SerpApi calls.
    """
    service = TrustService(db)
    pending = await service.retailers_needing_assessment(limit=limit)
    assessed, flagged, failed = 0, 0, 0
    for retailer in pending:
        try:
            score = await service.ensure_retailer_score(retailer, refresh=True)
            assessed += 1
            if score.risk_level == "high" and score.confidence_level in ("medium", "high"):
                flagged += 1
                logger.info(
                    "Merchant flagged as high risk: %s (score=%s, confidence=%s)",
                    retailer.name,
                    score.overall_score,
                    score.confidence_level,
                )
        except Exception as exc:
            failed += 1
            logger.warning("Trust assessment failed for %s: %s", retailer.slug, type(exc).__name__)
    return {"pending": len(pending), "assessed": assessed, "flagged": flagged, "failed": failed}


JOBS = {
    "refresh_prices": refresh_prices,
    "check_alerts": check_alerts,
    "refresh_trust": refresh_trust,
    "assess_new_retailers": assess_new_retailers,
    "cleanup": cleanup,
}


async def run_job(name: str, db: AsyncSession) -> dict:
    fn = JOBS.get(name)
    if fn is None:
        raise ValueError(f"Unknown job {name}. Available: {', '.join(JOBS)}")
    run = JobRun(job_name=name, status="running", started_at=_now())
    db.add(run)
    await db.flush()
    try:
        result = await fn(db)
        run.status = "success"
        run.details = result
        run.finished_at = _now()
        await db.commit()
        logger.info("Job %s finished: %s", name, result)
        return {"job": name, "status": "success", **result}
    except Exception as exc:
        await db.rollback()
        run = JobRun(
            job_name=name,
            status="failed",
            started_at=run.started_at,
            finished_at=_now(),
            error=f"{type(exc).__name__}: {exc}"[:1000],
        )
        db.add(run)
        await db.commit()
        logger.exception("Job %s failed", name)
        return {"job": name, "status": "failed", "error": type(exc).__name__}


async def run_job_standalone(name: str) -> dict:
    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        return await run_job(name, db)
