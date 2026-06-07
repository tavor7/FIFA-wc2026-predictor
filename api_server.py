"""FastAPI REST backend and web UI for WC 2026 predictor."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src import db
from src.api.routes import router
from src.model_storage import load_models_on_startup, save_models_after_train
from src.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_DIR / "static"
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "true").lower() in ("1", "true", "yes")


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Short cache for read-only GET JSON endpoints."""

    CACHE_PATHS = (
        "/teams",
        "/tournament/",
        "/players/",
        "/meta/freshness",
        "/matches/upcoming",
        "/matches/recent",
    )

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if request.method == "GET" and any(request.url.path.startswith(p) for p in self.CACHE_PATHS):
            response.headers["Cache-Control"] = "public, max-age=60"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    load_models_on_startup()
    if ENABLE_SCHEDULER:
        start_scheduler()
        logger.info("Background scheduler enabled")
    yield
    stop_scheduler()


app = FastAPI(
    title="WC 2026 Research API",
    description="Designed by Amit Tavor. Research recommendation system.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(CacheControlMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def web_app() -> FileResponse:
    index = WEB_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Web UI not found")
    return FileResponse(index)
