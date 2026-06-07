"""Persist squad/player records from API-Football."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from src import config, db
from src import db_extended as dbx
from src.api_client import APIClient

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_squad_player(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a players endpoint response item."""
    player = item.get("player") or item
    stats_list = item.get("statistics") or []
    stats = stats_list[0] if stats_list else {}
    games = stats.get("games") or {}
    goals = stats.get("goals") or {}

    return {
        "api_player_id": player.get("id"),
        "name": player.get("name", "Unknown"),
        "position": games.get("position") or player.get("position"),
        "rating": _safe_float(games.get("rating")),
        "caps": games.get("appearences") or games.get("appearances"),
        "club": (stats.get("team") or {}).get("name"),
    }


def sync_squads(
    client: Optional[APIClient] = None,
    season: Optional[int] = None,
) -> dict[str, Any]:
    """Fetch squad data for teams in upcoming matches and persist to players table."""
    client = client or APIClient()
    season = season if season is not None else config.SEASON

    db.init_db()
    upcoming = db.get_upcoming_matches(limit=100)
    team_map: dict[int, str] = {}
    for match in upcoming:
        if match["home_team_id"]:
            team_map[int(match["home_team_id"])] = match["home_team"]
        if match["away_team_id"]:
            team_map[int(match["away_team_id"])] = match["away_team"]

    teams_processed = 0
    players_written = 0
    errors = 0

    for api_team_id, team_name in team_map.items():
        try:
            internal_team_id = dbx.upsert_team(team_name, api_team_id=api_team_id)
            raw_players = client.get_players(api_team_id, season=season)
            teams_processed += 1
            for item in raw_players:
                row = _parse_squad_player(item)
                if not row.get("api_player_id"):
                    continue
                dbx.upsert_player(
                    name=row["name"],
                    team_id=internal_team_id,
                    api_player_id=row["api_player_id"],
                    position=row.get("position"),
                    rating=row.get("rating"),
                    caps=row.get("caps"),
                    club=row.get("club"),
                )
                players_written += 1
        except Exception as exc:
            logger.warning("Squad sync failed for team %s (%s): %s", team_name, api_team_id, exc)
            errors += 1

    result = {
        "teams_processed": teams_processed,
        "players_written": players_written,
        "errors": errors,
    }
    dbx.insert_sync_log(
        "sync_squads",
        "ok" if errors == 0 else "partial",
        source="api-football",
        records_affected=players_written,
        finished_at=datetime.utcnow().isoformat(),
    )
    logger.info("Squad sync: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(sync_squads())
