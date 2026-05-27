"""
Yelp Fusion API scraper (official, free tier — 5,000 calls/day).
Requires YELP_API_KEY in .env.  Returns [] gracefully if key is absent.

API docs: https://docs.developer.yelp.com/reference/v3_business_search
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.models import Business

logger = logging.getLogger(__name__)

_BASE = "https://api.yelp.com/v3/businesses/search"


class YelpAPIClient:
    """Async wrapper around the Yelp Fusion Business Search endpoint."""

    def __init__(self, api_key: str, timeout: float = 15.0, max_results: int = 50) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.max_results = max_results

    # ── public API ──────────────────────────────────────────────────────────

    async def search(self, query: str, location: str) -> list[Business]:
        if not self.api_key:
            return []

        results: list[Business] = []
        offset = 0
        per_page = min(50, self.max_results)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while len(results) < self.max_results:
                batch = await self._fetch(client, query, location, offset, per_page)
                if not batch:
                    break
                results.extend(batch)
                if len(batch) < per_page:
                    break
                offset += per_page

        return results[: self.max_results]

    # ── private helpers ─────────────────────────────────────────────────────

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        query: str,
        location: str,
        offset: int,
        limit: int,
    ) -> list[Business]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {
            "term": query,
            "location": location,
            "limit": limit,
            "offset": offset,
            "sort_by": "best_match",
        }
        try:
            r = await client.get(_BASE, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("Yelp API HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
            return []
        except Exception as exc:
            logger.warning("Yelp API error: %s", exc)
            return []

        return [self._parse(biz) for biz in data.get("businesses", [])]

    def _parse(self, biz: dict[str, Any]) -> Business:
        location = biz.get("location", {})
        address_parts = location.get("display_address", [])
        address = address_parts[0] if address_parts else None

        coords = biz.get("coordinates", {})
        categories = biz.get("categories", [])
        category = ", ".join(c.get("title", "") for c in categories) if categories else None

        return Business(
            name=biz.get("name", ""),
            address=address,
            city=location.get("city"),
            state=location.get("state"),
            zip_code=location.get("zip_code"),
            phone=biz.get("display_phone") or biz.get("phone"),
            website=biz.get("url"),
            rating=biz.get("rating"),
            review_count=biz.get("review_count"),
            category=category,
            source="yelp",
            source_url=biz.get("url"),
        )
