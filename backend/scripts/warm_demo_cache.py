#!/usr/bin/env python3
"""Warm the search cache before a demo.

Runs each query once against the live API so the answer is cached. During the
demo those searches are instant and cost nothing from the search-API allowance,
and they keep working even if the allowance runs out, because an expired answer
is still served when the provider is unavailable.

Run it the morning of the demo (the cache window is 24 hours):

    python backend/scripts/warm_demo_cache.py "iphone 17" "sony wh-1000xm5" ...
    python backend/scripts/warm_demo_cache.py --api https://your-api "query"

It also opens each product found, which warms the product pages too.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request

DEFAULT_API = "https://buywise-api-vaai.onrender.com"
DEFAULT_QUERIES = [
    "iphone 17",
    "samsung galaxy s25 ultra",
    "sony wh-1000xm5",
    "oneplus 13r",
    "boat airdopes 141",
]


def post(url: str, payload: bytes, timeout: int) -> dict:
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    import json

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def get(url: str, timeout: int) -> dict:
    import json

    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def main() -> int:
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queries", nargs="*", default=None, help="Searches to warm")
    parser.add_argument("--api", default=DEFAULT_API, help="API base URL")
    parser.add_argument("--timeout", type=int, default=240, help="Seconds per request")
    parser.add_argument("--products", type=int, default=3, help="Product pages to warm per query")
    args = parser.parse_args()

    api = args.api.rstrip("/")
    queries = args.queries or DEFAULT_QUERIES

    print(f"Waking {api} ...", flush=True)
    try:
        get(f"{api}/health", args.timeout)
    except urllib.error.URLError as exc:
        print(f"  could not reach the API: {exc}", file=sys.stderr)
        return 1

    failures = 0
    for query in queries:
        started = time.perf_counter()
        try:
            body = post(
                f"{api}/api/v1/search",
                json.dumps({"query": query, "page_size": 24}).encode(),
                args.timeout,
            )
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  {query!r}: FAILED ({exc})", file=sys.stderr)
            failures += 1
            continue
        elapsed = time.perf_counter() - started
        meta = body.get("meta", {})
        print(
            f"  {query!r}: {body.get('total_results', 0)} results in {elapsed:.1f}s"
            f" (cached={meta.get('cached')})",
            flush=True,
        )
        for result in body.get("results", [])[: args.products]:
            try:
                get(f"{api}/api/v1/products/{result['id']}/offers", args.timeout)
                get(f"{api}/api/v1/products/{result['id']}/trust", args.timeout)
            except (urllib.error.URLError, TimeoutError):
                pass

    print("\nWarmed. Re-run this any time; repeats inside the cache window are free.")
    if failures:
        print(f"{failures} query(ies) failed — check the API before the demo.", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
