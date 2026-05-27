"""
OpenStreetMap / Overpass API scraper.

Completely free, no API key required, no rate-limit issues.
Uses the Overpass QL API to find businesses by type + location.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.models import Business

logger = logging.getLogger(__name__)

# Public Overpass API endpoints (try in order if one is busy)
_OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Mapping of common search terms → OSM amenity/shop tags
_KEYWORD_MAP: dict[str, list[tuple[str, str]]] = {
    "pizza":          [("amenity", "restaurant"), ("cuisine", "pizza")],
    "restaurant":     [("amenity", "restaurant")],
    "cafe":           [("amenity", "cafe")],
    "coffee":         [("amenity", "cafe")],
    "bar":            [("amenity", "bar")],
    "pub":            [("amenity", "pub")],
    "hotel":          [("tourism", "hotel")],
    "dentist":        [("amenity", "dentist")],
    "doctor":         [("amenity", "doctors")],
    "pharmacy":       [("amenity", "pharmacy")],
    "gym":            [("leisure", "fitness_centre")],
    "supermarket":    [("shop", "supermarket")],
    "grocery":        [("shop", "grocery")],
    "bakery":         [("shop", "bakery")],
    "bookstore":      [("shop", "books")],
    "hardware":       [("shop", "hardware")],
    "bank":           [("amenity", "bank")],
    "atm":            [("amenity", "atm")],
    "gas station":    [("amenity", "fuel")],
    "parking":        [("amenity", "parking")],
    "school":         [("amenity", "school")],
    "hospital":       [("amenity", "hospital")],
    "laundry":        [("shop", "laundry")],
    "dry cleaning":   [("shop", "dry_cleaning")],
    "hair salon":     [("shop", "hairdresser")],
    "barber":         [("shop", "barber")],
    "nail salon":     [("shop", "beauty")],
    "spa":            [("leisure", "spa")],
    "yoga":           [("sport", "yoga")],
    "plumber":        [("trade", "plumber")],
    "electrician":    [("trade", "electrician")],
    "florist":        [("shop", "florist")],
    "jewelry":        [("shop", "jewelry")],
    "clothing":       [("shop", "clothes")],
    "shoes":          [("shop", "shoes")],
    "electronics":    [("shop", "electronics")],
    "car dealer":     [("shop", "car")],
    "car repair":     [("shop", "car_repair")],
}

_DEFAULT_TAGS: list[tuple[str, str]] = [("amenity", "restaurant")]


def _pick_tags(query: str) -> list[tuple[str, str]]:
    """Return the best OSM tag pair(s) for a free-text query."""
    q = query.lower()
    for keyword, tags in _KEYWORD_MAP.items():
        if keyword in q:
            return tags
    return _DEFAULT_TAGS


async def _geocode_location(client: httpx.AsyncClient, location: str) -> tuple[float, float, float] | None:
    """
    Geocode a location string → (lat, lon, radius_km).
    Returns None if geocoding fails.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": location,
        "format": "json",
        "limit": "1",
        "addressdetails": "1",
    }
    headers = {"User-Agent": "BusinessScanner/1.0 (educational project)"}
    try:
        r = await client.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        results = r.json()
        if not results:
            return None
        hit = results[0]
        lat = float(hit["lat"])
        lon = float(hit["lon"])
        # Estimate radius from bounding box
        bb = hit.get("boundingbox", [])
        if len(bb) == 4:
            lat_span = abs(float(bb[1]) - float(bb[0]))
            lon_span = abs(float(bb[3]) - float(bb[2]))
            radius_km = max(2.0, min(25.0, max(lat_span, lon_span) * 111 / 2))
        else:
            radius_km = 5.0
        return lat, lon, radius_km
    except Exception as exc:
        logger.warning("Geocoding failed for %r: %s", location, exc)
        return None


def _build_overpass_query(
    tags: list[tuple[str, str]],
    lat: float,
    lon: float,
    radius_m: float,
    limit: int,
) -> str:
    """Build an Overpass QL query for nodes/ways with the given tags near a point."""
    tag_filters = "".join(f'["{k}"="{v}"]' for k, v in tags)
    return (
        f"[out:json][timeout:25];"
        f"("
        f"  node{tag_filters}(around:{radius_m:.0f},{lat},{lon});"
        f"  way{tag_filters}(around:{radius_m:.0f},{lat},{lon});"
        f");"
        f"out body {limit};"
        f">;out skel qt;"
    )


def _element_to_business(el: dict[str, Any]) -> Business | None:
    """Convert an Overpass element dict to a Business."""
    tags: dict[str, str] = el.get("tags", {})
    name = tags.get("name") or tags.get("brand")
    if not name:
        return None

    # Address
    street  = tags.get("addr:street", "")
    housen  = tags.get("addr:housenumber", "")
    city    = tags.get("addr:city", "")
    state   = tags.get("addr:state", "")
    zipcode = tags.get("addr:postcode", "")
    address = f"{housen} {street}".strip() or None

    # Phone — normalise formats
    phone = tags.get("phone") or tags.get("contact:phone")
    if phone:
        phone = re.sub(r"[\s\-().+]", "", phone)
        if phone.startswith("1") and len(phone) == 11:
            phone = f"({phone[1:4]}) {phone[4:7]}-{phone[7:]}"
        elif len(phone) == 10:
            phone = f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"

    # Website
    website = tags.get("website") or tags.get("contact:website") or tags.get("url")
    if website and not website.startswith("http"):
        website = "https://" + website

    # Category — prefer cuisine, then amenity/shop/leisure
    category = (
        tags.get("cuisine")
        or tags.get("shop")
        or tags.get("amenity")
        or tags.get("leisure")
        or tags.get("tourism")
        or tags.get("trade")
    )
    if category:
        category = category.replace("_", " ").title()

    # Source URL — link to OSM object
    osm_type = el.get("type", "node")
    osm_id   = el.get("id", "")
    source_url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"

    return Business(
        name=name,
        address=address,
        city=city or None,
        state=state or None,
        zip_code=zipcode or None,
        phone=phone,
        website=website,
        category=category,
        source="openstreetmap",
        source_url=source_url,
    )


class OSMScraper:
    """Async scraper backed by OpenStreetMap Overpass API."""

    def __init__(self, timeout: float = 25.0, max_results: int = 50) -> None:
        self.timeout = timeout
        self.max_results = max_results

    async def search(self, query: str, location: str) -> list[Business]:
        """Search OSM for businesses matching query near location."""
        async with httpx.AsyncClient(follow_redirects=True, timeout=self.timeout) as client:
            geo = await _geocode_location(client, location)
            if not geo:
                logger.warning("OSM: Could not geocode %r", location)
                return []

            lat, lon, radius_km = geo
            radius_m = radius_km * 1000
            tags = _pick_tags(query)

            # If query doesn't map to a specific tag, fall back to name search
            if tags == _DEFAULT_TAGS and not any(
                kw in query.lower() for kw in ("restaurant", "food", "eat", "dine")
            ):
                return await self._name_search(client, query, lat, lon, radius_m)

            return await self._tag_search(client, tags, lat, lon, radius_m)

    async def _tag_search(
        self,
        client: httpx.AsyncClient,
        tags: list[tuple[str, str]],
        lat: float,
        lon: float,
        radius_m: float,
    ) -> list[Business]:
        oql = _build_overpass_query(tags, lat, lon, radius_m, self.max_results * 2)
        data = await self._overpass_query(client, oql)
        if data is None:
            return []

        results: list[Business] = []
        for el in data.get("elements", []):
            biz = _element_to_business(el)
            if biz:
                results.append(biz)

        logger.info("OSM tag search → %d businesses", len(results))
        return results[: self.max_results]

    async def _overpass_query(
        self,
        client: httpx.AsyncClient,
        oql: str,
    ) -> dict | None:
        """POST the Overpass QL query, trying mirrors on failure."""
        import urllib.parse
        encoded = urllib.parse.urlencode({"data": oql})
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "BusinessScanner/1.0 (educational project)",
        }
        for url in _OVERPASS_MIRRORS:
            try:
                r = await client.post(
                    url,
                    content=encoded.encode(),
                    headers=headers,
                    timeout=self.timeout,
                )
                r.raise_for_status()
                return r.json()
            except Exception as exc:
                logger.warning("Overpass mirror %s failed: %s", url, exc)
        return None

    async def _name_search(
        self,
        client: httpx.AsyncClient,
        query: str,
        lat: float,
        lon: float,
        radius_m: float,
    ) -> list[Business]:
        """Fallback: search by name using Nominatim."""
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": str(self.max_results),
            "addressdetails": "1",
            "extratags": "1",
            "viewbox": (
                f"{lon - 0.5},{lat + 0.5},{lon + 0.5},{lat - 0.5}"
            ),
            "bounded": "1",
        }
        headers = {"User-Agent": "BusinessScanner/1.0 (educational project)"}
        try:
            r = await client.get(url, params=params, headers=headers, timeout=10)
            r.raise_for_status()
            hits = r.json()
        except Exception as exc:
            logger.warning("Nominatim name search error: %s", exc)
            return []

        results: list[Business] = []
        for hit in hits:
            name = hit.get("display_name", "").split(",")[0]
            if not name:
                continue
            addr = hit.get("address", {})
            city = addr.get("city") or addr.get("town") or addr.get("village")
            state = addr.get("state")
            zipcode = addr.get("postcode")
            extra = hit.get("extratags", {})
            website = extra.get("website") or extra.get("contact:website")
            phone = extra.get("phone") or extra.get("contact:phone")
            category = hit.get("type", "").replace("_", " ").title() or None

            results.append(Business(
                name=name,
                city=city,
                state=state,
                zip_code=zipcode,
                phone=phone,
                website=website,
                category=category,
                source="openstreetmap",
                source_url=f"https://www.openstreetmap.org/{hit.get('osm_type','node')}/{hit.get('osm_id','')}",
            ))

        logger.info("OSM name search → %d results", len(results))
        return results[: self.max_results]
