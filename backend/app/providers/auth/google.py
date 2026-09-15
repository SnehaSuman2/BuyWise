"""Google Sign-In: server-side verification of ID tokens issued to our client id.

The frontend obtains an ID token with Google Identity Services and posts it to
/auth/google. We verify it with Google's tokeninfo endpoint and check the audience.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.http import request_with_retry

logger = logging.getLogger(__name__)


class GoogleAuthError(Exception):
    pass


@dataclass
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str | None
    picture: str | None


async def verify_google_id_token(id_token: str) -> GoogleIdentity:
    s = get_settings()
    if not s.google_auth_enabled:
        raise GoogleAuthError("Google sign-in is not configured")
    try:
        resp = await request_with_retry(
            "GET",
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
            timeout=10.0,
            max_retries=1,
        )
    except Exception as exc:
        raise GoogleAuthError("Could not reach Google to verify the token") from exc
    if resp.status_code != 200:
        raise GoogleAuthError("Invalid Google token")
    info = resp.json()
    if info.get("aud") != s.GOOGLE_CLIENT_ID:
        raise GoogleAuthError("Token audience mismatch")
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise GoogleAuthError("Token issuer mismatch")
    if not info.get("sub") or not info.get("email"):
        raise GoogleAuthError("Token is missing identity fields")
    return GoogleIdentity(
        sub=str(info["sub"]),
        email=str(info["email"]).lower(),
        email_verified=str(info.get("email_verified", "false")).lower() == "true",
        name=info.get("name"),
        picture=info.get("picture"),
    )
