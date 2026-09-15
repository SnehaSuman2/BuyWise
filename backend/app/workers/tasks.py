"""Celery tasks — thin wrappers that run the async jobs."""

import asyncio

from app.workers.celery_app import celery_app
from app.workers.jobs import run_job_standalone


@celery_app.task(name="app.workers.tasks.refresh_prices")
def refresh_prices():
    return asyncio.run(run_job_standalone("refresh_prices"))


@celery_app.task(name="app.workers.tasks.check_alerts")
def check_alerts():
    return asyncio.run(run_job_standalone("check_alerts"))


@celery_app.task(name="app.workers.tasks.refresh_trust")
def refresh_trust():
    return asyncio.run(run_job_standalone("refresh_trust"))


@celery_app.task(name="app.workers.tasks.cleanup")
def cleanup():
    return asyncio.run(run_job_standalone("cleanup"))


@celery_app.task(name="app.workers.tasks.assess_new_retailers")
def assess_new_retailers():
    return asyncio.run(run_job_standalone("assess_new_retailers"))
