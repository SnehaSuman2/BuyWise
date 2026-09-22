"""Razorpay client: order creation, payment fetch, and signature verification.

Signature verification uses constant-time HMAC-SHA256 comparison. Webhook
signatures are verified against the *raw* request body.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

from app.core.config import get_settings
from app.core.http import request_with_retry

logger = logging.getLogger(__name__)
RAZORPAY_API = "https://api.razorpay.com/v1"
# Result of the last credential check, and when it was taken. A key pair does
# not change between requests, so asking once every few minutes is enough.
_CREDENTIAL_CHECK: tuple[float, bool] | None = None
_CREDENTIAL_TTL = 600.0


class RazorpayError(Exception):
    pass


class RazorpayAuthError(RazorpayError):
    """Razorpay rejected our key id and secret.

    Kept apart from every other failure because the cause and the cure are
    different: nothing is wrong with the shopper or their payment, our own
    credentials are wrong, empty or from the other mode. Without this the
    logs said only "Razorpay HTTP 401" among ordinary upstream errors.
    """


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
            if resp.status_code in (401, 403):
                raise RazorpayAuthError(
                    f"Razorpay rejected the API credentials (HTTP {resp.status_code}): "
                    f"{desc or 'unauthorized'}. Check RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET "
                    f"are the pair from the same account and the same mode."
                )
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

    async def credentials_ok(self) -> bool:
        """Whether Razorpay still accepts the configured key id and secret.

        A key that has been regenerated or deleted still looks configured from
        inside: the settings are populated, so the site offers checkout, and
        the shopper meets a bare "Oops! Something went wrong" from Razorpay's
        own script at its loading screen. Asking first lets the page say what
        is actually wrong, and lets the logs name it.

        Being unable to reach Razorpay is not a verdict. Only an explicit
        refusal counts as a no, so a network blip never takes payments down.
        """
        global _CREDENTIAL_CHECK
        if not self.enabled:
            return False
        now = time.monotonic()
        if _CREDENTIAL_CHECK is not None and now - _CREDENTIAL_CHECK[0] < _CREDENTIAL_TTL:
            return _CREDENTIAL_CHECK[1]
        try:
            await self._request("GET", "/orders?count=1")
            ok = True
        except RazorpayAuthError as exc:
            logger.error("Razorpay refused the configured credentials: %s", exc)
            ok = False
        except RazorpayError as exc:
            logger.warning("Could not check Razorpay credentials: %s", exc)
            return _CREDENTIAL_CHECK[1] if _CREDENTIAL_CHECK is not None else True
        _CREDENTIAL_CHECK = (now, ok)
        return ok

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/payments/{payment_id}")

    async def fetch_order(self, order_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/orders/{order_id}")
