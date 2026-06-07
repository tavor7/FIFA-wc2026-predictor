"""Extended database layer — teams, players, events, standings, sync, features."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from src import config
from src.db import Row, _execute, get_connection


def _now() -> str:
    return datetime.utcnow().isoformat()


def _canonical_h2h(team_a: str, team_b: str) -> tuple[str, str]:
    """Return team pair in stable alphabetical order."""
    if team_a.lower() <= team_b.lower():
        return team_a, team_b
    return team_b, team_a


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


def upsert_team(
    name: str,
    slug: Optional[str] = None,
    country_code: Optional[str] = None,
    api_team_id: Optional[int] = None,
    logo_url: Optional[str] = None,
) -> int:
    now = _now()
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO teams (name, slug, country_code, api_team_id, logo_url, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                slug=COALESCE(excluded.slug, teams.slug),
                country_code=COALESCE(excluded.country_code, teams.country_code),
                api_team_id=COALESCE(excluded.api_team_id, teams.api_team_id),
                logo_url=COALESCE(excluded.logo_url, teams.logo_url),
                last_updated=excluded.last_updated
            """,
            (name, slug, country_code, api_team_id, logo_url, now),
        )
        row = _execute(conn, "SELECT id FROM teams WHERE name = ?", (name,)).fetchone()
        return int(row["id"])


def get_team_by_id(team_id: int) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(conn, "SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()


def get_team_by_slug(slug: str) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(conn, "SELECT * FROM teams WHERE slug = ?", (slug,)).fetchone()


def get_team_by_name(name: str) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(conn, "SELECT * FROM teams WHERE name = ?", (name,)).fetchone()


def get_team_by_api_id(api_team_id: int) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(
            conn, "SELECT * FROM teams WHERE api_team_id = ?", (api_team_id,)
        ).fetchone()


def get_all_teams() -> list[Row]:
    with get_connection() as conn:
        return _execute(conn, "SELECT * FROM teams ORDER BY name").fetchall()


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------


def upsert_player(
    name: str,
    team_id: Optional[int] = None,
    api_player_id: Optional[int] = None,
    position: Optional[str] = None,
    rating: Optional[float] = None,
    form: Optional[float] = None,
    caps: Optional[int] = None,
    club: Optional[str] = None,
) -> int:
    now = _now()
    with get_connection() as conn:
        if api_player_id is not None:
            _execute(
                conn,
                """
                INSERT INTO players (
                    api_player_id, team_id, name, position, rating, form, caps, club, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(api_player_id) DO UPDATE SET
                    team_id=COALESCE(excluded.team_id, players.team_id),
                    name=excluded.name,
                    position=COALESCE(excluded.position, players.position),
                    rating=COALESCE(excluded.rating, players.rating),
                    form=COALESCE(excluded.form, players.form),
                    caps=COALESCE(excluded.caps, players.caps),
                    club=COALESCE(excluded.club, players.club),
                    last_updated=excluded.last_updated
                """,
                (api_player_id, team_id, name, position, rating, form, caps, club, now),
            )
            row = _execute(
                conn, "SELECT id FROM players WHERE api_player_id = ?", (api_player_id,)
            ).fetchone()
        else:
            existing = _execute(
                conn,
                "SELECT id FROM players WHERE name = ? AND team_id IS ?",
                (name, team_id),
            ).fetchone()
            if existing:
                _execute(
                    conn,
                    """
                    UPDATE players SET
                        position=COALESCE(?, position),
                        rating=COALESCE(?, rating),
                        form=COALESCE(?, form),
                        caps=COALESCE(?, caps),
                        club=COALESCE(?, club),
                        last_updated=?
                    WHERE id=?
                    """,
                    (position, rating, form, caps, club, now, existing["id"]),
                )
                row = existing
            else:
                _execute(
                    conn,
                    """
                    INSERT INTO players (
                        api_player_id, team_id, name, position, rating, form, caps, club, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (None, team_id, name, position, rating, form, caps, club, now),
                )
                row = _execute(conn, "SELECT last_insert_rowid() AS id").fetchone()
        return int(row["id"])


def get_players_by_team_id(team_id: int) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            "SELECT * FROM players WHERE team_id = ? ORDER BY rating DESC, name",
            (team_id,),
        ).fetchall()


def get_player_by_api_id(api_player_id: int) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(
            conn, "SELECT * FROM players WHERE api_player_id = ?", (api_player_id,)
        ).fetchone()


def clear_players_for_team(team_id: int) -> None:
    with get_connection() as conn:
        _execute(conn, "DELETE FROM players WHERE team_id = ?", (team_id,))


# ---------------------------------------------------------------------------
# Player match stats
# ---------------------------------------------------------------------------


def upsert_player_match_stat(
    match_id: int,
    team: str,
    player_name: str,
    stats: dict[str, Any],
) -> None:
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO player_match_stats (
                match_id, api_player_id, player_name, team, goals, assists,
                yellow_cards, red_cards, minutes, rating, is_motm
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id, team, player_name) DO UPDATE SET
                api_player_id=COALESCE(excluded.api_player_id, player_match_stats.api_player_id),
                goals=excluded.goals,
                assists=excluded.assists,
                yellow_cards=excluded.yellow_cards,
                red_cards=excluded.red_cards,
                minutes=excluded.minutes,
                rating=excluded.rating,
                is_motm=excluded.is_motm
            """,
            (
                match_id,
                stats.get("api_player_id"),
                player_name,
                team,
                stats.get("goals", 0),
                stats.get("assists", 0),
                stats.get("yellow_cards", 0),
                stats.get("red_cards", 0),
                stats.get("minutes"),
                stats.get("rating"),
                1 if stats.get("is_motm") else 0,
            ),
        )


def get_player_match_stats(match_id: int) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            "SELECT * FROM player_match_stats WHERE match_id = ? ORDER BY team, rating DESC",
            (match_id,),
        ).fetchall()


def clear_player_match_stats(match_id: int) -> None:
    with get_connection() as conn:
        _execute(conn, "DELETE FROM player_match_stats WHERE match_id = ?", (match_id,))


# ---------------------------------------------------------------------------
# Match events
# ---------------------------------------------------------------------------


def upsert_match_event(
    match_id: int,
    minute: Optional[int],
    event_type: str,
    team: Optional[str] = None,
    player_name: Optional[str] = None,
    player_id: Optional[int] = None,
    extra_minute: Optional[int] = None,
    detail: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        if config.USE_POSTGRES:
            _execute(
                conn,
                """
                INSERT INTO match_events (
                    match_id, minute, extra_minute, team, player_name, player_id,
                    event_type, detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (match_id, minute, extra_minute, event_type, player_name, detail)
                DO UPDATE SET
                    team=excluded.team,
                    player_id=excluded.player_id
                """,
                (match_id, minute, extra_minute, team, player_name, player_id, event_type, detail),
            )
        else:
            existing = _execute(
                conn,
                """
                SELECT id FROM match_events
                WHERE match_id=? AND minute IS ? AND extra_minute IS ?
                  AND event_type=? AND player_name IS ? AND detail IS ?
                """,
                (match_id, minute, extra_minute, event_type, player_name, detail),
            ).fetchone()
            if existing:
                _execute(
                    conn,
                    """
                    UPDATE match_events SET team=?, player_id=?
                    WHERE id=?
                    """,
                    (team, player_id, existing["id"]),
                )
            else:
                _execute(
                    conn,
                    """
                    INSERT INTO match_events (
                        match_id, minute, extra_minute, team, player_name, player_id,
                        event_type, detail
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (match_id, minute, extra_minute, team, player_name, player_id, event_type, detail),
                )


def get_match_events(match_id: int) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM match_events
            WHERE match_id = ?
            ORDER BY minute ASC, extra_minute ASC, id ASC
            """,
            (match_id,),
        ).fetchall()


def clear_match_events(match_id: int) -> None:
    with get_connection() as conn:
        _execute(conn, "DELETE FROM match_events WHERE match_id = ?", (match_id,))


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------


def upsert_standing(
    group_name: str,
    team: str,
    season: int,
    stats: dict[str, Any],
    team_id: Optional[int] = None,
) -> None:
    now = _now()
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO standings (
                group_name, team, team_id, season, played, won, drawn, lost,
                goals_for, goals_against, goal_diff, points, rank, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(group_name, team, season) DO UPDATE SET
                team_id=COALESCE(excluded.team_id, standings.team_id),
                played=excluded.played,
                won=excluded.won,
                drawn=excluded.drawn,
                lost=excluded.lost,
                goals_for=excluded.goals_for,
                goals_against=excluded.goals_against,
                goal_diff=excluded.goal_diff,
                points=excluded.points,
                rank=excluded.rank,
                last_updated=excluded.last_updated
            """,
            (
                group_name, team, team_id, season,
                stats.get("played", 0),
                stats.get("won", 0),
                stats.get("drawn", 0),
                stats.get("lost", 0),
                stats.get("goals_for", 0),
                stats.get("goals_against", 0),
                stats.get("goal_diff", 0),
                stats.get("points", 0),
                stats.get("rank"),
                now,
            ),
        )


def get_standings_by_group(group_name: str, season: int) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM standings
            WHERE group_name = ? AND season = ?
            ORDER BY rank ASC, points DESC, goal_diff DESC
            """,
            (group_name, season),
        ).fetchall()


def get_all_standings(season: int) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM standings
            WHERE season = ?
            ORDER BY group_name, rank ASC, points DESC
            """,
            (season,),
        ).fetchall()


def clear_standings(season: int) -> None:
    with get_connection() as conn:
        _execute(conn, "DELETE FROM standings WHERE season = ?", (season,))


# ---------------------------------------------------------------------------
# Bracket
# ---------------------------------------------------------------------------


def upsert_bracket_node(
    stage: str,
    round_name: str,
    slot: int,
    match_id: Optional[int] = None,
    home_team: Optional[str] = None,
    away_team: Optional[str] = None,
    winner_team_id: Optional[int] = None,
    parent_node_id: Optional[int] = None,
) -> int:
    now = _now()
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO bracket_nodes (
                stage, round_name, slot, match_id, home_team, away_team,
                winner_team_id, parent_node_id, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stage, round_name, slot) DO UPDATE SET
                match_id=COALESCE(excluded.match_id, bracket_nodes.match_id),
                home_team=COALESCE(excluded.home_team, bracket_nodes.home_team),
                away_team=COALESCE(excluded.away_team, bracket_nodes.away_team),
                winner_team_id=COALESCE(excluded.winner_team_id, bracket_nodes.winner_team_id),
                parent_node_id=COALESCE(excluded.parent_node_id, bracket_nodes.parent_node_id),
                last_updated=excluded.last_updated
            """,
            (
                stage, round_name, slot, match_id, home_team, away_team,
                winner_team_id, parent_node_id, now,
            ),
        )
        row = _execute(
            conn,
            "SELECT id FROM bracket_nodes WHERE stage = ? AND round_name = ? AND slot = ?",
            (stage, round_name, slot),
        ).fetchone()
        return int(row["id"])


def get_bracket_nodes(stage: Optional[str] = None) -> list[Row]:
    with get_connection() as conn:
        if stage:
            return _execute(
                conn,
                """
                SELECT * FROM bracket_nodes
                WHERE stage = ?
                ORDER BY round_name, slot
                """,
                (stage,),
            ).fetchall()
        return _execute(
            conn, "SELECT * FROM bracket_nodes ORDER BY stage, round_name, slot"
        ).fetchall()


def clear_bracket_nodes(stage: Optional[str] = None) -> None:
    with get_connection() as conn:
        if stage:
            _execute(conn, "DELETE FROM bracket_nodes WHERE stage = ?", (stage,))
        else:
            _execute(conn, "DELETE FROM bracket_nodes")


# ---------------------------------------------------------------------------
# Head to head
# ---------------------------------------------------------------------------


def upsert_head_to_head(
    team_a: str,
    team_b: str,
    stats: dict[str, Any],
    team_a_id: Optional[int] = None,
    team_b_id: Optional[int] = None,
) -> None:
    canon_a, canon_b = _canonical_h2h(team_a, team_b)
    swapped = canon_a != team_a
    now = _now()
    if swapped:
        stats = {
            "matches_played": stats.get("matches_played", 0),
            "team_a_wins": stats.get("team_b_wins", 0),
            "team_b_wins": stats.get("team_a_wins", 0),
            "draws": stats.get("draws", 0),
            "team_a_goals": stats.get("team_b_goals", 0),
            "team_b_goals": stats.get("team_a_goals", 0),
            "summary_json": stats.get("summary_json"),
        }
        team_a_id, team_b_id = team_b_id, team_a_id
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO head_to_head (
                team_a, team_b, team_a_id, team_b_id, matches_played,
                team_a_wins, team_b_wins, draws, team_a_goals, team_b_goals,
                summary_json, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_a, team_b) DO UPDATE SET
                team_a_id=COALESCE(excluded.team_a_id, head_to_head.team_a_id),
                team_b_id=COALESCE(excluded.team_b_id, head_to_head.team_b_id),
                matches_played=excluded.matches_played,
                team_a_wins=excluded.team_a_wins,
                team_b_wins=excluded.team_b_wins,
                draws=excluded.draws,
                team_a_goals=excluded.team_a_goals,
                team_b_goals=excluded.team_b_goals,
                summary_json=excluded.summary_json,
                last_updated=excluded.last_updated
            """,
            (
                canon_a, canon_b, team_a_id, team_b_id,
                stats.get("matches_played", 0),
                stats.get("team_a_wins", 0),
                stats.get("team_b_wins", 0),
                stats.get("draws", 0),
                stats.get("team_a_goals", 0),
                stats.get("team_b_goals", 0),
                json.dumps(stats.get("summary_json")) if stats.get("summary_json") is not None else None,
                now,
            ),
        )


def get_head_to_head(team_a: str, team_b: str) -> Optional[Row]:
    canon_a, canon_b = _canonical_h2h(team_a, team_b)
    with get_connection() as conn:
        return _execute(
            conn,
            "SELECT * FROM head_to_head WHERE team_a = ? AND team_b = ?",
            (canon_a, canon_b),
        ).fetchone()


# ---------------------------------------------------------------------------
# Team history
# ---------------------------------------------------------------------------


def upsert_team_history(
    team: str,
    wc_appearances: int = 0,
    best_finish: Optional[str] = None,
    total_wc_goals: int = 0,
    history_json: Optional[dict[str, Any]] = None,
    team_id: Optional[int] = None,
) -> None:
    now = _now()
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO team_history (
                team, team_id, wc_appearances, best_finish, total_wc_goals,
                history_json, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team) DO UPDATE SET
                team_id=COALESCE(excluded.team_id, team_history.team_id),
                wc_appearances=excluded.wc_appearances,
                best_finish=excluded.best_finish,
                total_wc_goals=excluded.total_wc_goals,
                history_json=excluded.history_json,
                last_updated=excluded.last_updated
            """,
            (
                team, team_id, wc_appearances, best_finish, total_wc_goals,
                json.dumps(history_json) if history_json is not None else None,
                now,
            ),
        )


def get_team_history(team: str) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(conn, "SELECT * FROM team_history WHERE team = ?", (team,)).fetchone()


# ---------------------------------------------------------------------------
# Sync log
# ---------------------------------------------------------------------------


def insert_sync_log(
    job_name: str,
    status: str,
    source: Optional[str] = None,
    records_affected: int = 0,
    error_message: Optional[str] = None,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
) -> int:
    with get_connection() as conn:
        if config.USE_POSTGRES:
            row = _execute(
                conn,
                """
                INSERT INTO sync_log (
                    job_name, status, source, records_affected, error_message,
                    started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    job_name, status, source, records_affected, error_message,
                    started_at or _now(), finished_at,
                ),
            ).fetchone()
        else:
            _execute(
                conn,
                """
                INSERT INTO sync_log (
                    job_name, status, source, records_affected, error_message,
                    started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_name, status, source, records_affected, error_message,
                    started_at or _now(), finished_at,
                ),
            )
            row = _execute(conn, "SELECT last_insert_rowid() AS id").fetchone()
        return int(row["id"])


def finish_sync_log(
    log_id: int,
    status: str,
    records_affected: int = 0,
    error_message: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        _execute(
            conn,
            """
            UPDATE sync_log SET
                status=?, records_affected=?, error_message=?, finished_at=?
            WHERE id=?
            """,
            (status, records_affected, error_message, _now(), log_id),
        )


def get_recent_sync_logs(limit: int = 50) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM sync_log
            ORDER BY COALESCE(finished_at, started_at) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def get_sync_logs_by_job(job_name: str, limit: int = 20) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM sync_log
            WHERE job_name = ?
            ORDER BY COALESCE(finished_at, started_at) DESC
            LIMIT ?
            """,
            (job_name, limit),
        ).fetchall()


# ---------------------------------------------------------------------------
# Data freshness
# ---------------------------------------------------------------------------


def upsert_data_freshness(
    entity: str,
    completeness_pct: Optional[float] = None,
    source: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    now = _now()
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO data_freshness (entity, last_updated, completeness_pct, source, notes)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(entity) DO UPDATE SET
                last_updated=excluded.last_updated,
                completeness_pct=COALESCE(excluded.completeness_pct, data_freshness.completeness_pct),
                source=COALESCE(excluded.source, data_freshness.source),
                notes=COALESCE(excluded.notes, data_freshness.notes)
            """,
            (entity, now, completeness_pct, source, notes),
        )


def get_data_freshness(entity: str) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(
            conn, "SELECT * FROM data_freshness WHERE entity = ?", (entity,)
        ).fetchone()


def get_all_data_freshness() -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn, "SELECT * FROM data_freshness ORDER BY entity"
        ).fetchall()


# ---------------------------------------------------------------------------
# Prediction history
# ---------------------------------------------------------------------------


def insert_prediction_history(
    match_id: int,
    version: int,
    home_win_prob: float,
    draw_prob: float,
    away_win_prob: float,
    predicted_home_goals: float,
    predicted_away_goals: float,
    features: Optional[dict[str, Any]] = None,
    reason_changed: Optional[str] = None,
) -> None:
    now = _now()
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO prediction_history (
                match_id, version, generated_at, home_win_prob, draw_prob, away_win_prob,
                predicted_home_goals, predicted_away_goals, features_json, reason_changed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id, version) DO UPDATE SET
                generated_at=excluded.generated_at,
                home_win_prob=excluded.home_win_prob,
                draw_prob=excluded.draw_prob,
                away_win_prob=excluded.away_win_prob,
                predicted_home_goals=excluded.predicted_home_goals,
                predicted_away_goals=excluded.predicted_away_goals,
                features_json=excluded.features_json,
                reason_changed=excluded.reason_changed
            """,
            (
                match_id, version, now,
                home_win_prob, draw_prob, away_win_prob,
                predicted_home_goals, predicted_away_goals,
                json.dumps(features) if features is not None else None,
                reason_changed,
            ),
        )


def get_prediction_history(match_id: int) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM prediction_history
            WHERE match_id = ?
            ORDER BY version DESC
            """,
            (match_id,),
        ).fetchall()


def get_latest_prediction_history(match_id: int) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM prediction_history
            WHERE match_id = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (match_id,),
        ).fetchone()


def next_prediction_version(match_id: int) -> int:
    with get_connection() as conn:
        row = _execute(
            conn,
            "SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM prediction_history WHERE match_id = ?",
            (match_id,),
        ).fetchone()
        return int(row["next_version"])


# ---------------------------------------------------------------------------
# Feature store
# ---------------------------------------------------------------------------


def insert_feature_store(
    match_id: int,
    features: dict[str, Any],
    missing_flags: Optional[dict[str, Any]] = None,
) -> int:
    now = _now()
    with get_connection() as conn:
        if config.USE_POSTGRES:
            row = _execute(
                conn,
                """
                INSERT INTO feature_store (match_id, generated_at, features_json, missing_flags_json)
                VALUES (?, ?, ?, ?)
                RETURNING id
                """,
                (
                    match_id, now,
                    json.dumps(features),
                    json.dumps(missing_flags) if missing_flags is not None else None,
                ),
            ).fetchone()
        else:
            _execute(
                conn,
                """
                INSERT INTO feature_store (match_id, generated_at, features_json, missing_flags_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    match_id, now,
                    json.dumps(features),
                    json.dumps(missing_flags) if missing_flags is not None else None,
                ),
            )
            row = _execute(conn, "SELECT last_insert_rowid() AS id").fetchone()
        return int(row["id"])


def get_latest_features(match_id: int) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM feature_store
            WHERE match_id = ?
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            (match_id,),
        ).fetchone()


def get_feature_store_history(match_id: int, limit: int = 20) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM feature_store
            WHERE match_id = ?
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (match_id, limit),
        ).fetchall()


# ---------------------------------------------------------------------------
# Weather forecasts
# ---------------------------------------------------------------------------


def upsert_weather_forecast(match_id: int, forecast: dict[str, Any]) -> None:
    now = _now()
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO weather_forecasts (
                match_id, temp_c, humidity_pct, wind_kmh, rain_mm,
                conditions, forecast_json, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                temp_c=excluded.temp_c,
                humidity_pct=excluded.humidity_pct,
                wind_kmh=excluded.wind_kmh,
                rain_mm=excluded.rain_mm,
                conditions=excluded.conditions,
                forecast_json=excluded.forecast_json,
                last_updated=excluded.last_updated
            """,
            (
                match_id,
                forecast.get("temp_c"),
                forecast.get("humidity_pct"),
                forecast.get("wind_kmh"),
                forecast.get("rain_mm"),
                forecast.get("conditions"),
                json.dumps(forecast.get("forecast_json")) if forecast.get("forecast_json") is not None else None,
                now,
            ),
        )


def get_weather_forecast(match_id: int) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(
            conn, "SELECT * FROM weather_forecasts WHERE match_id = ?", (match_id,)
        ).fetchone()


# ---------------------------------------------------------------------------
# Referees
# ---------------------------------------------------------------------------


def upsert_referee(
    name: str,
    api_referee_id: Optional[int] = None,
    nationality: Optional[str] = None,
) -> int:
    now = _now()
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO referees (api_referee_id, name, nationality, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                api_referee_id=COALESCE(excluded.api_referee_id, referees.api_referee_id),
                nationality=COALESCE(excluded.nationality, referees.nationality),
                last_updated=excluded.last_updated
            """,
            (api_referee_id, name, nationality, now),
        )
        row = _execute(conn, "SELECT id FROM referees WHERE name = ?", (name,)).fetchone()
        return int(row["id"])


def get_referee_by_name(name: str) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(conn, "SELECT * FROM referees WHERE name = ?", (name,)).fetchone()


def upsert_referee_stats(referee_id: int, stats: dict[str, Any]) -> None:
    now = _now()
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO referee_stats (
                referee_id, matches_officiated, avg_yellow_cards, avg_red_cards,
                pen_rate, stats_json, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(referee_id) DO UPDATE SET
                matches_officiated=excluded.matches_officiated,
                avg_yellow_cards=excluded.avg_yellow_cards,
                avg_red_cards=excluded.avg_red_cards,
                pen_rate=excluded.pen_rate,
                stats_json=excluded.stats_json,
                last_updated=excluded.last_updated
            """,
            (
                referee_id,
                stats.get("matches_officiated", 0),
                stats.get("avg_yellow_cards"),
                stats.get("avg_red_cards"),
                stats.get("pen_rate"),
                json.dumps(stats.get("stats_json")) if stats.get("stats_json") is not None else None,
                now,
            ),
        )


def get_referee_stats(referee_id: int) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(
            conn, "SELECT * FROM referee_stats WHERE referee_id = ?", (referee_id,)
        ).fetchone()


# ---------------------------------------------------------------------------
# Match metadata (extended columns)
# ---------------------------------------------------------------------------


def update_match_metadata(
    match_id: int,
    stage: Optional[str] = None,
    group_name: Optional[str] = None,
    round_name: Optional[str] = None,
    referee_name: Optional[str] = None,
    weather_json: Optional[dict[str, Any]] = None,
) -> None:
    now = _now()
    with get_connection() as conn:
        _execute(
            conn,
            """
            UPDATE matches SET
                stage=COALESCE(?, stage),
                group_name=COALESCE(?, group_name),
                round_name=COALESCE(?, round_name),
                referee_name=COALESCE(?, referee_name),
                weather_json=COALESCE(?, weather_json),
                last_updated=?
            WHERE id=?
            """,
            (
                stage, group_name, round_name, referee_name,
                json.dumps(weather_json) if weather_json is not None else None,
                now, match_id,
            ),
        )


def upsert_prediction_extended(
    match_id: int,
    confidence_pct: Optional[float] = None,
    data_completeness_pct: Optional[float] = None,
    model_agreement: Optional[str] = None,
    ensemble: Optional[dict[str, Any]] = None,
    factor_breakdown: Optional[dict[str, Any]] = None,
) -> None:
    with get_connection() as conn:
        _execute(
            conn,
            """
            UPDATE predictions SET
                confidence_pct=COALESCE(?, confidence_pct),
                data_completeness_pct=COALESCE(?, data_completeness_pct),
                model_agreement=COALESCE(?, model_agreement),
                ensemble_json=COALESCE(?, ensemble_json),
                factor_breakdown_json=COALESCE(?, factor_breakdown_json)
            WHERE match_id=?
            """,
            (
                confidence_pct,
                data_completeness_pct,
                model_agreement,
                json.dumps(ensemble) if ensemble is not None else None,
                json.dumps(factor_breakdown) if factor_breakdown is not None else None,
                match_id,
            ),
        )


def get_player_leaderboard(metric: str, limit: int = 20) -> list[dict[str, Any]]:
    """Aggregate player_match_stats for tournament leaders."""
    col_map = {
        "goals": "goals",
        "assists": "assists",
        "rating": "rating",
        "minutes": "minutes",
    }
    col = col_map.get(metric, "goals")
    with get_connection() as conn:
        rows = _execute(
            conn,
            f"""
            SELECT player_id, player_name, team,
                   SUM(COALESCE(goals, 0)) AS goals,
                   SUM(COALESCE(assists, 0)) AS assists,
                   AVG(rating) AS rating,
                   SUM(COALESCE(minutes, 0)) AS minutes,
                   SUM(COALESCE(yellow_cards, 0)) AS yellow_cards,
                   SUM(COALESCE(red_cards, 0)) AS red_cards
            FROM player_match_stats
            GROUP BY player_id, player_name, team
            ORDER BY {col} DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_player_match_stats_history(player_id: int, limit: int = 20) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT pms.*, m.date, m.home_team, m.away_team
            FROM player_match_stats pms
            JOIN matches m ON m.id = pms.match_id
            WHERE pms.player_id = ?
            ORDER BY m.date DESC
            LIMIT ?
            """,
            (player_id, limit),
        ).fetchall()


def insert_live_prob_snapshot(
    match_id: int,
    home_win_prob: float,
    draw_prob: float,
    away_win_prob: float,
    match_minute: Optional[int] = None,
) -> None:
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO live_prob_history (
                match_id, recorded_at, home_win_prob, draw_prob, away_win_prob, match_minute
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (match_id, _now(), home_win_prob, draw_prob, away_win_prob, match_minute),
        )


def get_live_prob_history(match_id: int, limit: int = 100) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM live_prob_history
            WHERE match_id = ?
            ORDER BY recorded_at ASC
            LIMIT ?
            """,
            (match_id, limit),
        ).fetchall()
