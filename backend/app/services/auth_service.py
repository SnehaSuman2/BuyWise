"""Authentication: register / login / Google / refresh rotation / logout / password change."""

from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token_id,
    validate_password_strength,
    verify_password,
)
from app.models import RefreshSession, User
from app.providers.auth.google import GoogleAuthError, verify_google_id_token
from app.schemas.user import TokenResponse, UserResponse

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    def _sync_admin_role(self, user: User) -> None:
        """Reconcile the admin role from ADMIN_EMAILS on every sign-in.

        The role is otherwise only set at registration, so an operator who adds
        their address to ADMIN_EMAILS after signing up would never gain access.
        Removal demotes too, but only while the list is non-empty: an unset or
        blank ADMIN_EMAILS is far more likely a misconfigured deploy than a
        deliberate "revoke every admin", and silently demoting everyone on it
        would be a bad surprise.
        """
        admins = self.settings.admin_emails
        if user.email in admins:
            if user.role != "admin":
                user.role = "admin"
        elif admins and user.role == "admin":
            user.role = "user"

    async def _issue_tokens(self, user: User, user_agent: str | None = None) -> TokenResponse:
        access = create_access_token(str(user.id), user.token_version)
        refresh, jti, expires = create_refresh_token(str(user.id), user.token_version)
        self.db.add(
            RefreshSession(
                user_id=user.id,
                token_hash=hash_token_id(jti),
                user_agent=(user_agent or "")[:300] or None,
                created_at=_now(),
                expires_at=expires,
            )
        )
        user.last_login_at = _now()
        await self.db.flush()
        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user),
        )

    async def register(
        self,
        email: str,
        username: str,
        password: str,
        display_name: str | None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        email = email.lower().strip()
        weak = validate_password_strength(password)
        if weak:
            raise HTTPException(status_code=422, detail=weak)
        if (await self.db.execute(select(User).where(User.email == email))).scalar_one_or_none():
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        if (
            await self.db.execute(select(User).where(User.username == username))
        ).scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Username already taken")
        user = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            display_name=display_name or username,
            auth_provider="password",
            role="admin" if email in self.settings.admin_emails else "user",
        )
        self.db.add(user)
        await self.db.flush()
        return await self._issue_tokens(user, user_agent)

    async def login(
        self, email: str, password: str, user_agent: str | None = None
    ) -> TokenResponse:
        email = email.lower().strip()
        user = (await self.db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        # Constant-ish time: always run a hash comparison.
        ok = verify_password(password, user.password_hash if user else None)
        if not user or not ok or user.deleted_at is not None:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account deactivated")
        self._sync_admin_role(user)
        return await self._issue_tokens(user, user_agent)

    async def google_login(self, id_token: str, user_agent: str | None = None) -> TokenResponse:
        try:
            identity = await verify_google_id_token(id_token)
        except GoogleAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if not identity.email_verified:
            raise HTTPException(status_code=401, detail="Google account email is not verified")
        user = (
            await self.db.execute(select(User).where(User.google_sub == identity.sub))
        ).scalar_one_or_none()
        if user is None:
            user = (
                await self.db.execute(select(User).where(User.email == identity.email))
            ).scalar_one_or_none()
            if user is not None:
                user.google_sub = identity.sub
                user.is_verified = True
            else:
                base = (
                    re.sub(r"[^a-z0-9_.-]", "", identity.email.split("@")[0].lower())[:30] or "user"
                )
                username = base
                while (
                    await self.db.execute(select(User).where(User.username == username))
                ).scalar_one_or_none():
                    username = f"{base}-{secrets.token_hex(2)}"
                user = User(
                    email=identity.email,
                    username=username,
                    password_hash=None,
                    display_name=identity.name or username,
                    avatar_url=identity.picture,
                    auth_provider="google",
                    google_sub=identity.sub,
                    is_verified=True,
                    role="admin" if identity.email in self.settings.admin_emails else "user",
                )
                self.db.add(user)
                await self.db.flush()
        if user.deleted_at is not None or not user.is_active:
            raise HTTPException(status_code=403, detail="Account unavailable")
        self._sync_admin_role(user)
        return await self._issue_tokens(user, user_agent)

    async def refresh(self, refresh_token: str, user_agent: str | None = None) -> TokenResponse:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh" or not payload.get("jti"):
            raise HTTPException(status_code=401, detail="Invalid token type")
        session = (
            await self.db.execute(
                select(RefreshSession).where(
                    RefreshSession.token_hash == hash_token_id(payload["jti"])
                )
            )
        ).scalar_one_or_none()
        if (
            session is None
            or session.revoked_at is not None
            or session.expires_at.replace(tzinfo=session.expires_at.tzinfo or timezone.utc) < _now()
        ):
            raise HTTPException(status_code=401, detail="Refresh token is no longer valid")
        user = (
            await self.db.execute(select(User).where(User.id == session.user_id))
        ).scalar_one_or_none()
        if (
            user is None
            or user.deleted_at is not None
            or not user.is_active
            or payload.get("ver", 0) != user.token_version
        ):
            raise HTTPException(status_code=401, detail="Session expired, please sign in again")
        session.revoked_at = _now()  # rotation: old refresh token can't be reused
        return await self._issue_tokens(user, user_agent)

    async def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        try:
            payload = decode_token(refresh_token)
        except HTTPException:
            return
        if payload.get("jti"):
            session = (
                await self.db.execute(
                    select(RefreshSession).where(
                        RefreshSession.token_hash == hash_token_id(payload["jti"])
                    )
                )
            ).scalar_one_or_none()
            if session and session.revoked_at is None:
                session.revoked_at = _now()

    async def logout_all(self, user: User) -> None:
        user.token_version += 1
        sessions = (
            (
                await self.db.execute(
                    select(RefreshSession).where(
                        RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        for s in sessions:
            s.revoked_at = _now()

    async def change_password(
        self, user: User, current_password: str | None, new_password: str
    ) -> None:
        weak = validate_password_strength(new_password)
        if weak:
            raise HTTPException(status_code=422, detail=weak)
        if user.password_hash and not verify_password(current_password or "", user.password_hash):
            raise HTTPException(status_code=401, detail="Current password is incorrect")
        user.password_hash = hash_password(new_password)
        user.auth_provider = "password" if user.auth_provider == "password" else user.auth_provider
        await self.logout_all(user)
