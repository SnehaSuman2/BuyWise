"""Social auth security boundaries and HTTP contracts (mocked network)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.api.v1.oauth import digest
from app.core.config import get_settings
from app.models import OAuthAttempt, User
from app.providers.auth.oauth import exchange_identity

VERIFIER = "a" * 64


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    for name in ("YAHOO", "MICROSOFT"):
        monkeypatch.setattr(get_settings(), name + "_CLIENT_ID", "client-id")
        monkeypatch.setattr(get_settings(), name + "_CLIENT_SECRET", "client-secret")


async def begin(client, provider="yahoo", verifier=VERIFIER):
    r = await client.post(f"/api/v1/auth/oauth/{provider}/start", json={"verifier": verifier})
    assert r.status_code == 200, r.text
    return r.json()


async def finish(client, state, provider="yahoo", verifier=VERIFIER):
    return await client.post(
        f"/api/v1/auth/oauth/{provider}/complete",
        json={"state": state, "code": "auth-code", "verifier": verifier},
    )


async def test_provider_availability_and_pkce(client, monkeypatch):
    r = await client.get("/api/v1/auth/providers")
    assert r.json()["yahoo"] and r.json()["microsoft"]
    assert "client-secret" not in r.text
    start = await begin(client, "microsoft")
    params = parse_qs(urlparse(start["url"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == [
        get_settings().NEXT_PUBLIC_APP_URL.rstrip("/") + "/auth/callback"
    ]
    assert "client-secret" not in start["url"]
    monkeypatch.setattr(get_settings(), "YAHOO_CLIENT_SECRET", "")
    assert (
        await client.post("/api/v1/auth/oauth/yahoo/start", json={"verifier": VERIFIER})
    ).status_code == 503
    assert (
        await client.post("/api/v1/auth/oauth/evil/start", json={"verifier": VERIFIER})
    ).status_code == 503


async def test_login_repeat_and_replay(client, monkeypatch):
    mock = AsyncMock(
        return_value={
            "sub": "yahoo-user-1",
            "email": "person@example.com",
            "name": "Person",
            "email_verified": True,
        }
    )
    monkeypatch.setattr("app.api.v1.oauth.exchange_identity", mock)
    state = (await begin(client))["state"]
    first = await finish(client, state)
    assert first.status_code == 200, first.text
    assert first.json()["user"]["auth_provider"] == "yahoo"
    assert (await finish(client, state)).status_code == 400
    second = await finish(client, (await begin(client))["state"])
    assert second.status_code == 200
    assert second.json()["user"]["id"] == first.json()["user"]["id"]
    assert mock.await_count == 2
    assert (
        await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer " + first.json()["access_token"]}
        )
    ).status_code == 200


async def test_wrong_browser_provider_expired_state(client, monkeypatch, db):
    mock = AsyncMock()
    monkeypatch.setattr("app.api.v1.oauth.exchange_identity", mock)
    state = (await begin(client))["state"]
    assert (await finish(client, state, verifier="b" * 64)).status_code == 400
    assert (await finish(client, state, provider="microsoft")).status_code == 400
    attempt = await db.get(OAuthAttempt, digest(state))
    attempt.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()
    assert (await finish(client, state)).status_code == 400
    mock.assert_not_awaited()


async def test_existing_email_not_auto_linked(client, user_tokens, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.oauth.exchange_identity",
        AsyncMock(return_value={"sub": "other", "email": user_tokens["user"]["email"]}),
    )
    r = await finish(client, (await begin(client))["state"])
    assert r.status_code == 409


async def test_reserved_admin_email_cannot_register(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.oauth.exchange_identity",
        AsyncMock(
            return_value={
                "sub": "m1",
                "email": "admin@buywisetest.com",
                "email_verified": True,
            }
        ),
    )
    r = await finish(client, (await begin(client, "microsoft"))["state"], "microsoft")
    assert r.status_code == 403


async def test_microsoft_email_unverified_and_inactive_account_rejected(client, monkeypatch, db):
    monkeypatch.setattr(
        "app.api.v1.oauth.exchange_identity",
        AsyncMock(
            return_value={
                "sub": "m2",
                "email": "person@example.com",
                "email_verified": True,
            }
        ),
    )
    r = await finish(client, (await begin(client, "microsoft"))["state"], "microsoft")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["role"] == "user"
    user = (await db.execute(select(User).where(User.email == "person@example.com"))).scalar_one()
    assert not user.is_verified
    user.is_active = False
    await db.commit()
    assert (
        await finish(client, (await begin(client, "microsoft"))["state"], "microsoft")
    ).status_code == 403


async def test_provider_failure_consumes_state(client, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        "app.api.v1.oauth.exchange_identity", AsyncMock(side_effect=HTTPException(401, "Rejected"))
    )
    state = (await begin(client))["state"]
    assert (await finish(client, state)).status_code == 401
    assert (await finish(client, state)).status_code == 400


@pytest.mark.parametrize("provider", ["yahoo", "microsoft"])
async def test_exchange_contract(provider, monkeypatch):
    calls = []

    async def handler(request):
        calls.append(request)
        if request.method == "POST":
            assert b"grant_type=authorization_code" in request.content
            if provider == "yahoo":
                assert request.headers["authorization"].startswith("Basic ")
            else:
                assert b"code_verifier=" in request.content
                assert b"client_secret=client-secret" in request.content
            return httpx.Response(200, json={"access_token": "provider-token"})
        assert request.headers["authorization"] == "Bearer provider-token"
        return httpx.Response(200, json={"sub": "subject", "email": "Person@example.com"})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        "app.providers.auth.oauth.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = await exchange_identity(provider, "code", VERIFIER)
    assert result["email"] == "person@example.com"
    assert len(calls) == 2
