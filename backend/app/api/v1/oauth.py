"""Browser-bound, single-use social sign-in without session tokens in URLs."""

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.user import OAuthAttempt
from app.providers.auth.oauth import configured_provider, exchange_identity, redirect_uri
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth/oauth", tags=["auth"])


class Start(BaseModel):
    verifier: str = Field(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9_~-]+$")


class Complete(Start):
    state: str = Field(min_length=32, max_length=128)
    code: str = Field(min_length=1, max_length=4096)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@router.post("/{provider}/start")
@limiter.limit("10/minute")
async def start(provider: str, data: Start, request: Request, db: AsyncSession = Depends(get_db)):
    config = configured_provider(provider)
    state = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await db.execute(delete(OAuthAttempt).where(OAuthAttempt.expires_at < now))
    db.add(
        OAuthAttempt(
            state_hash=digest(state),
            verifier_hash=digest(data.verifier),
            provider=provider,
            expires_at=now + timedelta(minutes=10),
        )
    )
    params = {
        "client_id": config.client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
    }
    if provider == "microsoft":
        params.update(
            code_challenge=base64.urlsafe_b64encode(hashlib.sha256(data.verifier.encode()).digest())
            .decode()
            .rstrip("="),
            code_challenge_method="S256",
            response_mode="query",
        )
    return {"url": config.authorize + "?" + urlencode(params), "state": state}


@router.post("/{provider}/complete")
@limiter.limit("10/minute")
async def complete(
    provider: str, data: Complete, request: Request, db: AsyncSession = Depends(get_db)
):
    configured_provider(provider)
    # Atomic consumption prevents concurrent replay across workers; commit before
    # calling the provider so a failed exchange cannot make the state reusable.
    result = await db.execute(
        delete(OAuthAttempt)
        .where(
            OAuthAttempt.state_hash == digest(data.state),
            OAuthAttempt.verifier_hash == digest(data.verifier),
            OAuthAttempt.provider == provider,
            OAuthAttempt.expires_at > datetime.now(timezone.utc),
        )
        .returning(OAuthAttempt.state_hash)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            400, "This sign-in has expired or belongs to another browser. Please start again."
        )
    await db.commit()
    identity = await exchange_identity(provider, data.code, data.verifier)
    try:
        return await AuthService(db).oauth_login(
            provider, identity, request.headers.get("user-agent")
        )
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            409, "An account was created during this sign-in. Please sign in again."
        ) from exc
