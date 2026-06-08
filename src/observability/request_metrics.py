"""Request-scoped timing and persisted API performance metrics."""

from __future__ import annotations

import contextvars
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Iterator, Optional

from src import db
from src.db import _execute, get_connection

logger = logging.getLogger(__name__)

PERSIST_OBSERVABILITY = os.getenv("PERSIST_OBSERVABILITY", "false").lower() in ("1", "true", "yes")

SLOW_API_MS = 1000
METRICS_RETENTION_DAYS = 7
MAX_METRICS_ROWS = 10000

_request_path: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_path", default=None
)
_db_ms_accum: contextvars.ContextVar[float] = contextvars.ContextVar("db_ms_accum", default=0.0)


def set_request_path(path: str) -> None:
    _request_path.set(path)
    _db_ms_accum.set(0.0)


def get_request_path() -> Optional[str]:
    return _request_path.get()


def add_db_ms(ms: float) -> None:
    _db_ms_accum.set(_db_ms_accum.get() + ms)


def get_db_ms() -> float:
    return _db_ms_accum.get()


def record_api_metric(
    *,
    method: str,
    path: str,
    status_code: int,
    total_ms: float,
    db_ms: float,
    serialization_ms: float,
    cache_hit: bool,
    payload_bytes: int,
) -> None:
    if not PERSIST_OBSERVABILITY:
        return
    slow = 1 if total_ms >= SLOW_API_MS else 0
    now = datetime.utcnow().isoformat()
    try:
        with get_connection() as conn:
            _execute(
                conn,
                """
                INSERT INTO api_request_metrics (
                    recorded_at, method, path, status_code, total_ms, db_ms,
                    serialization_ms, cache_hit, payload_bytes, slow
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now, method, path, status_code, round(total_ms, 2),
                    round(db_ms, 2), round(serialization_ms, 2),
                    1 if cache_hit else 0, payload_bytes, slow,
                ),
            )
    except Exception as exc:
        logger.debug("Failed to record API metric: %s", exc)


def record_slow_query(duration_ms: float, sql: str) -> None:
    if not PERSIST_OBSERVABILITY:
        return
    fingerprint = " ".join(sql.strip().split()[:6])
    path = get_request_path() or ""
    now = datetime.utcnow().isoformat()
    try:
        with get_connection() as conn:
            _execute(
                conn,
                """
                INSERT INTO slow_query_log (recorded_at, duration_ms, sql_fingerprint, request_path)
                VALUES (?, ?, ?, ?)
                """,
                (now, round(duration_ms, 2), fingerprint, path),
            )
    except Exception as exc:
        logger.debug("Failed to record slow query: %s", exc)


def prune_old_metrics() -> None:
    cutoff = (datetime.utcnow() - timedelta(days=METRICS_RETENTION_DAYS)).isoformat()
    try:
        with get_connection() as conn:
            _execute(
                conn,
                "DELETE FROM api_request_metrics WHERE recorded_at < ?",
                (cutoff,),
            )
            _execute(
                conn,
                "DELETE FROM slow_query_log WHERE recorded_at < ?",
                (cutoff,),
            )
            row = _execute(conn, "SELECT COUNT(*) AS c FROM api_request_metrics").fetchone()
            count = int(dict(row)["c"])
            if count > MAX_METRICS_ROWS:
                excess = count - MAX_METRICS_ROWS
                _execute(
                    conn,
                    """
                    DELETE FROM api_request_metrics WHERE id IN (
                        SELECT id FROM api_request_metrics ORDER BY recorded_at ASC LIMIT ?
                    )
                    """,
                    (excess,),
                )
    except Exception as exc:
        logger.debug("Metrics prune failed: %s", exc)


def get_performance_summary() -> dict[str, Any]:
    """Aggregate API and query performance for the audit dashboard."""
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    with get_connection() as conn:
        endpoints = _execute(
            conn,
            """
            SELECT path,
                   COUNT(*) AS requests,
                   ROUND(AVG(total_ms), 1) AS avg_ms,
                   ROUND(MAX(total_ms), 1) AS max_ms,
                   SUM(cache_hit) AS cache_hits,
                   SUM(slow) AS slow_count
            FROM api_request_metrics
            WHERE recorded_at >= ?
            GROUP BY path
            ORDER BY avg_ms DESC
            LIMIT 20
            """,
            (cutoff,),
        ).fetchall()

        totals = _execute(
            conn,
            """
            SELECT COUNT(*) AS total_requests,
                   ROUND(AVG(total_ms), 1) AS avg_total_ms,
                   ROUND(AVG(db_ms), 1) AS avg_db_ms,
                   SUM(cache_hit) AS cache_hits
            FROM api_request_metrics
            """,
        ).fetchone()

        slow_queries = _execute(
            conn,
            """
            SELECT sql_fingerprint, COUNT(*) AS hits,
                   ROUND(AVG(duration_ms), 1) AS avg_ms,
                   ROUND(MAX(duration_ms), 1) AS max_ms
            FROM slow_query_log
            GROUP BY sql_fingerprint
            ORDER BY max_ms DESC
            LIMIT 15
            """,
        ).fetchall()

    t = dict(totals) if totals else {}
    total_req = int(t.get("total_requests") or 0)
    cache_hits = int(t.get("cache_hits") or 0)
    return {
        "total_requests": total_req,
        "avg_total_ms": float(t.get("avg_total_ms") or 0),
        "avg_db_ms": float(t.get("avg_db_ms") or 0),
        "cache_hit_ratio": round(cache_hits / max(total_req, 1) * 100, 1),
        "slowest_endpoints": [dict(r) for r in endpoints],
        "slowest_queries": [dict(r) for r in slow_queries],
        "slow_api_threshold_ms": SLOW_API_MS,
        "slow_query_threshold_ms": 500,
    }
