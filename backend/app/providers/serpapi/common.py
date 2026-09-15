"""Shared normalization helpers for SerpApi engines."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from app.providers.base import parse_int, parse_price

_ASIN_RE = re.compile(r"/(?:dp|gp/product|product)/([A-Z0-9]{10})(?:[/?]|$)")


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return None
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def extract_asin(url: str | None) -> str | None:
    if not url:
        return None
    m = _ASIN_RE.search(url)
    return m.group(1) if m else None


def unwrap_google_redirect(url: str | None) -> str | None:
    """Google Shopping links are often google.com/url?q=<real>. Return the real URL when present."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    if "google." in (parsed.hostname or "") and parsed.path in ("/url", "/aclk"):
        target = parse_qs(parsed.query).get("q") or parse_qs(parsed.query).get("url")
        if target:
            return target[0]
    return url


def availability_from_text(*texts: str | None) -> str:
    joined = " ".join(t for t in texts if t).lower()
    if not joined:
        return "unknown"
    if "out of stock" in joined or "unavailable" in joined or "sold out" in joined:
        return "out_of_stock"
    if "only" in joined and "left" in joined:
        return "limited"
    if "in stock" in joined or "delivery" in joined or "get it" in joined:
        return "in_stock"
    return "unknown"


def shipping_from_text(text: str | None) -> tuple[float | None, bool]:
    """Return (shipping_price, known). 'Free delivery' -> (0, True). '₹49 delivery' -> (49, True)."""
    if not text:
        return None, False
    lower = text.lower()
    if "free" in lower and ("deliver" in lower or "shipping" in lower):
        return 0.0, True
    price = parse_price(text)
    if price is not None and ("deliver" in lower or "shipping" in lower):
        return price, True
    return None, False


def delivery_days_from_text(text: str | None) -> int | None:
    if not text:
        return None
    lower = text.lower()
    if "today" in lower or "same day" in lower:
        return 0
    if "tomorrow" in lower:
        return 1
    m = re.search(r"(\d+)\s*[-–to]*\s*(\d+)?\s*(?:business\s+)?days?", lower)
    if m:
        return int(m.group(1))
    return None


def rating_of(value) -> float | None:
    try:
        f = float(value)
        return f if 0 < f <= 5 else None
    except (TypeError, ValueError):
        return None


def reviews_of(value) -> int | None:
    return parse_int(value)
