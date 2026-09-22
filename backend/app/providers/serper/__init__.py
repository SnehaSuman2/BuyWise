"""Serper.dev: a second source of Google Shopping and Google web results.

Kept entirely separate from the SerpApi transport in ``search_client``. That
client speaks one shape, an engine name and query parameters over GET; Serper
posts JSON to a per-endpoint URL and answers with different field names. Sharing
a client would have meant special-casing both inside one, so they sit side by
side and the registry chains them.
"""
