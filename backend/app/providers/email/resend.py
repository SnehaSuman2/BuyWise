"""Resend email provider (https://resend.com). Uses EMAIL_API_KEY and EMAIL_FROM."""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.core.http import request_with_retry
from app.providers.email.base import BaseEmailProvider, EmailResult
from app.providers.email.console import mask_email

logger = logging.getLogger(__name__)


class ResendEmailProvider(BaseEmailProvider):
    name = "resend"

    @property
    def enabled(self) -> bool:
        return get_settings().email_enabled

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> EmailResult:
        s = get_settings()
        if not self.enabled:
            return EmailResult(ok=False, provider=self.name, error="EMAIL_API_KEY not configured")
        payload = {"from": s.EMAIL_FROM, "to": [to], "subject": subject, "text": text}
        if html:
            payload["html"] = html
        try:
            resp = await request_with_retry(
                "POST",
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {s.EMAIL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15.0,
                max_retries=1,
            )
        except Exception as exc:
            logger.warning("Resend send failed for %s: %s", mask_email(to), type(exc).__name__)
            return EmailResult(ok=False, provider=self.name, error=type(exc).__name__)
        if resp.status_code >= 400:
            logger.warning("Resend returned HTTP %s for %s", resp.status_code, mask_email(to))
            return EmailResult(ok=False, provider=self.name, error=f"http_{resp.status_code}")
        return EmailResult(ok=True, provider=self.name, message_id=(resp.json() or {}).get("id"))
