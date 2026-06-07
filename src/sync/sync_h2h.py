"""Cache head-to-head fixture history between team pairs."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from src import db
from src import db_extended as dbx
from src.api_client import APIClient

logger = logging.getLogger(__name__)


def _summarize_h2h(
    team1_id: int,
    team2_id: int,
    fixtures: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return summary stats from raw API fixtures for team1 vs team2."""
    team1_wins = draws = team2_wins = 0
    team1_goals = team2_goals = 0
    for item in fixtures:
        teams = item.get("teams") or {}
        goals = item.get("goals") or {}
        home_id = (teams.get("home") or {}).get("id")
        away_id = (teams.get("away") or {}).get("id")
        hg, ag = goals.get("home"), goals.get("away")
        if hg is None or ag is None:
            continue
        if home_id == team1_id:
            team1_goals += int(hg)
            team2_goals += int(ag)
        elif away_id == team1_id:
            team1_goals += int(ag)
            team2_goals += int(hg)
        if hg == ag:
            draws += 1
        elif (home_id == team1_id and hg > ag) or (away_id == team1_id and ag > hg):
            team1_wins += 1
        else:
            team2_wins += 1
    return {
        "matches_played": len(fixtures),
        "team_a_wins": team1_wins,
        "team_b_wins": team2_wins,
        "draws": draws,
        "team_a_goals": team1_goals,
        "team_b_goals": team2_goals,
        "summary_json": fixtures,
    }


def sync_h2h_for_pair(
    client: APIClient,
    team1_name: str,
    team2_name: str,
    team1_id: int,
    team2_id: int,
) -> dict[str, Any]:
    """Fetch and cache head-to-head for a single team pair."""
    fixtures = client.get_head_to_head(team1_id, team2_id)
    stats = _summarize_h2h(team1_id, team2_id, fixtures)
    dbx.upsert_head_to_head(
        team1_name,
        team2_name,
        stats,
        team_a_id=team1_id,
        team_b_id=team2_id,
    )
    return {"team1": team1_name, "team2": team2_name, **stats}


def sync_h2h(
    client: Optional[APIClient] = None,
    limit_pairs: int = 50,
) -> dict[str, Any]:
    """Cache head-to-head records for upcoming match team pairs."""
    client = client or APIClient()
    db.init_db()

    upcoming = db.get_upcoming_matches(limit=limit_pairs)
    pairs: dict[tuple[str, str], tuple[str, str, int, int]] = {}
    for match in upcoming:
        h_name, a_name = match["home_team"], match["away_team"]
        h_id, a_id = match.get("home_team_id"), match.get("away_team_id")
        if h_id and a_id:
            key = tuple(sorted((h_name, a_name)))
            if key not in pairs:
                id_by_name = {h_name: int(h_id), a_name: int(a_id)}
                pairs[key] = (key[0], key[1], id_by_name[key[0]], id_by_name[key[1]])

    synced = 0
    skipped = 0
    errors = 0

    for (t1_name, t2_name, t1_id, t2_id) in pairs.values():
        existing = dbx.get_head_to_head(t1_name, t2_name)
        if existing:
            skipped += 1
            continue
        try:
            sync_h2h_for_pair(client, t1_name, t2_name, t1_id, t2_id)
            synced += 1
        except Exception as exc:
            logger.warning("H2H sync failed for %s vs %s: %s", t1_name, t2_name, exc)
            errors += 1

    result = {
        "pairs_found": len(pairs),
        "synced": synced,
        "skipped_cached": skipped,
        "errors": errors,
    }
    dbx.insert_sync_log(
        "sync_h2h",
        "ok" if errors == 0 else "partial",
        source="api-football",
        records_affected=synced,
        finished_at=datetime.utcnow().isoformat(),
    )
    logger.info("H2H sync: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(sync_h2h())
