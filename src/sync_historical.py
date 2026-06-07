"""Sync historical World Cup data for team profiles."""

from __future__ import annotations

import logging
from typing import Any

from src import db
from src.api_client import APIClient
from src.sync_matches import _upsert_fixture

logger = logging.getLogger(__name__)

HISTORICAL_SEASONS = (2022,)


def sync_historical_seasons(
    client: APIClient | None = None,
    seasons: tuple[int, ...] = HISTORICAL_SEASONS,
) -> dict[str, Any]:
    """
    Fetch finished World Cup fixtures from past seasons.
    Used to build team form when 2026 data is not yet available.
    """
    client = client or APIClient()
    db.init_db()
    total_synced = 0
    by_season: dict[int, int] = {}

    for season in seasons:
        synced = 0
        try:
            data = client._api_football_request(
                "fixtures",
                {"league": 1, "season": season, "timezone": "UTC"},
            )
            for raw in data.get("response", []):
                fixture = client._normalize_fixture(raw)
                if fixture.get("status") not in ("FT", "AET", "PEN", "FINISHED"):
                    continue
                if _upsert_fixture(fixture) is not None:
                    synced += 1
        except Exception as exc:
            logger.warning("Historical sync failed for season %s: %s", season, exc)
        by_season[season] = synced
        total_synced += synced
        logger.info("Synced %d historical fixtures for season %s", synced, season)

    return {"seasons": by_season, "total_synced": total_synced}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(sync_historical_seasons())
