"""Sync historical World Cup data for data-driven team strength ratings."""

from __future__ import annotations

import logging
from typing import Any

from src import config, db
from src.analytics.computed_strength import recompute_and_persist
from src.api_client import APIClient, APIError
from src.sync_matches import _upsert_fixture

logger = logging.getLogger(__name__)

# Past World Cup seasons used to build empirical strength (not guesses).
HISTORICAL_SEASONS = (2014, 2018, 2022)


def _sync_api_football_season(client: APIClient, season: int) -> int:
    synced = 0
    try:
        data = client._api_football_request(
            "fixtures",
            {"league": config.LEAGUE_ID, "season": season, "timezone": "UTC"},
        )
        for raw in data.get("response", []):
            fixture = client._normalize_fixture(raw)
            if fixture.get("status") not in ("FT", "AET", "PEN", "FINISHED"):
                continue
            if fixture.get("home_goals") is None or fixture.get("away_goals") is None:
                continue
            if _upsert_fixture(fixture) is not None:
                synced += 1
    except Exception as exc:
        logger.warning("API-Football historical sync failed for %s: %s", season, exc)
    return synced


def _sync_football_data_season(client: APIClient, season: int) -> int:
    """Pull finished WC matches from football-data.org (free tier)."""
    synced = 0
    try:
        data = client._football_data_request(
            f"competitions/{config.FOOTBALL_DATA_COMPETITION_ID}/matches",
            {"season": season},
        )
        for raw in data.get("matches", []):
            if raw.get("status") != "FINISHED":
                continue
            score = raw.get("score") or {}
            ft = score.get("fullTime") or {}
            if ft.get("home") is None or ft.get("away") is None:
                continue
            fixture = client._normalize_fixture(raw, "football-data")
            if _upsert_fixture(fixture) is not None:
                synced += 1
    except APIError as exc:
        logger.warning("football-data historical sync failed for %s: %s", season, exc)
    except Exception as exc:
        logger.warning("football-data historical sync error for %s: %s", season, exc)
    return synced


def sync_historical_seasons(
    client: APIClient | None = None,
    seasons: tuple[int, ...] = HISTORICAL_SEASONS,
) -> dict[str, Any]:
    """
    Fetch finished World Cup fixtures (2018 + 2022) and recompute team strength from results.
    Uses API-Football when available, always attempts football-data.org fallback.
    """
    client = client or APIClient()
    db.init_db()

    from src.seed.historical_loader import load_historical_seeds

    seed_result = load_historical_seeds()
    total_synced = seed_result.get("matches", 0)
    by_season: dict[int, dict[str, int]] = {}

    for season in seasons:
        af = _sync_api_football_season(client, season)
        fd = _sync_football_data_season(client, season)
        by_season[season] = {"api_football": af, "football_data": fd}
        total_synced += af + fd
        logger.info(
            "Historical season %s: api-football=%d, football-data=%d",
            season, af, fd,
        )

    strength = recompute_and_persist()
    return {
        "seeds": seed_result,
        "seasons": by_season,
        "total_synced": total_synced,
        "strength": strength,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(sync_historical_seasons())
