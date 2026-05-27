# Business Scanner — CLAUDE.md

## Project Overview
A web-based **Business Scraper & Analyzer** that lets users search for businesses by type and location, scrapes multiple sources, enriches the data, and exports results to CSV or JSON.

**Stack:**
- **Backend**: Python 3.14 · FastAPI · Uvicorn · BeautifulSoup4 · httpx
- **Frontend**: Vanilla HTML + Tailwind CSS (CDN) + Alpine.js (CDN) — no build step
- **Scraping targets**: Yelp, Yellow Pages, (Google Maps via SerpAPI if key provided)
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
    │   ├── yelp.py         ← Yelp search scraper
    │   ├── yellowpages.py  ← Yellow Pages scraper
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
- Scrapers use **httpx** (async) with rotating User-Agent strings and polite delays to avoid blocks.
- The enricher deduplicates by fuzzy-matching `name + address` (Levenshtein distance ≤ 0.15).
- Session results are stored in-memory (`app.state.results`) — no database required for MVP.
- The frontend polls `/api/search` via fetch and renders results with Alpine.js reactivity.

---

## Changelog
| Date | What changed |
|------|-------------|
| 2026-05-26 | Initial scaffold: models, scrapers (Yelp, YP), routes, frontend |
