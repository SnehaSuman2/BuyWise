"""Public metadata: data mode, integration availability (no secrets)."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.providers import registry

router = APIRouter(tags=["meta"])


@router.get("/meta")
async def meta():
    s = get_settings()
    return {
        "app": s.APP_NAME,
        "version": s.APP_VERSION,
        "data_mode": s.data_mode,
        "demo_mode": s.demo_mode,
        "ai_mode": "live" if s.ai_enabled else "demo",
        "ai_provider": "gemini" if s.gemini_enabled else ("openai" if s.openai_enabled else "demo"),
        "search_provider": s.active_search_provider if s.search_api_enabled else "demo",
        "payments_enabled": s.razorpay_enabled,
        "google_auth_enabled": s.google_auth_enabled,
        "image_search_enabled": any(p.name != "demo" for p in registry.image_search_providers()),
        "trust_sources": registry.provider_status()["trust_evidence"],
        "razorpay_key_id": s.RAZORPAY_KEY_ID or None,  # public key id; never the secret
    }
