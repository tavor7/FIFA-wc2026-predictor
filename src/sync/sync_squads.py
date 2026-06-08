"""Persist squad/player records from API-Football."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Optional

from src import config, db
from src import db_extended as dbx
from src.api_client import APIClient
from src.tournament_teams import is_wc2026_team

logger = logging.getLogger(__name__)


def full_squad_size() -> int:
    return config.FC26_SQUAD_SIZE


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
    """API team id → name for WC nations (tournament table first, matches as fallback)."""
    team_map: dict[int, str] = {}

    for row in dbx.get_tournament_teams():
        d = dict(row)
        api_id = d.get("api_team_id")
        if api_id:
            team_map[int(api_id)] = d["name"]

    if len(team_map) >= 40:
        return team_map

    for match in db.get_upcoming_matches(limit=120, tournament_only=True):
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
    thin_teams_only: bool = False,
    should_cancel: Optional[Callable[[], bool]] = None,
    max_teams: Optional[int] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> dict[str, Any]:
    """Fetch squad data for WC 2026 teams and fill gaps where Kaggle FC26 data is thin."""
    from src.services.pipeline_cancel import PipelineCancelled

    client = client or APIClient()
    season = season if season is not None else config.SEASON

    db.init_db()
    team_map = _tournament_team_api_map()
    target = full_squad_size()
    fc26_counts = dbx.fc26_per_team_counts()

    work: list[tuple[int, str, int]] = []
    teams_skipped = 0
    for api_team_id, team_name in team_map.items():
        internal_team_id = dbx.upsert_team(team_name, api_team_id=api_team_id)
        fc26_count = fc26_counts.get(internal_team_id, 0)
        if thin_teams_only or fill_thin_squads:
            if fc26_count >= target:
                teams_skipped += 1
                continue
        elif fc26_count >= min(15, target):
            teams_skipped += 1
            continue
        work.append((api_team_id, team_name, internal_team_id))

    if max_teams is not None and len(work) > max_teams:
        work = work[:max_teams]

    teams_processed = 0
    players_written = 0
    errors = 0
    total = len(work)

    if progress_callback:
        if total == 0:
            progress_callback(100, "All squads already loaded")
        else:
            progress_callback(15, f"API squad sync for {total} team(s)…")

    for i, (api_team_id, team_name, internal_team_id) in enumerate(work):
        if should_cancel and should_cancel():
            raise PipelineCancelled()
        if progress_callback and total:
            pct = 15 + round((i / total) * 80, 1)
            progress_callback(pct, f"Squad sync {i + 1}/{total}: {team_name}")
        try:
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

    if progress_callback:
        progress_callback(100, f"Squad sync done ({teams_processed} teams)")

    result = {
        "teams_processed": teams_processed,
        "teams_skipped_full_fc26": teams_skipped,
        "teams_deferred": max(0, len(team_map) - teams_skipped - teams_processed - errors),
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
