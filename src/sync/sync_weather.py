"""Open-Meteo weather forecast stub for upcoming matches."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import requests

from src import db
from src import db_extended as dbx

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

VENUE_COORDS: dict[str, tuple[float, float]] = {
    "metlife stadium": (40.8128, -74.0742),
    "sofi stadium": (33.9535, -118.3392),
    "mercedes-benz stadium": (33.7553, -84.4006),
    "hard rock stadium": (25.9580, -80.2389),
    "lumen field": (47.5952, -122.3316),
    "levi's stadium": (37.4030, -121.9697),
    "gillette stadium": (42.0909, -71.2643),
    "lincoln financial field": (39.9008, -75.1675),
    "arrowhead stadium": (39.0489, -94.4839),
    "nrg stadium": (29.6847, -95.4107),
    "at&t stadium": (32.7473, -97.0945),
    "default": (40.7128, -74.0060),
}


def _resolve_coords(venue: Optional[str]) -> tuple[float, float]:
    if not venue:
        return VENUE_COORDS["default"]
    key = venue.lower().strip()
    for name, coords in VENUE_COORDS.items():
        if name in key or key in name:
            return coords
    return VENUE_COORDS["default"]


def fetch_weather_forecast(
    latitude: float,
    longitude: float,
    match_date: str,
) -> dict[str, Any]:
    """
    Fetch hourly weather from Open-Meteo (free, no API key).
    Returns parsed forecast for the match hour or nearest available.
    """
    try:
        match_dt = datetime.fromisoformat(match_date.replace("Z", "+00:00"))
    except ValueError:
        match_dt = datetime.utcnow()

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
        "timezone": "UTC",
        "forecast_days": 7,
    }

    try:
        response = requests.get(OPEN_METEO_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.warning("Open-Meteo request failed: %s", exc)
        return {
            "conditions": "unavailable",
            "forecast_json": {"error": str(exc)},
        }

    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    target = match_dt.strftime("%Y-%m-%dT%H:00")

    idx = 0
    if target in times:
        idx = times.index(target)
    elif times:
        idx = min(len(times) - 1, max(0, len(times) // 2))

    def _at(key: str) -> Any:
        values = hourly.get(key) or []
        return values[idx] if idx < len(values) else None

    weather_code = _at("weather_code")
    return {
        "temp_c": _at("temperature_2m"),
        "humidity_pct": _at("relative_humidity_2m"),
        "wind_kmh": _at("wind_speed_10m"),
        "rain_mm": _at("precipitation"),
        "conditions": _weather_code_label(weather_code),
        "forecast_json": data,
    }


def _weather_code_label(code: Optional[int]) -> str:
    """Map WMO weather code to a short label."""
    if code is None:
        return "unknown"
    if code == 0:
        return "clear"
    if code in (1, 2, 3):
        return "partly_cloudy"
    if code in (45, 48):
        return "fog"
    if code in (51, 53, 55, 56, 57):
        return "drizzle"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "thunderstorm"
    return "other"


def sync_weather(limit: int = 20) -> dict[str, Any]:
    """
    Fetch and persist weather forecasts for upcoming matches (Open-Meteo stub).
    Uses venue name heuristics for coordinates until geocoding is added.
    """
    db.init_db()
    upcoming = db.get_upcoming_matches(limit=limit)
    written = 0
    errors = 0

    for match in upcoming:
        try:
            lat, lon = _resolve_coords(match.get("venue"))
            forecast = fetch_weather_forecast(lat, lon, match.get("date", ""))
            dbx.upsert_weather_forecast(int(match["id"]), forecast)
            written += 1
        except Exception as exc:
            logger.warning(
                "Weather sync failed for match %s: %s", match.get("external_fixture_id"), exc
            )
            errors += 1

    result = {
        "matches_checked": len(upcoming),
        "forecasts_written": written,
        "errors": errors,
    }
    dbx.insert_sync_log(
        "sync_weather",
        "ok" if errors == 0 else "partial",
        source="open-meteo",
        records_affected=written,
        finished_at=datetime.utcnow().isoformat(),
    )
    logger.info("Weather sync: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(sync_weather())
