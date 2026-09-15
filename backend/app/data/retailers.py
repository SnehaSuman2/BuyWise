"""Curated registry of Indian retailers.

Policy facts here are *public, retailer-published* facts with source URLs. They are
inputs to the Trust Engine (source_type="policy"), not verdicts. Keep claims
conservative and verifiable; update `verified_on` when re-checked.

Nothing in this file may reference affiliate programs or commercial terms.
"""

from __future__ import annotations

RETAILERS: list[dict] = [
    {
        "slug": "amazon-india",
        "name": "Amazon.in",
        "domain": "amazon.in",
        "aliases": ["amazon", "amazon.in", "amazon india"],
        "website_url": "https://www.amazon.in",
        "is_marketplace": True,
        "policies": {
            "publishes_return_policy": True,
            "return_window_days": 7,
            "return_policy_url": "https://www.amazon.in/gp/help/customer/display.html?nodeId=202111910",
            "cod_available": True,
            "buyer_protection": "A-to-z Guarantee",
            "buyer_protection_url": "https://www.amazon.in/gp/help/customer/display.html?nodeId=201889410",
            "grievance_officer_published": True,
            "verified_on": "2026-09-01",
        },
    },
    {
        "slug": "flipkart",
        "name": "Flipkart",
        "domain": "flipkart.com",
        "aliases": ["flipkart", "flipkart.com"],
        "website_url": "https://www.flipkart.com",
        "is_marketplace": True,
        "policies": {
            "publishes_return_policy": True,
            "return_window_days": 7,
            "return_policy_url": "https://www.flipkart.com/pages/returnpolicy",
            "cod_available": True,
            "buyer_protection": "Flipkart Assured / Open Box Delivery on select items",
            "grievance_officer_published": True,
            "verified_on": "2026-09-01",
        },
    },
    {
        "slug": "croma",
        "name": "Croma",
        "domain": "croma.com",
        "aliases": ["croma", "croma.com", "tata croma"],
        "website_url": "https://www.croma.com",
        "is_marketplace": False,
        "policies": {
            "publishes_return_policy": True,
            "return_window_days": 7,
            "return_policy_url": "https://www.croma.com/return-policy",
            "cod_available": True,
            "physical_stores": True,
            "verified_on": "2026-09-01",
        },
    },
    {
        "slug": "reliance-digital",
        "name": "Reliance Digital",
        "domain": "reliancedigital.in",
        "aliases": ["reliance digital", "reliancedigital", "reliancedigital.in"],
        "website_url": "https://www.reliancedigital.in",
        "is_marketplace": False,
        "policies": {
            "publishes_return_policy": True,
            "return_window_days": 7,
            "return_policy_url": "https://www.reliancedigital.in/returns-and-refund-policy",
            "cod_available": True,
            "physical_stores": True,
            "verified_on": "2026-09-01",
        },
    },
    {
        "slug": "tata-cliq",
        "name": "Tata CLiQ",
        "domain": "tatacliq.com",
        "aliases": ["tata cliq", "tatacliq", "tatacliq.com", "cliq"],
        "website_url": "https://www.tatacliq.com",
        "is_marketplace": True,
        "policies": {
            "publishes_return_policy": True,
            "return_window_days": 7,
            "return_policy_url": "https://www.tatacliq.com/returns-policy",
            "cod_available": True,
            "verified_on": "2026-09-01",
        },
    },
    {
        "slug": "vijay-sales",
        "name": "Vijay Sales",
        "domain": "vijaysales.com",
        "aliases": ["vijay sales", "vijaysales", "vijaysales.com"],
        "website_url": "https://www.vijaysales.com",
        "is_marketplace": False,
        "policies": {
            "publishes_return_policy": True,
            "physical_stores": True,
            "verified_on": "2026-09-01",
        },
    },
    {
        "slug": "jiomart",
        "name": "JioMart",
        "domain": "jiomart.com",
        "aliases": ["jiomart", "jio mart", "jiomart.com"],
        "website_url": "https://www.jiomart.com",
        "is_marketplace": True,
        "policies": {
            "publishes_return_policy": True,
            "cod_available": True,
            "verified_on": "2026-09-01",
        },
    },
    {
        "slug": "apple-india",
        "name": "Apple Store India",
        "domain": "apple.com",
        "aliases": ["apple", "apple.com", "apple store", "apple india"],
        "website_url": "https://www.apple.com/in/",
        "is_marketplace": False,
        "policies": {
            "publishes_return_policy": True,
            "return_window_days": 14,
            "verified_on": "2026-09-01",
        },
    },
    {
        "slug": "samsung-india",
        "name": "Samsung Shop India",
        "domain": "samsung.com",
        "aliases": ["samsung", "samsung.com", "samsung shop", "samsung india"],
        "website_url": "https://www.samsung.com/in/",
        "is_marketplace": False,
        "policies": {"publishes_return_policy": True, "verified_on": "2026-09-01"},
    },
    {
        "slug": "myntra",
        "name": "Myntra",
        "domain": "myntra.com",
        "aliases": ["myntra", "myntra.com"],
        "website_url": "https://www.myntra.com",
        "is_marketplace": True,
        "policies": {
            "publishes_return_policy": True,
            "cod_available": True,
            "verified_on": "2026-09-01",
        },
    },
    {
        "slug": "ajio",
        "name": "AJIO",
        "domain": "ajio.com",
        "aliases": ["ajio", "ajio.com"],
        "website_url": "https://www.ajio.com",
        "is_marketplace": True,
        "policies": {
            "publishes_return_policy": True,
            "cod_available": True,
            "verified_on": "2026-09-01",
        },
    },
    {
        "slug": "nykaa",
        "name": "Nykaa",
        "domain": "nykaa.com",
        "aliases": ["nykaa", "nykaa.com"],
        "website_url": "https://www.nykaa.com",
        "is_marketplace": True,
        "policies": {
            "publishes_return_policy": True,
            "cod_available": True,
            "verified_on": "2026-09-01",
        },
    },
    {
        "slug": "boat",
        "name": "boAt",
        "domain": "boat-lifestyle.com",
        "aliases": ["boat", "boat-lifestyle.com", "boat lifestyle"],
        "website_url": "https://www.boat-lifestyle.com",
        "is_marketplace": False,
        "policies": {"publishes_return_policy": True, "verified_on": "2026-09-01"},
    },
    {
        "slug": "oneplus-india",
        "name": "OnePlus Store India",
        "domain": "oneplus.in",
        "aliases": ["oneplus", "oneplus.in", "oneplus store"],
        "website_url": "https://www.oneplus.in",
        "is_marketplace": False,
        "policies": {"publishes_return_policy": True, "verified_on": "2026-09-01"},
    },
    {
        "slug": "sony-india",
        "name": "Sony Center India",
        "domain": "shopatsc.com",
        "aliases": ["sony", "shopatsc", "shopatsc.com", "sony center", "sony india"],
        "website_url": "https://www.shopatsc.com",
        "is_marketplace": False,
        "policies": {"publishes_return_policy": True, "verified_on": "2026-09-01"},
    },
]

_BY_SLUG = {r["slug"]: r for r in RETAILERS}
_BY_DOMAIN = {r["domain"]: r for r in RETAILERS}
_ALIAS_INDEX: dict[str, dict] = {}
for _r in RETAILERS:
    for _a in _r["aliases"]:
        _ALIAS_INDEX[_a.lower()] = _r


def get_by_slug(slug: str) -> dict | None:
    return _BY_SLUG.get(slug)


def _norm_domain(domain: str) -> str:
    d = domain.lower().strip()
    if d.startswith("www."):
        d = d[4:]
    return d


def resolve_retailer(name: str | None = None, domain: str | None = None) -> dict | None:
    """Resolve a retailer by domain (preferred) or by display name/alias."""
    if domain:
        d = _norm_domain(domain)
        if d in _BY_DOMAIN:
            return _BY_DOMAIN[d]
        # subdomains e.g. m.flipkart.com, dl.flipkart.com
        for known, r in _BY_DOMAIN.items():
            if d.endswith("." + known):
                return r
    if name:
        n = name.lower().strip()
        if n in _ALIAS_INDEX:
            return _ALIAS_INDEX[n]
        for alias, r in _ALIAS_INDEX.items():
            if len(alias) >= 4 and alias in n:
                return r
    return None


def slugify(name: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in name.strip())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:190] or "retailer"
