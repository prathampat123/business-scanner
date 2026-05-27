"""
GET /api/export/csv   — download results as CSV
GET /api/export/json  — download results as JSON
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from app.models import Business

router = APIRouter()

_CSV_FIELDS = [
    "id", "name", "address", "city", "state", "zip_code",
    "phone", "website", "email",
    "rating", "review_count", "category",
    "source", "source_url", "scraped_at",
]


def _get_results(request: Request) -> list[Business]:
    results: list[Business] | None = getattr(request.app.state, "last_results", None)
    if not results:
        raise HTTPException(
            status_code=404,
            detail="No results to export. Run a search first.",
        )
    return results


def _filename(ext: str, request: Request) -> str:
    query = getattr(request.app.state, "last_query", "results")
    location = getattr(request.app.state, "last_location", "")
    slug = (
        f"{query}-{location}".lower()
        .replace(" ", "_")
        .replace(",", "")[:40]
    )
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"businesses_{slug}_{ts}.{ext}"


@router.get("/export/csv")
async def export_csv(request: Request) -> StreamingResponse:
    """Download last search results as a CSV file."""
    results = _get_results(request)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for biz in results:
        row = biz.model_dump()
        row["scraped_at"] = biz.scraped_at.isoformat()
        writer.writerow(row)

    buf.seek(0)
    filename = _filename("csv", request)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/json")
async def export_json(request: Request) -> Response:
    """Download last search results as a JSON file."""
    results = _get_results(request)

    payload = {
        "query": getattr(request.app.state, "last_query", ""),
        "location": getattr(request.app.state, "last_location", ""),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "businesses": [b.model_dump(mode="json") for b in results],
    }

    filename = _filename("json", request)
    return Response(
        content=json.dumps(payload, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
