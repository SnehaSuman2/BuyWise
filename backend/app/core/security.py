"""Security utilities: JWT tokens, password hashing, auth dependencies.

- Access tokens are short-lived JWTs.
- Refresh tokens are JWTs with a `jti`; the hashed jti is stored in `refresh_sessions`
  so refresh tokens can be rotated and revoked (logout / logout-all / account deletion).
- Passwords are hashed with bcrypt (cost 12).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db

settings = get_settings()
security_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def validate_password_strength(password: str) -> str | None:
    """Return an error message if the password is too weak, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if len(password) > 128:
        return "Password is too long"
    if password.isdigit() or password.isalpha():
        return "Password must contain both letters and numbers"
    if password.lower() in {"password1", "12345678a", "qwerty123"}:
        return "Password is too common"
    return None


# ---------------------------------------------------------------- tokens
def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    subject: str, token_version: int = 0, expires_delta: Optional[timedelta] = None
) -> str:
    expire = _now() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": _now(),
        "type": "access",
        "ver": token_version,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str, token_version: int = 0) -> tuple[str, str, datetime]:
    """Return (token, jti, expires_at). The caller persists the hashed jti."""
    jti = secrets.token_urlsafe(24)
    expire = _now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": _now(),
        "type": "refresh",
        "jti": jti,
        "ver": token_version,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM), jti, expire


def hash_token_id(jti: str) -> str:
    return hashlib.sha256(jti.encode("utf-8")).hexdigest()


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc


# ---------------------------------------------------------------- dependencies
async def _load_user(db: AsyncSession, payload: dict):
    from app.models.user import User

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    try:
        uid = UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token payload") from exc
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is deactivated")
    if payload.get("ver", 0) != user.token_version:
        raise HTTPException(status_code=401, detail="Session expired, please sign in again")
    return user


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return await _load_user(db, payload)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
):
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


async def get_admin_user(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def get_pro_user(user=Depends(get_current_user)):
    if user.plan != "pro":
        raise HTTPException(status_code=402, detail="BuyWise Pro subscription required")
    return user
