"""Pipeline runs, progress tracking, and UI cache table access."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from src.db import Row, _execute, get_connection

PIPELINE_STEPS = [
    ("A", "sync_fixtures"),
    ("B", "sync_teams_squads"),
    ("C", "sync_injuries"),
    ("D", "sync_recent_results"),
    ("E", "generate_features"),
    ("F", "validate_features"),
    ("G", "generate_predictions"),
    ("H", "validate_predictions"),
    ("I", "generate_explanations"),
    ("J", "refresh_ui_cache"),
]

STEP_LABELS: dict[str, str] = {
    "A": "Syncing fixtures",
    "B": "Syncing teams & squads",
    "C": "Syncing injuries",
    "D": "Syncing live results",
    "E": "Generating features",
    "F": "Validating features",
    "G": "Generating predictions",
    "H": "Validating predictions",
    "I": "Building explanations",
    "J": "Updating app cache",
}

# Relative time weights (sum = 100)
STEP_WEIGHTS = [14, 10, 8, 8, 14, 4, 28, 4, 2, 8]

PHASE_GROUPS: list[tuple[str, list[int]]] = [
    ("Syncing data", [0, 1, 2, 3]),
    ("Building features", [4, 5]),
    ("Generating predictions", [6, 7, 8]),
    ("Updating cache", [9]),
]


def _phase_label_for_step(step_index: int) -> str:
    for label, indices in PHASE_GROUPS:
        if step_index in indices:
            return label
    return STEP_LABELS.get(PIPELINE_STEPS[step_index][0], "Running pipeline")


def compute_overall_pct(
    step_index: int,
    step_progress_pct: float,
    active_step_indices: list[int],
) -> float:
    """Weighted 0–100% based only on steps in the current pipeline mode."""
    if not active_step_indices:
        return 0.0
    if step_index not in active_step_indices:
        step_index = active_step_indices[0]

    weights = [STEP_WEIGHTS[i] for i in active_step_indices]
    total_weight = sum(weights) or 1
    pos = active_step_indices.index(step_index)
    completed_weight = sum(weights[:pos])
    current_weight = weights[pos]

    if step_progress_pct >= 100 and step_index == active_step_indices[-1]:
        return 100.0

    if step_progress_pct >= 100:
        frac = 1.0
    else:
        frac = max(step_progress_pct / 100.0, 0.12)

    overall = (completed_weight + current_weight * frac) / total_weight * 100
    return round(min(99.0, max(2.0, overall)), 1)


def start_pipeline_run(service_name: str, triggered_by: str = "scheduler") -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        if conn.__class__.__module__.startswith("psycopg"):
            row = conn.execute(
                """
                INSERT INTO pipeline_runs (started_at, service_name, status, triggered_by)
                VALUES (%s, %s, 'running', %s)
                RETURNING id
                """,
                (now, service_name, triggered_by),
            ).fetchone()
            run_id = int(row["id"])
        else:
            cur = _execute(
                conn,
                """
                INSERT INTO pipeline_runs (started_at, service_name, status, triggered_by)
                VALUES (?, ?, 'running', ?)
                """,
                (now, service_name, triggered_by),
            )
            run_id = int(cur.lastrowid)
        _execute(
            conn,
            """
            INSERT INTO pipeline_progress (
                run_id, current_step, step_index, total_steps,
                step_progress_pct, overall_progress_pct, message, updated_at
            ) VALUES (?, ?, 0, ?, 0, 0, 'Starting...', ?)
            ON CONFLICT(run_id) DO UPDATE SET
                current_step=excluded.current_step,
                step_index=excluded.step_index,
                step_progress_pct=0,
                overall_progress_pct=0,
                message=excluded.message,
                updated_at=excluded.updated_at
            """,
            (run_id, "A", len(PIPELINE_STEPS), now),
        )
    return run_id


def update_pipeline_progress(
    run_id: int,
    step_key: str,
    step_index: int,
    step_progress_pct: float,
    message: str,
    active_step_indices: Optional[list[int]] = None,
) -> None:
    active = active_step_indices or list(range(len(PIPELINE_STEPS)))
    overall = compute_overall_pct(step_index, step_progress_pct, active)
    total = len(active)
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        _execute(
            conn,
            """
            UPDATE pipeline_progress SET
                current_step = ?,
                step_index = ?,
                step_progress_pct = ?,
                overall_progress_pct = ?,
                message = ?,
                updated_at = ?
            WHERE run_id = ?
            """,
            (step_key, step_index, step_progress_pct, overall, message, now, run_id),
        )


def finish_pipeline_run(
    run_id: int,
    status: str,
    records_read: int = 0,
    records_written: int = 0,
    records_failed: int = 0,
    error_message: Optional[str] = None,
    started_at: Optional[str] = None,
) -> None:
    now = datetime.utcnow().isoformat()
    duration = None
    if started_at:
        try:
            start = datetime.fromisoformat(started_at.replace("Z", ""))
            end = datetime.fromisoformat(now.replace("Z", ""))
            duration = round((end - start).total_seconds(), 2)
        except ValueError:
            pass
    with get_connection() as conn:
        _execute(
            conn,
            """
            UPDATE pipeline_runs SET
                finished_at = ?,
                status = ?,
                records_read = ?,
                records_written = ?,
                records_failed = ?,
                duration_seconds = ?,
                error_message = ?
            WHERE id = ?
            """,
            (now, status, records_read, records_written, records_failed, duration, error_message, run_id),
        )
        if status in ("success", "failed", "partial"):
            _execute(conn, "DELETE FROM pipeline_progress WHERE run_id = ?", (run_id,))


def get_active_pipeline_progress() -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = _execute(
            conn,
            """
            SELECT p.*, r.started_at, r.service_name, r.triggered_by
            FROM pipeline_progress p
            JOIN pipeline_runs r ON r.id = p.run_id
            WHERE r.finished_at IS NULL
            ORDER BY p.updated_at DESC
            LIMIT 1
            """,
        ).fetchone()
    if not row:
        return {"running": False}
    d = dict(row)
    started = d.get("started_at")
    elapsed = 0.0
    if started:
        try:
            elapsed = round(
                (datetime.utcnow() - datetime.fromisoformat(started.replace("Z", ""))).total_seconds(), 1
            )
        except ValueError:
            pass
    step_idx = int(d["step_index"])
    phase = _phase_label_for_step(step_idx)
    step_key = d.get("current_step") or ""
    step_label = STEP_LABELS.get(step_key, phase)

    return {
        "running": True,
        "run_id": d["run_id"],
        "service_name": d.get("service_name"),
        "current_step": step_key,
        "step_index": step_idx,
        "total_steps": d["total_steps"],
        "step_progress_pct": d["step_progress_pct"],
        "overall_progress_pct": d["overall_progress_pct"],
        "phase_label": phase,
        "step_label": step_label,
        "message": d.get("message"),
        "elapsed_seconds": elapsed,
        "triggered_by": d.get("triggered_by"),
    }


def get_latest_pipeline_runs_per_service() -> list[dict[str, Any]]:
    with get_connection() as conn:
        is_pg = "psycopg" in type(conn).__module__
        if is_pg:
            rows = conn.execute(
                """
                SELECT DISTINCT ON (service_name) *
                FROM pipeline_runs
                ORDER BY service_name, finished_at DESC NULLS LAST, started_at DESC
                """
            ).fetchall()
        else:
            rows = _execute(
                conn,
                """
                SELECT r.* FROM pipeline_runs r
                INNER JOIN (
                    SELECT service_name, MAX(COALESCE(finished_at, started_at)) AS max_ts
                    FROM pipeline_runs GROUP BY service_name
                ) latest ON r.service_name = latest.service_name
                    AND COALESCE(r.finished_at, r.started_at) = latest.max_ts
                ORDER BY r.service_name
                """,
            ).fetchall()
    return [dict(r) for r in rows]


def get_pipeline_aggregate_counts() -> dict[str, int]:
    """Single-query monitor counts."""
    with get_connection() as conn:
        row = _execute(
            conn,
            """
            SELECT
                (SELECT COUNT(*) FROM matches) AS fixtures,
                (SELECT COUNT(*) FROM teams) AS teams,
                (SELECT COUNT(*) FROM players) AS players,
                (SELECT COUNT(*) FROM injuries) AS injuries,
                (SELECT COUNT(*) FROM predictions) AS predictions,
                (SELECT COUNT(*) FROM matches m
                 WHERE NOT EXISTS (SELECT 1 FROM predictions p WHERE p.match_id = m.id)
                   AND (m.status IN ('NS','TBD','SCHEDULED','TIMED','Not Started')
                        OR m.home_goals IS NULL)) AS missing_predictions
            """,
        ).fetchone()
    return {k: int(dict(row)[k]) for k in dict(row)}


def upsert_home_view_cache(payload: dict[str, Any]) -> None:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO home_view_cache (id, payload_json, computed_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                payload_json = excluded.payload_json,
                computed_at = excluded.computed_at
            """,
            (json.dumps(payload), now),
        )


def get_home_view_cache() -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = _execute(conn, "SELECT * FROM home_view_cache WHERE id = 1").fetchone()
    if not row:
        return None
    d = dict(row)
    d["payload"] = json.loads(d["payload_json"])
    return d


def clear_match_cards_cache() -> None:
    with get_connection() as conn:
        _execute(conn, "DELETE FROM match_cards_cache")


def upsert_match_card_cache(row: dict[str, Any]) -> None:
    now = datetime.utcnow().isoformat()
    fields = [
        "match_id", "home_team", "away_team", "home_slug", "away_slug",
        "home_flag_url", "away_flag_url", "date", "status", "stage", "group_name",
        "home_goals", "away_goals", "predicted_home", "predicted_away",
        "home_win_prob", "draw_prob", "away_win_prob", "exact_score_prob",
        "confidence_pct", "prediction_source_mode",
        "completeness_flags_json", "explanation_summary_json", "top_scorelines_json",
        "last_prediction_update", "computed_at",
    ]
    vals = []
    for f in fields:
        v = row.get(f)
        if f.endswith("_json") and isinstance(v, (dict, list)):
            v = json.dumps(v)
        if f == "computed_at" and v is None:
            v = now
        vals.append(v)
    placeholders = ",".join("?" * len(fields))
    updates = ", ".join(f"{f}=excluded.{f}" for f in fields if f != "match_id")
    with get_connection() as conn:
        _execute(
            conn,
            f"""
            INSERT INTO match_cards_cache ({', '.join(fields)})
            VALUES ({placeholders})
            ON CONFLICT(match_id) DO UPDATE SET {updates}
            """,
            vals,
        )


def get_match_cards_cached(
    status_filter: Optional[str] = None,
    stage: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    live_statuses = ("1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED")
    finished = ("FT", "AET", "PEN", "FINISHED")

    if status_filter == "live":
        clauses.append(f"status IN ({','.join('?' * len(live_statuses))})")
        params.extend(live_statuses)
    elif status_filter == "upcoming":
        clauses.append(
            "(status IN ('NS','TBD','SCHEDULED','TIMED','Not Started') OR "
            "(status NOT IN ('FT','AET','PEN','CANC','ABD','AWD','WO') AND home_goals IS NULL))"
        )
    elif status_filter == "finished":
        clauses.append(f"status IN ({','.join('?' * len(finished))})")
        params.extend(finished)

    if stage:
        clauses.append("stage = ?")
        params.append(stage)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    offset = (page - 1) * page_size

    with get_connection() as conn:
        total_row = _execute(
            conn, f"SELECT COUNT(*) AS c FROM match_cards_cache {where}", params
        ).fetchone()
        rows = _execute(
            conn,
            f"""
            SELECT * FROM match_cards_cache {where}
            ORDER BY date ASC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        ).fetchall()

    items = []
    for r in rows:
        d = dict(r)
        for key in ("completeness_flags_json", "explanation_summary_json", "top_scorelines_json"):
            if d.get(key) and isinstance(d[key], str):
                try:
                    d[key.replace("_json", "")] = json.loads(d[key])
                except json.JSONDecodeError:
                    pass
        items.append(d)

    total = int(dict(total_row)["c"])
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def get_match_card_cached(match_id: int) -> Optional[Row]:
    with get_connection() as conn:
        return _execute(
            conn, "SELECT * FROM match_cards_cache WHERE match_id = ?", (match_id,)
        ).fetchone()


def clear_team_cards_cache() -> None:
    with get_connection() as conn:
        _execute(conn, "DELETE FROM team_cards_cache")


def upsert_team_card_cache(row: dict[str, Any]) -> None:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO team_cards_cache (
                team_id, name, slug, flag_url, group_name, rating,
                recent_form, injury_count, momentum_score, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id) DO UPDATE SET
                name=excluded.name, slug=excluded.slug, flag_url=excluded.flag_url,
                group_name=excluded.group_name, rating=excluded.rating,
                recent_form=excluded.recent_form, injury_count=excluded.injury_count,
                momentum_score=excluded.momentum_score, computed_at=excluded.computed_at
            """,
            (
                row["team_id"], row["name"], row.get("slug"), row.get("flag_url"),
                row.get("group_name"), row.get("rating"), row.get("recent_form"),
                row.get("injury_count", 0), row.get("momentum_score"), now,
            ),
        )


def get_team_cards_cached(page: int = 1, page_size: int = 48) -> dict[str, Any]:
    offset = (page - 1) * page_size
    with get_connection() as conn:
        total_row = _execute(conn, "SELECT COUNT(*) AS c FROM team_cards_cache").fetchone()
        rows = _execute(
            conn,
            "SELECT * FROM team_cards_cache ORDER BY name LIMIT ? OFFSET ?",
            (page_size, offset),
        ).fetchall()
    total = int(dict(total_row)["c"])
    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def get_stage_goal_prior(stage: Optional[str]) -> Optional[dict[str, Any]]:
    if not stage:
        return None
    key = _normalize_stage_key(stage)
    with get_connection() as conn:
        row = _execute(
            conn, "SELECT * FROM stage_goal_priors WHERE stage_key = ?", (key,)
        ).fetchone()
    return dict(row) if row else None


def _normalize_stage_key(stage: str) -> str:
    s = stage.lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "group_stage": "group",
        "group": "group",
        "round_of_32": "round_of_32",
        "round_of_16": "round_of_16",
        "quarter_final": "quarter_finals",
        "quarter_finals": "quarter_finals",
        "semi_final": "semi_finals",
        "semi_finals": "semi_finals",
        "3rd_place": "third_place",
        "third_place": "third_place",
        "final": "final",
    }
    for k, v in mapping.items():
        if k in s:
            return v
    return "group"
