"""
Pydantic models for Business Scanner.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────────────────
# Core domain model
# ──────────────────────────────────────────────────────────────────────────────

class Business(BaseModel):
    """A single business record scraped from one source."""

    id: str = Field(default="", description="SHA-256 hash of name+address (auto-computed)")
    name: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    phone: str | None = None
    website: str | None = None
    email: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    category: str | None = None
    source: Literal["yelp", "yellowpages", "google_maps", "unknown"] = "unknown"
    source_url: str | None = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def model_post_init(self, __context: object) -> None:
        """Auto-generate id from name + address if not supplied."""
        if not self.id:
            key = f"{(self.name or '').lower().strip()}|{(self.address or '').lower().strip()}"
            self.id = hashlib.sha256(key.encode()).hexdigest()[:16]

    @field_validator("rating", mode="before")
    @classmethod
    def clamp_rating(cls, v: float | None) -> float | None:
        if v is None:
            return None
        return round(max(0.0, min(5.0, float(v))), 1)

    @field_validator("phone", mode="before")
    @classmethod
    def clean_phone(cls, v: str | None) -> str | None:
        """Strip excess whitespace from phone strings."""
        return v.strip() if isinstance(v, str) else v


# ──────────────────────────────────────────────────────────────────────────────
# Request / response schemas
# ──────────────────────────────────────────────────────────────────────────────

SourceName = Literal["yelp", "yellowpages", "google_maps"]


class SearchRequest(BaseModel):
    """Payload for POST /api/search."""

    query: str = Field(..., min_length=1, max_length=200, examples=["pizza restaurants"])
    location: str = Field(..., min_length=1, max_length=200, examples=["New York, NY"])
    sources: list[SourceName] = Field(
        default=["yelp", "yellowpages"],
        description="Which scrapers to run.",
    )
    max_results: int = Field(default=20, ge=1, le=100)

    @field_validator("query", "location", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class SearchResponse(BaseModel):
    """Response from POST /api/search."""

    results: list[Business]
    total: int
    sources_used: list[str]
    query: str
    location: str
    duration_ms: float


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
