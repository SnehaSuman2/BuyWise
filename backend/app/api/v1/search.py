"""Search routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_optional_user
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["search"])
settings = get_settings()


async def _run(request: SearchRequest, db: AsyncSession, user) -> SearchResponse:
    try:
        return await SearchService(db).search(request, user.id if user else None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("", response_model=SearchResponse)
@limiter.limit(settings.RATE_LIMIT_SEARCH)
async def search_products(
    request: Request,
    body: SearchRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_optional_user),
):
    """Search by text, product URL or image (image_url / image_base64)."""
    return await _run(body, db, user)


@router.get("", response_model=SearchResponse)
@limiter.limit(settings.RATE_LIMIT_SEARCH)
async def search_products_get(
    request: Request,
    q: str | None = Query(None, max_length=300),
    url: str | None = Query(None, max_length=2048),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    sort_by: str | None = Query(None),
    page: int = Query(1, ge=1, le=20),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_optional_user),
):
    if q and q.lower().startswith(("http://", "https://")):
        url, q = q, None
    return await _run(
        SearchRequest(
            query=q,
            url=url,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
            page=page,
            page_size=page_size,
        ),
        db,
        user,
    )
