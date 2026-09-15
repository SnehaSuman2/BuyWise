"""Demo catalog used ONLY when SERPAPI_API_KEY is not configured.

Everything produced from this file is labelled is_demo=True and the API/UI
show a DEMO DATA badge. It exists so the product can be exercised end-to-end
without paid API access. It includes variant pairs (256GB vs 512GB, colours)
so product matching can be demonstrated honestly.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone

DEMO_PRODUCTS: list[dict] = [
    {
        "key": "sony-wh1000xm5-black",
        "title": "Sony WH-1000XM5 Wireless Noise Cancelling Headphones (Black)",
        "brand": "Sony",
        "model": "WH-1000XM5",
        "category": "Headphones",
        "gtin": "4548736132610",
        "mpn": "WH1000XM5/B",
        "base_price": 26990,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=Sony+WH-1000XM5",
        "specs": {
            "type": "Over-ear",
            "noise_cancelling": "Yes",
            "battery": "30 hours",
            "colour": "Black",
        },
    },
    {
        "key": "sony-wh1000xm5-silver",
        "title": "Sony WH-1000XM5 Wireless Noise Cancelling Headphones (Silver)",
        "brand": "Sony",
        "model": "WH-1000XM5",
        "category": "Headphones",
        "gtin": "4548736132627",
        "mpn": "WH1000XM5/S",
        "base_price": 27490,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=Sony+WH-1000XM5+Silver",
        "specs": {
            "type": "Over-ear",
            "noise_cancelling": "Yes",
            "battery": "30 hours",
            "colour": "Silver",
        },
    },
    {
        "key": "airpods-pro-2-usbc",
        "title": "Apple AirPods Pro (2nd Generation) with MagSafe Case (USB-C)",
        "brand": "Apple",
        "model": "AirPods Pro 2",
        "category": "Headphones",
        "mpn": "MTJV3HN/A",
        "base_price": 22900,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=AirPods+Pro+2",
        "specs": {"type": "In-ear", "noise_cancelling": "Yes"},
    },
    {
        "key": "sony-wf1000xm5",
        "title": "Sony WF-1000XM5 True Wireless Noise Cancelling Earbuds (Black)",
        "brand": "Sony",
        "model": "WF-1000XM5",
        "category": "Headphones",
        "mpn": "WF1000XM5/B",
        "base_price": 21990,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=Sony+WF-1000XM5",
        "specs": {"type": "In-ear"},
    },
    {
        "key": "bose-qc-ultra",
        "title": "Bose QuietComfort Ultra Wireless Noise Cancelling Headphones (Black)",
        "brand": "Bose",
        "model": "QuietComfort Ultra",
        "category": "Headphones",
        "base_price": 32900,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=Bose+QC+Ultra",
        "specs": {"type": "Over-ear"},
    },
    {
        "key": "iphone-15-pro-max-256-titanium",
        "title": "Apple iPhone 15 Pro Max (256 GB) - Natural Titanium",
        "brand": "Apple",
        "model": "iPhone 15 Pro Max",
        "category": "Smartphones",
        "mpn": "MU793HN/A",
        "base_price": 148900,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=iPhone+15+Pro+Max",
        "specs": {"storage": "256GB", "colour": "Natural Titanium"},
    },
    {
        "key": "iphone-15-pro-max-512-titanium",
        "title": "Apple iPhone 15 Pro Max (512 GB) - Natural Titanium",
        "brand": "Apple",
        "model": "iPhone 15 Pro Max",
        "category": "Smartphones",
        "mpn": "MU7E3HN/A",
        "base_price": 168900,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=iPhone+15+Pro+Max+512",
        "specs": {"storage": "512GB", "colour": "Natural Titanium"},
    },
    {
        "key": "galaxy-s24-ultra-256",
        "title": "Samsung Galaxy S24 Ultra 5G (Titanium Gray, 12GB, 256GB Storage)",
        "brand": "Samsung",
        "model": "Galaxy S24 Ultra",
        "category": "Smartphones",
        "mpn": "SM-S928BZTCINS",
        "base_price": 109999,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=Galaxy+S24+Ultra",
        "specs": {"storage": "256GB", "ram": "12GB", "colour": "Titanium Gray"},
    },
    {
        "key": "galaxy-s24-ultra-512",
        "title": "Samsung Galaxy S24 Ultra 5G (Titanium Gray, 12GB, 512GB Storage)",
        "brand": "Samsung",
        "model": "Galaxy S24 Ultra",
        "category": "Smartphones",
        "mpn": "SM-S928BZTHINS",
        "base_price": 121999,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=Galaxy+S24+Ultra+512",
        "specs": {"storage": "512GB", "ram": "12GB", "colour": "Titanium Gray"},
    },
    {
        "key": "oneplus-12-256",
        "title": "OnePlus 12 (Flowy Emerald, 16GB RAM, 512GB Storage)",
        "brand": "OnePlus",
        "model": "OnePlus 12",
        "category": "Smartphones",
        "base_price": 64999,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=OnePlus+12",
        "specs": {"storage": "512GB", "ram": "16GB", "colour": "Flowy Emerald"},
    },
    {
        "key": "pixel-8a",
        "title": "Google Pixel 8a (Obsidian, 8GB RAM, 128GB Storage)",
        "brand": "Google",
        "model": "Pixel 8a",
        "category": "Smartphones",
        "base_price": 44999,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=Pixel+8a",
        "specs": {"storage": "128GB", "ram": "8GB", "colour": "Obsidian"},
    },
    {
        "key": "macbook-air-m3-15-256",
        "title": "Apple MacBook Air 15-inch M3 chip (8GB RAM, 256GB SSD) - Midnight",
        "brand": "Apple",
        "model": "MacBook Air M3 15",
        "category": "Laptops",
        "mpn": "MRYU3HN/A",
        "base_price": 134900,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=MacBook+Air+M3",
        "specs": {"storage": "256GB", "ram": "8GB", "size": "15 inch"},
    },
    {
        "key": "dell-xps-15",
        "title": "Dell XPS 15 9530 Laptop, Intel Core i7-13700H, 16GB RAM, 512GB SSD, 15.6-inch 3.5K OLED",
        "brand": "Dell",
        "model": "XPS 15 9530",
        "category": "Laptops",
        "base_price": 189990,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=Dell+XPS+15",
        "specs": {"storage": "512GB", "ram": "16GB", "size": "15.6 inch"},
    },
    {
        "key": "asus-vivobook-15",
        "title": "ASUS Vivobook 15 Intel Core i5-12500H 16GB RAM 512GB SSD 15.6-inch FHD Laptop",
        "brand": "ASUS",
        "model": "Vivobook 15",
        "category": "Laptops",
        "base_price": 58990,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=ASUS+Vivobook+15",
        "specs": {"storage": "512GB", "ram": "16GB", "size": "15.6 inch"},
    },
    {
        "key": "logitech-mx-keys-s",
        "title": "Logitech MX Keys S Wireless Keyboard (Graphite)",
        "brand": "Logitech",
        "model": "MX Keys S",
        "category": "Keyboards",
        "mpn": "920-011406",
        "base_price": 10995,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=MX+Keys+S",
        "specs": {"colour": "Graphite"},
    },
    {
        "key": "keychron-k2-v2",
        "title": "Keychron K2 V2 Wireless Mechanical Keyboard (Gateron Brown, RGB)",
        "brand": "Keychron",
        "model": "K2 V2",
        "category": "Keyboards",
        "base_price": 7999,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=Keychron+K2",
        "specs": {},
    },
    {
        "key": "logitech-mx-master-3s",
        "title": "Logitech MX Master 3S Wireless Mouse (Graphite)",
        "brand": "Logitech",
        "model": "MX Master 3S",
        "category": "Mice",
        "mpn": "910-006559",
        "base_price": 9995,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=MX+Master+3S",
        "specs": {"colour": "Graphite"},
    },
    {
        "key": "apple-watch-s9-45",
        "title": "Apple Watch Series 9 GPS 45mm Midnight Aluminium Case",
        "brand": "Apple",
        "model": "Watch Series 9",
        "category": "Smartwatches",
        "base_price": 44900,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=Apple+Watch+S9",
        "specs": {"size": "45mm"},
    },
    {
        "key": "galaxy-watch6-classic-47",
        "title": "Samsung Galaxy Watch6 Classic Bluetooth 47mm (Black)",
        "brand": "Samsung",
        "model": "Galaxy Watch6 Classic",
        "category": "Smartwatches",
        "base_price": 36999,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=Galaxy+Watch6",
        "specs": {"size": "47mm"},
    },
    {
        "key": "ipad-air-m2-11-128",
        "title": "Apple iPad Air 11-inch M2 Wi-Fi 128GB - Space Grey",
        "brand": "Apple",
        "model": "iPad Air M2 11",
        "category": "Tablets",
        "base_price": 59900,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=iPad+Air+M2",
        "specs": {"storage": "128GB", "size": "11 inch"},
    },
    {
        "key": "jbl-charge-5",
        "title": "JBL Charge 5 Portable Bluetooth Speaker (Black)",
        "brand": "JBL",
        "model": "Charge 5",
        "category": "Speakers",
        "base_price": 15999,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=JBL+Charge+5",
        "specs": {},
    },
    {
        "key": "lg-c4-55-oled",
        "title": "LG 139 cm (55 inch) C4 OLED evo 4K Smart TV OLED55C4PSA",
        "brand": "LG",
        "model": "OLED55C4",
        "category": "TVs",
        "mpn": "OLED55C4PSA",
        "base_price": 139990,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=LG+C4+OLED",
        "specs": {"size": "55 inch"},
    },
    {
        "key": "dyson-v15",
        "title": "Dyson V15 Detect Absolute Cordless Vacuum Cleaner",
        "brand": "Dyson",
        "model": "V15 Detect",
        "category": "Home Appliances",
        "base_price": 62900,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=Dyson+V15",
        "specs": {},
    },
    {
        "key": "boat-airdopes-141",
        "title": "boAt Airdopes 141 True Wireless Earbuds (Bold Black)",
        "brand": "boAt",
        "model": "Airdopes 141",
        "category": "Headphones",
        "base_price": 1299,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=boAt+Airdopes+141",
        "specs": {"type": "In-ear"},
    },
    {
        "key": "iphone-15-pro-max-case",
        "title": "Spigen Ultra Hybrid Case for iPhone 15 Pro Max (Crystal Clear)",
        "brand": "Spigen",
        "model": "Ultra Hybrid",
        "category": "Accessories",
        "base_price": 1499,
        "image": "https://placehold.co/600x600/1a1a2e/e0e0e0?text=Spigen+Case",
        "specs": {},
    },
]

# Retailer offer profile for demo mode: (slug, retailer_name, domain, price multiplier, shipping known?, delivery days)
DEMO_RETAILER_PROFILES = [
    (
        "amazon-india",
        "Amazon.in",
        "amazon.in",
        1.00,
        True,
        2,
        ["Appario Retail Private Ltd", "Clicktech Retail Private Ltd", "SuperComNet"],
    ),
    (
        "flipkart",
        "Flipkart",
        "flipkart.com",
        0.985,
        True,
        3,
        ["RetailNet", "OmniTech Retail", "Truecomretail"],
    ),
    ("croma", "Croma", "croma.com", 1.015, True, 4, ["Croma"]),
    (
        "reliance-digital",
        "Reliance Digital",
        "reliancedigital.in",
        1.01,
        False,
        4,
        ["Reliance Retail"],
    ),
    ("tata-cliq", "Tata CLiQ", "tatacliq.com", 1.03, False, 3, ["Tata CLiQ"]),
    ("vijay-sales", "Vijay Sales", "vijaysales.com", 1.02, False, 5, ["Vijay Sales"]),
]


def _rng(*parts: str) -> random.Random:
    seed = int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:12], 16)
    return random.Random(seed)


def demo_offers_for(product: dict, day_offset: int = 0) -> list[dict]:
    """Deterministic demo offers for a catalog product. `day_offset` shifts the simulated date."""
    offers = []
    for slug, name, domain, mult, shipping_known, delivery_days, sellers in DEMO_RETAILER_PROFILES:
        rng = _rng(product["key"], slug, str(day_offset))
        if rng.random() < 0.12:
            continue  # retailer doesn't list it
        price = round(product["base_price"] * mult * rng.uniform(0.96, 1.04), -1)
        original = round(price * rng.uniform(1.08, 1.25), -1) if rng.random() > 0.35 else None
        shipping = rng.choice([0, 0, 0, 49, 99]) if shipping_known else None
        coupon_code, coupon_amount = (None, None)
        if rng.random() > 0.75:
            coupon_code, coupon_amount = (
                f"SAVE{rng.choice([5, 10])}",
                round(price * rng.uniform(0.02, 0.06), -1),
            )
        offers.append(
            {
                "retailer_slug": slug,
                "retailer_name": name,
                "retailer_domain": domain,
                "seller_name": rng.choice(sellers),
                "title": product["title"],
                "url": f"https://www.{domain}/demo/{product['key']}",
                "price": price,
                "original_price": original,
                "shipping_price": shipping,
                "shipping_known": shipping_known,
                "coupon_code": coupon_code,
                "coupon_amount": coupon_amount,
                "delivery_days": delivery_days + rng.randint(0, 2),
                "availability": "in_stock" if rng.random() > 0.08 else "limited",
                "rating": round(rng.uniform(3.9, 4.7), 1),
                "rating_count": rng.randint(200, 20000),
            }
        )
    return offers


def demo_price_series(product: dict, days: int = 90) -> list[dict]:
    """Deterministic simulated observations, oldest first. Labelled demo downstream."""
    rng = _rng(product["key"], "history")
    base = product["base_price"]
    price = base * rng.uniform(1.0, 1.08)
    now = datetime.now(timezone.utc)
    series = []
    for i in range(days, -1, -1):
        drift = -base * 0.0004
        noise = rng.gauss(0, base * 0.006)
        if rng.random() < 0.04:
            noise -= base * rng.uniform(0.04, 0.12)  # sale event
        price = max(base * 0.82, min(base * 1.12, price + drift + noise))
        series.append({"observed_at": now - timedelta(days=i), "price": round(price, -1)})
    return series


def demo_evidence_for(retailer_name: str) -> list[dict]:
    """Clearly-simulated evidence for demo mode. Neutral, generic and labelled."""
    rng = _rng(retailer_name, "evidence")
    templates = [
        (
            "delivery",
            0.6,
            "Demo: customers describe deliveries arriving within the promised window",
            "https://example.com/demo-evidence/delivery",
        ),
        (
            "returns",
            0.5,
            "Demo: return requests are described as straightforward for most orders",
            "https://example.com/demo-evidence/returns",
        ),
        (
            "customer_service",
            -0.3,
            "Demo: some reports of slow customer-support replies",
            "https://example.com/demo-evidence/support",
        ),
        (
            "delivery",
            -0.4,
            "Demo: a few complaints about delayed deliveries to smaller towns",
            "https://example.com/demo-evidence/delays",
        ),
        (
            "authenticity",
            0.4,
            "Demo: products generally described as genuine with valid warranty",
            "https://example.com/demo-evidence/authenticity",
        ),
        (
            "transparency",
            0.5,
            "Demo: retailer publishes contact, return and refund policies",
            "https://example.com/demo-evidence/policy",
        ),
    ]
    out = []
    for topic, sentiment, claim, url in templates:
        if rng.random() < 0.15:
            continue
        out.append(
            {
                "topic": topic,
                "sentiment": sentiment + rng.uniform(-0.15, 0.15),
                "severity": 0.5 if sentiment < 0 else 0.3,
                "confidence": 0.45,
                "claim": claim,
                "url": url,
            }
        )
    return out
