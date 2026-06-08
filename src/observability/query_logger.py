"""Database query duration logging."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from src.observability.request_metrics import add_db_ms, record_slow_query

logger = logging.getLogger(__name__)
SLOW_QUERY_MS = 500


def timed_execute(execute_fn: Callable, conn: Any, sql: str, params: tuple | list = ()) -> Any:
    t0 = time.perf_counter()
    result = execute_fn(sql, params)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    add_db_ms(elapsed_ms)
    label = sql.strip().split()[0:3]
    label_str = " ".join(label)
    if elapsed_ms > SLOW_QUERY_MS:
        logger.warning("Slow query %.0fms: %s", elapsed_ms, label_str)
        record_slow_query(elapsed_ms, sql)
    else:
        logger.debug("Query %.1fms: %s", elapsed_ms, label_str)
    return result
