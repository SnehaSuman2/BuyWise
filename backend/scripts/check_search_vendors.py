"""Which search vendors are configured, and does each one actually answer?

Run after adding or changing a key:

    cd backend && .venv/bin/python scripts/check_search_vendors.py

Spends one search credit per configured vendor. Prints no keys.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.providers import registry  # noqa: E402
from app.providers.serpapi.google_shopping import GoogleShoppingProvider  # noqa: E402
from app.providers.serper.google_shopping import SerperShoppingProvider  # noqa: E402

QUERY = "iphone 17 256gb"


async def probe(provider) -> None:
    label = f"{provider.name}:{provider.engine}"
    if not provider.enabled:
        print(f"  {label:28s} not configured")
        return
    try:
        res = await provider.search_products(QUERY, max_results=10)
    except Exception as exc:
        print(f"  {label:28s} RAISED {type(exc).__name__}: {exc}")
        return
    if not res.ok:
        print(f"  {label:28s} FAILED  {res.error}")
        return
    priced = [i for i in res.items if i.price]
    stores = {i.retailer_name for i in priced if i.retailer_name}
    cached = " (from cache)" if res.cached else ""
    print(f"  {label:28s} OK      {len(priced)} priced results, {len(stores)} stores{cached}")
    for item in priced[:3]:
        print(f"      - {item.title[:52]:52s} {item.retailer_name} ₹{item.price:,.0f}")


async def main() -> None:
    s = get_settings()
    print("Configured vendors:")
    print("  SerpApi / SearchApi :", "yes" if s.search_api_enabled else "no")
    print("  Serper.dev          :", "yes" if s.serper_enabled else "no")
    if not s.any_search_vendor_enabled:
        print("\nNo search vendor is configured. Set SERPER_API_KEY or SERPAPI_API_KEY.")
        return
    print(f"\nAsking each vendor for {QUERY!r}:")
    await probe(GoogleShoppingProvider())
    await probe(SerperShoppingProvider())

    print("\nThrough the chain the site actually uses:")
    for provider in registry.product_search_providers():
        await probe(provider)
        print(f"  -> answered by: {provider.name}")

    from app.core.http import close_http_client

    await close_http_client()


if __name__ == "__main__":
    asyncio.run(main())
