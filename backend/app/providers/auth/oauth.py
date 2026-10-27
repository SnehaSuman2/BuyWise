"""Confidential-client authorization code exchange for Yahoo and Microsoft.

Only server-obtained access tokens reach fixed UserInfo endpoints. Email is never
used to link identities or grant roles: provider + subject is the account key.
"""

from dataclasses import dataclass

import httpx
from fastapi import HTTPException
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.config import get_settings


@dataclass(frozen=True)
class Provider:
    name: str
    authorize: str
    token: str
    userinfo: str
    client_id: str
    client_secret: str


def providers() -> dict[str, Provider]:
    s = get_settings()
    return {
        "yahoo": Provider(
            "Yahoo",
            "https://api.login.yahoo.com/oauth2/request_auth",
            "https://api.login.yahoo.com/oauth2/get_token",
            "https://api.login.yahoo.com/openid/v1/userinfo",
            s.YAHOO_CLIENT_ID,
            s.YAHOO_CLIENT_SECRET,
        ),
        "microsoft": Provider(
            "Microsoft",
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "https://graph.microsoft.com/oidc/userinfo",
            s.MICROSOFT_CLIENT_ID,
            s.MICROSOFT_CLIENT_SECRET,
        ),
    }


def configured_provider(name: str) -> Provider:
    provider = providers().get(name)
    if not provider or not provider.client_id or not provider.client_secret:
        raise HTTPException(
            503, "This sign-in method is not available. Please use email or another provider."
        )
    return provider


def redirect_uri() -> str:
    return get_settings().NEXT_PUBLIC_APP_URL.rstrip("/") + "/auth/callback"


async def exchange_identity(name: str, code: str, verifier: str) -> dict:
    provider = configured_provider(name)
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri()}
    auth = None
    if name == "yahoo":
        auth = httpx.BasicAuth(provider.client_id, provider.client_secret)
    else:
        data.update(
            client_id=provider.client_id,
            client_secret=provider.client_secret,
            code_verifier=verifier,
        )
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            token = await client.post(provider.token, data=data, auth=auth)
            token.raise_for_status()
            access = token.json().get("access_token")
            if not isinstance(access, str) or not access:
                raise ValueError("missing access token")
            response = await client.get(
                provider.userinfo, headers={"Authorization": f"Bearer {access}"}
            )
            response.raise_for_status()
            identity = response.json()
            if not isinstance(identity.get("sub"), str) or not 1 <= len(identity["sub"]) <= 255:
                raise ValueError("missing subject")
            identity["email"] = str(
                TypeAdapter(EmailStr).validate_python(identity.get("email"))
            ).lower()
            return identity
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, ValidationError) as exc:
        raise HTTPException(
            401, "Sign-in could not be completed. Try again, or use email sign-in."
        ) from exc
