"""Load bundled seed data when APIs are unavailable or DB is empty."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from src import config, db
from src.db import _execute
from src import db_extended as dbx
from src.analytics.computed_strength import recompute_and_persist
from src.sync_matches import _upsert_fixture
from src.team_flags import get_country_code, slugify
from src.team_names import normalize_team_name

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "seeds"
PLACEHOLDER_KEYS = {"", "your_api_football_key_here", "your_football_data_key_here"}


def api_keys_status() -> dict[str, Any]:
    """Report whether external API keys are configured (not placeholders)."""
    af = config.API_FOOTBALL_KEY not in PLACEHOLDER_KEYS
    fd = config.FOOTBALL_DATA_KEY not in PLACEHOLDER_KEYS
    return {
        "api_football": af,
        "football_data": fd,
        "any_configured": af or fd,
        "database": "postgres" if config.USE_POSTGRES else "sqlite",
    }


def _load_json(name: str) -> Any:
    path = SEED_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Missing seed file: {path}")
    return json.loads(path.read_text())


def _safe_upsert_team(name: str, api_id: Optional[int] = None) -> None:
    try:
        dbx.upsert_team(
            name,
            slug=slugify(name),
            country_code=get_country_code(name),
            api_team_id=api_id,
        )
    except Exception as exc:
        logger.debug("Team upsert failed for %s: %s", name, exc)
        try:
            dbx.upsert_team(
                name,
                slug=slugify(name),
                country_code=get_country_code(name),
            )
        except Exception:
            pass


def _team_group_map(groups: dict[str, list[str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for group_name, teams in groups.items():
        for team in teams:
            out[normalize_team_name(team)] = group_name
    return out


def _upsert_seed_match(row: dict[str, Any], team_groups: dict[str, str]) -> Optional[int]:
    home = normalize_team_name(row["home_team"])
    away = normalize_team_name(row["away_team"])
    fixture = {
        "external_fixture_id": str(row["external_fixture_id"]),
        "date": row["date"],
        "league": row.get("league") or "FIFA World Cup",
        "season": row.get("season") or config.SEASON,
        "home_team": home,
        "away_team": away,
        "home_team_id": row.get("home_team_id"),
        "away_team_id": row.get("away_team_id"),
        "status": row.get("status", "TIMED"),
        "home_goals": row.get("home_goals"),
        "away_goals": row.get("away_goals"),
        "venue": row.get("venue"),
    }
    match_id = _upsert_fixture(fixture)
    if not match_id:
        return None

    group = team_groups.get(home) or team_groups.get(away)
    dbx.update_match_metadata(
        match_id,
        stage="Group Stage" if group else None,
        group_name=group,
        round_name="Group Stage",
    )

    for team_name, api_id in ((home, row.get("home_team_id")), (away, row.get("away_team_id"))):
        _safe_upsert_team(team_name, api_id)
    return match_id


def load_group_standings(season: Optional[int] = None) -> dict[str, Any]:
    """Seed pre-tournament group tables (0 points) from official draw."""
    season = season or config.SEASON
    payload = _load_json("wc2026_groups.json")
    groups = payload.get("groups") or {}
    dbx.clear_standings(season)
    written = 0
    for group_name, teams in groups.items():
        for rank, team in enumerate(teams, start=1):
            name = normalize_team_name(team)
            dbx.upsert_standing(
                group_name=group_name,
                team=name,
                season=season,
                stats={
                    "played": 0,
                    "won": 0,
                    "drawn": 0,
                    "lost": 0,
                    "goals_for": 0,
                    "goals_against": 0,
                    "goal_diff": 0,
                    "points": 0,
                    "rank": rank,
                },
            )
            _safe_upsert_team(name)
            written += 1
    return {"groups": len(groups), "rows_written": written, "season": season}


def load_fixture_seeds(season: Optional[int] = None) -> dict[str, Any]:
    """Load WC 2026 schedule + 2022 results from bundled JSON."""
    season = season or config.SEASON
    groups_payload = _load_json("wc2026_groups.json")
    team_groups = _team_group_map(groups_payload.get("groups") or {})

    wc2026 = _load_json("wc2026_fixtures.json")
    wc2022 = _load_json("wc2022_results.json")

    synced_2026 = 0
    synced_2022 = 0
    for row in wc2026:
        if _upsert_seed_match(row, team_groups):
            synced_2026 += 1
    for row in wc2022:
        if _upsert_seed_match(row, {}):
            synced_2022 += 1

    return {
        "wc2026_fixtures": synced_2026,
        "wc2022_results": synced_2022,
        "season": season,
    }


def table_counts() -> dict[str, int]:
    """Row counts for core tables (for monitor / diagnostics)."""
    tables = [
        "matches",
        "teams",
        "predictions",
        "standings",
        "bracket_nodes",
        "players",
        "player_match_stats",
        "match_events",
        "lineups",
        "injuries",
        "head_to_head",
        "sync_log",
        "tournament_simulations",
        "prediction_history",
    ]
    counts: dict[str, int] = {}
    with db.get_connection() as conn:
        for table in tables:
            try:
                row = _execute(conn, f"SELECT COUNT(*) AS c FROM {table}").fetchone()
                counts[table] = int(dict(row)["c"])
            except Exception:
                counts[table] = -1
    return counts


def _run_seed_job(force: bool = False) -> None:
    """Background-safe seed runner with logging."""
    try:
        if force:
            load_all_seeds(run_predictions=True)
        else:
            ensure_baseline_data(min_matches=10, run_predictions=True)
    except Exception as exc:
        logger.exception("Seed job failed: %s", exc)
        try:
            dbx.insert_sync_log("load_seeds", "error", source="bundled", error_message=str(exc)[:500])
        except Exception:
            pass


def load_standings_only() -> dict[str, Any]:
    """Fast path: group tables + teams only (for quick HTTP response)."""
    db.init_db()
    standings = load_group_standings()
    strength = recompute_and_persist()
    counts = table_counts()
    dbx.insert_sync_log("load_seeds_standings", "ok", source="bundled", records_affected=counts.get("standings", 0))
    return {"standings": standings, "strength": strength, "counts": counts}


def ensure_baseline_data(min_matches: int = 10, run_predictions: bool = False) -> dict[str, Any]:
    """
    Load seeds when the DB is sparse. Safe to call repeatedly (upserts).
    Returns summary; skips fixture load if enough matches already exist.
    """
    db.init_db()
    counts_before = table_counts()
    result: dict[str, Any] = {
        "keys": api_keys_status(),
        "counts_before": counts_before,
        "actions": [],
    }

    match_count = counts_before.get("matches", 0)
    if match_count < min_matches:
        fixtures = load_fixture_seeds()
        result["actions"].append({"load_fixtures": fixtures})
    else:
        result["actions"].append({"load_fixtures": "skipped", "reason": f"{match_count} matches already"})

    if counts_before.get("standings", 0) < 48:
        standings = load_group_standings()
        result["actions"].append({"load_standings": standings})
    else:
        result["actions"].append({"load_standings": "skipped"})

    strength = recompute_and_persist()
    result["strength"] = strength

    if run_predictions:
        from src.predict import generate_predictions

        result["predictions"] = generate_predictions()

    result["counts_after"] = table_counts()
    dbx.insert_sync_log(
        "load_seeds",
        "ok",
        source="bundled",
        records_affected=result["counts_after"].get("matches", 0),
    )
    logger.info("Baseline seed complete: %s", result)
    return result


def load_all_seeds(run_predictions: bool = True) -> dict[str, Any]:
    """Force-load all bundled seeds and refresh strength + predictions."""
    db.init_db()
    result: dict[str, Any] = {
        "keys": api_keys_status(),
        "fixtures": load_fixture_seeds(),
        "standings": load_group_standings(),
    }
    result["strength"] = recompute_and_persist()
    if run_predictions:
        from src.predict import generate_predictions

        result["predictions"] = generate_predictions()
    result["counts"] = table_counts()
    dbx.insert_sync_log("load_seeds", "ok", source="bundled", records_affected=result["counts"].get("matches", 0))
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(load_all_seeds(), indent=2, default=str))
