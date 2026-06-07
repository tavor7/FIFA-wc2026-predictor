"""Database query duration logging."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)
SLOW_QUERY_MS = 500


def timed_execute(execute_fn: Callable, conn: Any, sql: str, params: tuple | list = ()) -> Any:
    t0 = time.perf_counter()
    result = execute_fn(sql, params)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    label = sql.strip().split()[0:3]
    label_str = " ".join(label)
    if elapsed_ms > SLOW_QUERY_MS:
        logger.warning("Slow query %.0fms: %s", elapsed_ms, label_str)
    else:
        logger.debug("Query %.1fms: %s", elapsed_ms, label_str)
    return result
