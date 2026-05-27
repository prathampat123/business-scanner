# 🔍 Business Scanner

A full-stack **business data scraper & analyzer** — search by keyword and location, scrape Yelp + Yellow Pages concurrently, deduplicate and enrich the results, then export to **CSV** or **JSON**.

![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688)
![License](https://img.shields.io/badge/license-MIT-green)

---

## ✨ Features

| Feature | Details |
|---------|---------|
| **Multi-source scraping** | Yelp + Yellow Pages run concurrently |
| **Smart deduplication** | Fuzzy-match (rapidfuzz WRatio ≥ 88) merges duplicates |
| **Live filter & sort** | Filter by name/category/city; sort by rating, reviews, or name |
| **Export** | Download results as CSV or JSON with one click |
| **Zero build frontend** | Tailwind CSS CDN + Alpine.js — no Node.js required |
| **REST API** | Full OpenAPI docs at `/docs` |

---

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/prathampat123/business-scanner.git
cd business-scanner

# 2. Install dependencies (Python 3.12+)
pip install -r requirements.txt

# 3. (Optional) Configure environment
cp .env.example .env
# Edit .env to add SERPAPI_KEY, adjust timeouts, etc.

# 4. Start the server
python run.py
```

Open **http://localhost:8000** in your browser.

---

## 🖥️ Screenshots

```
┌─────────────────────────────────────────────────────┐
│  🔍 Business Scanner            scrape · enrich · export │
├─────────────────────────────────────────────────────┤
│  Keyword: [pizza restaurants      ]                 │
│  Location:[New York, NY           ]                 │
│  Sources: ☑ Yelp  ☑ Yellow Pages  Max: [20 ▼]      │
│                                       [ Search ]    │
├─────────────────────────────────────────────────────┤
│  42 businesses found · "pizza" in New York · 3200ms │
│  Filter: [____________]  Sort: [Rating ↓]  CSV  JSON │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │
│  │ Joe's Pizza  │  │ NY Pizza HQ  │  │ Grimaldi │  │
│  │ ★★★★½  4.5  │  │ ★★★★  4.0   │  │ ★★★★★   │  │
│  │ (2,341)      │  │ (890)        │  │ (5,102)  │  │
│  │ 📍 W 4th St  │  │ 📍 8th Ave   │  │ Brooklyn │  │
│  │ 📞 212-…     │  │ 📞 212-…     │  │ 📞 718-… │  │
│  └──────────────┘  └──────────────┘  └──────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 📡 API Reference

### `POST /api/search`

```json
{
  "query": "coffee shops",
  "location": "Austin, TX",
  "sources": ["yelp", "yellowpages"],
  "max_results": 20
}
```

**Response:**
```json
{
  "results": [ { "id": "…", "name": "…", "rating": 4.5, … } ],
  "total": 18,
  "sources_used": ["yelp", "yellowpages"],
  "query": "coffee shops",
  "location": "Austin, TX",
  "duration_ms": 2847.3
}
```

### `GET /api/export/csv`
Downloads the last search as a `.csv` file.

### `GET /api/export/json`
Downloads the last search as a `.json` file.

### `GET /api/health`
```json
{ "status": "ok", "version": "1.0.0" }
```

Full interactive docs: **http://localhost:8000/docs**

---

## 🗂️ Project Structure

```
business-scanner/
├── run.py                  # Start server: python run.py
├── requirements.txt
├── .env.example
├── CLAUDE.md               # Architecture notes for AI assistants
└── app/
    ├── main.py             # FastAPI factory + routes + static mount
    ├── models.py           # Pydantic schemas
    ├── scrapers/
    │   ├── yelp.py         # Yelp SERP scraper (async httpx)
    │   ├── yellowpages.py  # Yellow Pages scraper (async httpx)
    │   └── enricher.py     # Fuzzy dedup + merge
    ├── routes/
    │   ├── search.py       # POST /api/search
    │   └── export.py       # GET  /api/export/{csv,json}
    └── static/
        └── index.html      # SPA (Tailwind + Alpine.js)
```

---

## ⚙️ Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SERPAPI_KEY` | *(empty)* | Enables Google Maps results ([free tier](https://serpapi.com)) |
| `REQUEST_TIMEOUT` | `15` | HTTP timeout per request (seconds) |
| `MAX_RESULTS` | `50` | Max results per source |
| `CORS_ORIGINS` | `*` | Allowed CORS origins (comma-separated) |

---

## 🤝 Contributing

1. Fork the repo  
2. Create a feature branch: `git checkout -b feat/my-feature`  
3. Commit your changes  
4. Push and open a PR  

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

> **Note:** This tool is for legitimate research and lead generation. Respect each website's `robots.txt` and terms of service. Use responsibly.
