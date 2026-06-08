"""FastAPI REST backend and web UI for WC 2026 predictor."""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src import config, db
from src.api.routes import router
from src.cache.response_cache import cache_key, get_cache_meta, get_cached, _ttl_for_path
from src.model_storage import load_models_on_startup
from src.observability.request_metrics import (
    get_db_ms,
    record_api_metric,
    set_request_path,
)
from src.scheduler import start_scheduler, stop_scheduler
from src.seed.load_seeds import ensure_baseline_data

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_DIR / "static"
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "true").lower() in ("1", "true", "yes")
STARTUP_SEED = os.getenv("STARTUP_SEED", "true").lower() in ("1", "true", "yes")


def _background_startup() -> None:
    """DB migrations + seed after the server is listening (Render port binding)."""
    try:
        db.init_db()
        logger.info("Database initialization finished")
    except Exception as exc:
        logger.error("Database initialization failed: %s", exc)
        return
    _startup_seed_worker()


def _startup_seed_worker() -> None:
    """Baseline data load and FC26 import when needed."""
    try:
        ensure_baseline_data(min_matches=10, run_predictions=False)
        from src import db_extended as ext
        from src.services.data_sync_service import DataSyncService

        ext.prune_non_tournament_teams()
        from src.seed.import_fc26_players import needs_fc26_reimport

        if needs_fc26_reimport():
            DataSyncService().ensure_fc26_squads()
        logger.info("Background startup seed finished")
    except Exception as exc:
        logger.warning("Startup seed failed: %s", exc)


def _delayed_scheduler_start() -> None:
    """Start cron jobs after deploy health check passes."""
    import time as _time

    _time.sleep(30)
    if ENABLE_SCHEDULER:
        from src.observability.request_metrics import prune_old_metrics

        prune_old_metrics()
        start_scheduler()
        logger.info("Background scheduler enabled (delayed start)")


class TimingAndCacheMiddleware(BaseHTTPMiddleware):
    """Response timing headers, cache detection, and persisted API metrics."""

    CACHE_PATHS = (
        "/home",
        "/matches",
        "/teams",
        "/tournament/",
        "/players/",
        "/meta/freshness",
        "/monitor/status",
    )

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        set_request_path(path)
        t0 = time.perf_counter()
        cache_hit = False
        if request.method == "GET":
            key = cache_key(path, str(request.url.query))
            cache_hit = get_cached(key) is not None

        response = await call_next(request)
        handler_ms = (time.perf_counter() - t0) * 1000

        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        serialization_ms = (time.perf_counter() - t0) * 1000 - handler_ms
        total_ms = (time.perf_counter() - t0) * 1000
        db_ms = get_db_ms()

        response = Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

        response.headers["X-Response-Time-ms"] = str(round(total_ms, 1))
        response.headers["X-DB-Time-ms"] = str(round(db_ms, 1))
        meta = get_cache_meta()
        if meta.get("data_version"):
            response.headers["X-Data-Version"] = meta["data_version"]
        if meta.get("last_prediction_update"):
            response.headers["X-Last-Prediction-Update"] = meta["last_prediction_update"]

        if request.method == "GET":
            response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
            if any(path.startswith(p) for p in self.CACHE_PATHS):
                ttl = _ttl_for_path(path)
                if ttl:
                    response.headers["Cache-Control"] = f"public, max-age={min(ttl, 120)}"

        record_api_metric(
            method=request.method,
            path=path,
            status_code=response.status_code,
            total_ms=total_ms,
            db_ms=db_ms,
            serialization_ms=max(serialization_ms, 0),
            cache_hit=cache_hit,
            payload_bytes=len(body),
        )

        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_models_on_startup()
    # Bind $PORT before migrations — init_db can deadlock with the previous deploy.
    threading.Thread(target=_background_startup, daemon=True).start()
    if ENABLE_SCHEDULER:
        threading.Thread(target=_delayed_scheduler_start, daemon=True).start()
    yield
    stop_scheduler()
    db.close_postgres_pool()


app = FastAPI(
    title="WC 2026 Research API",
    description="Designed by Amit Tavor. Research recommendation system.",
    version="2.2.0",
    lifespan=lifespan,
)

app.add_middleware(TimingAndCacheMiddleware)
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


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    icon = STATIC_DIR / "favicon.svg"
    if not icon.is_file():
        raise HTTPException(status_code=404, detail="Favicon not found")
    return FileResponse(icon, media_type="image/svg+xml")


@app.get("/")
def web_app() -> HTMLResponse:
    """Serve index.html with cache-busted static asset URLs after each deploy."""
    index = WEB_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Web UI not found")
    version = config.GIT_COMMIT or "local"
    html = index.read_text(encoding="utf-8").replace("__ASSET_VERSION__", version)
    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )
