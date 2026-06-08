"""Lightweight per-screen API payloads."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Optional

from src import config
from src import db
from src import db_extended as ext
from src import db_pipeline as pipe_db
from src.api.helpers import match_with_prediction, team_meta
from src.cache.response_cache import get_cache_meta

_app_start_time = datetime.utcnow().isoformat()
_scheduler_heartbeat: Optional[str] = None


def set_scheduler_heartbeat() -> None:
    global _scheduler_heartbeat
    _scheduler_heartbeat = datetime.utcnow().isoformat()


def _card_to_match_dict(card: dict[str, Any]) -> dict[str, Any]:
    """Convert match_cards_cache row to API match + prediction shape."""
    top = card.get("top_scorelines") or []
    if not top and card.get("top_scorelines_json"):
        try:
            top = json.loads(card["top_scorelines_json"])
        except (json.JSONDecodeError, TypeError):
            top = []

    expl = card.get("explanation_summary") or card.get("explanation_summary_json")
    if isinstance(expl, str):
        try:
            expl = json.loads(expl)
        except json.JSONDecodeError:
            expl = None

    completeness = card.get("completeness_flags") or card.get("completeness_flags_json")
    if isinstance(completeness, str):
        try:
            completeness = json.loads(completeness)
        except json.JSONDecodeError:
            completeness = None

    prediction = None
    if card.get("home_win_prob") is not None:
        prediction = {
            "predicted_home_goals": card.get("predicted_home"),
            "predicted_away_goals": card.get("predicted_away"),
            "home_win_prob": card.get("home_win_prob"),
            "draw_prob": card.get("draw_prob"),
            "away_win_prob": card.get("away_win_prob"),
            "exact_score_prob": card.get("exact_score_prob"),
            "top_scorelines": top[:3],
            "confidence_pct": card.get("confidence_pct"),
            "prediction_source_mode": card.get("prediction_source_mode"),
            "completeness_flags": completeness,
            "explanation_json": expl,
            "generated_at": card.get("last_prediction_update"),
        }

    return {
        "id": card["match_id"],
        "home_team": card["home_team"],
        "away_team": card["away_team"],
        "date": card["date"],
        "status": card.get("status"),
        "stage": card.get("stage"),
        "group_name": card.get("group_name"),
        "home_goals": card.get("home_goals"),
        "away_goals": card.get("away_goals"),
        "home": {
            "name": card["home_team"],
            "slug": card.get("home_slug"),
            "flag_url": card.get("home_flag_url"),
        },
        "away": {
            "name": card["away_team"],
            "slug": card.get("away_slug"),
            "flag_url": card.get("away_flag_url"),
        },
        "prediction": prediction,
    }


def get_home_screen(limit: int = 8) -> dict[str, Any]:
    cached = pipe_db.get_home_view_cache()
    meta = get_cache_meta()

    if cached and cached.get("payload"):
        payload = cached["payload"]
        live = [_card_to_match_dict(c) for c in payload.get("live", [])[:4]]
        upcoming = [_card_to_match_dict(c) for c in payload.get("upcoming", [])[:limit]]
        return {
            "stats": payload.get("stats", {}),
            "live": live,
            "matches": upcoming,
            "last_updated": payload.get("last_updated") or cached.get("computed_at"),
            "data_version": payload.get("data_version") or meta.get("data_version"),
        }

    from src.api.helpers import home_dashboard
    data = home_dashboard(limit=limit)
    return {
        **data,
        "live": [],
        "last_updated": datetime.utcnow().isoformat(),
        "data_version": meta.get("data_version") or "",
    }


def get_matches_screen(
    status: str = "upcoming",
    stage: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    result = pipe_db.get_match_cards_cached(
        status_filter=status if status != "all" else None,
        stage=stage,
        page=page,
        page_size=page_size,
    )
    if result["total"] > 0:
        return {
            "matches": [_card_to_match_dict(c) for c in result["items"]],
            "pagination": {
                "page": result["page"],
                "page_size": result["page_size"],
                "total": result["total"],
                "pages": result["pages"],
            },
            "last_updated": result["items"][0].get("computed_at") if result["items"] else None,
        }

    from src.api.helpers import matches_with_predictions
    if status == "live":
        rows = db.get_live_matches(tournament_only=True)
    elif status == "finished":
        rows = db.get_recent_matches(limit=page_size * page, tournament_only=True)
    else:
        rows = db.get_upcoming_matches(limit=page_size, tournament_only=True)
    matches = matches_with_predictions(rows)
    return {
        "matches": matches,
        "pagination": {"page": 1, "page_size": len(matches), "total": len(matches), "pages": 1},
        "last_updated": datetime.utcnow().isoformat(),
    }


def get_match_detail_screen(match_id: int) -> dict[str, Any]:
    card = pipe_db.get_match_card_cached(match_id)
    row = db.get_match_by_id(match_id)
    if not row:
        return {}
    detail = match_with_prediction(row)
    if card:
        cached_match = _card_to_match_dict(dict(card))
        if cached_match.get("prediction"):
            detail["prediction"] = {
                **(detail.get("prediction") or {}),
                **cached_match["prediction"],
            }
    detail["injuries"] = [
        dict(i) for i in db.get_injuries_for_teams([detail["home_team"], detail["away_team"]])
    ]
    detail["lineups"] = [dict(l) for l in db.get_lineups(match_id)]
    detail["team_stats"] = [dict(s) for s in db.get_team_match_stats(match_id)]
    detail["events"] = [dict(e) for e in ext.get_match_events(match_id)]
    detail["weather"] = dict(ext.get_weather_forecast(match_id) or {})
    fs = db.get_feature_store(match_id)
    if fs:
        fs_d = dict(fs)
        detail["features"] = {
            "features": json.loads(fs_d.get("features_json") or "{}"),
            "missing_flags": json.loads(fs_d.get("missing_flags_json") or "{}"),
            "metadata": json.loads(fs_d.get("metadata_json") or "{}"),
        }
    return detail


def get_teams_screen(page: int = 1, page_size: int = 48) -> dict[str, Any]:
    result = pipe_db.get_team_cards_cached(page=page, page_size=page_size)
    if result["total"] > 0:
        return {
            "teams": result["items"],
            "pagination": {
                "page": result["page"],
                "page_size": result["page_size"],
                "total": result["total"],
                "pages": result["pages"],
            },
            "last_updated": result["items"][0].get("computed_at") if result["items"] else None,
        }
    from src import db_extended as ext2
    from src.api.helpers import team_meta as tm
    teams = []
    for t in ext2.get_tournament_teams():
        d = dict(t)
        d["flag_url"] = tm(d["name"])["flag_url"]
        teams.append(d)
    return {
        "teams": teams,
        "pagination": {"page": 1, "page_size": len(teams), "total": len(teams), "pages": 1},
        "last_updated": datetime.utcnow().isoformat(),
    }


def get_monitor_screen() -> dict[str, Any]:
    t0 = time.perf_counter()
    counts = pipe_db.get_pipeline_aggregate_counts()
    db_ping_ms = round((time.perf_counter() - t0) * 1000, 1)

    latest_runs = pipe_db.get_latest_pipeline_runs_per_service()
    failed = [r for r in latest_runs if r.get("status") == "failed"]
    progress = pipe_db.get_active_pipeline_progress()

    import os
    return {
        "database": db.db_backend(),
        "health": "ok",
        "counts": counts,
        "table_counts": counts,
        "pipeline_runs": latest_runs,
        "active_progress": progress,
        "failed_jobs": failed,
        "latest_errors": {
            r["service_name"]: r.get("error_message")
            for r in latest_runs
            if r.get("error_message")
        },
        "deployment": {
            "app_start_time": _app_start_time,
            "database_latency_ms": db_ping_ms,
            "scheduler_enabled": os.getenv("ENABLE_SCHEDULER", "true").lower() in ("1", "true", "yes"),
            "last_scheduler_heartbeat": _scheduler_heartbeat,
            "app_version": config.APP_VERSION,
            "git_commit": config.GIT_COMMIT,
        },
        "stats": {
            "upcoming": counts.get("fixtures", 0),
            "predictions": counts.get("predictions", 0),
            "teams": counts.get("teams", 0),
            "missing_predictions": counts.get("missing_predictions", 0),
        },
        "success_criteria": {
            "all_predictions_present": counts.get("missing_predictions", 0) == 0,
            "all_explanations_present": None,
            "cache_valid": None,
        },
        "last_updated": datetime.utcnow().isoformat(),
    }
