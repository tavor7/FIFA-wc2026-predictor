"""Sync tournament standings into the database."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from src import config, db
from src import db_extended as dbx
from src.api_client import APIClient

logger = logging.getLogger(__name__)


def sync_standings(
    client: Optional[APIClient] = None,
    league: Optional[int] = None,
    season: Optional[int] = None,
) -> dict[str, Any]:
    """Fetch standings from API-Football and persist group tables."""
    client = client or APIClient()
    league = league if league is not None else config.LEAGUE_ID
    season = season if season is not None else config.SEASON

    db.init_db()
    dbx.clear_standings(season)

    raw = client.get_standings(league, season)
    rows = client.parse_standings(raw)
    written = 0
    errors = 0

    for row in rows:
        try:
            group_name = row.get("group_name") or "Overall"
            stats = {
                "played": row.get("played") or 0,
                "won": row.get("win") or 0,
                "drawn": row.get("draw") or 0,
                "lost": row.get("loss") or 0,
                "goals_for": row.get("goals_for") or 0,
                "goals_against": row.get("goals_against") or 0,
                "goal_diff": row.get("goal_diff") or 0,
                "points": row.get("points") or 0,
                "rank": row.get("rank"),
            }
            dbx.upsert_standing(
                group_name=group_name,
                team=row.get("team_name", "Unknown"),
                season=season,
                stats=stats,
                team_id=row.get("team_id"),
            )
            written += 1
        except Exception as exc:
            logger.error("Failed to upsert standing for team %s: %s", row.get("team_name"), exc)
            errors += 1

    result = {
        "league": league,
        "season": season,
        "fetched_groups": len(raw),
        "rows_written": written,
        "errors": errors,
    }
    if not rows and client.last_warning:
        result["warning"] = client.last_warning

    dbx.insert_sync_log(
        "sync_standings",
        "ok" if errors == 0 else "partial",
        source="api-football",
        records_affected=written,
        finished_at=datetime.utcnow().isoformat(),
    )
    logger.info("Standings sync: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(sync_standings())
