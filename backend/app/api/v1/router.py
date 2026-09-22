"""API v1 main router."""

from fastapi import APIRouter

from app.api.v1 import (
    account,
    admin,
    affiliate,
    agent,
    alerts,
    auth,
    billing,
    catalog,
    community,
    internal,
    meta,
    products,
    retailers,
    search,
)

router = APIRouter(prefix="/api/v1")
for r in (
    meta.router,
    auth.router,
    search.router,
    products.router,
    catalog.router,
    retailers.router,
    agent.router,
    alerts.router,
    account.router,
    billing.router,
    affiliate.router,
    community.router,
    internal.router,
    admin.router,
):
    router.include_router(r)
