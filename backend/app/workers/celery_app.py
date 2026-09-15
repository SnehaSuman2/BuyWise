"""Celery application configuration (Redis broker when REDIS_URL is set)."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("buywise", broker=settings.celery_broker, backend=settings.celery_backend)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=15 * 60,
)
celery_app.conf.beat_schedule = {
    "refresh-prices": {
        "task": "app.workers.tasks.refresh_prices",
        "schedule": crontab(minute="15", hour="*/6"),
    },
    "check-price-alerts": {
        "task": "app.workers.tasks.check_alerts",
        "schedule": crontab(minute="*/30"),
    },
    "refresh-trust": {
        "task": "app.workers.tasks.refresh_trust",
        "schedule": crontab(minute="0", hour="3"),
    },
    "cleanup": {"task": "app.workers.tasks.cleanup", "schedule": crontab(minute="30", hour="4")},
}
celery_app.autodiscover_tasks(["app.workers"])
