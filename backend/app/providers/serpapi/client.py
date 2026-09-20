"""Compatibility surface for engine modules written against the SerpApi client.

The transport now lives in app.providers.search_client and serves whichever
vendor is configured (SerpApi or SearchApi). These aliases keep the older names
working so every engine module goes through the same cache, quota handling and
circuit breaker.
"""

from app.providers import search_client as _search_client

SERPAPI_URL = "https://serpapi.com/search.json"

STATS = _search_client.STATS
BREAKER = _search_client.BREAKER
SerpApiError = _search_client.SearchApiError
SerpApiAuthError = _search_client.SearchApiAuthError
SerpApiRateLimited = _search_client.SearchApiRateLimited
SerpApiQuotaExceeded = _search_client.SearchApiQuotaExceeded
SerpApiClient = _search_client.SearchClient
get_serpapi_client = _search_client.get_search_client
serpapi_stats = _search_client.search_stats
breaker_status = _search_client.breaker_status
