"""Category browsing over the curated catalogue."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_optional_user
from app.data.catalog_models import CATEGORIES
from app.schemas.catalog import CatalogPage
from app.services.catalog_browse import CatalogBrowser
from app.services.subscription_service import entitlements_for

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("", response_model=dict)
async def list_categories() -> dict:
    return {"categories": [{"key": k, "title": v} for k, v in CATEGORIES.items()]}


@router.get("/{category}", response_model=CatalogPage)
async def browse_category(
    category: str,
    brand: list[str] | None = Query(None),
    ram: list[int] | None = Query(
        None, description="RAM in GB; a model matches if it comes in any"
    ),
    storage: list[int] | None = Query(
        None, description="Storage in GB; a model matches if it comes in any"
    ),
    min_screen: float | None = Query(None, ge=0),
    max_screen: float | None = Query(None, ge=0),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    sort: str = Query("newest", pattern="^(newest|price_asc|price_desc|name)$"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_optional_user),
):
    """Curated models in a category, filtered by specification. Prices are live
    figures from stored offers and are withheld without Pro."""
    see_prices = (await entitlements_for(db, user)).see_prices
    page = await CatalogBrowser(db).page(
        category,
        see_prices=see_prices,
        brands=brand,
        ram_gb=ram,
        storage_gb=storage,
        min_screen=min_screen,
        max_screen=max_screen,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Unknown category")
    return page
