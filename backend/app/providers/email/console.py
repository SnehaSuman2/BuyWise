"""Console email provider — logs the email (recipient masked) instead of sending it."""

from __future__ import annotations

import logging

from app.providers.email.base import BaseEmailProvider, EmailResult

logger = logging.getLogger(__name__)


def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[:2]}***@{domain}"


class ConsoleEmailProvider(BaseEmailProvider):
    name = "console"

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> EmailResult:
        logger.info(
            "[console-email] to=%s subject=%r (EMAIL_API_KEY not configured; not sent)",
            mask_email(to),
            subject,
        )
        return EmailResult(ok=True, provider=self.name, skipped=True)
