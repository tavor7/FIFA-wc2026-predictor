"""Sync player statistics for teams in upcoming matches."""

from __future__ import annotations

import logging
from typing import Any

from src import db
from src.api_client import APIClient

logger = logging.getLogger(__name__)


def sync_players_for_upcoming(client: APIClient | None = None) -> dict[str, Any]:
    """
    Fetch squad data for teams in upcoming matches.
    Player stats are used indirectly via lineup strength calculations.
    """
    client = client or APIClient()
    db.init_db()

    upcoming = db.get_upcoming_matches(limit=100)
    team_ids: set[int] = set()
    for match in upcoming:
        if match["home_team_id"]:
            team_ids.add(int(match["home_team_id"]))
        if match["away_team_id"]:
            team_ids.add(int(match["away_team_id"]))

    fetched_teams = 0
    total_players = 0
    for tid in team_ids:
        try:
            players = client.get_players(tid)
            fetched_teams += 1
            total_players += len(players)
        except Exception as exc:
            logger.warning("Player sync failed for team %s: %s", tid, exc)

    return {
        "teams_processed": fetched_teams,
        "player_records": total_players,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(sync_players_for_upcoming())
