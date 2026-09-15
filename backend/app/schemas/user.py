"""User / auth schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_\.\-]+$")
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str | None = Field(None, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=128)


class GoogleLogin(BaseModel):
    id_token: str = Field(..., min_length=20, max_length=4096)


class UserUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=100)
    notification_preferences: dict | None = None


class PasswordChange(BaseModel):
    current_password: str | None = None
    new_password: str = Field(..., min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None
    auth_provider: str
    is_active: bool
    is_verified: bool
    role: str
    plan: str
    notification_preferences: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class TokenRefresh(BaseModel):
    refresh_token: str


class AccountDelete(BaseModel):
    confirm: str = Field(..., description='Must be the literal string "DELETE"')
    password: str | None = None
