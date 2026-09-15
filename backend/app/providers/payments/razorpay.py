"""Razorpay client: order creation, payment fetch, and signature verification.

Signature verification uses constant-time HMAC-SHA256 comparison. Webhook
signatures are verified against the *raw* request body.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from app.core.config import get_settings
from app.core.http import request_with_retry

logger = logging.getLogger(__name__)
RAZORPAY_API = "https://api.razorpay.com/v1"


class RazorpayError(Exception):
    pass


def verify_payment_signature(
    order_id: str, payment_id: str, signature: str, key_secret: str
) -> bool:
    """Checkout signature: HMAC_SHA256(order_id + '|' + payment_id, key_secret)."""
    if not (order_id and payment_id and signature and key_secret):
        return False
    expected = hmac.new(
        key_secret.encode("utf-8"), f"{order_id}|{payment_id}".encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def verify_webhook_signature(raw_body: bytes, signature: str, webhook_secret: str) -> bool:
    """Webhook signature: HMAC_SHA256(raw_body, webhook_secret) sent as X-Razorpay-Signature."""
    if not (raw_body and signature and webhook_secret):
        return False
    expected = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


class RazorpayClient:
    def __init__(self) -> None:
        s = get_settings()
        self.key_id = s.RAZORPAY_KEY_ID
        self.key_secret = s.RAZORPAY_KEY_SECRET

    @property
    def enabled(self) -> bool:
        return bool(self.key_id and self.key_secret)

    async def _request(self, method: str, path: str, json: dict | None = None) -> dict[str, Any]:
        if not self.enabled:
            raise RazorpayError("Razorpay is not configured")
        try:
            resp = await request_with_retry(
                method,
                f"{RAZORPAY_API}{path}",
                auth=(self.key_id, self.key_secret),
                json=json,
                timeout=20.0,
                max_retries=1,
            )
        except Exception as exc:
            raise RazorpayError(f"Razorpay request failed: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            try:
                desc = (resp.json().get("error") or {}).get("description")
            except ValueError:
                desc = None
            raise RazorpayError(f"Razorpay HTTP {resp.status_code}: {desc or 'error'}")
        return resp.json()

    async def create_order(
        self, amount_paise: int, currency: str, receipt: str, notes: dict[str, str]
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/orders",
            {"amount": amount_paise, "currency": currency, "receipt": receipt, "notes": notes},
        )

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/payments/{payment_id}")

    async def fetch_order(self, order_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/orders/{order_id}")
