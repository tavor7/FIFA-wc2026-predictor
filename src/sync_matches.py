"""Sync upcoming and recent matches from APIs into SQLite."""

from __future__ import annotations

import logging
from typing import Any

from src import db
from src.api_client import APIClient

logger = logging.getLogger(__name__)


def _upsert_fixture(fixture: dict[str, Any]) -> int | None:
    """Upsert a single normalized fixture; return match id or None on failure."""
    try:
        ext_id = fixture.get("external_fixture_id")
        if not ext_id:
            return None
        season = fixture.get("season")
        if isinstance(season, str) and season.isdigit():
            season = int(season)
        elif not isinstance(season, int):
            season = None

        return db.upsert_match(
            external_fixture_id=str(ext_id),
            date=fixture.get("date", ""),
            league=fixture.get("league", ""),
            season=season or 0,
            home_team=fixture.get("home_team", "Unknown"),
            away_team=fixture.get("away_team", "Unknown"),
            status=fixture.get("status", "NS"),
            home_goals=fixture.get("home_goals"),
            away_goals=fixture.get("away_goals"),
            venue=fixture.get("venue"),
            home_team_id=fixture.get("home_team_id"),
            away_team_id=fixture.get("away_team_id"),
        )
    except Exception as exc:
        logger.error("Failed to upsert fixture %s: %s", fixture.get("external_fixture_id"), exc)
        return None


def sync_upcoming_matches(client: APIClient | None = None, days_ahead: int = 14) -> dict[str, int]:
    """Fetch and store upcoming fixtures."""
    client = client or APIClient()
    db.init_db()
    fixtures = client.get_upcoming_matches(days_ahead=days_ahead)
    synced = 0
    for fixture in fixtures:
        if _upsert_fixture(fixture) is not None:
            synced += 1
    logger.info("Synced %d/%d upcoming matches", synced, len(fixtures))
    result: dict[str, Any] = {"fetched": len(fixtures), "synced": synced}
    if client.last_warning and not fixtures:
        result["warning"] = client.last_warning
    return result


def sync_recent_matches(client: APIClient | None = None, days_back: int = 14) -> dict[str, int]:
    """Fetch and store recently finished fixtures."""
    client = client or APIClient()
    db.init_db()
    fixtures = client.get_recent_matches(days_back=days_back)
    synced = 0
    for fixture in fixtures:
        if _upsert_fixture(fixture) is not None:
            synced += 1
    logger.info("Synced %d/%d recent matches", synced, len(fixtures))
    result: dict[str, Any] = {"fetched": len(fixtures), "synced": synced}
    if client.last_warning and not fixtures:
        result["warning"] = client.last_warning
    return result


def sync_all_matches(
    client: APIClient | None = None,
    days_ahead: int = 14,
    days_back: int = 14,
) -> dict[str, Any]:
    """Sync both upcoming and recent matches."""
    client = client or APIClient()
    upcoming = sync_upcoming_matches(client, days_ahead)
    recent = sync_recent_matches(client, days_back)
    return {"upcoming": upcoming, "recent": recent}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = sync_all_matches()
    print(result)
