"""In-memory TTL response cache for screen endpoints."""

from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, Optional

_CACHE: dict[str, tuple[float, Any]] = {}

TTL_SECONDS: dict[str, int] = {
    "/home": 90,
    "/matches": 90,
    "/matches/live": 30,
    "/teams": 420,
    "/monitor/status": 15,
    "/admin/pipeline/status": 15,
    "/admin/pipeline/progress": 5,
}

_data_version: str = ""
_last_prediction_update: str = ""


def set_cache_meta(data_version: str = "", last_prediction_update: str = "") -> None:
    global _data_version, _last_prediction_update
    if data_version:
        _data_version = data_version
    if last_prediction_update:
        _last_prediction_update = last_prediction_update


def get_cache_meta() -> dict[str, str]:
    return {
        "data_version": _data_version,
        "last_prediction_update": _last_prediction_update,
    }


def _ttl_for_path(path: str) -> int:
    for prefix, ttl in TTL_SECONDS.items():
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?"):
            return ttl
    if path.startswith("/teams/"):
        return 2700
    return 0


def cache_key(path: str, query: str = "") -> str:
    return f"{path}?{query}" if query else path


def get_cached(key: str) -> Optional[Any]:
    entry = _CACHE.get(key)
    if not entry:
        return None
    expires, value = entry
    if time.time() > expires:
        del _CACHE[key]
        return None
    return value


def set_cached(key: str, value: Any, ttl: int) -> None:
    _CACHE[key] = (time.time() + ttl, value)


def invalidate_prefix(prefix: str) -> None:
    to_del = [k for k in _CACHE if k.startswith(prefix)]
    for k in to_del:
        del _CACHE[k]


def invalidate_all() -> None:
    _CACHE.clear()


def cached_endpoint(path_prefix: str):
    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        wrapper._cache_prefix = path_prefix
        return wrapper
    return decorator
