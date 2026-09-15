"""Product routes: detail, offers, price history, trust, recommendations, reviews."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_optional_user
from app.schemas.common import DataMeta
from app.schemas.offer import OfferComparison
from app.schemas.price import PriceHistoryResponse
from app.schemas.product import ProductDetail, ProductVariantResponse
from app.schemas.recommendation import RecommendationSet
from app.schemas.review import ReviewAnalysisResponse
from app.schemas.trust import TrustScoreResponse
from app.services import catalog
from app.services.offer_service import OfferService
from app.services.price_history_service import PriceHistoryService
from app.services.recommendation_engine import RecommendationEngine
from app.services.review_analyzer import ReviewAnalyzer
from app.services.trust_service import TrustService

router = APIRouter(prefix="/products", tags=["products"])
settings = get_settings()


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(product_id: UUID, db: AsyncSession = Depends(get_db)):
    product = await catalog.load_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    offers = await catalog.load_offers(db, product_id)
    exact = [o for o in offers if o.match_type == "exact_match"]
    prices = [float(o.estimated_final_price) for o in (exact or offers)]
    ratings = [(float(o.rating), o.rating_count or 1) for o in offers if o.rating]
    is_demo = product.is_demo or (bool(offers) and all(o.is_demo for o in offers))
    return ProductDetail(
        id=product.id,
        name=product.name,
        brand=product.brand,
        model=product.model,
        category=product.category,
        description=product.description,
        gtin=product.gtin,
        sku=product.sku,
        mpn=product.mpn,
        asin=product.asin,
        attributes=product.attributes,
        specifications=product.specifications,
        images=product.images or [],
        source_provider=product.source_provider,
        is_demo=is_demo,
        created_at=product.created_at,
        variants=[ProductVariantResponse.model_validate(v) for v in product.variants],
        lowest_price=min(prices) if prices else None,
        highest_price=max(prices) if prices else None,
        offer_count=len(offers),
        exact_offer_count=len(exact),
        average_rating=round(sum(r * n for r, n in ratings) / sum(n for _, n in ratings), 1)
        if ratings
        else None,
        rating_count=sum(n for _, n in ratings) if ratings else None,
        meta=DataMeta(
            data_mode="demo" if is_demo else "live",
            is_demo=is_demo,
            providers=sorted({o.source_provider for o in offers}),
        ),
    )


@router.get("/{product_id}/offers", response_model=OfferComparison)
async def get_product_offers(
    product_id: UUID,
    refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_optional_user),
):
    """Offers with true-price breakdown, match confidence and trust. `refresh=true` forces a live refresh (Pro or admin)."""
    if refresh and not (user and (user.plan == "pro" or user.role == "admin")):
        refresh = False
    result = await OfferService(db).compare(product_id, refresh=refresh)
    if result is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return result


@router.get("/{product_id}/history", response_model=PriceHistoryResponse)
@router.get(
    "/{product_id}/price-history", response_model=PriceHistoryResponse, include_in_schema=False
)
async def get_price_history(
    product_id: UUID,
    days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_optional_user),
):
    max_days = (
        settings.PRO_HISTORY_DAYS if user and user.plan == "pro" else settings.FREE_HISTORY_DAYS
    )
    result = await PriceHistoryService(db).get_history(
        product_id, days, max_days=max(max_days, 90 if settings.demo_mode else max_days)
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return result


@router.get("/{product_id}/trust", response_model=list[TrustScoreResponse])
async def get_product_trust(product_id: UUID, db: AsyncSession = Depends(get_db)):
    """Trust scores for every retailer currently offering this product."""
    offers = await catalog.load_offers(db, product_id)
    if not offers and not await catalog.load_product(db, product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    trust = TrustService(db)
    out = []
    for rid in {o.retailer_id for o in offers}:
        t = await trust.get_retailer_trust(rid, include_evidence=False)
        if t:
            out.append(t)
    return sorted(out, key=lambda t: -(t.score or 0))


@router.get("/{product_id}/recommendations", response_model=RecommendationSet)
async def get_recommendations(product_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await RecommendationEngine(db).generate(product_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return result


@router.get("/{product_id}/reviews", response_model=ReviewAnalysisResponse)
async def get_review_analysis(product_id: UUID, db: AsyncSession = Depends(get_db)):
    if not await catalog.load_product(db, product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    return await ReviewAnalyzer(db).analyze(product_id)
