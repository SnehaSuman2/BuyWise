"""Affiliate link building and click tracking.

Isolation rule: this module is the only place affiliate tags are applied. It is
never imported by the trust engine, the matcher or the recommendation ranking.
"""

from __future__ import annotations

import hashlib
import uuid
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import AffiliateClick, Offer


def _with_param(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[key] = value
    return urlunparse(parsed._replace(query=urlencode(query)))


def build_affiliate_url(
    product_url: str | None, retailer_slug: str | None
) -> tuple[str | None, str | None]:
    """Return (destination_url, program). Falls back to the plain product URL when no program exists."""
    if not product_url:
        return None, None
    s = get_settings()
    if retailer_slug == "amazon-india" and s.AMAZON_AFFILIATE_TAG:
        return _with_param(product_url, "tag", s.AMAZON_AFFILIATE_TAG), "amazon_associates"
    if retailer_slug == "flipkart" and s.FLIPKART_AFFILIATE_ID:
        return _with_param(product_url, "affid", s.FLIPKART_AFFILIATE_ID), "flipkart_affiliate"
    return product_url, None


def go_url_for(offer_id: uuid.UUID) -> str:
    return f"{get_settings().API_PUBLIC_URL.rstrip('/')}/api/v1/go/{offer_id}"


async def record_click(
    db: AsyncSession,
    offer: Offer,
    destination: str,
    program: str | None,
    *,
    user_id: uuid.UUID | None,
    ip: str | None,
    user_agent: str | None,
    referer: str | None,
) -> None:
    ip_hash = (
        hashlib.sha256(f"{ip}|{get_settings().SECRET_KEY[:8]}".encode()).hexdigest() if ip else None
    )
    db.add(
        AffiliateClick(
            offer_id=offer.id,
            product_id=offer.product_id,
            retailer_id=offer.retailer_id,
            user_id=user_id,
            destination_url=destination,
            affiliate_applied=program is not None,
            program=program,
            ip_hash=ip_hash,
            user_agent=(user_agent or "")[:300] or None,
            referer=(referer or "")[:500] or None,
        )
    )
