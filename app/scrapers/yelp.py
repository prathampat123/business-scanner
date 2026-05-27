"""
Yelp scraper — parses Yelp search result pages.
Uses httpx (async) + BeautifulSoup. No API key required.
"""
from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from typing import TYPE_CHECKING

import httpx
from bs4 import BeautifulSoup

from app.models import Business

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Rotate through a few common user-agents to reduce bot detection
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

_BASE_URL = "https://www.yelp.com/search"


class YelpScraper:
    """Async scraper for Yelp business search results."""

    def __init__(self, timeout: float = 15.0, max_results: int = 20) -> None:
        self.timeout = timeout
        self.max_results = max_results
        self._ua_index = 0

    # ── public API ────────────────────────────────────────────────────────────

    async def search(self, query: str, location: str) -> list[Business]:
        """
        Search Yelp and return a list of Business objects.
        Falls back gracefully on network errors — returns [] instead of raising.
        """
        results: list[Business] = []
        offset = 0
        page = 0

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout,
            headers=self._headers(),
        ) as client:
            while len(results) < self.max_results:
                try:
                    html = await self._fetch_page(client, query, location, offset)
                except Exception as exc:
                    logger.warning("Yelp fetch error (page %d): %s", page, exc)
                    break

                page_results = self._parse_page(html)
                if not page_results:
                    break

                results.extend(page_results)
                if len(page_results) < 10:
                    break  # last page

                offset += 10
                page += 1
                await asyncio.sleep(0.8)  # polite delay

        return results[: self.max_results]

    # ── private helpers ───────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        ua = _USER_AGENTS[self._ua_index % len(_USER_AGENTS)]
        self._ua_index += 1
        return {
            "User-Agent": ua,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.yelp.com/",
        }

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        query: str,
        location: str,
        offset: int,
    ) -> str:
        params = {
            "find_desc": query,
            "find_loc": location,
            "start": str(offset),
        }
        url = f"{_BASE_URL}?{urllib.parse.urlencode(params)}"
        logger.debug("Yelp GET %s", url)
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text

    def _parse_page(self, html: str) -> list[Business]:
        """Extract business cards from a Yelp SERP page."""
        soup = BeautifulSoup(html, "lxml")
        businesses: list[Business] = []

        # Yelp renders results inside <li> tags with data-testid or aria-label
        # Try multiple selector strategies for resilience across Yelp's changing markup.
        cards = (
            soup.select("li.y-css-1sqctm3")          # common 2024 class
            or soup.select("li[class*='border-color']")
            or soup.select("div[data-testid='serp-ia-card']")
            or soup.select("div.container__09f24__21w3G")  # older markup
        )

        # Fallback: find all <h3> or <h4> inside search result containers
        if not cards:
            cards = soup.select("div#main-content li")

        for card in cards:
            biz = self._parse_card(card)
            if biz:
                businesses.append(biz)

        return businesses

    def _parse_card(self, card: BeautifulSoup) -> Business | None:
        """Parse a single Yelp result card into a Business object."""
        try:
            # ── Name ──────────────────────────────────────────────────────────
            name_tag = (
                card.select_one("a[name]")
                or card.select_one("span[class*='css-1egxyvc']")
                or card.select_one("a.css-166la90")
                or card.select_one("h3 > span")
                or card.select_one("h4 > span")
            )
            # Many Yelp cards wrap the name in a link with a numbered prefix like "1. Pizza Hut"
            name_link = card.select_one("a[href*='/biz/']")
            name = None
            source_url = None

            if name_link:
                raw = name_link.get_text(strip=True)
                # strip leading "1. ", "10. " numbering
                name = re.sub(r"^\d+\.\s*", "", raw).strip()
                href = name_link.get("href", "")
                source_url = (
                    href if href.startswith("http") else f"https://www.yelp.com{href}"
                )
            elif name_tag:
                name = name_tag.get_text(strip=True)

            if not name:
                return None

            # ── Rating ────────────────────────────────────────────────────────
            rating_tag = (
                card.select_one("div[aria-label*='star rating']")
                or card.select_one("[class*='i-stars']")
            )
            rating: float | None = None
            if rating_tag:
                aria = rating_tag.get("aria-label", "")
                m = re.search(r"([\d.]+)\s*star", aria, re.IGNORECASE)
                if m:
                    rating = float(m.group(1))

            # ── Review count ──────────────────────────────────────────────────
            review_count: int | None = None
            for span in card.find_all("span"):
                text = span.get_text(strip=True)
                m = re.match(r"^([\d,]+)\s*reviews?$", text, re.IGNORECASE)
                if m:
                    review_count = int(m.group(1).replace(",", ""))
                    break

            # ── Address / phone ───────────────────────────────────────────────
            address: str | None = None
            phone: str | None = None
            for p in card.find_all(["p", "address", "span"]):
                text = p.get_text(strip=True)
                if re.match(r"\d{3}[-.\s]\d{3}[-.\s]\d{4}", text):
                    phone = text
                elif re.search(r"\b[A-Z]{2}\b\s+\d{5}", text):
                    address = text

            # ── Category ─────────────────────────────────────────────────────
            category: str | None = None
            cat_tag = card.select_one("span.css-11bijt4") or card.select_one(
                "a[href*='/c/']"
            )
            if cat_tag:
                category = cat_tag.get_text(strip=True)

            return Business(
                name=name,
                address=address,
                phone=phone,
                rating=rating,
                review_count=review_count,
                category=category,
                source="yelp",
                source_url=source_url,
            )
        except Exception as exc:
            logger.debug("Failed to parse Yelp card: %s", exc)
            return None
