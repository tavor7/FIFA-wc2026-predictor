"""Persist squad/player records from API-Football."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from src import config, db
from src import db_extended as dbx
from src.api_client import APIClient
from src.tournament_teams import is_wc2026_team

logger = logging.getLogger(__name__)

FULL_SQUAD_SIZE = 26


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_squad_player(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a players endpoint response item."""
    player = item.get("player") or item
    stats_list = item.get("statistics") or []
    stats = stats_list[0] if stats_list else {}
    games = stats.get("games") or {}

    return {
        "api_player_id": player.get("id"),
        "name": player.get("name", "Unknown"),
        "position": games.get("position") or player.get("position"),
        "rating": _safe_float(games.get("rating")),
        "age": _safe_int(player.get("age")),
        "caps": games.get("appearences") or games.get("appearances"),
        "club": (stats.get("team") or {}).get("name"),
    }


def _tournament_team_api_map() -> dict[int, str]:
    """API team id → name for all 48 WC nations we can resolve."""
    team_map: dict[int, str] = {}

    for row in dbx.get_tournament_teams():
        d = dict(row)
        api_id = d.get("api_team_id")
        if api_id:
            team_map[int(api_id)] = d["name"]

    for match in db.get_upcoming_matches(limit=500, tournament_only=True):
        for side in ("home", "away"):
            api_id = match.get(f"{side}_team_id")
            name = match[f"{side}_team"]
            if not api_id or not is_wc2026_team(name):
                continue
            api_id = int(api_id)
            team_map[api_id] = name
            dbx.upsert_team(name, api_team_id=api_id)

    return team_map


def sync_squads(
    client: Optional[APIClient] = None,
    season: Optional[int] = None,
    *,
    fill_thin_squads: bool = False,
) -> dict[str, Any]:
    """Fetch squad data for WC 2026 teams and fill gaps where Kaggle FC26 data is thin."""
    client = client or APIClient()
    season = season if season is not None else config.SEASON

    db.init_db()
    team_map = _tournament_team_api_map()

    teams_processed = 0
    players_written = 0
    teams_skipped = 0
    errors = 0

    for api_team_id, team_name in team_map.items():
        try:
            internal_team_id = dbx.upsert_team(team_name, api_team_id=api_team_id)
            fc26_count = dbx.count_fc26_players_for_team(internal_team_id)
            if fc26_count >= FULL_SQUAD_SIZE:
                teams_skipped += 1
                continue
            if not fill_thin_squads and fc26_count >= 15:
                teams_skipped += 1
                continue
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
                    age=row.get("age"),
                    caps=row.get("caps"),
                    club=row.get("club"),
                )
                players_written += 1
        except Exception as exc:
            logger.warning("Squad sync failed for team %s (%s): %s", team_name, api_team_id, exc)
            errors += 1

    result = {
        "teams_processed": teams_processed,
        "teams_skipped_full_fc26": teams_skipped,
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
