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
    # Spare/replacement parts. A listing titled exactly "Apple iPhone 17 Pro" that is
    # actually a spare back panel is worse than a mislabelled case: nothing in the
    # ordinary product title marks it, only this vocabulary does.
    "housing",
    "body housing",
    "full housing",
    "housing panel",
    "body panel",
    "back panel",
    "back glass",
    "back cover panel",
    "flex cable",
    "digitizer",
    "logic board",
    "motherboard",
    "charging port",
    "spare part",
    "display panel",
    "lcd panel",
    "camera lens protector",
}

# A rental listing ("on rent", "monthly rental") is not a price for owning the
# product and is not comparable to a purchase price.
# Words a listing title starts with that sell rather than describe. Never a brand.
SALES_WORDS = {
    "buy",
    "shop",
    "new",
    "genuine",
    "original",
    "latest",
    "best",
    "cheap",
    "cheapest",
    "online",
    "offer",
    "sale",
    "top",
    "premium",
    "official",
}

# Words that are never the name half of a model phrase like "PixaPlay 35" or
# "Beem 440": the specification and marketing vocabulary of a listing title.
GENERIC_WORDS = {
    "projector",
    "smart",
    "home",
    "portable",
    "mini",
    "led",
    "lcd",
    "wifi",
    "android",
    "support",
    "supports",
    "lumens",
    "lumen",
    "inch",
    "inches",
    "display",
    "screen",
    "cinema",
    "theater",
    "theatre",
    "native",
    "resolution",
    "version",
    "pack",
    "set",
    "size",
    "model",
    "type",
    "edition",
    "watt",
    "watts",
    "hours",
    "hour",
    "battery",
    "camera",
    "pixels",
    "pixel",
    "ram",
    "rom",
    "storage",
    "memory",
    "plus",
    "pro",
    "max",
    "ultra",
    "lite",
    "speaker",
    "speakers",
    "laptop",
    "phone",
    "mobile",
    "wireless",
    "bluetooth",
    "usb",
    "hdmi",
    "bass",
    "driver",
    "drivers",
    "year",
    "years",
    "month",
    "months",
    "day",
    "days",
    "piece",
    "pieces",
    "pcs",
    "litre",
    "liter",
    "ltr",
    "with",
    "and",
    "for",
    "the",
    "new",
    "latest",
    "best",
    "top",
    "full",
    "hd",
    "fhd",
    "uhd",
    "upto",
    "up",
    "to",
    "of",
    "in",
    "at",
    "by",
    "from",
    "rotation",
    "degree",
    "keystone",
    "correction",
    "zoom",
    "dual",
    "band",
    "audio",
    "video",
    "sound",
    "stereo",
    "output",
    "input",
    "port",
    "ports",
    "slot",
    "card",
    "sd",
    "tf",
    "remote",
    "control",
    "stand",
    "kit",
    "bundle",
    "combo",
    "offer",
    "deal",
    "sale",
    "price",
    "free",
    "delivery",
    "warranty",
    "genuine",
    "original",
    "official",
    "imported",
    "india",
    "indian",
    "black",
    "white",
    "grey",
    "gray",
    "blue",
    "red",
    "green",
    "gold",
    "silver",
    "yellow",
    "orange",
    "pink",
    "purple",
    "os",
    "tv",
    "box",
    "stick",
    "system",
    "device",
    "unit",
    "series",
    "gen",
    "generation",
    "capacity",
    "wattage",
    "voltage",
    "power",
    "fast",
    "charging",
    "charger",
    "cable",
    "adapter",
    "case",
    "cover",
    "mp",
    "megapixel",
    "front",
    "rear",
    "back",
    "large",
    "small",
    "big",
    "long",
    "short",
    "high",
    "low",
}

RENTAL_WORDS = {"on rent", "for rent", "rental", "rent to own"}
# A service sold against a product's name is not the product: carrier unlocks,
# activations, repairs. They are priced in hundreds and would otherwise become
# the "cheapest iPhone 17" on the page.
SERVICE_WORDS = {
    "unlock service",
    "unlocking service",
    "network unlock",
    "carrier unlock",
    "sim unlock",
    "factory unlock service",
    "activation service",
    "network services",
    "fast service",
    "repair service",
    "esim service",
    "active line",
    "imei check",
    "imei service",
    "service only",
    "screen replacement service",
    "battery replacement service",
}
# Display names for product lines the title regex recognises, keyed by the
# family text with spaces removed. Anything absent is title-cased.
_FAMILY_LABELS = {
    "iphone": "iPhone",
    "ipad": "iPad",
    "ipadair": "iPad Air",
    "ipadpro": "iPad Pro",
    "ipadmini": "iPad mini",
    "macbookair": "MacBook Air",
    "macbookpro": "MacBook Pro",
    "applewatch": "Apple Watch",
    "applewatchse": "Apple Watch SE",
    "applewatchultra": "Apple Watch Ultra",
    "airpods": "AirPods",
    "airpodspro": "AirPods Pro",
    "oneplus": "OnePlus",
    "oneplusnord": "OnePlus Nord",
    "oneplusnordce": "OnePlus Nord CE",
    "nord": "OnePlus Nord",
    "nordce": "OnePlus Nord CE",
    "motoedge": "Motorola Edge",
    "motog": "Moto G",
    "iqoo": "iQOO",
    "iqooz": "iQOO Z",
    "iqooneo": "iQOO Neo",
    "rog": "ROG",
    "xps": "XPS",
    "tuf": "TUF",
    "cmfphone": "CMF Phone",
    "firetv": "Fire TV",
    "firetvstick": "Fire TV Stick",
    "xboxseries": "Xbox Series",
    "pocox": "POCO X",
    "pocof": "POCO F",
    "pocom": "POCO M",
    "pococ": "POCO C",
    "galaxyzfold": "Galaxy Z Fold",
    "galaxyzflip": "Galaxy Z Flip",
    "galaxytabs": "Galaxy Tab S",
    "galaxytaba": "Galaxy Tab A",
    "galaxys": "Galaxy S",
    "galaxya": "Galaxy A",
    "galaxym": "Galaxy M",
    "galaxyf": "Galaxy F",
    "galaxynote": "Galaxy Note",
    "realmegt": "Realme GT",
    "redminote": "Redmi Note",
    "motorolaedge": "Motorola Edge",
    "nothingphone": "Nothing Phone",
    "thinkpadx": "ThinkPad X",
    "thinkpadt": "ThinkPad T",
    "thinkpadl": "ThinkPad L",
    "thinkpade": "ThinkPad E",
    "thinkpadp": "ThinkPad P",
    "ideapad": "IdeaPad",
    "vivobook": "Vivobook",
    "zenbook": "Zenbook",
}
_TIER_LABELS = {"fe": "FE", "se": "SE", "ce": "CE", "pro+": "Pro+", "pro plus": "Pro Plus"}
# Families whose number attaches to a letter: "Galaxy S25", "POCO X7", "Vivo T4".
_ATTACHED_NUMBER_FAMILIES = {
    "galaxys",
    "galaxya",
    "galaxym",
    "galaxyf",
    "pocox",
    "pocof",
    "pocom",
    "pococ",
    "vivot",
    "vivov",
    "vivox",
    "vivoy",
    "iqooz",
    "thinkpadx",
    "thinkpadt",
    "thinkpadl",
    "thinkpade",
    "thinkpadp",
}
# The tier words a listing that "sells every model" strings together.
_TIER_LIST_RE = re.compile(
    r"\b(pro\s?max|pro\s?plus|pro\+|pro|max|plus|ultra|air|mini|fe|lite|neo)\b", re.I
)
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
# Product lines whose generation is a bare number: "iPhone 17", "Galaxy S25 Ultra",
# "OnePlus 13R", "Pixel 9a", "Redmi Note 14 Pro". These carry no code like
# WH-1000XM5, so without this the matcher saw "iPhone 13" and "iPhone 17" as the
# same product with different wording and a search for one returned all of them.
_LINE_RE = re.compile(
    r"\b("
    r"iphone|ipad(?:\s?(?:air|pro|mini))?|macbook\s?(?:air|pro)|apple\s?watch(?:\s?(?:se|ultra))?|"
    r"airpods(?:\s?pro)?|"
    r"galaxy\s?(?:z\s?(?:fold|flip)|tab\s?[sa]|note|[samf])|pixel(?:\s?fold)?|"
    r"oneplus(?:\s?nord(?:\s?ce)?)?|nord(?:\s?ce)?|"
    r"redmi(?:\s?note)?|poco\s?[xfmc]|realme(?:\s?narzo|\s?gt)?|narzo|iqoo(?:\s?z|\s?neo)?|"
    r"vivo\s?[tvxy]|moto(?:rola)?\s?(?:g|edge)|nothing\s?phone|cmf\s?phone|xperia|"
    r"surface\s?(?:pro|laptop|go)|thinkpad\s?[xtlep]|ideapad|vivobook|zenbook|inspiron|xps|"
    r"pavilion|omen|legion|tuf|rog|playstation|xbox\s?series|kindle|"
    r"echo\s?(?:dot|show)?|fire\s?tv(?:\s?stick)?"
    r")"
    r"(?:\s?(?:series\s?)?"
    r"(\d{1,3}(?!\s?(?:gb|tb|mm|hz|mah|mp|w|inch|in\b|g\b))[a-z]{0,2}))?"
    r"(?:\s?(pro\s?max|pro\s?plus|pro\+|pro|max|plus|ultra|fe|lite|neo|mini|air|edge|se|"
    r"prime|power|turbo|classic|fold|flip)|(\+))?(?![a-z0-9])",
    re.I,
)
# Lines people write two ways, folded to one token: "OnePlus Nord 5" and
# "Nord 5", "Motorola Edge 60" and "Moto Edge 60".
_FAMILY_ALIASES = {
    "oneplusnord": "nord",
    "oneplusnordce": "nordce",
    "motorolaedge": "motoedge",
    "motorolag": "motog",
}


def find_line(text: str):
    """The first product-line mention that carries a number or a tier.

    "iPhone 17", "iPhone Air" and "Galaxy S25 Ultra" all count; a bare "iphone"
    (as in "iphone case") does not. Returns (family, number, tier) or None.
    """
    for m in _LINE_RE.finditer(text):
        family, number, tier = m.group(1), m.group(2), m.group(3) or m.group(4)
        if tier == "+":
            tier = "plus"
        if number or tier:
            if family.lower() == "iphone" and tier and tier.lower() == "air":
                # Apple's line is "iPhone Air"; retailers write "iPhone 17 Air".
                number = None
            return family, number, tier
    return None


def line_token(family: str, number: str | None, tier: str | None) -> str:
    fam = re.sub(r"\s+", "", family.lower())
    fam = _FAMILY_ALIASES.get(fam, fam)
    return re.sub(r"[\s+]", "", f"{fam}{number or ''}{tier or ''}").lower()


def line_label(family: str, number: str | None, tier: str | None) -> str:
    """A display name for a line: "iPhone 17 Pro Max", "Galaxy S25 Ultra"."""
    key = re.sub(r"\s+", "", family.lower())
    key = _FAMILY_ALIASES.get(key, key)
    name = _FAMILY_LABELS.get(key) or family.title()
    if number:
        shown = number if key == "pixel" else number.upper()
        name = f"{name}{shown}" if key in _ATTACHED_NUMBER_FAMILIES else f"{name} {shown}"
    if tier:
        t = re.sub(r"\s+", " ", tier.lower())
        name = f"{name} {_TIER_LABELS.get(t) or t.title()}"
    return name


# A quantity with a unit ("30hrs", "48mp", "6.3-inch", "256gb") is a specification,
# never a model code, however code-like it looks to the token pattern below.
_UNIT_TOKEN_RE = re.compile(
    r"\d+(?:\.\d+)?-?(?:gb|tb|mb|mm|cm|m|hz|khz|ghz|w|kw|mah|mp|hrs?|h|ms|db|kg|g|ml|l|"
    r"fps|nits|ppi|x|k|p|in|inch|inches|hr)s?"
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
    is_rental: bool = False
    # A service sold under the product's name (unlock, activation, repair).
    is_service: bool = False
    # A listing that names several models or every storage size at once: a
    # wholesaler's catalogue entry, not one product at one price.
    is_catalogue: bool = False
    # The product line with its generation and tier ("iphone17promax"), and the
    # way people write it ("iPhone 17 Pro Max"). Storage and colour are variants
    # within a line; everything sold as this line belongs to one family.
    line: str | None = None
    line_label: str | None = None
    # The parts of the line: "iphone" and "17". A different family or a
    # different generation is a different product; a different tier (Pro, Max)
    # is a sibling of the same generation.
    line_family: str | None = None
    line_number: str | None = None
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
            "line": self.line,
            "line_label": self.line_label,
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
    t = re.sub(r"\bi\s?-?\s?phone\b", "iphone", t)
    t = re.sub(r"\((\d{1,3}[a-z]?)\)", r" \1 ", t)  # "Phone (3a)" names a model, not an aside
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
        if (
            first.isalpha()
            and len(first) > 2
            and first not in STOPWORDS
            and first not in SALES_WORDS
        ):
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
    attrs.is_accessory = any(re.search(rf"\b{re.escape(w)}s?\b", text) for w in ACCESSORY_WORDS)
    attrs.is_rental = any(re.search(rf"\b{re.escape(w)}\b", text) for w in RENTAL_WORDS)
    attrs.is_service = any(re.search(rf"\b{re.escape(w)}\b", text) for w in SERVICE_WORDS)
    tiers = {re.sub(r"\s+", " ", m.group(1).lower()) for m in _TIER_LIST_RE.finditer(text)}
    sizes = {_norm_storage(m.group(1), m.group(2)) for m in _STORAGE_RE.finditer(text)}
    attrs.is_catalogue = len(tiers) >= 3 or len(sizes) >= 4

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
        distinct = {_norm_storage(str(v), u) for v, u in candidates}
        if len(distinct) >= 3:
            # "256GB/512GB/1TB" is a menu, not this listing's storage.
            attrs.storage = None
        elif candidates:
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
    if len(sizes) >= 3:
        # "256GB/512GB/1TB" is a menu of sizes, not this listing's storage, and
        # the first pair of it is not RAM either.
        attrs.storage = None
        if pair and attrs.ram == f"{int(pair.group(1))}GB":
            attrs.ram = None

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
    line_tokens: list[str] = []
    line = find_line(text)
    if line:
        family, number, tier = line
        if number and not attrs.generation:
            attrs.generation = number.lower()
        token = line_token(family, number, tier)
        line_tokens.append(token)
        attrs.line = token
        attrs.line_label = line_label(family, number, tier)
        fam = re.sub(r"\s+", "", family.lower())
        attrs.line_family = _FAMILY_ALIASES.get(fam, fam)
        attrs.line_number = number.lower() if number else None
    chip = _CHIP_RE.search(text)
    if chip:
        attrs.chip = re.sub(r"\s+", " ", chip.group(1).lower())

    # model tokens: alphanumeric codes like WH-1000XM5, SM-S928B, 920-011406
    attrs.model_tokens = sorted(
        {
            m.lower()
            for m in _MODEL_TOKEN_RE.findall(title)
            if not _UNIT_TOKEN_RE.fullmatch(m.lower())
            and m.lower() not in {"5g", "4g", "usb-c", "wi-fi"}
        }
    )
    # Products without a code still have a name-and-number model phrase most of
    # the time: "PixaPlay 35", "Beem 440", "Cinehead E1", "Airdopes 141". Each
    # retailer wraps it in different marketing words, so without this the same
    # projector from Flipkart and Amazon never recognised each other and every
    # product on a results page carried exactly one offer.
    for m in re.finditer(r"\b([a-z][a-z\-]{3,})\s+(\d{1,4}[a-z]{0,2}|[a-z]\d{1,3})\b", text):
        word, number = m.group(1), m.group(2)
        if (
            word in STOPWORDS
            or word in GENERIC_WORDS
            or word in KNOWN_BRANDS
            or word in COLORS
            or _UNIT_TOKEN_RE.fullmatch(number)
            or re.fullmatch(r"(19|20)\d\d", number)
            or re.fullmatch(r"a1[5-9]|m[1-4]", number)  # a chip, not a model
            or (number.isdigit() and len(number) > 4)
        ):
            continue
        token = f"{word}{number}"
        if token not in attrs.model_tokens and token not in line_tokens:
            line_tokens.append(token)

    # URL slugs split codes on hyphens ("wh 1000xm5"): rejoin a short alpha prefix with a following code token.
    # A unit ("256gb", "50mm") is not a code, so "max 256gb" must not become "max256gb".
    words = text.split()
    for i in range(len(words) - 1):
        a, b = words[i], words[i + 1]
        if (
            1 <= len(a) <= 3
            and a.isalpha()
            and re.search(r"\d", b)
            and re.search(r"[a-z]", b)
            and len(b) >= 4
            and not _UNIT_TOKEN_RE.fullmatch(b)
            and (a + b) not in attrs.model_tokens
        ):
            attrs.model_tokens.append(a + b)
    attrs.model_tokens = sorted(set(attrs.model_tokens) | set(line_tokens))
    # The line is the model people know ("iphone17"); a stray code in the title
    # ("A3258", a seller's SKU) must not displace it.
    attrs.model = (
        specs.get("model") or attrs.line or (attrs.model_tokens[0] if attrs.model_tokens else None)
    )

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


def search_query_for(title: str, brand: str | None = None, specs: dict | None = None) -> str:
    """A short marketplace query for finding this product at other retailers.

    A retailer's own title ("Nermosa Women's Hand Block Floral Printed Straight Kurta
    Set with Palazzo Pants & Dupatta Ethnic Kurta Set for Casual Outings ...") is far
    too specific for a marketplace search. A literal model code with the brand
    ("sony wh-1000xm5") is the best query there is; otherwise the head of the title,
    trimmed of sales words, plus the storage size when the product has one.
    """
    attrs = extract_attributes(title, specs, brand)
    codes = sorted(
        (t for t in attrs.model_tokens if t in attrs.clean_title),
        key=lambda t: ("-" not in t, -len(t)),  # hyphenated, then longest, first
    )
    if codes:
        query = f"{attrs.brand} {codes[0]}" if attrs.brand else codes[0]
    else:
        head = re.split(r"\s[-|,(]\s*|\(", attrs.clean_title, maxsplit=1)[0].strip()
        while head.split(" ", 1)[0] in SALES_WORDS and " " in head:
            head = head.split(" ", 1)[1]
        query = " ".join(head.split()[:8])
        if attrs.brand and attrs.brand not in query:
            query = f"{attrs.brand} {query}"
    if attrs.storage and attrs.storage.lower() not in query.replace(" ", "").lower():
        query = f"{query} {attrs.storage.lower()}"
    return query.strip().lower() or title


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
