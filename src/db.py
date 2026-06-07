"""Database layer — Supabase Postgres (production) or SQLite (local dev)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator, Optional, Union

from src import config

Row = Union[dict[str, Any], sqlite3.Row]


def _adapt_sql(sql: str) -> str:
    """Convert SQLite-style ? placeholders to PostgreSQL %s when needed."""
    if config.USE_POSTGRES:
        return sql.replace("?", "%s")
    return sql


def _normalize_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def _ensure_db_dir() -> None:
    if not config.USE_POSTGRES:
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection() -> Generator[Any, None, None]:
    """Yield a database connection (SQLite or Supabase Postgres)."""
    _ensure_db_dir()
    if config.USE_POSTGRES:
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(
            _normalize_db_url(config.DATABASE_URL),
            row_factory=dict_row,
        )
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
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
            if stmt.upper().startswith("CREATE INDEX") or stmt.upper().startswith("CREATE TABLE"):
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
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
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
    match_id: int, predicted_home_goals: float, predicted_away_goals: float,
    home_win_prob: float, draw_prob: float, away_win_prob: float,
    exact_score_prob: float, top_scorelines: list[dict[str, Any]], explanation: str,
) -> None:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO predictions (
                match_id, generated_at, predicted_home_goals, predicted_away_goals,
                home_win_prob, draw_prob, away_win_prob, exact_score_prob,
                top_scorelines_json, explanation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                generated_at=excluded.generated_at,
                predicted_home_goals=excluded.predicted_home_goals,
                predicted_away_goals=excluded.predicted_away_goals,
                home_win_prob=excluded.home_win_prob,
                draw_prob=excluded.draw_prob,
                away_win_prob=excluded.away_win_prob,
                exact_score_prob=excluded.exact_score_prob,
                top_scorelines_json=excluded.top_scorelines_json,
                explanation=excluded.explanation
            """,
            (
                match_id, now, predicted_home_goals, predicted_away_goals,
                home_win_prob, draw_prob, away_win_prob, exact_score_prob,
                json.dumps(top_scorelines), explanation,
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


def get_matches_by_status(statuses: list[str]) -> list[Row]:
    placeholders = ",".join("?" * len(statuses))
    with get_connection() as conn:
        return _execute(
            conn,
            f"SELECT * FROM matches WHERE status IN ({placeholders}) ORDER BY date",
            statuses,
        ).fetchall()


def get_upcoming_matches(limit: int = 50) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM matches
            WHERE status IN ('NS', 'TBD', 'SCHEDULED', 'TIMED', 'Not Started')
               OR (status NOT IN ('FT', 'AET', 'PEN', 'CANC', 'ABD', 'AWD', 'WO')
                   AND home_goals IS NULL)
            ORDER BY date ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def get_live_matches() -> list[Row]:
    return get_matches_by_status(["1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED"])


def get_recent_matches(limit: int = 50) -> list[Row]:
    with get_connection() as conn:
        return _execute(
            conn,
            """
            SELECT * FROM matches
            WHERE status IN ('FT', 'AET', 'PEN', 'FINISHED')
            ORDER BY date DESC
            LIMIT ?
            """,
            (limit,),
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
