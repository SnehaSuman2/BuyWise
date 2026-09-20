"""Endpoints for trusted automation, such as a scheduler running background jobs.

Authenticated by a shared secret header rather than a user session, so a cron
runner needs no account and no token that expires. Disabled entirely until
CRON_SECRET is set.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.workers import jobs

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_cron_secret(request: Request) -> None:
    settings = get_settings()
    supplied = request.headers.get("X-Cron-Secret", "")
    if not settings.CRON_SECRET or not hmac.compare_digest(supplied, settings.CRON_SECRET):
        raise HTTPException(status_code=401, detail="Invalid or missing cron secret")


@router.post("/jobs/{job_name}")
async def run_scheduled_job(
    job_name: str, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    """Run one background job inline. job_name: refresh_prices | check_alerts |
    assess_new_retailers | refresh_trust | cleanup."""
    _require_cron_secret(request)
    if job_name not in jobs.JOBS:
        raise HTTPException(status_code=404, detail=f"Unknown job {job_name}")
    return await jobs.run_job(job_name, db)
