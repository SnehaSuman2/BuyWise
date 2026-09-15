"""Shared outbound HTTP client with timeouts and retry helpers.

Also provides SSRF-safe URL validation for user-supplied URLs.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import random
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=10.0),
            headers={"User-Agent": "BuyWise/2.0 (+https://www.buywise.co.in)"},
            follow_redirects=False,
        )
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def request_with_retry(
    method: str,
    url: str,
    *,
    max_retries: int = 2,
    backoff_base: float = 0.8,
    **kwargs,
) -> httpx.Response:
    """Perform a request, retrying transient failures with exponential backoff."""
    client = get_http_client()
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = await client.request(method, url, **kwargs)
            if response.status_code in RETRYABLE_STATUS and attempt < max_retries:
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else backoff_base * (2**attempt)
                )
                await asyncio.sleep(min(delay + random.uniform(0, 0.3), 10))
                continue
            return response
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            if attempt < max_retries:
                await asyncio.sleep(backoff_base * (2**attempt))
                continue
            raise
    assert last_exc is not None  # pragma: no cover
    raise last_exc


class UnsafeURLError(ValueError):
    pass


def validate_public_http_url(url: str) -> str:
    """Reject non-http(s) URLs and obvious private/loopback targets (SSRF guard)."""
    try:
        parsed = urlparse(url.strip())
    except Exception as exc:  # pragma: no cover
        raise UnsafeURLError("Invalid URL") from exc
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError("Only http(s) URLs are supported")
    host = (parsed.hostname or "").lower()
    if (
        not host
        or host in {"localhost", "0.0.0.0"}
        or host.endswith(".local")
        or host.endswith(".internal")
    ):
        raise UnsafeURLError("URL host is not allowed")
    ip = None
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None  # hostname, not an IP literal
    if ip is not None and (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise UnsafeURLError("URL host is not allowed")
    if host.endswith((".localhost", ".lan", ".home", ".corp")) or "." not in host:
        raise UnsafeURLError("URL host is not allowed")
    if len(url) > 2048:
        raise UnsafeURLError("URL too long")
    return url.strip()
