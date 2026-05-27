"""
Business Scanner — FastAPI application.

Startup:  python run.py
          uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models import HealthResponse
from app.routes import search as search_router
from app.routes import export as export_router

# ── Environment ───────────────────────────────────────────────────────────────
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise app-level state on startup."""
    app.state.settings = {
        "REQUEST_TIMEOUT": os.getenv("REQUEST_TIMEOUT", "15"),
        "MAX_RESULTS": os.getenv("MAX_RESULTS", "50"),
        "SERPAPI_KEY": os.getenv("SERPAPI_KEY", ""),
        "YELP_API_KEY": os.getenv("YELP_API_KEY", ""),
    }
    app.state.last_results = []
    app.state.last_query = ""
    app.state.last_location = ""
    logger.info("Business Scanner started ✓  →  http://localhost:8000")
    yield
    logger.info("Business Scanner shutting down.")


# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Business Scanner",
    description="Search, scrape, enrich, and export business data from multiple sources.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ────────────────────────────────────────────────────────────────
app.include_router(search_router.router, prefix="/api", tags=["search"])
app.include_router(export_router.router, prefix="/api", tags=["export"])


@app.get("/api/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    return HealthResponse()


# ── Static / SPA ──────────────────────────────────────────────────────────────
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_spa() -> FileResponse:
        return FileResponse(str(STATIC_DIR / "index.html"))
