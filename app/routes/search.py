"""
POST /api/search — run scrapers and return enriched results.

Source priority:
  1. openstreetmap  — always available, no key needed (Overpass API)
  2. yelp           — uses Yelp Fusion API if YELP_API_KEY is set,
                      otherwise falls back to HTML scraping (may be blocked)
  3. yellowpages    — HTML scraping (may be blocked by Cloudflare)
"""
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException, Request

from app.models import SearchRequest, SearchResponse, Business
from app.scrapers import OSMScraper, YelpAPIClient, YelpScraper, YellowPagesScraper, Enricher

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search_businesses(payload: SearchRequest, request: Request) -> SearchResponse:
    """
    Search for businesses across selected sources, running them concurrently.
    Results are merged + deduplicated by the Enricher and stored in app.state
    for the export endpoints.
    """
    settings = request.app.state.settings
    timeout: float = float(settings.get("REQUEST_TIMEOUT", 15))
    max_results: int = min(payload.max_results, int(settings.get("MAX_RESULTS", 50)))
    yelp_api_key: str = settings.get("YELP_API_KEY", "")

    source_lists: list[list[Business]] = []
    sources_used: list[str] = []

    coros = []

    for source in payload.sources:
        if source == "openstreetmap":
            scraper = OSMScraper(timeout=timeout, max_results=max_results)
            coros.append(("openstreetmap", scraper.search(payload.query, payload.location)))

        elif source == "yelp":
            if yelp_api_key:
                client = YelpAPIClient(api_key=yelp_api_key, timeout=timeout, max_results=max_results)
            else:
                # Fallback to HTML scraper (may be 403'd by Yelp)
                client = YelpScraper(timeout=timeout, max_results=max_results)  # type: ignore[assignment]
            coros.append(("yelp", client.search(payload.query, payload.location)))

        elif source == "yellowpages":
            scraper_yp = YellowPagesScraper(timeout=timeout, max_results=max_results)
            coros.append(("yellowpages", scraper_yp.search(payload.query, payload.location)))

    if not coros:
        raise HTTPException(status_code=400, detail="No valid sources selected.")

    start = time.perf_counter()

    # Run all scrapers concurrently; capture exceptions per-source so one
    # failure doesn't kill the whole search.
    async def run_safe(name: str, coro: object) -> tuple[str, list[Business]]:
        try:
            results = await coro  # type: ignore[misc]
            logger.info("Source %-14s → %d results", name, len(results))
            return name, results
        except Exception as exc:
            logger.warning("Source %s failed: %s", name, exc)
            return name, []

    gathered = await asyncio.gather(*[run_safe(n, c) for n, c in coros])
    duration_ms = (time.perf_counter() - start) * 1000

    for name, results in gathered:
        sources_used.append(name)
        source_lists.append(results)

    enricher = Enricher()
    merged = enricher.merge(source_lists)

    # Store for export endpoints
    request.app.state.last_results = merged
    request.app.state.last_query = payload.query
    request.app.state.last_location = payload.location

    logger.info(
        "Search %r in %r → %d merged results in %.0f ms",
        payload.query, payload.location, len(merged), duration_ms,
    )

    return SearchResponse(
        results=merged,
        total=len(merged),
        sources_used=sources_used,
        query=payload.query,
        location=payload.location,
        duration_ms=round(duration_ms, 1),
    )
