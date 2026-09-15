"""Email providers: Resend (live) or console (logs only)."""

from app.core.config import get_settings
from app.providers.email.base import BaseEmailProvider, EmailResult
from app.providers.email.console import ConsoleEmailProvider
from app.providers.email.resend import ResendEmailProvider


def get_email_provider() -> BaseEmailProvider:
    s = get_settings()
    if s.email_enabled:
        return ResendEmailProvider()
    return ConsoleEmailProvider()


__all__ = [
    "BaseEmailProvider",
    "EmailResult",
    "ConsoleEmailProvider",
    "ResendEmailProvider",
    "get_email_provider",
]
