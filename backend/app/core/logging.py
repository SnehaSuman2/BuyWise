"""Logging configuration with secret redaction.

Never log API keys, passwords, tokens or payment secrets. The redaction filter
scrubs anything that looks like one of our configured secrets or a bearer token.
"""

import logging
import re
import sys
from collections import deque
from datetime import datetime, timezone

from app.core.config import get_settings

_SECRET_PATTERNS = [
    re.compile(r"(api_key=)[^&\s]+", re.I),
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.I),
    re.compile(r"(rzp_(?:test|live)_[A-Za-z0-9]{6})[A-Za-z0-9]+"),
    re.compile(r"(sk-[A-Za-z0-9]{4})[A-Za-z0-9\-_]{10,}"),
    re.compile(r"(\"?password\"?\s*[:=]\s*\"?)[^\"\s,}]+", re.I),
]

# Small in-memory ring buffer of recent errors for the admin diagnostics endpoint.
RECENT_ERRORS: deque[dict] = deque(maxlen=100)


class RedactingFilter(logging.Filter):
    def __init__(self) -> None:
        super().__init__()
        s = get_settings()
        self._literal_secrets = [
            v
            for v in (
                s.SERPAPI_API_KEY,
                s.OPENAI_API_KEY,
                s.RAZORPAY_KEY_SECRET,
                s.RAZORPAY_WEBHOOK_SECRET,
                s.EMAIL_API_KEY,
                s.GOOGLE_CLIENT_SECRET,
                s.TRUSTPILOT_API_KEY,
                s.TRUSTPILOT_API_SECRET,
                s.TRUSTPILOT_ACCESS_TOKEN,
                s.SECRET_KEY,
            )
            if v and len(v) >= 8
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover
            return True
        redacted = msg
        for secret in self._literal_secrets:
            redacted = redacted.replace(secret, "[REDACTED]")
        for pat in _SECRET_PATTERNS:
            redacted = pat.sub(r"\1[REDACTED]", redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        if record.levelno >= logging.ERROR:
            RECENT_ERRORS.appendleft(
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "logger": record.name,
                    "message": redacted[:500],
                }
            )
        return True


def configure_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    if getattr(root, "_buywise_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-5s [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    handler.addFilter(RedactingFilter())
    root.handlers = [handler]
    root.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))
    for noisy in ("httpx", "httpcore", "sqlalchemy.engine", "celery"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._buywise_configured = True  # type: ignore[attr-defined]
