"""Decide which pipeline steps still need to run (skip work already done)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from src import config, db
from src import db_extended as ext
from src import db_pipeline as pipe_db
from src.db_pipeline import PIPELINE_MODES, PIPELINE_STEPS, STEP_LABELS
from src.seed.import_fc26_players import needs_fc26_reimport, squad_size_target

logger = logging.getLogger(__name__)

# Max age before a sync step is considered stale
FIXTURES_MAX_AGE_H = 6.0
SQUADS_MAX_AGE_H = 12.0
INJURIES_MAX_AGE_H = 6.0
PREDICTIONS_MAX_AGE_H = 6.0
CACHE_MAX_AGE_H = 2.0


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except ValueError:
        return None


def _hours_since(value: Optional[str]) -> Optional[float]:
    ts = _parse_ts(value)
    if not ts:
        return None
    return (datetime.utcnow() - ts).total_seconds() / 3600.0


def _freshness_recent(entity: str, max_hours: float) -> bool:
    row = ext.get_data_freshness(entity)
    if not row:
        return False
    age = _hours_since(dict(row).get("last_updated"))
    return age is not None and age <= max_hours


def _target_match_ids() -> list[int]:
    upcoming = db.get_upcoming_matches(limit=500, tournament_only=True)
    live = db.get_live_matches(tournament_only=True)
    seen = {int(m["id"]) for m in upcoming}
    for m in live:
        if int(m["id"]) not in seen:
            seen.add(int(m["id"]))
    return sorted(seen)


def missing_prediction_ids() -> list[int]:
    ids = _target_match_ids()
    if not ids:
        return []
    pred_map = db.get_predictions_for_match_ids(ids)
    return [mid for mid in ids if mid not in pred_map]


def thin_squad_teams() -> list[str]:
    target = squad_size_target()
    per_team = ext.fc26_per_team_counts()
    thin: list[str] = []
    for row in ext.get_tournament_teams():
        if per_team.get(int(row["id"]), 0) < target:
            thin.append(row["name"])
    return thin


def ui_cache_is_fresh() -> bool:
    home = pipe_db.get_home_view_cache()
    if not home:
        return False
    age = _hours_since(dict(home).get("computed_at"))
    if age is None or age > CACHE_MAX_AGE_H:
        return False
    try:
        with db.get_connection() as conn:
            from src.db import _execute

            cards = int(
                dict(_execute(conn, "SELECT COUNT(*) AS c FROM match_cards_cache").fetchone())["c"]
            )
            teams = int(
                dict(_execute(conn, "SELECT COUNT(*) AS c FROM team_cards_cache").fetchone())["c"]
            )
    except Exception:
        return False
    target_matches = len(_target_match_ids())
    if target_matches and cards < max(1, int(target_matches * 0.85)):
        return False
    if teams < 40:
        return False
    ids = _target_match_ids()
    if ids:
        card = pipe_db.get_match_card_cached(ids[0])
        if card and db.get_predictions_for_match_ids([ids[0]]).get(ids[0]):
            if card.get("home_win_prob") is None:
                return False
    return True


def _step_skip_reasons(mode: str, *, fast: bool = True) -> dict[int, str]:
    """Return step_index -> reason for steps that can be skipped."""
    skip: dict[int, str] = {}
    all_steps = PIPELINE_MODES.get(mode, PIPELINE_MODES["full_pipeline"])
    counts = pipe_db.get_pipeline_aggregate_counts()
    missing_preds = missing_prediction_ids()

    if 0 in all_steps:
        upcoming = len(_target_match_ids())
        if (
            counts.get("fixtures", 0) >= 36
            and upcoming >= 10
            and _freshness_recent("fixtures", FIXTURES_MAX_AGE_H)
        ):
            skip[0] = "fixtures already synced recently"

    if 1 in all_steps:
        thin = thin_squad_teams()
        squads_ok = not needs_fc26_reimport() and len(thin) == 0
        if squads_ok and _freshness_recent("team_stats", SQUADS_MAX_AGE_H):
            skip[1] = "Kaggle squads loaded and squads recently synced"
        elif not needs_fc26_reimport() and _freshness_recent("team_stats", SQUADS_MAX_AGE_H):
            if len(thin) <= 3:
                skip[1] = "squads mostly complete (few thin nations in Kaggle)"

    if 2 in all_steps:
        if _freshness_recent("injuries", INJURIES_MAX_AGE_H):
            skip[2] = "injuries recently synced"

    if 3 in all_steps:
        live = db.get_live_matches(tournament_only=True)
        if not live and _freshness_recent("fixtures", FIXTURES_MAX_AGE_H):
            skip[3] = "no live matches right now"

    if 4 in all_steps:
        if fast and mode == "full_pipeline":
            skip[4] = "features built during prediction step"
        else:
            ids = _target_match_ids()
            if ids:
                missing_fs = sum(1 for mid in ids if not db.get_feature_store(mid))
                if missing_fs == 0:
                    skip[4] = "features already stored for all matches"

    if 5 in all_steps and 4 in skip:
        skip[5] = "feature validation not needed"

    if 6 in all_steps:
        if not missing_preds and _freshness_recent("predictions", PREDICTIONS_MAX_AGE_H):
            skip[6] = f"predictions up to date ({counts.get('predictions', 0)} stored)"

    if 7 in all_steps and 6 in skip:
        skip[7] = "predictions already validated"

    if 8 in all_steps and 6 in skip:
        skip[8] = "explanations already in predictions"

    if 9 in all_steps and ui_cache_is_fresh():
        skip[9] = "UI cache is fresh"

    return skip


def plan_pipeline_steps(mode: str = "full_pipeline", *, fast: bool = True) -> dict[str, Any]:
    """
    Build a run plan: only steps that are still missing or stale.
    Scheduler / forced modes can pass skip_planning via orchestrator.
    """
    all_steps = PIPELINE_MODES.get(mode, PIPELINE_MODES["full_pipeline"])
    skip = _step_skip_reasons(mode, fast=fast)
    to_run = [i for i in all_steps if i not in skip]

    return {
        "mode": mode,
        "all_steps": all_steps,
        "steps_to_run": to_run,
        "steps_skipped": {
            PIPELINE_STEPS[i][0]: {"index": i, "label": STEP_LABELS[PIPELINE_STEPS[i][0]], "reason": skip[i]}
            for i in sorted(skip)
        },
        "skip_count": len(skip),
        "run_count": len(to_run),
        "nothing_to_do": len(to_run) == 0,
    }


def apply_skipped_progress(
    run_id: int,
    plan: dict[str, Any],
    active_indices: list[int],
) -> None:
    """Mark skipped steps complete in the progress UI and step-run history."""
    for _key, info in plan.get("steps_skipped", {}).items():
        idx = int(info["index"])
        step_key, step_name = PIPELINE_STEPS[idx]
        started = datetime.utcnow().isoformat()
        pipe_db.start_step_run(
            run_id, step_key, idx, step_name, status="skipped",
        )
        pipe_db.finish_step_run(
            run_id,
            step_key,
            status="skipped",
            error_message=info.get("reason"),
            started_at=started,
        )
        pipe_db.update_pipeline_progress(
            run_id,
            _key,
            idx,
            100.0,
            f"Skipped — {info['reason']}",
            active_step_indices=active_indices,
        )
