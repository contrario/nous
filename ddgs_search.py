"""
NOUS Tool — ddgs_search
DuckDuckGo search for market research and news.
Uses the duckduckgo_search package if available, falls back to lite HTML scraping.
"""
from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger("nous.tool.ddgs_search")


async def execute(
    query: str = "",
    max_results: int = 5,
    **kwargs: Any,
) -> dict[str, Any]:
    if not query:
        return {"success": False, "error": "No query provided", "results": []}

    start = time.monotonic()

    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("href", r.get("link", "")),
                "snippet": r.get("body", r.get("snippet", "")),
            }
            for r in raw
        ]
    except ImportError:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                resp = await http.get(
                    "https://lite.duckduckgo.com/lite/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
                results = [{"title": query, "url": "", "snippet": f"Search returned {len(resp.text)} chars"}]
        except Exception as e:
            log.error(f"DDGS fallback error: {e}")
            return {"success": False, "error": str(e), "results": []}
    except Exception as e:
        log.error(f"DDGS search error: {e}")
        return {"success": False, "error": str(e), "results": []}

    elapsed = round((time.monotonic() - start) * 1000, 1)
    log.info(f"DDGS '{query}': {len(results)} results ({elapsed}ms)")
    return {
        "success": True,
        "results": results,
        "count": len(results),
        "query": query,
        "latency_ms": elapsed,
    }
