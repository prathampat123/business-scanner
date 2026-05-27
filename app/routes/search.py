"""
POST /api/search — run scrapers and return enriched results.
"""
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException, Request

from app.models import SearchRequest, SearchResponse, Business
from app.scrapers import YelpScraper, YellowPagesScraper, Enricher

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search_businesses(payload: SearchRequest, request: Request) -> SearchResponse:
    """
    Search for businesses across selected sources.

    - Runs scrapers concurrently with asyncio.gather.
    - Merges + deduplicates via the Enricher.
    - Stores results in app.state for the export endpoints.
    """
    settings = request.app.state.settings
    timeout: float = float(settings.get("REQUEST_TIMEOUT", 15))
    max_results: int = min(payload.max_results, int(settings.get("MAX_RESULTS", 50)))

    sources_used: list[str] = []
    tasks: list[asyncio.Task[list[Business]]] = []

    if "yelp" in payload.sources:
        scraper = YelpScraper(timeout=timeout, max_results=max_results)
        tasks.append(asyncio.create_task(scraper.search(payload.query, payload.location)))
        sources_used.append("yelp")

    if "yellowpages" in payload.sources:
        scraper_yp = YellowPagesScraper(timeout=timeout, max_results=max_results)
        tasks.append(asyncio.create_task(scraper_yp.search(payload.query, payload.location)))
        sources_used.append("yellowpages")

    if not tasks:
        raise HTTPException(status_code=400, detail="No valid sources selected.")

    start = time.perf_counter()
    try:
        raw_lists: list[list[Business]] = await asyncio.gather(*tasks, return_exceptions=False)
    except Exception as exc:
        logger.error("Scraping error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Scraping failed: {exc}") from exc
    duration_ms = (time.perf_counter() - start) * 1000

    enricher = Enricher()
    results = enricher.merge(list(raw_lists))

    # Persist results for export endpoints
    request.app.state.last_results = results
    request.app.state.last_query = payload.query
    request.app.state.last_location = payload.location

    logger.info(
        "Search '%s' in '%s' → %d results in %.0f ms",
        payload.query, payload.location, len(results), duration_ms,
    )

    return SearchResponse(
        results=results,
        total=len(results),
        sources_used=sources_used,
        query=payload.query,
        location=payload.location,
        duration_ms=round(duration_ms, 1),
    )
