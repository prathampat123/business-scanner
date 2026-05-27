"""
Enricher — merges and deduplicates Business records from multiple scrapers.

Deduplication strategy:
  1. Normalize names (lowercase, strip punctuation).
  2. Use rapidfuzz WRatio similarity ≥ 88 on (name + city) to detect duplicates.
  3. When merging, prefer the record with more non-null fields.
"""
from __future__ import annotations

import re
import logging
from itertools import combinations

from rapidfuzz import fuzz

from app.models import Business

logger = logging.getLogger(__name__)


def _normalize(text: str | None) -> str:
    """Lowercase, strip punctuation for fuzzy comparison."""
    if not text:
        return ""
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def _field_count(biz: Business) -> int:
    """Count non-None, non-empty fields — used to pick the 'richer' record."""
    fields = [
        biz.address, biz.city, biz.state, biz.zip_code,
        biz.phone, biz.website, biz.email,
        biz.rating, biz.review_count, biz.category,
    ]
    return sum(1 for f in fields if f is not None and f != "")


def _merge(primary: Business, secondary: Business) -> Business:
    """Merge two records, filling nulls in primary from secondary."""
    data = primary.model_dump()
    for field, value in secondary.model_dump().items():
        if field in ("id", "source", "source_url", "scraped_at"):
            continue
        if data.get(field) is None and value is not None:
            data[field] = value
    return Business(**data)


class Enricher:
    """
    Merges multiple lists of Business records.

    Usage::

        enricher = Enricher(similarity_threshold=88)
        merged = enricher.merge([yelp_results, yp_results])
    """

    def __init__(self, similarity_threshold: int = 88) -> None:
        self.threshold = similarity_threshold

    def merge(self, source_lists: list[list[Business]]) -> list[Business]:
        """
        Flatten source lists, deduplicate, merge duplicates, sort by rating desc.
        """
        all_records: list[Business] = []
        for lst in source_lists:
            all_records.extend(lst)

        if not all_records:
            return []

        logger.info("Enricher: %d raw records → deduplicating …", len(all_records))

        # Build merge groups using Union-Find
        n = len(all_records)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        keys = [
            _normalize(r.name) + " " + _normalize(r.city or r.address or "")
            for r in all_records
        ]

        for i, j in combinations(range(n), 2):
            if keys[i] and keys[j]:
                score = fuzz.WRatio(keys[i], keys[j])
                if score >= self.threshold:
                    union(i, j)

        # Group by root
        groups: dict[int, list[int]] = {}
        for idx in range(n):
            root = find(idx)
            groups.setdefault(root, []).append(idx)

        merged: list[Business] = []
        for indices in groups.values():
            records = sorted(
                [all_records[i] for i in indices],
                key=_field_count,
                reverse=True,
            )
            combined = records[0]
            for extra in records[1:]:
                combined = _merge(combined, extra)
            merged.append(combined)

        # Sort: rated first, then by review_count, then by name
        merged.sort(
            key=lambda b: (
                -(b.rating or 0),
                -(b.review_count or 0),
                b.name.lower(),
            )
        )

        logger.info("Enricher: %d unique businesses after dedup", len(merged))
        return merged
