"""AI shopping agent route."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_optional_user
from app.schemas.recommendation import AgentRequest, AgentResponse
from app.services.shopping_agent import ShoppingAgent

router = APIRouter(prefix="/agent", tags=["agent"])
settings = get_settings()


@router.post("", response_model=AgentResponse)
@router.post("/search", response_model=AgentResponse, include_in_schema=False)
@limiter.limit(settings.RATE_LIMIT_AGENT)
async def agent_query(
    request: Request,
    body: AgentRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_optional_user),
):
    return await ShoppingAgent(db).process(body.query, user.id if user else None, body.product_id)
