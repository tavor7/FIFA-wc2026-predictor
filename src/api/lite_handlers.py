"""Minimal read-only payloads for fast home, match, team, and health screens."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from src import db
from src import db_extended as ext
from src import db_pipeline as pipe_db
from src.api.helpers import _list_prediction_dict, row_to_dict, team_meta
from src.cache.response_cache import get_cached, cache_key

_BASELINE_MODES = frozenset({
    "baseline_only",
    "heuristic_plus_elo",
    "insufficient_data",
    "ensemble_without_xgb",
})


def _short_explanation(pred: dict[str, Any]) -> str:
    text = (pred.get("explanation") or "").strip()
    mode = (pred.get("prediction_source_mode") or "").lower()
    if mode in _BASELINE_MODES and not text.lower().startswith("baseline"):
        text = f"Baseline prediction used because full data is not available yet. {text}".strip()
    if len(text) > 320:
        text = text[:317] + "…"
    return text


def _placeholder_prediction() -> dict[str, Any]:
    return {
        "predicted_home_goals": 1,
        "predicted_away_goals": 1,
        "home_win_prob": 0.33,
        "draw_prob": 0.34,
        "away_win_prob": 0.33,
        "top_scorelines": [{"home": 1, "away": 1, "probability": 0.11}],
        "confidence_pct": 0,
        "data_completeness_pct": 0,
        "prediction_source_mode": "pending",
        "explanation": "Prediction pending — use Monitor → Refresh predictions (admin).",
        "generated_at": None,
        "is_placeholder": True,
    }


def _lite_prediction(pred_row: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not pred_row:
        return _placeholder_prediction()
    lite = _list_prediction_dict(pred_row)
    lite["explanation"] = _short_explanation(lite)
    if lite.get("prediction_source_mode") in _BASELINE_MODES:
        lite["baseline_notice"] = "Baseline prediction used because full data is not available yet."
    return lite


def _match_lite_row(match: dict[str, Any], pred_map: dict[int, Any]) -> dict[str, Any]:
    mid = int(match["id"])
    pred_raw = pred_map.get(mid)
    pred = _lite_prediction(dict(pred_raw) if pred_raw else None)
    return {
        "id": mid,
        "home_team": match["home_team"],
        "away_team": match["away_team"],
        "date": match["date"],
        "status": match.get("status"),
        "stage": match.get("stage"),
        "group_name": match.get("group_name"),
        "home_goals": match.get("home_goals"),
        "away_goals": match.get("away_goals"),
        "home": team_meta(match["home_team"]),
        "away": team_meta(match["away_team"]),
        "prediction": pred,
    }


def get_home_lite(limit: int = 48, live_limit: int = 8) -> dict[str, Any]:
    feed = db.get_home_lite_feed(upcoming_limit=limit, live_limit=live_limit)
    pred_map = {mid: dict(r) for mid, r in feed["predictions"].items()}
    upcoming = [_match_lite_row(row_to_dict(r), pred_map) for r in feed["upcoming"]]
    live = [_match_lite_row(row_to_dict(r), pred_map) for r in feed["live"]]
    return {
        "stats": feed["stats"],
        "matches": upcoming,
        "live": live,
        "last_prediction_update": feed.get("last_prediction_update"),
        "last_updated": datetime.utcnow().isoformat(),
    }


def get_match_lite(match_id: int) -> Optional[dict[str, Any]]:
    bundle = db.get_match_lite_bundle(match_id)
    if not bundle:
        return None
    match = bundle["match"]
    pred = _lite_prediction(bundle.get("prediction"))
    out = _match_lite_row(match, {match_id: bundle.get("prediction")} if bundle.get("prediction") else {})
    out["prediction"] = pred
    out["injuries"] = bundle.get("injuries") or []
    if bundle.get("lineups"):
        out["lineups"] = bundle["lineups"]
    out["team_stats"] = bundle.get("team_stats") or []
    return out


def get_team_lite(slug: str) -> Optional[dict[str, Any]]:
    team = ext.get_team_by_slug(slug)
    if not team:
        return None
    name = team["name"]
    tid = int(team["id"])
    injuries = [row_to_dict(i) for i in db.get_injuries_for_teams([name])]
    squad = ext.get_squad_players(tid)[:18]
    players = [
        {
            "name": p.get("name"),
            "position": p.get("position"),
            "rating": p.get("rating"),
            "injured": (p.get("name") or "").lower() in {(i.get("player_name") or "").lower() for i in injuries},
        }
        for p in squad
    ]
    return {
        "team": row_to_dict(team),
        "flag_url": team_meta(name)["flag_url"],
        "players": players,
        "injuries": injuries,
        "squad_count": len(squad),
    }


def get_monitor_lite() -> dict[str, Any]:
    counts = pipe_db.get_pipeline_aggregate_counts()
    runs = pipe_db.get_latest_pipeline_runs_per_service()
    last_run = (
        max(runs, key=lambda r: r.get("finished_at") or r.get("started_at") or "")
        if runs
        else None
    )
    latest_pred = db.get_latest_prediction_timestamp()
    return {
        "database_connected": True,
        "database": db.db_backend(),
        "matches_count": counts.get("fixtures", 0),
        "predictions_count": counts.get("predictions", 0),
        "missing_predictions": counts.get("missing_predictions", 0),
        "last_prediction_update": latest_pred,
        "last_pipeline_run": {
            "id": last_run.get("id") if last_run else None,
            "status": last_run.get("status") if last_run else None,
            "service_name": last_run.get("service_name") if last_run else None,
            "finished_at": last_run.get("finished_at") if last_run else None,
            "error_message": last_run.get("error_message") if last_run else None,
        },
        "active_pipeline": pipe_db.get_active_pipeline_progress(),
    }


def get_core_status() -> dict[str, Any]:
    counts = pipe_db.get_pipeline_aggregate_counts()
    mode_counts = db.get_prediction_source_counts()
    empty_expl = db.count_empty_explanations()
    home_cache = get_cached(cache_key("/home-lite", "limit=48"))
    latest_pred = db.get_latest_prediction_timestamp()
    upcoming = counts.get("fixtures", 0)
    missing = counts.get("missing_predictions", 0)
    with_pred = max(0, upcoming - missing) if upcoming else 0
    return {
        "total_matches": counts.get("fixtures", 0),
        "upcoming_matches": upcoming,
        "predictions_total": counts.get("predictions", 0),
        "upcoming_matches_with_predictions": with_pred,
        "missing_predictions": missing,
        "baseline_predictions": mode_counts.get("baseline", 0),
        "full_model_predictions": mode_counts.get("full_model", 0),
        "empty_explanations": empty_expl,
        "cache_status": "warm" if home_cache else "cold",
        "latest_prediction_update": latest_pred,
    }
