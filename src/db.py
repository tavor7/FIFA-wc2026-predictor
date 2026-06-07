"""Database layer — Supabase Postgres (production) or SQLite (local dev)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator, Optional, Union

from src import config

Row = Union[dict[str, Any], sqlite3.Row]

WC_LEAGUE_LIKE = "%world cup%"
WC_FILTER_SQL = " AND LOWER(league) LIKE ? AND season = ?"

_pg_pool: Any = None


def _wc_filter_params() -> list[Any]:
    return [WC_LEAGUE_LIKE, config.SEASON]


def _normalize_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def _postgres_pool() -> Any:
    global _pg_pool
    if _pg_pool is None:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        _pg_pool = ConnectionPool(
            conninfo=_normalize_db_url(config.DATABASE_URL),
            min_size=1,
            max_size=6,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pg_pool


def close_postgres_pool() -> None:
    global _pg_pool
    if _pg_pool is not None:
        _pg_pool.close()
        _pg_pool = None


def _adapt_sql(sql: str) -> str:
    """Convert SQLite-style ? placeholders to PostgreSQL %s when needed."""
    if config.USE_POSTGRES:
        return sql.replace("?", "%s")
    return sql


def _ensure_db_dir() -> None:
    if not config.USE_POSTGRES:
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection() -> Generator[Any, None, None]:
    """Yield a database connection (SQLite or Supabase Postgres)."""
    _ensure_db_dir()
    if config.USE_POSTGRES:
        with _postgres_pool().connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    else:
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _execute(conn: Any, sql: str, params: tuple | list = ()) -> Any:
    return conn.execute(_adapt_sql(sql), params)


def _executescript(conn: Any, script: str) -> None:
    if config.USE_POSTGRES:
        for stmt in filter(None, (s.strip() for s in script.split(";"))):
            upper = stmt.upper()
            if upper.startswith((
                "CREATE INDEX", "CREATE TABLE", "ALTER TABLE",
            )):
                conn.execute(stmt)
    else:
        conn.executescript(script)


SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_fixture_id TEXT UNIQUE NOT NULL,
    date TEXT NOT NULL,
    league TEXT,
    season INTEGER,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_team_id INTEGER,
    away_team_id INTEGER,
    status TEXT,
    home_goals INTEGER,
    away_goals INTEGER,
    venue TEXT,
    stage TEXT,
    group_name TEXT,
    round_name TEXT,
    referee_name TEXT,
    weather_json TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS team_match_stats (
    match_id INTEGER NOT NULL,
    team TEXT NOT NULL,
    shots INTEGER,
    shots_on_target INTEGER,
    possession REAL,
    passes INTEGER,
    pass_accuracy REAL,
    corners INTEGER,
    fouls INTEGER,
    yellow_cards INTEGER,
    red_cards INTEGER,
    PRIMARY KEY (match_id, team),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lineups (
    match_id INTEGER NOT NULL,
    team TEXT NOT NULL,
    player_id INTEGER,
    player_name TEXT NOT NULL,
    position TEXT,
    is_starting INTEGER DEFAULT 1,
    rating REAL,
    minutes INTEGER,
    PRIMARY KEY (match_id, team, player_name),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS injuries (
    player_id INTEGER,
    player_name TEXT NOT NULL,
    team TEXT NOT NULL,
    injury_type TEXT,
    reason TEXT,
    expected_return TEXT,
    last_updated TEXT,
    PRIMARY KEY (player_id, team)
);

CREATE TABLE IF NOT EXISTS predictions (
    match_id INTEGER PRIMARY KEY,
    generated_at TEXT NOT NULL,
    predicted_home_goals REAL,
    predicted_away_goals REAL,
    home_win_prob REAL,
    draw_prob REAL,
    away_win_prob REAL,
    exact_score_prob REAL,
    top_scorelines_json TEXT,
    explanation TEXT,
    confidence_pct REAL,
    data_completeness_pct REAL,
    model_agreement TEXT,
    ensemble_json TEXT,
    factor_breakdown_json TEXT,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    slug TEXT UNIQUE,
    country_code TEXT,
    api_team_id INTEGER UNIQUE,
    logo_url TEXT,
    attack_strength REAL,
    defense_strength REAL,
    strength_matches INTEGER,
    strength_avg_scored REAL,
    strength_avg_conceded REAL,
    strength_source TEXT,
    strength_updated_at TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_player_id INTEGER UNIQUE,
    team_id INTEGER,
    name TEXT NOT NULL,
    position TEXT,
    positions_detail TEXT,
    rating REAL,
    potential REAL,
    age INTEGER,
    form REAL,
    caps INTEGER,
    club TEXT,
    preferred_foot TEXT,
    jersey_number INTEGER,
    stat_pace REAL,
    stat_shooting REAL,
    stat_passing REAL,
    stat_dribbling REAL,
    stat_defending REAL,
    stat_physical REAL,
    int_reputation INTEGER,
    photo_url TEXT,
    last_updated TEXT,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS player_match_stats (
    match_id INTEGER NOT NULL,
    api_player_id INTEGER,
    player_name TEXT NOT NULL,
    team TEXT NOT NULL,
    goals INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    yellow_cards INTEGER DEFAULT 0,
    red_cards INTEGER DEFAULT 0,
    minutes INTEGER,
    rating REAL,
    is_motm INTEGER DEFAULT 0,
    PRIMARY KEY (match_id, team, player_name),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    minute INTEGER,
    extra_minute INTEGER,
    team TEXT,
    player_name TEXT,
    player_id INTEGER,
    event_type TEXT NOT NULL,
    detail TEXT,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS standings (
    group_name TEXT NOT NULL,
    team TEXT NOT NULL,
    team_id INTEGER,
    season INTEGER NOT NULL,
    played INTEGER DEFAULT 0,
    won INTEGER DEFAULT 0,
    drawn INTEGER DEFAULT 0,
    lost INTEGER DEFAULT 0,
    goals_for INTEGER DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    goal_diff INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0,
    rank INTEGER,
    last_updated TEXT,
    PRIMARY KEY (group_name, team, season)
);

CREATE TABLE IF NOT EXISTS bracket_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage TEXT NOT NULL,
    round_name TEXT NOT NULL,
    slot INTEGER NOT NULL,
    match_id INTEGER,
    home_team TEXT,
    away_team TEXT,
    winner_team_id INTEGER,
    parent_node_id INTEGER,
    last_updated TEXT,
    UNIQUE (stage, round_name, slot),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS head_to_head (
    team_a TEXT NOT NULL,
    team_b TEXT NOT NULL,
    team_a_id INTEGER,
    team_b_id INTEGER,
    matches_played INTEGER DEFAULT 0,
    team_a_wins INTEGER DEFAULT 0,
    team_b_wins INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0,
    team_a_goals INTEGER DEFAULT 0,
    team_b_goals INTEGER DEFAULT 0,
    summary_json TEXT,
    last_updated TEXT,
    PRIMARY KEY (team_a, team_b)
);

CREATE TABLE IF NOT EXISTS team_history (
    team TEXT PRIMARY KEY,
    team_id INTEGER,
    wc_appearances INTEGER DEFAULT 0,
    best_finish TEXT,
    total_wc_goals INTEGER DEFAULT 0,
    history_json TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT,
    records_affected INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS data_freshness (
    entity TEXT PRIMARY KEY,
    last_updated TEXT,
    completeness_pct REAL,
    source TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS prediction_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    home_win_prob REAL,
    draw_prob REAL,
    away_win_prob REAL,
    predicted_home_goals REAL,
    predicted_away_goals REAL,
    features_json TEXT,
    reason_changed TEXT,
    UNIQUE (match_id, version),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feature_store (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    features_json TEXT,
    missing_flags_json TEXT,
    metadata_json TEXT,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tournament_simulations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL,
    n_simulations INTEGER NOT NULL,
    results_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS live_prob_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    home_win_prob REAL,
    draw_prob REAL,
    away_win_prob REAL,
    match_minute INTEGER,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_live_prob_match ON live_prob_history(match_id, recorded_at);

CREATE TABLE IF NOT EXISTS weather_forecasts (
    match_id INTEGER PRIMARY KEY,
    temp_c REAL,
    humidity_pct REAL,
    wind_kmh REAL,
    rain_mm REAL,
    conditions TEXT,
    forecast_json TEXT,
    last_updated TEXT,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS referees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_referee_id INTEGER UNIQUE,
    name TEXT NOT NULL UNIQUE,
    nationality TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS referee_stats (
    referee_id INTEGER PRIMARY KEY,
    matches_officiated INTEGER DEFAULT 0,
    avg_yellow_cards REAL,
    avg_red_cards REAL,
    pen_rate REAL,
    stats_json TEXT,
    last_updated TEXT,
    FOREIGN KEY (referee_id) REFERENCES referees(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team, away_team);
"""

SCHEMA_POSTGRES = open(
    config.PROJECT_ROOT / "supabase" / "schema.sql", encoding="utf-8"
).read()


def init_db() -> None:
    """Create tables if they do not exist."""
    with get_connection() as conn:
        script = SCHEMA_POSTGRES if config.USE_POSTGRES else SCHEMA_SQLITE
        _executescript(conn, script)
        _migrate_extended_schema(conn)


def _table_columns(conn: Any, table: str) -> set[str]:
    if config.USE_POSTGRES:
        rows = conn.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table,),
        ).fetchall()
        return {r["column_name"] for r in rows}
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _table_exists(conn: Any, table: str) -> bool:
    if config.USE_POSTGRES:
        row = conn.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table,),
        ).fetchone()
        return row is not None
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _migrate_extended_schema(conn: Any) -> None:
    """Add extended columns and analytics tables on existing databases."""
    match_cols = {
        "stage": "TEXT",
        "group_name": "TEXT",
        "round_name": "TEXT",
        "referee_name": "TEXT",
        "weather_json": "TEXT",
        "competition_type": "TEXT",
        "competition_weight": "REAL",
    }
    if _table_exists(conn, "matches"):
        existing_match = _table_columns(conn, "matches")
        for col, col_type in match_cols.items():
            if col not in existing_match:
                conn.execute(f"ALTER TABLE matches ADD COLUMN {col} {col_type}")

    pred_cols = {
        "confidence_pct": "REAL",
        "data_completeness_pct": "REAL",
        "model_agreement": "TEXT",
        "ensemble_json": "TEXT",
        "factor_breakdown_json": "TEXT",
        "lambda_home_mean": "REAL",
        "lambda_home_std": "REAL",
        "lambda_away_mean": "REAL",
        "lambda_away_std": "REAL",
        "prediction_type": "TEXT",
        "model_version": "TEXT",
        "feature_version": "TEXT",
        "data_snapshot_timestamp": "TEXT",
        "model_weights_json": "TEXT",
        "freshness_json": "TEXT",
        "live_prediction_json": "TEXT",
    }
    existing = _table_columns(conn, "predictions")
    for col, col_type in pred_cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE predictions ADD COLUMN {col} {col_type}")

    if _table_exists(conn, "teams"):
        team_cols = {
            "attack_strength": "REAL",
            "defense_strength": "REAL",
            "strength_matches": "INTEGER",
            "strength_avg_scored": "REAL",
            "strength_avg_conceded": "REAL",
            "strength_source": "TEXT",
            "strength_updated_at": "TEXT",
        }
        existing_teams = _table_columns(conn, "teams")
        for col, col_type in team_cols.items():
            if col not in existing_teams:
                conn.execute(f"ALTER TABLE teams ADD COLUMN {col} {col_type}")

    if _table_exists(conn, "feature_store"):
        fs_cols = _table_columns(conn, "feature_store")
        if "metadata_json" not in fs_cols:
            conn.execute("ALTER TABLE feature_store ADD COLUMN metadata_json TEXT")

    if _table_exists(conn, "players"):
        player_cols = {
            "positions_detail": "TEXT",
            "potential": "REAL",
            "age": "INTEGER",
            "preferred_foot": "TEXT",
            "jersey_number": "INTEGER",
            "stat_pace": "REAL",
            "stat_shooting": "REAL",
            "stat_passing": "REAL",
            "stat_dribbling": "REAL",
            "stat_defending": "REAL",
            "stat_physical": "REAL",
            "int_reputation": "INTEGER",
            "photo_url": "TEXT",
        }
        existing_players = _table_columns(conn, "players")
        for col, col_type in player_cols.items():
            if col not in existing_players:
                conn.execute(f"ALTER TABLE players ADD COLUMN {col} {col_type}")

    if _table_exists(conn, "prediction_history"):
        hist_cols = {
            "explanation_json": "TEXT",
            "ensemble_json": "TEXT",
            "change_bullets_json": "TEXT",
            "model_version": "TEXT",
        }
        existing_hist = _table_columns(conn, "prediction_history")
        for col, col_type in hist_cols.items():
            if col not in existing_hist:
                conn.execute(f"ALTER TABLE prediction_history ADD COLUMN {col} {col_type}")

    registry_sql = """
        CREATE TABLE IF NOT EXISTS model_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_version TEXT NOT NULL,
            feature_version TEXT,
            trained_at TEXT NOT NULL,
            weights_json TEXT,
            active_models_json TEXT,
            metrics_json TEXT
        )
    """
    backtest_sql = """
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT NOT NULL,
            tournament TEXT,
            metrics_json TEXT NOT NULL
        )
    """
    if config.USE_POSTGRES:
        registry_sql = registry_sql.replace(
            "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"
        ).replace("id SERIAL PRIMARY KEY", "id SERIAL PRIMARY KEY")
        backtest_sql = backtest_sql.replace(
            "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"
        )
    if not _table_exists(conn, "model_registry"):
        conn.execute(registry_sql if not config.USE_POSTGRES else """
            CREATE TABLE IF NOT EXISTS model_registry (
                id SERIAL PRIMARY KEY,
                model_version TEXT NOT NULL,
                feature_version TEXT,
                trained_at TEXT NOT NULL,
                weights_json TEXT,
                active_models_json TEXT,
                metrics_json TEXT
            )
        """)
    if not _table_exists(conn, "backtest_runs"):
        conn.execute(backtest_sql if not config.USE_POSTGRES else """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id SERIAL PRIMARY KEY,
                run_at TEXT NOT NULL,
                tournament TEXT,
                metrics_json TEXT NOT NULL
            )
        """)

    if config.USE_POSTGRES:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feature_store (
                id SERIAL PRIMARY KEY,
                match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
                generated_at TEXT NOT NULL,
                features_json TEXT NOT NULL,
                missing_flags_json TEXT,
                metadata_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tournament_simulations (
                id SERIAL PRIMARY KEY,
                generated_at TEXT NOT NULL,
                n_simulations INTEGER NOT NULL,
                results_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feature_store_match ON feature_store(match_id)"
        )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feature_store (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                generated_at TEXT NOT NULL,
                features_json TEXT NOT NULL,
                missing_flags_json TEXT,
                metadata_json TEXT,
                FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feature_store_match ON feature_store(match_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tournament_simulations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                generated_at TEXT NOT NULL,
                n_simulations INTEGER NOT NULL,
                results_json TEXT NOT NULL
            )
            """
        )

    _ensure_optional_indexes(conn)


def _ensure_optional_indexes(conn: Any) -> None:
    """Create indexes only when referenced columns exist."""
    if _table_exists(conn, "matches"):
        cols = _table_columns(conn, "matches")
        if {"stage", "group_name", "round_name"}.issubset(cols):
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_matches_stage ON matches(stage, group_name, round_name)"
            )
    if _table_exists(conn, "teams") and "slug" in _table_columns(conn, "teams"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_teams_slug ON teams(slug)")
    if _table_exists(conn, "match_events"):
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_match_events_match ON match_events(match_id)"
        )
    if _table_exists(conn, "standings"):
        cols = _table_columns(conn, "standings")
        if {"group_name", "season"}.issubset(cols):
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_standings_group ON standings(group_name, season)"
            )
    if _table_exists(conn, "feature_store"):
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feature_store_match ON feature_store(match_id)"
        )


def db_backend() -> str:
    """Return active database backend label."""
    return "supabase_postgres" if config.USE_POSTGRES else "sqlite"


def upsert_match(
    external_fixture_id: str,
    date: str,
    league: str,
    season: int,
    home_team: str,
    away_team: str,
    status: str,
    home_goals: Optional[int],
    away_goals: Optional[int],
    venue: Optional[str],
    home_team_id: Optional[int] = None,
    away_team_id: Optional[int] = None,
) -> int:
    """Insert or update a match row; return internal match id."""
    now = datetime.utcnow().isoformat()
    # Postgres requires table-qualified column names in ON CONFLICT UPDATE
    existing_home_id = "matches.home_team_id" if config.USE_POSTGRES else "home_team_id"
    existing_away_id = "matches.away_team_id" if config.USE_POSTGRES else "away_team_id"
    with get_connection() as conn:
        _execute(
            conn,
            f"""
            INSERT INTO matches (
                external_fixture_id, date, league, season,
                home_team, away_team, home_team_id, away_team_id,
                status, home_goals, away_goals, venue, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(external_fixture_id) DO UPDATE SET
                date=excluded.date,
                league=excluded.league,
                season=excluded.season,
                home_team=excluded.home_team,
                away_team=excluded.away_team,
                home_team_id=COALESCE(excluded.home_team_id, {existing_home_id}),
                away_team_id=COALESCE(excluded.away_team_id, {existing_away_id}),
                status=excluded.status,
                home_goals=excluded.home_goals,
                away_goals=excluded.away_goals,
                venue=excluded.venue,
                last_updated=excluded.last_updated
            """,
            (
                external_fixture_id, date, league, season,
                home_team, away_team, home_team_id, away_team_id,
                status, home_goals, away_goals, venue, now,
            ),
        )
        row = _execute(
            conn,
            "SELECT id FROM matches WHERE external_fixture_id = ?",
            (external_fixture_id,),
        ).fetchone()
        return int(row["id"])


def upsert_team_stats(match_id: int, team: str, stats: dict[str, Any]) -> None:
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO team_match_stats (
                match_id, team, shots, shots_on_target, possession,
                passes, pass_accuracy, corners, fouls, yellow_cards, red_cards
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id, team) DO UPDATE SET
                shots=excluded.shots,
                shots_on_target=excluded.shots_on_target,
                possession=excluded.possession,
                passes=excluded.passes,
                pass_accuracy=excluded.pass_accuracy,
                corners=excluded.corners,
                fouls=excluded.fouls,
                yellow_cards=excluded.yellow_cards,
                red_cards=excluded.red_cards
            """,
            (
                match_id, team,
                stats.get("shots"), stats.get("shots_on_target"), stats.get("possession"),
                stats.get("passes"), stats.get("pass_accuracy"), stats.get("corners"),
                stats.get("fouls"), stats.get("yellow_cards"), stats.get("red_cards"),
            ),
        )


def upsert_lineup(
    match_id: int, team: str, player_id: Optional[int], player_name: str,
    position: Optional[str], is_starting: bool, rating: Optional[float],
    minutes: Optional[int],
) -> None:
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO lineups (
                match_id, team, player_id, player_name, position,
                is_starting, rating, minutes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id, team, player_name) DO UPDATE SET
                player_id=excluded.player_id,
                position=excluded.position,
                is_starting=excluded.is_starting,
                rating=excluded.rating,
                minutes=excluded.minutes
            """,
            (match_id, team, player_id, player_name, position,
             1 if is_starting else 0, rating, minutes),
        )


def clear_lineups_for_match(match_id: int) -> None:
    with get_connection() as conn:
        _execute(conn, "DELETE FROM lineups WHERE match_id = ?", (match_id,))


def upsert_injury(
    player_id: Optional[int], player_name: str, team: str,
    injury_type: Optional[str], reason: Optional[str], expected_return: Optional[str],
) -> None:
    now = datetime.utcnow().isoformat()
    pid = player_id if player_id is not None else hash(f"{player_name}_{team}") % (10**9)
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO injuries (
                player_id, player_name, team, injury_type, reason,
                expected_return, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, team) DO UPDATE SET
                player_name=excluded.player_name,
                injury_type=excluded.injury_type,
                reason=excluded.reason,
                expected_return=excluded.expected_return,
                last_updated=excluded.last_updated
            """,
            (pid, player_name, team, injury_type, reason, expected_return, now),
        )


def upsert_prediction(
    match_id: int,
    predicted_home_goals: float,
    predicted_away_goals: float,
    home_win_prob: float,
    draw_prob: float,
    away_win_prob: float,
    exact_score_prob: float,
    top_scorelines: list[dict[str, Any]],
    explanation: str,
    confidence_pct: Optional[float] = None,
    data_completeness_pct: Optional[float] = None,
    model_agreement: Optional[str] = None,
    ensemble_json: Optional[dict[str, Any]] = None,
    factor_breakdown_json: Optional[dict[str, Any]] = None,
    lambda_home_mean: Optional[float] = None,
    lambda_home_std: Optional[float] = None,
    lambda_away_mean: Optional[float] = None,
    lambda_away_std: Optional[float] = None,
    prediction_type: Optional[str] = "prematch",
    model_version: Optional[str] = None,
    feature_version: Optional[str] = None,
    data_snapshot_timestamp: Optional[str] = None,
    model_weights_json: Optional[dict[str, Any]] = None,
    freshness_json: Optional[dict[str, Any]] = None,
    live_prediction_json: Optional[dict[str, Any]] = None,
) -> None:
    now = datetime.utcnow().isoformat()
    if top_scorelines:
        best = top_scorelines[0]
        predicted_home_goals = int(best.get("home", round(float(predicted_home_goals))))
        predicted_away_goals = int(best.get("away", round(float(predicted_away_goals))))
    else:
        predicted_home_goals = int(round(float(predicted_home_goals)))
        predicted_away_goals = int(round(float(predicted_away_goals)))
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO predictions (
                match_id, generated_at, predicted_home_goals, predicted_away_goals,
                home_win_prob, draw_prob, away_win_prob, exact_score_prob,
                top_scorelines_json, explanation,
                confidence_pct, data_completeness_pct, model_agreement,
                ensemble_json, factor_breakdown_json,
                lambda_home_mean, lambda_home_std, lambda_away_mean, lambda_away_std,
                prediction_type, model_version, feature_version, data_snapshot_timestamp,
                model_weights_json, freshness_json, live_prediction_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                generated_at=excluded.generated_at,
                predicted_home_goals=excluded.predicted_home_goals,
                predicted_away_goals=excluded.predicted_away_goals,
                home_win_prob=excluded.home_win_prob,
                draw_prob=excluded.draw_prob,
                away_win_prob=excluded.away_win_prob,
                exact_score_prob=excluded.exact_score_prob,
                top_scorelines_json=excluded.top_scorelines_json,
                explanation=excluded.explanation,
                confidence_pct=excluded.confidence_pct,
                data_completeness_pct=excluded.data_completeness_pct,
                model_agreement=excluded.model_agreement,
                ensemble_json=excluded.ensemble_json,
                factor_breakdown_json=excluded.factor_breakdown_json,
                lambda_home_mean=excluded.lambda_home_mean,
                lambda_home_std=excluded.lambda_home_std,
                lambda_away_mean=excluded.lambda_away_mean,
                lambda_away_std=excluded.lambda_away_std,
                prediction_type=excluded.prediction_type,
                model_version=excluded.model_version,
                feature_version=excluded.feature_version,
                data_snapshot_timestamp=excluded.data_snapshot_timestamp,
                model_weights_json=excluded.model_weights_json,
                freshness_json=excluded.freshness_json,
                live_prediction_json=excluded.live_prediction_json
            """,
            (
                match_id, now, predicted_home_goals, predicted_away_goals,
                home_win_prob, draw_prob, away_win_prob, exact_score_prob,
                json.dumps(top_scorelines), explanation,
                confidence_pct, data_completeness_pct, model_agreement,
                json.dumps(ensemble_json) if ensemble_json is not None else None,
                json.dumps(factor_breakdown_json) if factor_breakdown_json is not None else None,
                lambda_home_mean, lambda_home_std, lambda_away_mean, lambda_away_std,
                prediction_type, model_version, feature_version, data_snapshot_timestamp,
                json.dumps(model_weights_json) if model_weights_json is not None else None,
                json.dumps(freshness_json) if freshness_json is not None else None,
                json.dumps(live_prediction_json) if live_prediction_json is not None else None,
            ),
        )


def get_match_by_id(match_id: int) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(conn, "SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()


def get_match_by_external_id(external_id: str) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(
            conn, "SELECT * FROM matches WHERE external_fixture_id = ?", (external_id,)
        ).fetchone()


def get_matches_by_status(statuses: list[str], tournament_only: bool = False) -> list[Row]:
    placeholders = ",".join("?" * len(statuses))
    wc_clause = WC_FILTER_SQL if tournament_only else ""
    params: list[Any] = list(statuses)
    if tournament_only:
        params.extend(_wc_filter_params())
    with get_connection() as conn:
        return _execute(
            conn,
            f"SELECT * FROM matches WHERE status IN ({placeholders}){wc_clause} ORDER BY date",
            params,
        ).fetchall()


def get_upcoming_matches(limit: int = 50, tournament_only: bool = True) -> list[Row]:
    wc_clause = WC_FILTER_SQL if tournament_only else ""
    params: list[Any] = (*_wc_filter_params(), limit) if tournament_only else [limit]
    with get_connection() as conn:
        return _execute(
            conn,
            f"""
            SELECT * FROM matches
            WHERE (
                status IN ('NS', 'TBD', 'SCHEDULED', 'TIMED', 'Not Started')
                OR (status NOT IN ('FT', 'AET', 'PEN', 'CANC', 'ABD', 'AWD', 'WO')
                    AND home_goals IS NULL)
            ){wc_clause}
            ORDER BY date ASC
            LIMIT ?
            """,
            params,
        ).fetchall()


def get_live_matches(tournament_only: bool = True) -> list[Row]:
    return get_matches_by_status(
        ["1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED"],
        tournament_only=tournament_only,
    )


def get_recent_matches(limit: int = 50, tournament_only: bool = True) -> list[Row]:
    wc_clause = WC_FILTER_SQL if tournament_only else ""
    params: list[Any] = (*_wc_filter_params(), limit) if tournament_only else [limit]
    with get_connection() as conn:
        return _execute(
            conn,
            f"""
            SELECT * FROM matches
            WHERE status IN ('FT', 'AET', 'PEN', 'FINISHED'){wc_clause}
            ORDER BY date DESC
            LIMIT ?
            """,
            params,
        ).fetchall()


def get_all_finished_matches() -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM matches
            WHERE status IN ('FT', 'AET', 'PEN', 'FINISHED')
              AND home_goals IS NOT NULL AND away_goals IS NOT NULL
            ORDER BY date ASC
            """,
        ).fetchall()


def get_prediction(match_id: int) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(conn, "SELECT * FROM predictions WHERE match_id = ?", (match_id,)).fetchone()


def get_predictions_for_match_ids(match_ids: list[int]) -> dict[int, Row]:
    """Batch-load predictions for list endpoints (one query instead of N)."""
    if not match_ids:
        return {}
    placeholders = ",".join("?" * len(match_ids))
    with get_connection() as conn:
        rows = _execute(
            conn,
            f"SELECT * FROM predictions WHERE match_id IN ({placeholders})",
            match_ids,
        ).fetchall()
    return {int(dict(r)["match_id"]): r for r in rows}


def get_platform_stats(tournament_only: bool = True) -> dict[str, int]:
    """Fast counts for dashboard — single round-trip to the database."""
    wc_params = _wc_filter_params() if tournament_only else []
    wc_match = WC_FILTER_SQL if tournament_only else ""
    live_statuses = ("1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED")
    live_ph = ",".join("?" * len(live_statuses))

    upcoming_where = f"""
        (
            status IN ('NS', 'TBD', 'SCHEDULED', 'TIMED', 'Not Started')
            OR (status NOT IN ('FT', 'AET', 'PEN', 'CANC', 'ABD', 'AWD', 'WO')
                AND home_goals IS NULL)
        ){wc_match}
    """
    live_where = f"status IN ({live_ph}){wc_match}"

    params = wc_params + list(live_statuses) + wc_params
    with get_connection() as conn:
        row = _execute(
            conn,
            f"""
            SELECT
                (SELECT COUNT(*) FROM matches WHERE {upcoming_where}) AS upcoming,
                (SELECT COUNT(*) FROM matches WHERE {live_where}) AS live,
                (SELECT COUNT(*) FROM predictions) AS predictions,
                (SELECT COUNT(*) FROM teams) AS teams
            """,
            params,
        ).fetchone()
    d = dict(row)
    return {
        "upcoming": int(d["upcoming"]),
        "live": int(d["live"]),
        "predictions": int(d["predictions"]),
        "teams": int(d["teams"]),
    }


def get_home_feed(limit: int = 48, tournament_only: bool = True) -> dict[str, Any]:
    """Stats + upcoming matches + predictions in one pooled connection."""
    wc = WC_FILTER_SQL if tournament_only else ""
    wc_params = _wc_filter_params() if tournament_only else []
    match_params: list[Any] = list(wc_params) + [limit] if tournament_only else [limit]
    live_statuses = ("1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED")
    live_ph = ",".join("?" * len(live_statuses))
    upcoming_where = f"""
        (
            status IN ('NS', 'TBD', 'SCHEDULED', 'TIMED', 'Not Started')
            OR (status NOT IN ('FT', 'AET', 'PEN', 'CANC', 'ABD', 'AWD', 'WO')
                AND home_goals IS NULL)
        ){wc}
    """
    live_where = f"status IN ({live_ph}){wc}"
    stats_params = wc_params + list(live_statuses) + wc_params

    with get_connection() as conn:
        stats_row = _execute(
            conn,
            f"""
            SELECT
                (SELECT COUNT(*) FROM matches WHERE {upcoming_where}) AS upcoming,
                (SELECT COUNT(*) FROM matches WHERE {live_where}) AS live,
                (SELECT COUNT(*) FROM predictions) AS predictions,
                (SELECT COUNT(*) FROM teams) AS teams
            """,
            stats_params,
        ).fetchone()
        match_rows = _execute(
            conn,
            f"""
            SELECT * FROM matches
            WHERE (
                status IN ('NS', 'TBD', 'SCHEDULED', 'TIMED', 'Not Started')
                OR (status NOT IN ('FT', 'AET', 'PEN', 'CANC', 'ABD', 'AWD', 'WO')
                    AND home_goals IS NULL)
            ){wc}
            ORDER BY date ASC
            LIMIT ?
            """,
            match_params,
        ).fetchall()
        ids = [int(dict(r)["id"]) for r in match_rows]
        pred_map: dict[int, Row] = {}
        if ids:
            placeholders = ",".join("?" * len(ids))
            for row in _execute(
                conn,
                f"SELECT * FROM predictions WHERE match_id IN ({placeholders})",
                ids,
            ).fetchall():
                pred_map[int(dict(row)["match_id"])] = row

    sd = dict(stats_row)
    return {
        "stats": {
            "upcoming": int(sd["upcoming"]),
            "live": int(sd["live"]),
            "predictions": int(sd["predictions"]),
            "teams": int(sd["teams"]),
        },
        "matches": match_rows,
        "predictions": pred_map,
    }


def get_all_predictions() -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT p.*, m.home_team, m.away_team, m.date, m.status
            FROM predictions p
            JOIN matches m ON m.id = p.match_id
            ORDER BY m.date ASC
            """,
        ).fetchall()


def get_lineups(match_id: int) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            "SELECT * FROM lineups WHERE match_id = ? ORDER BY team, is_starting DESC",
            (match_id,),
        ).fetchall()


def get_injuries_for_teams(teams: list[str]) -> list[Row]:
    if not teams:
        return []
    placeholders = ",".join("?" * len(teams))
    with get_connection() as conn:
        return _execute(
            conn, f"SELECT * FROM injuries WHERE team IN ({placeholders})", teams
        ).fetchall()


def get_team_match_stats(match_id: int) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn, "SELECT * FROM team_match_stats WHERE match_id = ?", (match_id,)
        ).fetchall()


def get_team_recent_matches(team: str, before_date: str, limit: int = 5) -> list[Row]:
    from src.team_profiles import normalize_team_name

    team = normalize_team_name(team)
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM matches
            WHERE (home_team = ? OR away_team = ?)
              AND date < ?
              AND status IN ('FT', 'AET', 'PEN', 'FINISHED')
              AND home_goals IS NOT NULL
            ORDER BY date DESC
            LIMIT ?
            """,
            (team, team, before_date, limit),
        ).fetchall()


def get_team_all_time_averages(team: str) -> dict[str, float]:
    from src.team_profiles import normalize_team_name

    team = normalize_team_name(team)
    with get_connection() as conn:
        rows = _execute(
            conn,
            """
            SELECT * FROM matches
            WHERE (home_team = ? OR away_team = ?)
              AND status IN ('FT', 'AET', 'PEN', 'FINISHED')
              AND home_goals IS NOT NULL
            """,
            (team, team),
        ).fetchall()

    if not rows:
        return {"matches": 0, "scored": 0.0, "conceded": 0.0, "form": 0.5}

    scored, conceded, points = [], [], []
    for m in rows:
        is_home = m["home_team"] == team
        hg, ag = int(m["home_goals"]), int(m["away_goals"])
        scored.append(float(hg if is_home else ag))
        conceded.append(float(ag if is_home else hg))
        if hg == ag:
            points.append(0.5)
        elif (is_home and hg > ag) or (not is_home and ag > hg):
            points.append(1.0)
        else:
            points.append(0.0)

    n = len(rows)
    return {
        "matches": n,
        "scored": sum(scored) / n,
        "conceded": sum(conceded) / n,
        "form": sum(points) / n,
    }


def upsert_feature_store(
    match_id: int,
    features: dict[str, float],
    missing_flags: dict[str, bool],
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        _execute(conn, "DELETE FROM feature_store WHERE match_id = ?", (match_id,))
        _execute(
            conn,
            """
            INSERT INTO feature_store (
                match_id, generated_at, features_json, missing_flags_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                match_id,
                now,
                json.dumps(features),
                json.dumps(missing_flags),
                json.dumps(metadata or {}),
            ),
        )


def get_feature_store(match_id: int) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            "SELECT * FROM feature_store WHERE match_id = ? ORDER BY id DESC LIMIT 1",
            (match_id,),
        ).fetchone()


def upsert_tournament_simulation(n_simulations: int, results: dict[str, Any]) -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO tournament_simulations (generated_at, n_simulations, results_json)
            VALUES (?, ?, ?)
            """,
            (now, n_simulations, json.dumps(results)),
        )
        if config.USE_POSTGRES:
            row = conn.execute("SELECT currval(pg_get_serial_sequence('tournament_simulations','id')) AS id").fetchone()
            return int(row["id"])
        return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def get_latest_tournament_simulation() -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = _execute(
            conn,
            "SELECT * FROM tournament_simulations ORDER BY id DESC LIMIT 1",
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["results"] = json.loads(data["results_json"])
    return data
