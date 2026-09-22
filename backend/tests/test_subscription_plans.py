"""Plan pricing and the rules that protect a paid subscription."""

import pytest

from app.core.config import get_settings
from app.services.subscription_service import plan_by_id, plans


def test_the_three_paid_periods_and_their_prices():
    by_id = {p.id: p for p in plans()}
    assert by_id["pro_monthly"].price_inr == 99 and by_id["pro_monthly"].period_days == 30
    assert by_id["pro_6month"].price_inr == 449 and by_id["pro_6month"].period_days == 180
    assert by_id["pro_yearly"].price_inr == 799 and by_id["pro_yearly"].period_days == 365
    assert by_id["free"].price_inr == 0


def test_savings_are_real_and_never_overstated():
    by_id = {p.id: p for p in plans()}
    monthly = by_id["pro_monthly"].price_inr
    for plan_id in ("pro_6month", "pro_yearly"):
        plan = by_id[plan_id]
        months = plan.period_days / 30
        # The per-month figure is the price divided by the period, nothing else.
        assert plan.monthly_equivalent_inr == pytest.approx(plan.price_inr / months, abs=0.01)
        assert plan.monthly_equivalent_inr < monthly
        claimed = plan.savings_percent
        actual = (1 - plan.monthly_equivalent_inr / monthly) * 100
        assert claimed <= actual, f"{plan_id} claims {claimed}% but saves {actual:.1f}%"
        assert actual - claimed < 1


def test_the_longest_plan_is_the_one_marked_best_value():
    best = [p.id for p in plans() if p.is_best_value]
    assert best == ["pro_yearly"]


def test_prices_follow_configuration_rather_than_being_hard_coded(monkeypatch):
    monkeypatch.setattr(get_settings(), "PRO_MONTHLY_PRICE_INR", 149)
    monkeypatch.setattr(get_settings(), "PRO_HALFYEARLY_PRICE_INR", 699)
    by_id = {p.id: p for p in plans()}
    assert by_id["pro_monthly"].price_inr == 149
    assert by_id["pro_6month"].monthly_equivalent_inr == pytest.approx(699 / 6, abs=0.01)


def test_an_unknown_plan_is_refused():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        plan_by_id("pro_lifetime_free")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_the_plans_endpoint_serves_all_four(client):
    r = await client.get("/api/v1/subscription/plans")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert ids == ["free", "pro_monthly", "pro_6month", "pro_yearly"], ids


@pytest.mark.asyncio
async def test_the_order_amount_comes_from_the_server_not_the_request(
    client, auth_headers, monkeypatch
):
    """A client must not be able to name its own price."""
    from app.providers.payments import razorpay as rzp
    from app.services import subscription_service as svc

    created = {}

    class FakeClient:
        async def create_order(self, amount, currency, receipt, notes):
            created.update(amount=amount, currency=currency, notes=notes)
            return {"id": "order_test123"}

        async def fetch_payment(self, payment_id):
            raise rzp.RazorpayError("not needed")

    # The service builds its client in __init__, so replace the class it builds.
    monkeypatch.setattr(svc, "RazorpayClient", lambda: FakeClient())
    monkeypatch.setattr(get_settings(), "RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setattr(get_settings(), "RAZORPAY_KEY_SECRET", "secret")

    r = await client.post(
        "/api/v1/payments/create",
        headers=auth_headers,
        json={"plan": "pro_6month", "amount": 1},  # the amount here must be ignored
    )
    assert r.status_code == 200, r.text
    assert created["amount"] == 449 * 100  # paise, from configuration
    assert r.json()["amount"] == 449 * 100
    assert created["notes"]["plan"] == "pro_6month"


@pytest.mark.asyncio
async def test_every_advertised_plan_can_actually_be_bought(client, auth_headers, monkeypatch):
    """The list of plans on the page and the list the order endpoint accepts must
    be the same list. They were not: a hard-coded pattern rejected a new plan."""
    from app.services import subscription_service as svc

    class FakeClient:
        async def create_order(self, amount, currency, receipt, notes):
            return {"id": f"order_{notes['plan']}"}

    # The service builds its client in __init__, so replace the class it builds.
    monkeypatch.setattr(svc, "RazorpayClient", lambda: FakeClient())
    monkeypatch.setattr(get_settings(), "RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setattr(get_settings(), "RAZORPAY_KEY_SECRET", "secret")

    advertised = (await client.get("/api/v1/subscription/plans")).json()
    for plan in advertised:
        r = await client.post(
            "/api/v1/payments/create", headers=auth_headers, json={"plan": plan["id"]}
        )
        if plan["price_inr"] == 0:
            assert r.status_code == 400, f"{plan['id']}: free plans are not bought"
        else:
            assert r.status_code == 200, f"{plan['id']}: {r.text}"
            assert r.json()["amount"] == plan["price_inr"] * 100


@pytest.mark.asyncio
async def test_a_made_up_plan_is_refused_by_the_endpoint(client, auth_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setattr(get_settings(), "RAZORPAY_KEY_SECRET", "secret")
    r = await client.post(
        "/api/v1/payments/create", headers=auth_headers, json={"plan": "pro_free_forever"}
    )
    assert r.status_code == 400 and "Unknown plan" in r.text
