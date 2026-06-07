"""Sync injury data from API-Football into SQLite."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src import db
from src.api_client import APIClient

logger = logging.getLogger(__name__)


def sync_injuries(
    client: APIClient | None = None,
    team_id: Optional[int] = None,
    fixture_id: Optional[int] = None,
) -> dict[str, Any]:
    """Fetch and upsert current injury records."""
    client = client or APIClient()
    db.init_db()

    raw = client.get_injuries(team_id=team_id, fixture_id=fixture_id)
    records = client.parse_injuries(raw)
    synced = 0

    for rec in records:
        try:
            db.upsert_injury(
                player_id=rec.get("player_id"),
                player_name=rec.get("player_name", "Unknown"),
                team=rec.get("team", "Unknown"),
                injury_type=rec.get("injury_type"),
                reason=rec.get("reason"),
                expected_return=rec.get("expected_return"),
            )
            synced += 1
        except Exception as exc:
            logger.error("Failed to upsert injury for %s: %s", rec.get("player_name"), exc)

    logger.info("Synced %d/%d injury records", synced, len(records))
    return {"fetched": len(records), "synced": synced}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(sync_injuries())
