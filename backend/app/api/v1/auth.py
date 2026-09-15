"""Auth routes."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.models import User
from app.schemas.user import (
    GoogleLogin,
    PasswordChange,
    TokenRefresh,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def register(request: Request, data: UserCreate, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).register(
        data.email,
        data.username,
        data.password,
        data.display_name,
        request.headers.get("user-agent"),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(request: Request, data: UserLogin, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).login(data.email, data.password, request.headers.get("user-agent"))


@router.post("/google", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def google_login(request: Request, data: GoogleLogin, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).google_login(data.id_token, request.headers.get("user-agent"))


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh_token(request: Request, data: TokenRefresh, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).refresh(data.refresh_token, request.headers.get("user-agent"))


@router.post("/logout", status_code=204)
async def logout(data: TokenRefresh, db: AsyncSession = Depends(get_db)):
    await AuthService(db).logout(data.refresh_token)


@router.post("/logout-all", status_code=204)
async def logout_all(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await AuthService(db).logout_all(user)


@router.post("/password", status_code=204)
async def change_password(
    data: PasswordChange, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await AuthService(db).change_password(user, data.current_password, data.new_password)


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)


@router.get("/providers")
async def auth_providers():
    """Public: which sign-in methods are available (no secrets)."""
    return {
        "password": True,
        "google": settings.google_auth_enabled,
        "google_client_id": settings.GOOGLE_CLIENT_ID or None,
    }
