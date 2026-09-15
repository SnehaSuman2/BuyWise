"""Outbound retailer redirect with affiliate tagging and click tracking."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_optional_user
from app.models import Offer
from app.services.affiliate_service import build_affiliate_url, record_click

router = APIRouter(tags=["affiliate"])


@router.get("/go/{offer_id}")
async def go_to_offer(
    offer_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_optional_user),
):
    offer = (await db.execute(select(Offer).where(Offer.id == offer_id))).scalar_one_or_none()
    if offer is None or not offer.product_url:
        raise HTTPException(status_code=404, detail="Offer not found")
    if not offer.product_url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Offer URL is not a web link")
    destination, program = build_affiliate_url(
        offer.product_url, offer.retailer.slug if offer.retailer else None
    )
    await record_click(
        db,
        offer,
        destination,
        program,
        user_id=user.id if user else None,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        referer=request.headers.get("referer"),
    )
    return RedirectResponse(destination, status_code=302)


@router.get("/affiliate/disclosure")
async def affiliate_disclosure():
    from app.core.config import get_settings

    s = get_settings()
    return {
        "programs": [
            p
            for p, on in (
                ("Amazon Associates (amazon.in)", bool(s.AMAZON_AFFILIATE_TAG)),
                ("Flipkart Affiliate", bool(s.FLIPKART_AFFILIATE_ID)),
            )
            if on
        ],
        "statement": "BuyWise may earn a commission when you buy through some retailer links. Commissions never affect Trust Scores, rankings or recommendations.",
    }
