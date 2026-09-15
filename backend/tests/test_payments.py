"""Razorpay signature verification, server-side checkout verification, webhook idempotency."""

import hashlib
import hmac
import json
import uuid

import pytest

from app.models import Payment
from app.providers.payments.razorpay import (
    RazorpayClient,
    verify_payment_signature,
    verify_webhook_signature,
)

SECRET = "test_razorpay_secret"
WH = "test_webhook_secret"


def sign(order_id, payment_id, secret=SECRET):
    return hmac.new(
        secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()


def test_payment_signature():
    assert verify_payment_signature("order_1", "pay_1", sign("order_1", "pay_1"), SECRET)
    assert not verify_payment_signature("order_1", "pay_1", sign("order_1", "pay_2"), SECRET)
    assert not verify_payment_signature("order_1", "pay_1", "", SECRET)


def test_webhook_signature_uses_raw_body():
    body = b'{"event":"payment.captured"}'
    sig = hmac.new(WH.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(body, sig, WH)
    assert not verify_webhook_signature(body + b" ", sig, WH)


@pytest.mark.asyncio
async def test_checkout_verification_activates_pro(
    client, db, auth_headers, user_tokens, monkeypatch
):
    user_id = uuid.UUID(user_tokens["user"]["id"])
    db.add(
        Payment(
            user_id=user_id,
            provider="razorpay",
            provider_order_id="order_ok",
            plan="pro_monthly",
            period_days=30,
            amount=19900,
            currency="INR",
            status="created",
        )
    )
    await db.commit()

    async def fake_fetch(self, payment_id):
        return {
            "id": payment_id,
            "order_id": "order_ok",
            "amount": 19900,
            "status": "captured",
            "method": "upi",
        }

    monkeypatch.setattr(RazorpayClient, "fetch_payment", fake_fetch)
    bad = await client.post(
        "/api/v1/payments/verify",
        json={
            "razorpay_order_id": "order_ok",
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": "deadbeef",
        },
        headers=auth_headers,
    )
    assert bad.status_code == 400
    ok = await client.post(
        "/api/v1/payments/verify",
        json={
            "razorpay_order_id": "order_ok",
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": sign("order_ok", "pay_1"),
        },
        headers=auth_headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["is_pro"] is True and ok.json()["plan"] == "pro_monthly"
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.json()["plan"] == "pro"
    again = await client.post(
        "/api/v1/payments/verify",
        json={
            "razorpay_order_id": "order_ok",
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": sign("order_ok", "pay_1"),
        },
        headers=auth_headers,
    )
    assert again.status_code == 200  # idempotent


@pytest.mark.asyncio
async def test_other_user_cannot_verify_my_order(client, db, user_tokens):
    db.add(
        Payment(
            user_id=uuid.UUID(user_tokens["user"]["id"]),
            provider="razorpay",
            provider_order_id="order_x",
            plan="pro_monthly",
            period_days=30,
            amount=19900,
            currency="INR",
            status="created",
        )
    )
    await db.commit()
    other = await client.post(
        "/api/v1/auth/register",
        json={"email": "o@buywisetest.com", "username": "other", "password": "Passw0rd!x"},
    )
    r = await client.post(
        "/api/v1/payments/verify",
        json={
            "razorpay_order_id": "order_x",
            "razorpay_payment_id": "p",
            "razorpay_signature": sign("order_x", "p"),
        },
        headers={"Authorization": f"Bearer {other.json()['access_token']}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_webhook_idempotent_and_signature_checked(client, db, user_tokens):
    user_id = uuid.UUID(user_tokens["user"]["id"])
    db.add(
        Payment(
            user_id=user_id,
            provider="razorpay",
            provider_order_id="order_wh",
            plan="pro_yearly",
            period_days=365,
            amount=149900,
            currency="INR",
            status="created",
        )
    )
    await db.commit()
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_wh",
                    "order_id": "order_wh",
                    "amount": 149900,
                    "status": "captured",
                }
            }
        },
    }
    body = json.dumps(payload).encode()
    sig = hmac.new(WH.encode(), body, hashlib.sha256).hexdigest()
    bad = await client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={
            "X-Razorpay-Signature": "nope",
            "X-Razorpay-Event-Id": "evt_bad",
            "Content-Type": "application/json",
        },
    )
    assert bad.status_code == 400
    first = await client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={
            "X-Razorpay-Signature": sig,
            "X-Razorpay-Event-Id": "evt_1",
            "Content-Type": "application/json",
        },
    )
    assert (
        first.status_code == 200
        and first.json()["status"] == "processed"
        and first.json().get("activated") is True
    )
    dup = await client.post(
        "/api/v1/webhooks/razorpay",
        content=body,
        headers={
            "X-Razorpay-Signature": sig,
            "X-Razorpay-Event-Id": "evt_1",
            "Content-Type": "application/json",
        },
    )
    assert dup.json()["status"] == "duplicate"
    sub = await client.get(
        "/api/v1/subscription", headers={"Authorization": f"Bearer {user_tokens['access_token']}"}
    )
    assert sub.json()["is_pro"] is True and sub.json()["plan"] == "pro_yearly"
