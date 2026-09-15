"""Account, dashboard and saved-product routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, verify_password
from app.models import User
from app.schemas.user import AccountDelete, UserResponse, UserUpdate
from app.services.account_service import AccountService

router = APIRouter(tags=["account"])


class SaveProductRequest(BaseModel):
    product_id: UUID
    note: str | None = Field(None, max_length=500)


@router.get("/account", response_model=UserResponse)
async def get_account(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)


@router.patch("/account", response_model=UserResponse)
async def update_account(
    data: UserUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return UserResponse.model_validate(
        await AccountService(db).update_profile(
            user, data.display_name, data.notification_preferences
        )
    )


@router.delete("/account", status_code=204)
async def delete_account(
    data: AccountDelete, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    if data.confirm != "DELETE":
        raise HTTPException(status_code=422, detail='Type "DELETE" to confirm')
    if user.password_hash and not verify_password(data.password or "", user.password_hash):
        raise HTTPException(status_code=401, detail="Password is incorrect")
    await AccountService(db).delete_account(user)


@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await AccountService(db).dashboard(user)


@router.get("/saved-products")
async def saved_products(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await AccountService(db).saved_products(user)


@router.post("/saved-products", status_code=201)
async def save_product(
    data: SaveProductRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await AccountService(db).save_product(user, data.product_id, data.note)


@router.delete("/saved-products/{product_id}", status_code=204)
async def unsave_product(
    product_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    if not await AccountService(db).unsave_product(user, product_id):
        raise HTTPException(status_code=404, detail="Not saved")
