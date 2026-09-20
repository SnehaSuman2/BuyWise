"""Admin / diagnostics routes (role=admin only)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import STATS as CACHE_STATS
from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import RECENT_ERRORS
from app.core.security import get_admin_user
from app.models import (
    JobRun,
    Offer,
    PriceAlert,
    Product,
    Retailer,
    TrustEvidence,
    User,
    WebhookEvent,
)
from app.providers import registry
from app.providers.llm.openai import STATS as OPENAI_STATS
from app.providers.search_client import breaker_status, search_stats
from app.schemas.community import CommunityReportResponse, ModerationAction
from app.services.community_service import CommunityService

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_admin_user)])


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db)):
    s = get_settings()
    counts = {}
    for name, model in (
        ("users", User),
        ("products", Product),
        ("offers", Offer),
        ("retailers", Retailer),
        ("alerts", PriceAlert),
        ("trust_evidence", TrustEvidence),
    ):
        counts[name] = (await db.execute(select(func.count()).select_from(model))).scalar_one()
    jobs = (
        (await db.execute(select(JobRun).order_by(JobRun.started_at.desc()).limit(20)))
        .scalars()
        .all()
    )
    failed_webhooks = (
        (
            await db.execute(
                select(WebhookEvent)
                .where(WebhookEvent.processing_error.is_not(None))
                .order_by(WebhookEvent.received_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    return {
        "environment": s.ENVIRONMENT,
        "integrations": s.integration_status(),
        "providers": registry.provider_status(),
        "search_api": search_stats(),
        "search_breaker": breaker_status(),
        "openai": OPENAI_STATS,
        "cache": CACHE_STATS,
        "counts": counts,
        "recent_jobs": [
            {
                "job": j.job_name,
                "status": j.status,
                "started_at": j.started_at,
                "finished_at": j.finished_at,
                "details": j.details,
                "error": j.error,
            }
            for j in jobs
        ],
        "failed_jobs": [
            {"job": j.job_name, "started_at": j.started_at, "error": j.error}
            for j in jobs
            if j.status == "failed"
        ],
        "failed_webhooks": [
            {
                "event_id": w.event_id,
                "type": w.event_type,
                "error": w.processing_error,
                "received_at": w.received_at,
            }
            for w in failed_webhooks
        ],
        "recent_errors": list(RECENT_ERRORS)[:25],
    }


@router.get("/moderation", response_model=list[CommunityReportResponse])
async def moderation_queue(status: str = Query("pending"), db: AsyncSession = Depends(get_db)):
    return await CommunityService(db).moderation_queue(status)


@router.post("/moderation/{report_id}", response_model=CommunityReportResponse)
async def moderate(
    report_id: UUID,
    data: ModerationAction,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_admin_user),
):
    return await CommunityService(db).moderate(admin, report_id, data.action, data.note)


@router.post("/jobs/{job_name}")
async def run_job(job_name: str, db: AsyncSession = Depends(get_db)):
    """Run a background job inline (useful without Celery). job_name: check_alerts | refresh_prices | refresh_trust | cleanup."""
    from app.workers import jobs

    return await jobs.run_job(job_name, db)
