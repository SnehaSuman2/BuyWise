"""Product normalization: extract brand, model and variant attributes from listing titles/specs.

Pure functions, no I/O. Used by the matcher and for canonical product keys.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

KNOWN_BRANDS = [
    "apple",
    "samsung",
    "sony",
    "bose",
    "oneplus",
    "google",
    "xiaomi",
    "redmi",
    "poco",
    "realme",
    "vivo",
    "oppo",
    "iqoo",
    "motorola",
    "nothing",
    "dell",
    "hp",
    "lenovo",
    "asus",
    "acer",
    "msi",
    "lg",
    "jbl",
    "boat",
    "noise",
    "logitech",
    "keychron",
    "razer",
    "dyson",
    "philips",
    "panasonic",
    "whirlpool",
    "bosch",
    "canon",
    "nikon",
    "sennheiser",
    "jabra",
    "marshall",
    "amazfit",
    "garmin",
    "fitbit",
    "spigen",
    "anker",
    "tp-link",
    "netgear",
]
COLORS = [
    "black",
    "white",
    "silver",
    "grey",
    "gray",
    "graphite",
    "midnight",
    "starlight",
    "blue",
    "green",
    "red",
    "pink",
    "purple",
    "gold",
    "titanium",
    "natural titanium",
    "blue titanium",
    "white titanium",
    "black titanium",
    "phantom black",
    "titanium gray",
    "titanium grey",
    "titanium black",
    "titanium violet",
    "titanium yellow",
    "flowy emerald",
    "silky black",
    "obsidian",
    "porcelain",
    "bay",
    "aloe",
    "space grey",
    "space gray",
    "space black",
    "rose gold",
    "yellow",
    "orange",
    "beige",
    "cream",
    "navy",
    "teal",
    "emerald",
    "crystal clear",
    "bold black",
]
ACCESSORY_WORDS = {
    "case",
    "cover",
    "screen protector",
    "tempered glass",
    "charger",
    "cable",
    "adapter",
    "skin",
    "stand",
    "mount",
    "strap",
    "band",
    "ear tips",
    "earpads",
    "ear pads",
    "pouch",
    "sleeve",
    "protector",
    "holder",
    "dock",
    "replacement",
    "wrap",
    "decal",
    "sticker",
    "guard",
    "grip",
    "carrying case",
    "hard case",
    "travel case",
    "ear cushion",
    "earcup",
    "cushion",
}
PRODUCT_LINE_BRANDS = {
    "iphone": "apple",
    "ipad": "apple",
    "macbook": "apple",
    "airpods": "apple",
    "imac": "apple",
    "apple watch": "apple",
    "galaxy": "samsung",
    "pixel": "google",
    "redmi": "xiaomi",
    "poco": "xiaomi",
    "nord": "oneplus",
    "xps": "dell",
    "thinkpad": "lenovo",
    "ideapad": "lenovo",
    "zenbook": "asus",
    "vivobook": "asus",
    "rog": "asus",
    "pavilion": "hp",
    "airdopes": "boat",
    "rockerz": "boat",
    "playstation": "sony",
    "bravia": "sony",
    "surface": "microsoft",
}
STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "with",
    "for",
    "of",
    "in",
    "by",
    "new",
    "latest",
    "edition",
    "5g",
    "4g",
    "wifi",
    "wi-fi",
    "-",
    "|",
    "&",
}

_STORAGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(tb|gb)\b(?!\s*ram)", re.I)
_RAM_RE = re.compile(r"(\d+)\s*gb\s*(?:ram|memory)", re.I)
_PAIR_RE = re.compile(r"\(?\b(\d+)\s*gb\s*(?:\+|/|,)\s*(\d+)\s*(gb|tb)\b\)?", re.I)
_INCH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|\s)?(?:inch|inches|in\b|\"|”)", re.I)
_MM_RE = re.compile(r"\b(\d{2})\s*mm\b", re.I)
_GEN_RE = re.compile(
    r"\b(\d+)(?:st|nd|rd|th)\s*gen(?:eration)?\b|\bgen\s*(\d+)\b|\bseries\s*(\d+)\b", re.I
)
_MODEL_TOKEN_RE = re.compile(
    r"\b(?=[A-Za-z0-9-]{4,}\b)(?=[A-Za-z0-9-]*\d)(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9-]+\b"
)
_CHIP_RE = re.compile(
    r"\b(m[1-4](?:\s?(?:pro|max|ultra))?|a1[5-9]\s?(?:pro|bionic)?|snapdragon\s?\d+(?:\s?gen\s?\d)?)\b",
    re.I,
)


@dataclass
class NormalizedAttributes:
    brand: str | None = None
    model: str | None = None
    storage: str | None = None
    ram: str | None = None
    color: str | None = None
    size: str | None = None
    generation: str | None = None
    chip: str | None = None
    is_accessory: bool = False
    model_tokens: list[str] = field(default_factory=list)
    tokens: set[str] = field(default_factory=set)
    clean_title: str = ""

    def variant_attrs(self) -> dict[str, str]:
        return {
            k: v
            for k, v in {
                "storage": self.storage,
                "ram": self.ram,
                "color": self.color,
                "size": self.size,
            }.items()
            if v
        }

    def as_dict(self) -> dict:
        return {
            "brand": self.brand,
            "model": self.model,
            "storage": self.storage,
            "ram": self.ram,
            "color": self.color,
            "size": self.size,
            "generation": self.generation,
            "chip": self.chip,
            "is_accessory": self.is_accessory,
        }


def _norm_storage(num: str, unit: str) -> str:
    value = float(num)
    unit = unit.upper()
    if unit == "TB":
        return f"{int(value * 1024)}GB" if value < 1 else f"{value:g}TB"
    return f"{int(value)}GB"


def normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[™®©]", " ", t)
    t = re.sub(r"[\[\]{}]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def extract_attributes(
    title: str, specs: dict | None = None, brand_hint: str | None = None
) -> NormalizedAttributes:
    specs = {str(k).lower(): str(v) for k, v in (specs or {}).items()}
    text = normalize_title(title)
    spec_text = " ".join(f"{k} {v}" for k, v in specs.items()).lower()
    attrs = NormalizedAttributes(clean_title=text)

    # brand
    brand = (brand_hint or specs.get("brand") or "").strip().lower() or None
    if not brand:
        for b in KNOWN_BRANDS:
            if re.search(rf"\b{re.escape(b)}\b", text):
                brand = b
                break
    if not brand:
        for line, b in PRODUCT_LINE_BRANDS.items():
            if re.search(rf"\b{re.escape(line)}\b", text):
                brand = b
                break
    if not brand:
        first = text.split(" ")[0] if text else ""
        if first.isalpha() and len(first) > 2 and first not in STOPWORDS:
            brand = first
    if brand in PRODUCT_LINE_BRANDS:
        brand = PRODUCT_LINE_BRANDS[brand]
    attrs.brand = brand

    # Accessory detection. The presence of an accessory noun is sufficient on its own:
    # real listings such as "XtremeSkins <Product> Skins & Wraps" name no second trigger,
    # and treating them as the product itself drags a ₹1,200 decal into a ₹25,000
    # headphone comparison. Plurals are matched too ("skins", "wraps").
    # If the shopper is genuinely searching for an accessory, the reference listing is
    # flagged the same way, so like still matches like.
    attrs.is_accessory = any(
        re.search(rf"\b{re.escape(w)}s?\b", text) for w in ACCESSORY_WORDS
    )

    # RAM / storage
    pair = _PAIR_RE.search(text)
    if pair:
        a, b, unit_b = pair.groups()
        attrs.ram = f"{int(a)}GB"
        attrs.storage = _norm_storage(b, unit_b)
    ram = _RAM_RE.search(text) or _RAM_RE.search(spec_text)
    if ram and not attrs.ram:
        attrs.ram = f"{int(ram.group(1))}GB"
    if not attrs.storage:
        candidates = [(float(m.group(1)), m.group(2)) for m in _STORAGE_RE.finditer(text)]
        candidates = [
            (v, u)
            for v, u in candidates
            if not (attrs.ram and f"{int(v)}GB" == attrs.ram and u.lower() == "gb")
        ]
        if candidates:
            v, u = max(candidates, key=lambda c: c[0] * (1024 if c[1].lower() == "tb" else 1))
            attrs.storage = _norm_storage(str(v), u)
        elif specs.get("storage"):
            m = _STORAGE_RE.search(specs["storage"])
            if m:
                attrs.storage = _norm_storage(m.group(1), m.group(2))
    if not attrs.ram and specs.get("ram"):
        m = re.search(r"(\d+)", specs["ram"])
        if m:
            attrs.ram = f"{int(m.group(1))}GB"

    # color (longest match wins)
    color_source = f"{text} {specs.get('colour', '')} {specs.get('color', '')}".lower()
    for c in sorted(COLORS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(c)}\b", color_source):
            attrs.color = c
            break

    # size
    inch = _INCH_RE.search(text) or _INCH_RE.search(spec_text)
    mm = _MM_RE.search(text) or _MM_RE.search(spec_text)
    if inch:
        attrs.size = f"{float(inch.group(1)):g}in"
    elif mm:
        attrs.size = f"{mm.group(1)}mm"

    gen = _GEN_RE.search(text)
    if gen:
        attrs.generation = next(g for g in gen.groups() if g)
    chip = _CHIP_RE.search(text)
    if chip:
        attrs.chip = re.sub(r"\s+", " ", chip.group(1).lower())

    # model tokens: alphanumeric codes like WH-1000XM5, SM-S928B, 920-011406
    attrs.model_tokens = sorted(
        {
            m.lower()
            for m in _MODEL_TOKEN_RE.findall(title)
            if not re.fullmatch(r"\d+(gb|tb|mm|hz|w|mah|mp)", m.lower())
            and m.lower() not in {"5g", "4g", "usb-c", "wi-fi"}
        }
    )
    # URL slugs split codes on hyphens ("wh 1000xm5"): rejoin a short alpha prefix with a following code token.
    words = text.split()
    for i in range(len(words) - 1):
        a, b = words[i], words[i + 1]
        if (
            1 <= len(a) <= 3
            and a.isalpha()
            and re.search(r"\d", b)
            and re.search(r"[a-z]", b)
            and len(b) >= 4
            and (a + b) not in attrs.model_tokens
        ):
            attrs.model_tokens.append(a + b)
    attrs.model_tokens = sorted(set(attrs.model_tokens))
    attrs.model = specs.get("model") or (attrs.model_tokens[0] if attrs.model_tokens else None)

    # generic tokens for similarity: strip variant words so variants of one product look alike
    core = _PAIR_RE.sub(" ", text)
    core = _RAM_RE.sub(" ", core)
    core = _STORAGE_RE.sub(" ", core)
    core = _INCH_RE.sub(" ", core)
    core = _MM_RE.sub(" ", core)
    core = re.sub(r"\b(ram|storage|rom|memory)\b", " ", core)
    for c in sorted(COLORS, key=len, reverse=True):
        core = re.sub(rf"\b{re.escape(c)}\b", " ", core)
    raw_tokens = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", core)
    attrs.tokens = {t for t in raw_tokens if t not in STOPWORDS and len(t) > 1}
    return attrs


def canonical_key(attrs: NormalizedAttributes, identifiers: dict | None = None) -> str:
    """Stable key for deduplicating products/variants. Prefers hard identifiers."""
    identifiers = identifiers or {}
    for id_key in ("gtin", "asin", "mpn"):
        if identifiers.get(id_key):
            return f"{id_key}:{str(identifiers[id_key]).strip().lower()}"
    base = attrs.model_tokens[0] if attrs.model_tokens else " ".join(sorted(attrs.tokens))[:80]
    payload = "|".join(
        [
            attrs.brand or "",
            base,
            attrs.storage or "",
            attrs.ram or "",
            attrs.color or "",
            attrs.size or "",
        ]
    )
    return "attr:" + hashlib.sha1(payload.encode()).hexdigest()[:24]


def product_family_key(attrs: NormalizedAttributes) -> str:
    """Key shared by all variants of the same product (brand + model, no variant attrs)."""
    base = (
        attrs.model_tokens[0]
        if attrs.model_tokens
        else " ".join(sorted(t for t in attrs.tokens if not re.fullmatch(r"\d+(gb|tb)", t)))[:80]
    )
    return f"{attrs.brand or ''}|{base}"
