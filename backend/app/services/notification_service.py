"""Notification records + delivery through the configured email provider."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Notification, User
from app.providers.email import get_email_provider

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def notify(
        self,
        user: User,
        *,
        kind: str,
        subject: str,
        body: str,
        html: str | None = None,
        alert_id: uuid.UUID | None = None,
        payload: dict | None = None,
        channel: str = "email",
    ) -> Notification:
        prefs = user.notification_preferences or {}
        record = Notification(
            user_id=user.id,
            alert_id=alert_id,
            channel=channel,
            kind=kind,
            subject=subject[:300],
            body=body,
            payload=payload or {},
            status="pending",
        )
        self.db.add(record)
        await self.db.flush()
        if channel == "email" and prefs.get("email", True) is False:
            record.status = "skipped"
            record.error = "user disabled email notifications"
            return record
        if channel != "email":
            record.status = "sent"
            record.sent_at = datetime.now(timezone.utc)
            return record
        provider = get_email_provider()
        result = await provider.send(user.email, subject, body, html)
        record.provider = result.provider
        record.provider_message_id = result.message_id
        if result.ok and not result.skipped:
            record.status = "sent"
            record.sent_at = datetime.now(timezone.utc)
        elif result.skipped:
            record.status = "skipped"
            record.error = "email provider not configured (console mode)"
        else:
            record.status = "failed"
            record.error = result.error
        return record
