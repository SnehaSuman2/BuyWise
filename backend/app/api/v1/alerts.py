"""Price alert routes (authenticated; users only see their own alerts)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User
from app.schemas.alert import AlertCreate, AlertResponse
from app.services.alert_service import AlertService

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("", response_model=AlertResponse, status_code=201)
async def create_alert(
    data: AlertCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await AlertService(db).create(user, data)


@router.get("", response_model=list[AlertResponse])
async def get_alerts(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await AlertService(db).list_for_user(user.id)


@router.post("/{alert_id}/pause", response_model=AlertResponse)
async def pause_alert(
    alert_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await AlertService(db).toggle(alert_id, user.id, False)


@router.post("/{alert_id}/resume", response_model=AlertResponse)
async def resume_alert(
    alert_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await AlertService(db).toggle(alert_id, user.id, True)


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(
    alert_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    if not await AlertService(db).delete(alert_id, user.id):
        raise HTTPException(status_code=404, detail="Alert not found")
