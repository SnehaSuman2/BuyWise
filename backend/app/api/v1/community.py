"""Community routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User
from app.schemas.community import CommunityReportCreate, CommunityReportResponse, ReportFlagCreate
from app.services.community_service import CommunityService

router = APIRouter(prefix="/community", tags=["community"])


@router.post("/reports", response_model=CommunityReportResponse, status_code=201)
async def create_report(
    data: CommunityReportCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await CommunityService(db).create(user, data)


@router.get("/reports", response_model=list[CommunityReportResponse])
async def get_reports(
    product_id: UUID | None = Query(None),
    retailer_id: UUID | None = Query(None),
    seller_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    return await CommunityService(db).list_public(
        product_id, retailer_id, seller_id, page, page_size
    )


@router.get("/reports/mine", response_model=list[CommunityReportResponse])
async def my_reports(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await CommunityService(db).mine(user)


@router.post("/reports/{report_id}/flag", status_code=204)
async def flag_report(
    report_id: UUID,
    data: ReportFlagCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await CommunityService(db).flag(user, report_id, data.reason)
