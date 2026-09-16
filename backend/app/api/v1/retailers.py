"""Retailer / seller routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_optional_user
from app.models import Offer, Retailer
from app.schemas.retailer import RetailerDetail
from app.schemas.trust import TrustScoreResponse
from app.services.trust_service import TrustService

router = APIRouter(prefix="/retailers", tags=["retailers"])


@router.get("", response_model=list[RetailerDetail])
async def list_retailers(db: AsyncSession = Depends(get_db)):
    retailers = (await db.execute(select(Retailer).order_by(Retailer.name))).scalars().all()
    trust = TrustService(db)
    out = []
    for r in retailers:
        score = await trust._latest_score(retailer_id=r.id)
        count = (
            await db.execute(
                select(func.count())
                .select_from(Offer)
                .where(Offer.retailer_id == r.id, Offer.is_active.is_(True))
            )
        ).scalar_one()
        out.append(
            RetailerDetail(
                **{
                    c: getattr(r, c)
                    for c in (
                        "id",
                        "name",
                        "slug",
                        "domain",
                        "website_url",
                        "logo_url",
                        "description",
                        "country",
                        "is_marketplace",
                        "is_curated",
                        "is_demo",
                        "policies",
                    )
                },
                trust_score=score.overall_score if score else None,
                risk_level=score.risk_level if score else None,
                total_offers=count,
            )
        )
    return out


@router.get("/{retailer_id}", response_model=RetailerDetail)
async def get_retailer(retailer_id: UUID, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(Retailer).where(Retailer.id == retailer_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Retailer not found")
    trust = await TrustService(db).stored_retailer_trust(retailer_id, include_evidence=False)
    count = (
        await db.execute(
            select(func.count())
            .select_from(Offer)
            .where(Offer.retailer_id == r.id, Offer.is_active.is_(True))
        )
    ).scalar_one()
    return RetailerDetail(
        **{
            c: getattr(r, c)
            for c in (
                "id",
                "name",
                "slug",
                "domain",
                "website_url",
                "logo_url",
                "description",
                "country",
                "is_marketplace",
                "is_curated",
                "is_demo",
                "policies",
            )
        },
        trust_score=trust.score if trust else None,
        risk_level=trust.risk_level if trust else None,
        total_offers=count,
    )


@router.get("/{retailer_id}/trust", response_model=TrustScoreResponse)
async def get_trust_score(
    retailer_id: UUID,
    refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_optional_user),
):
    if refresh and not (user and user.role == "admin"):
        refresh = False
    service = TrustService(db)
    # A normal page view reads what is on record; only an admin asking for a
    # refresh is allowed to trigger live evidence collection, which is slow.
    result = (
        await service.get_retailer_trust(retailer_id, include_evidence=True, refresh=True)
        if refresh
        else await service.stored_retailer_trust(retailer_id, include_evidence=True)
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Retailer not found")
    return result


@router.get("/sellers/{seller_id}/trust", response_model=TrustScoreResponse)
async def get_seller_trust(seller_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await TrustService(db).get_seller_trust(seller_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Seller not found")
    return result
