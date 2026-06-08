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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src import db
from src.api.routes import router
from src.cache.response_cache import cache_key, get_cache_meta, get_cached, set_cached, _ttl_for_path
from src.model_storage import load_models_on_startup, save_models_after_train
from src.scheduler import start_scheduler, stop_scheduler
from src.seed.load_seeds import ensure_baseline_data

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_DIR / "static"
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "true").lower() in ("1", "true", "yes")
STARTUP_SEED = os.getenv("STARTUP_SEED", "true").lower() in ("1", "true", "yes")


def _startup_seed_worker() -> None:
    """Run after the server is listening — avoids Render deploy port-timeout."""
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
        start_scheduler()
        logger.info("Background scheduler enabled (delayed start)")


class TimingAndCacheMiddleware(BaseHTTPMiddleware):
    """Response timing headers + HTTP cache-control for read endpoints."""

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
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        response.headers["X-Response-Time-ms"] = str(elapsed_ms)
        meta = get_cache_meta()
        if meta.get("data_version"):
            response.headers["X-Data-Version"] = meta["data_version"]
        if meta.get("last_prediction_update"):
            response.headers["X-Last-Prediction-Update"] = meta["last_prediction_update"]

        if request.method == "GET":
            key = cache_key(request.url.path, str(request.url.query))
            response.headers["X-Cache"] = "HIT" if get_cached(key) is not None else "MISS"
            if any(request.url.path.startswith(p) for p in self.CACHE_PATHS):
                ttl = _ttl_for_path(request.url.path)
                if ttl:
                    response.headers["Cache-Control"] = f"public, max-age={min(ttl, 120)}"

        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    load_models_on_startup()
    if STARTUP_SEED:
        threading.Thread(target=_startup_seed_worker, daemon=True).start()
    if ENABLE_SCHEDULER:
        threading.Thread(target=_delayed_scheduler_start, daemon=True).start()
    yield
    stop_scheduler()
    db.close_postgres_pool()


app = FastAPI(
    title="WC 2026 Research API",
    description="Designed by Amit Tavor. Research recommendation system.",
    version="2.1.0",
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


@app.get("/")
def web_app() -> FileResponse:
    index = WEB_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Web UI not found")
    return FileResponse(index)
