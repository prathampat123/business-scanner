"""
Yellow Pages scraper — parses yellowpages.com search results.
Uses httpx (async) + BeautifulSoup. No API key required.
"""
from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup

from app.models import Business

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

_BASE_URL = "https://www.yellowpages.com/search"


class YellowPagesScraper:
    """Async scraper for Yellow Pages business search results."""

    def __init__(self, timeout: float = 15.0, max_results: int = 20) -> None:
        self.timeout = timeout
        self.max_results = max_results
        self._ua_index = 0

    # ── public API ────────────────────────────────────────────────────────────

    async def search(self, query: str, location: str) -> list[Business]:
        """
        Search Yellow Pages and return Business objects.
        Returns [] on network/parse errors.
        """
        results: list[Business] = []
        page = 1

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout,
            headers=self._headers(),
        ) as client:
            while len(results) < self.max_results:
                try:
                    html = await self._fetch_page(client, query, location, page)
                except Exception as exc:
                    logger.warning("YellowPages fetch error (page %d): %s", page, exc)
                    break

                page_results = self._parse_page(html)
                if not page_results:
                    break

                results.extend(page_results)
                if len(page_results) < 10:
                    break

                page += 1
                await asyncio.sleep(0.8)

        return results[: self.max_results]

    # ── private helpers ───────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        ua = _USER_AGENTS[self._ua_index % len(_USER_AGENTS)]
        self._ua_index += 1
        return {
            "User-Agent": ua,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.yellowpages.com/",
        }

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        query: str,
        location: str,
        page: int,
    ) -> str:
        params = {
            "search_terms": query,
            "geo_location_terms": location,
            "page": str(page),
        }
        url = f"{_BASE_URL}?{urllib.parse.urlencode(params)}"
        logger.debug("YellowPages GET %s", url)
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text

    def _parse_page(self, html: str) -> list[Business]:
        """Extract business listings from a Yellow Pages SERP page."""
        soup = BeautifulSoup(html, "lxml")
        businesses: list[Business] = []

        # Primary container for organic listings
        cards = (
            soup.select("div.result")
            or soup.select("div.v-card")
            or soup.select("article.result")
        )

        for card in cards:
            # Skip ad listings
            if card.select_one(".is-ad") or "sponsored" in card.get("class", []):
                continue
            biz = self._parse_card(card)
            if biz:
                businesses.append(biz)

        return businesses

    def _parse_card(self, card: BeautifulSoup) -> Business | None:
        """Parse a single YP result card into a Business object."""
        try:
            # ── Name ──────────────────────────────────────────────────────────
            name_tag = (
                card.select_one("a.business-name")
                or card.select_one("h2.n span")
                or card.select_one(".business-name")
            )
            if not name_tag:
                return None
            name = name_tag.get_text(strip=True)
            if not name:
                return None

            # ── Source URL ────────────────────────────────────────────────────
            link = card.select_one("a.business-name")
            source_url: str | None = None
            if link:
                href = link.get("href", "")
                source_url = (
                    href
                    if href.startswith("http")
                    else f"https://www.yellowpages.com{href}"
                )

            # ── Phone ─────────────────────────────────────────────────────────
            phone_tag = card.select_one("div.phones") or card.select_one(".phone")
            phone = phone_tag.get_text(strip=True) if phone_tag else None

            # ── Address ───────────────────────────────────────────────────────
            street_tag = card.select_one("div.street-address") or card.select_one(".street-address")
            locality_tag = card.select_one("div.locality") or card.select_one(".locality")
            address_parts = []
            if street_tag:
                address_parts.append(street_tag.get_text(strip=True))
            if locality_tag:
                address_parts.append(locality_tag.get_text(strip=True))
            address = ", ".join(address_parts) if address_parts else None

            # ── City / state / zip from locality ─────────────────────────────
            city: str | None = None
            state: str | None = None
            zip_code: str | None = None
            if locality_tag:
                locality_text = locality_tag.get_text(strip=True)
                # e.g. "New York, NY 10001"
                m = re.match(
                    r"^([^,]+),\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)?$",
                    locality_text,
                )
                if m:
                    city = m.group(1).strip()
                    state = m.group(2)
                    zip_code = m.group(3)

            # ── Rating ────────────────────────────────────────────────────────
            rating: float | None = None
            rating_tag = card.select_one("div.ratings") or card.select_one("[class*='star']")
            if rating_tag:
                aria = rating_tag.get("class", [])
                # YP uses class like "rated-4", "rated-4-5"
                for cls in (aria if isinstance(aria, list) else []):
                    m = re.match(r"rated-([\d]+)(?:-([\d]+))?", cls)
                    if m:
                        whole = int(m.group(1))
                        frac = int(m.group(2)) / 10 if m.group(2) else 0.0
                        rating = float(whole) + frac
                        break

            # ── Review count ──────────────────────────────────────────────────
            review_count: int | None = None
            count_tag = card.select_one(".count")
            if count_tag:
                m = re.search(r"(\d+)", count_tag.get_text())
                if m:
                    review_count = int(m.group(1))

            # ── Category ─────────────────────────────────────────────────────
            cat_tag = card.select_one(".categories") or card.select_one("div.categories a")
            category = cat_tag.get_text(strip=True) if cat_tag else None

            # ── Website ───────────────────────────────────────────────────────
            website_tag = card.select_one("a.track-visit-website")
            website = website_tag.get("href") if website_tag else None

            return Business(
                name=name,
                address=address,
                city=city,
                state=state,
                zip_code=zip_code,
                phone=phone,
                website=website,
                rating=rating,
                review_count=review_count,
                category=category,
                source="yellowpages",
                source_url=source_url,
            )
        except Exception as exc:
            logger.debug("Failed to parse YP card: %s", exc)
            return None
