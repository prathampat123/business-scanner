# Business Scanner — CLAUDE.md

## Project Overview
A web-based **Business Scraper & Analyzer** that lets users search for businesses by type and location, scrapes multiple sources, enriches the data, and exports results to CSV or JSON.

**Stack:**
- **Backend**: Python 3.14 · FastAPI · Uvicorn · BeautifulSoup4 · httpx
- **Frontend**: Vanilla HTML + Tailwind CSS (CDN) + Alpine.js (CDN) — no build step
- **Data sources**: OpenStreetMap/Overpass (default, free, no key), Yelp Fusion API (YELP_API_KEY), Yellow Pages scraper (may be Cloudflare-blocked)
- **Exports**: CSV, JSON

---

## Directory Structure
```
business-scanner/
├── CLAUDE.md               ← this file
├── README.md
├── requirements.txt
├── .env.example
├── run.py                  ← start server: python run.py
└── app/
    ├── main.py             ← FastAPI app + static mount
    ├── models.py           ← Pydantic schemas (Business, SearchRequest, …)
    ├── scrapers/
    │   ├── __init__.py
    │   ├── osm.py          ← OpenStreetMap/Overpass scraper (default, free)
    │   ├── yelp_api.py     ← Yelp Fusion API client (needs YELP_API_KEY)
    │   ├── yelp.py         ← Yelp HTML scraper (fallback, often 403'd)
    │   ├── yellowpages.py  ← Yellow Pages HTML scraper (often 403'd)
    │   └── enricher.py     ← Merges + deduplicates results
    ├── routes/
    │   ├── __init__.py
    │   ├── search.py       ← POST /api/search
    │   └── export.py       ← GET  /api/export/{format}
    └── static/
        └── index.html      ← Single-page frontend
```

---

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start the development server
python run.py
# → http://localhost:8000

# Or with uvicorn directly
uvicorn app.main:app --reload --port 8000
```

---

## Environment Variables
Copy `.env.example` → `.env` and fill in optional keys:
```
YELP_API_KEY=         # Optional: enables Yelp Fusion API (free, 5k calls/day)
SERPAPI_KEY=          # Optional: enables Google Maps results
REQUEST_TIMEOUT=15    # Seconds per HTTP request (default 15)
MAX_RESULTS=50        # Max results per source (default 50)
```

---

## API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/search` | Search businesses; body: `{query, location, sources[]}` |
| `GET`  | `/api/export/csv` | Export last session results as CSV |
| `GET`  | `/api/export/json` | Export last session results as JSON |
| `GET`  | `/api/health` | Health check |
| `GET`  | `/` | Serves the frontend SPA |

---

## Data Model — `Business`
```python
class Business(BaseModel):
    id: str           # sha256 hash of name+address
    name: str
    address: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    phone: str | None
    website: str | None
    email: str | None
    rating: float | None
    review_count: int | None
    category: str | None
    source: str       # "yelp" | "yellowpages" | "google_maps"
    source_url: str | None
    scraped_at: datetime
```

---

## Development Notes
- **Primary source**: OpenStreetMap Overpass API (`osm.py`) — always works, no key required.
  - Geocodes the location via Nominatim, then queries Overpass QL within the bounding radius.
  - 30+ keyword→OSM-tag mappings; falls back to Nominatim name search for unknown keywords.
  - Tries 3 public Overpass mirrors if one is overloaded.
- **Yelp Fusion API** (`yelp_api.py`) — official REST API, 5,000 free calls/day.
  - Set `YELP_API_KEY` in `.env` to activate; otherwise falls back to HTML scraper.
- **HTML scrapers** (`yelp.py`, `yellowpages.py`) — kept for completeness but both sites now
  return 403 via Cloudflare when accessed server-side. May work from some IPs.
- The enricher deduplicates by fuzzy-matching `name + city` (rapidfuzz WRatio ≥ 88).
- Session results are stored in-memory (`app.state.last_results`) — no database required for MVP.
- The frontend renders results with Alpine.js reactivity; live filter + sort client-side.

---

## Python 3.14 Compatibility Notes
- `lxml` has **no pre-built wheels for Python 3.14** — use `html.parser` (stdlib) in all `BeautifulSoup(html, ...)` calls.
- `pydantic-core` v2.13.4+ ships Python 3.14 wheels — install without strict pins (`pydantic>=2.0.0`).
- `uvicorn[standard]` installs fine; `websockets` binary may warn about PATH — harmless.

## Running in Dev
```bash
python run.py
# FastAPI auto-reload enabled; edits to app/ restart the server automatically.
# API docs live at http://localhost:8000/docs
```

## Changelog
| Date | What changed |
|------|-------------|
| 2026-05-26 | Initial scaffold: CLAUDE.md, requirements, .env.example, .gitignore, run.py |
| 2026-05-26 | Backend core: Pydantic models, Yelp scraper, Yellow Pages scraper, Enricher |
| 2026-05-26 | FastAPI routes: POST /api/search, GET /api/export/{csv,json}, GET /api/health |
| 2026-05-26 | Frontend SPA: Tailwind CDN + Alpine.js, search form, results grid, export buttons |
| 2026-05-26 | Fixed Python 3.14 compat: replaced lxml → html.parser, relaxed pydantic pin |
| 2026-05-26 | README with quickstart, API reference, project structure, config table |
| 2026-05-27 | Fix: Yelp/YP return 403 (Cloudflare); replaced with OSM Overpass API + Yelp Fusion API client |
