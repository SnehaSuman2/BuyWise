"""Restrict results to the target market (India).

Google Shopping returns international merchants even when queried with gl=in.
A shopper in India cannot meaningfully buy a ₹45,000 listing from a Japanese or
Tanzanian storefront, and its price is a currency conversion rather than a real
checkout price — so those listings are worse than no result at all.

Classification, in order of confidence:
  1. Curated Indian retailers (app/data/retailers.py) → india
  2. Indian ccTLD (.in / .co.in) → india
  3. Extra known-Indian commerce domains on generic TLDs → india
  4. Known foreign ccTLD → foreign
  5. Anything else → unknown

`unknown` is treated as foreign when STRICT_MARKET_FILTER is on (the default),
because an unrecognised merchant cannot be trust-assessed either. Turn it off to
trade precision for coverage.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.config import get_settings
from app.data.retailers import RETAILERS, resolve_retailer

INDIA_TLDS = (".in", ".co.in")

# Well-known Indian commerce sites that use generic TLDs, so the ccTLD rule misses them.
EXTRA_INDIAN_DOMAINS = {
    "snapdeal.com",
    "meesho.com",
    "shopclues.com",
    "firstcry.com",
    "pepperfry.com",
    "lenskart.com",
    "gonoise.com",
    "boult.co.in",
    "poorvika.com",
    "sangeethamobiles.com",
    "headphonezone.in",
    "theitdepot.com",
    "mdcomputers.in",
    "primeabgb.com",
    "vedantcomputers.com",
    "bigbasket.com",
    "blinkit.com",
    "zeptonow.com",
    "swiggy.com",
    "tatatcliq.com",
    "luxury.tatacliq.com",
    "decathlon.in",
    "titan.co.in",
    "tanishq.co.in",
    "bata.in",
    "westside.com",
    "shoppersstop.com",
    "pantaloons.com",
    "lifestylestores.com",
    "maxfashion.in",
    "urbanic.com",
    "bewakoof.com",
    "thesouledstore.com",
    "chumbak.com",
    "wakefit.co",
    "sleepyhead.in",
    "boat-lifestyle.com",
    "mi.com",
    "realme.com",
    "vivo.com",
    "oppo.com",
    "motorola.in",
    "nothing.tech",
    "asus.com",
    "lenovo.com",
    "hp.com",
    "dell.com",
    # Seen in live Indian Google Shopping results
    "cashify.in",
    "gadgetsnow.com",
    "easyphones.in",
    "vlebazaar.in",
    "dailydeals365.in",
    "shoptheworld.in",
    "eazypc.in",
    "beyoung.in",
    "tatacliqluxury.com",
    "croma.in",
    "sathya.in",
    "ezoneonline.in",
    "electronicsbazaar.in",
}

# Merchants whose display name has no domain but which are known Indian businesses.
KNOWN_INDIAN_NAMES = {
    "cashify",
    "zepto",
    "gadgets now",
    "easyphones",
    "vijay sales",
    "sangeetha mobiles",
    "poorvika",
    "reliance digital",
    "croma",
    "tata cliq",
    "tata cliq luxury",
    "jiomart",
    "bigbasket",
    "blinkit",
    "snapdeal",
    "meesho",
    "flipkart",
    "myntra",
    "ajio",
    "nykaa",
    "lenskart",
    "firstcry",
    "pepperfry",
    "headphone zone",
    "the it depot",
    "md computers",
    "prime abgb",
    "vedant computers",
    "shopclues",
    "paytm mall",
    "indiamart",
    "moglix",
}

# Country-code TLDs that clearly indicate a non-Indian storefront.
FOREIGN_TLDS = {
    ".jp",
    ".co.jp",
    ".uk",
    ".co.uk",
    ".tz",
    ".co.tz",
    ".tr",
    ".com.tr",
    ".de",
    ".fr",
    ".it",
    ".es",
    ".nl",
    ".be",
    ".se",
    ".no",
    ".dk",
    ".fi",
    ".pl",
    ".pt",
    ".gr",
    ".ch",
    ".at",
    ".ie",
    ".cz",
    ".ro",
    ".hu",
    ".ua",
    ".ru",
    ".cn",
    ".com.cn",
    ".hk",
    ".tw",
    ".kr",
    ".co.kr",
    ".sg",
    ".com.sg",
    ".my",
    ".com.my",
    ".id",
    ".co.id",
    ".ph",
    ".com.ph",
    ".th",
    ".co.th",
    ".vn",
    ".com.vn",
    ".pk",
    ".com.pk",
    ".bd",
    ".com.bd",
    ".lk",
    ".np",
    ".ae",
    ".sa",
    ".com.sa",
    ".qa",
    ".kw",
    ".bh",
    ".om",
    ".il",
    ".co.il",
    ".za",
    ".co.za",
    ".ke",
    ".co.ke",
    ".ng",
    ".com.ng",
    ".eg",
    ".ma",
    ".gh",
    ".au",
    ".com.au",
    ".nz",
    ".co.nz",
    ".ca",
    ".mx",
    ".com.mx",
    ".br",
    ".com.br",
    ".ar",
    ".com.ar",
    ".cl",
    ".co",
    ".pe",
    ".us",
    ".me",
    ".tv",
    ".cc",
    ".ws",
    ".eu",
    ".asia",
    ".africa",
    ".sk",
    ".si",
    ".hr",
    ".bg",
    ".lt",
    ".lv",
    ".ee",
    ".is",
    ".lu",
    ".mt",
    ".cy",
    ".by",
    ".kz",
    ".uz",
    ".ge",
    ".am",
    ".az",
}

# Google Shopping returns no merchant URL at all — `product_link` always points back
# to google.com and the merchant is identified only by its display name. Treating these
# as the merchant domain would misclassify every single result.
AGGREGATOR_DOMAINS = {
    "google.com",
    "google.co.in",
    "googleadservices.com",
    "googleusercontent.com",
    "bing.com",
    "shopping.google.com",
    "serpapi.com",
}

# Strong signals that a listing is served to a different country, taken from real
# foreign listings that leaked through (Tanzania, Turkey, Japan storefronts).
FOREIGN_PLACE_WORDS = {
    "tanzania",
    "kenya",
    "nigeria",
    "uganda",
    "ghana",
    "dubai",
    "uae",
    "qatar",
    "kuwait",
    "bahrain",
    "oman",
    "saudi",
    "singapore",
    "malaysia",
    "indonesia",
    "philippines",
    "thailand",
    "vietnam",
    "japan",
    "tokyo",
    "china",
    "shanghai",
    "korea",
    "taiwan",
    "hong kong",
    "turkey",
    "istanbul",
    "russia",
    "brazil",
    "mexico",
    "canada",
    "australia",
    "new zealand",
    "pakistan",
    "bangladesh",
    "sri lanka",
    "nepal",
    "united kingdom",
    "germany",
    "france",
    "italy",
    "spain",
}

# Merchants identifiable as foreign by name alone (seen in live Indian results).
KNOWN_FOREIGN_NAMES = {
    "wafuu.com",
    "wafuu",
    "etoren.com",
    "etoren",
    "dakauf.eu",
    "dakauf",
    "empire online shopping",
    "xtremeskins",
}

INDIA = "india"
FOREIGN = "foreign"
UNKNOWN = "unknown"

_CURATED_DOMAINS = {r["domain"].lower() for r in RETAILERS}


def _domain_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def _matches_suffix(domain: str, suffixes) -> bool:
    return any(domain == s.lstrip(".") or domain.endswith(s) for s in suffixes)


def _classify_domain(domain: str) -> str:
    domain = domain.lower().removeprefix("www.")
    if domain in _CURATED_DOMAINS or any(domain.endswith("." + d) for d in _CURATED_DOMAINS):
        return INDIA
    if _matches_suffix(domain, INDIA_TLDS):
        return INDIA
    if domain in EXTRA_INDIAN_DOMAINS or any(
        domain.endswith("." + d) for d in EXTRA_INDIAN_DOMAINS
    ):
        return INDIA
    if _matches_suffix(domain, FOREIGN_TLDS):
        return FOREIGN
    return UNKNOWN


def has_foreign_signal(*texts: str | None) -> bool:
    """True when the text names another country or uses a non-Indian script.

    Devanagari and Latin are both normal for Indian listings; CJK is not.
    """
    joined = " ".join(t for t in texts if t).lower()
    if not joined:
        return False
    if any(re.search(rf"\b{re.escape(w)}\b", joined) for w in FOREIGN_PLACE_WORDS):
        return True
    # CJK ranges: Hiragana/Katakana, CJK Unified Ideographs, Hangul.
    return bool(re.search(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]", joined))


def classify_market(domain: str | None, retailer_name: str | None = None) -> str:
    """Return india | foreign | unknown for a merchant."""
    if domain:
        clean = domain.lower().removeprefix("www.")
        # An aggregator link tells us nothing about the merchant — fall through to name.
        if clean not in AGGREGATOR_DOMAINS and not any(
            clean.endswith("." + a) for a in AGGREGATOR_DOMAINS
        ):
            return _classify_domain(clean)

    if retailer_name:
        name = retailer_name.strip()
        # Curated registry (handles "TATA CLiQ LUXURY", "Amazon.in", "Flipkart", ...).
        if resolve_retailer(name, None):
            return INDIA
        lowered = name.lower().strip()
        if lowered in KNOWN_FOREIGN_NAMES or any(
            re.search(rf"\b{re.escape(k)}\b", lowered) for k in KNOWN_FOREIGN_NAMES
        ):
            return FOREIGN
        if lowered in KNOWN_INDIAN_NAMES or any(
            re.search(rf"\b{re.escape(k)}\b", lowered) for k in KNOWN_INDIAN_NAMES
        ):
            return INDIA
        # Many merchant names are literally their domain ("TechCommerce.in", "wafuu.com").
        candidate = name.lower().replace(" ", "")
        if "." in candidate and not candidate.endswith("."):
            verdict = _classify_domain(candidate)
            if verdict != UNKNOWN:
                return verdict
    return UNKNOWN


def listing_market(listing) -> str:
    """Classify a NormalizedListing by merchant domain, then name, then text signals."""
    if has_foreign_signal(listing.title, listing.retailer_name):
        return FOREIGN
    domain = listing.retailer_domain or _domain_of(listing.url)
    return classify_market(domain, listing.retailer_name)


def filter_to_market(listings: list) -> tuple[list, int, list[str]]:
    """Keep only listings sold into the target market.

    Returns (kept, excluded_count, excluded_merchant_names).
    """
    settings = get_settings()
    if not settings.MARKET_FILTER_ENABLED:
        return listings, 0, []

    kept, excluded = [], []
    for listing in listings:
        market = listing_market(listing)
        if market == INDIA or (market == UNKNOWN and not settings.STRICT_MARKET_FILTER):
            kept.append(listing)
        else:
            excluded.append(listing.retailer_name or listing.retailer_domain or "unknown")
    # Preserve first-seen order of the excluded merchant names, de-duplicated.
    seen, names = set(), []
    for name in excluded:
        if name not in seen:
            seen.add(name)
            names.append(name)
    return kept, len(excluded), names
