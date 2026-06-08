"""Diagnostics, audit reports, and data-flow analysis for the Monitor console."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional

from src import config, db
from src import db_extended as ext
from src import db_pipeline as pipe_db
from src.db import _execute, get_connection
from src.seed.import_fc26_players import squad_size_target
from src.services.pipeline_planner import missing_prediction_ids


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


def _target_matches() -> list[dict[str, Any]]:
    upcoming = db.get_upcoming_matches(limit=500, tournament_only=True)
    live = db.get_live_matches(tournament_only=True)
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for m in live + upcoming:
        mid = int(m["id"])
        if mid not in seen:
            seen.add(mid)
            out.append(dict(m))
    return out


def _json_load(raw: Any) -> Any:
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw


def _missing_data_reasons(pred: Optional[dict], expl: Any, flags: Any, val_errors: Any) -> list[str]:
    reasons: list[str] = []
    if expl and isinstance(expl, dict):
        for item in expl.get("missing_data") or []:
            if item and item not in reasons:
                reasons.append(str(item))
    if flags and isinstance(flags, dict):
        for item in flags.get("confidence_penalty_reasons") or []:
            if item and item not in reasons:
                reasons.append(str(item))
    if val_errors:
        if isinstance(val_errors, str):
            val_errors = _json_load(val_errors)
        if isinstance(val_errors, list):
            reasons.extend(str(e) for e in val_errors if e)
    return reasons


def get_prediction_audit(*, limit: int = 500, offset: int = 0) -> dict[str, Any]:
    matches = _target_matches()
    if not matches:
        return {"items": [], "summary": _empty_summary(), "total": 0, "limit": limit, "offset": offset}

    ids = [int(m["id"]) for m in matches]
    pred_map = db.get_predictions_for_match_ids(ids)
    cache_map: dict[int, dict] = {}
    with get_connection() as conn:
        if ids:
            placeholders = ",".join("?" * len(ids))
            rows = _execute(
                conn,
                f"SELECT * FROM match_cards_cache WHERE match_id IN ({placeholders})",
                ids,
            ).fetchall()
            cache_map = {int(dict(r)["match_id"]): dict(r) for r in rows}

    items: list[dict[str, Any]] = []
    summary = {
        "total_upcoming_matches": len(matches),
        "predictions_generated": 0,
        "missing_predictions": 0,
        "full_model": 0,
        "ensemble_without_xgb": 0,
        "heuristic_plus_elo": 0,
        "baseline_only": 0,
        "insufficient_data": 0,
        "empty_explanations": 0,
        "missing_features": 0,
        "stale_cache_entries": 0,
        "failed_pipeline_steps": len(pipe_db.get_failed_step_runs(limit=100)),
    }

    mode_keys = (
        "full_model", "ensemble_without_xgb", "heuristic_plus_elo",
        "baseline_only", "insufficient_data",
    )

    for m in matches:
        mid = int(m["id"])
        pred_row = pred_map.get(mid)
        pred = dict(pred_row) if pred_row else None
        has_pred = pred is not None
        has_fs = db.get_feature_store(mid) is not None
        cache = cache_map.get(mid)
        expl = _json_load(pred.get("explanation_json")) if pred else None
        flags = _json_load(pred.get("completeness_flags_json")) if pred else None
        top_raw = pred.get("top_scorelines_json") if pred else None
        top = _json_load(top_raw) if top_raw else (pred.get("top_scorelines") if pred else None)
        top_line = None
        if top and isinstance(top, list) and top:
            t0 = top[0]
            top_line = f"{t0.get('home', 0)}-{t0.get('away', 0)}"

        has_expl = bool(
            (pred and pred.get("explanation"))
            or (expl and (expl.get("headline") or expl.get("summary")))
        )
        source_mode = pred.get("prediction_source_mode") if pred else None
        pred_at = pred.get("generated_at") if pred else None
        cache_at = cache.get("computed_at") if cache else None
        stale_cache = False
        if has_pred and cache_at and pred_at:
            stale_cache = cache_at < pred_at
        elif has_pred and not cache:
            stale_cache = True
        if stale_cache:
            summary["stale_cache_entries"] += 1

        if has_pred:
            summary["predictions_generated"] += 1
            if not has_expl:
                summary["empty_explanations"] += 1
            if source_mode in mode_keys:
                summary[source_mode] += 1
        else:
            summary["missing_predictions"] += 1
        if not has_fs:
            summary["missing_features"] += 1

        items.append({
            "match_id": mid,
            "home_team": m.get("home_team"),
            "away_team": m.get("away_team"),
            "kickoff": m.get("date"),
            "stage": m.get("stage"),
            "has_match_record": True,
            "has_feature_store": has_fs,
            "has_prediction": has_pred,
            "prediction_source_mode": source_mode,
            "has_explanation": has_expl,
            "confidence": pred.get("confidence_pct") if pred else None,
            "data_completeness": pred.get("data_completeness_pct") if pred else None,
            "top_scoreline": top_line,
            "lambda_home": pred.get("lambda_home_mean") if pred else None,
            "lambda_away": pred.get("lambda_away_mean") if pred else None,
            "model_version": pred.get("model_version") if pred else None,
            "last_prediction_update": pred_at,
            "is_present_in_match_cards_cache": cache is not None,
            "cache_last_updated": cache_at,
            "missing_data_reasons": _missing_data_reasons(
                pred, expl, flags, pred.get("validation_errors_json") if pred else None,
            ),
            "validation_status": pred.get("validation_status") if pred else None,
            "stale_cache": stale_cache,
        })

    page = items[offset: offset + limit]
    return {"items": page, "summary": summary, "total": len(items), "limit": limit, "offset": offset}


def _empty_summary() -> dict[str, int]:
    return {
        "total_upcoming_matches": 0,
        "predictions_generated": 0,
        "missing_predictions": 0,
        "full_model": 0,
        "ensemble_without_xgb": 0,
        "heuristic_plus_elo": 0,
        "baseline_only": 0,
        "insufficient_data": 0,
        "empty_explanations": 0,
        "missing_features": 0,
        "stale_cache_entries": 0,
        "failed_pipeline_steps": 0,
    }


def get_data_flow() -> dict[str, Any]:
    matches = _target_matches()
    ids = [int(m["id"]) for m in matches]
    n_matches = len(ids)

    n_features = 0
    n_predictions = 0
    n_explanations = 0
    n_cache = 0

    if ids:
        pred_map = db.get_predictions_for_match_ids(ids)
        n_predictions = len(pred_map)
        for mid in ids:
            if db.get_feature_store(mid):
                n_features += 1
            p = pred_map.get(mid)
            if p:
                pd = dict(p)
                expl = _json_load(pd.get("explanation_json"))
                if pd.get("explanation") or (expl and expl.get("headline")):
                    n_explanations += 1

        with get_connection() as conn:
            placeholders = ",".join("?" * len(ids))
            row = _execute(
                conn,
                f"SELECT COUNT(*) AS c FROM match_cards_cache WHERE match_id IN ({placeholders})",
                ids,
            ).fetchone()
            n_cache = int(dict(row)["c"])

    stages = [
        {"stage": "Matches", "key": "matches", "count": n_matches},
        {"stage": "Features", "key": "features", "count": n_features},
        {"stage": "Predictions", "key": "predictions", "count": n_predictions},
        {"stage": "Explanations", "key": "explanations", "count": n_explanations},
        {"stage": "UI Cache", "key": "ui_cache", "count": n_cache},
    ]
    prev = n_matches
    for s in stages[1:]:
        s["drop_off"] = prev - s["count"]
        prev = s["count"]

    return {
        "stages": stages,
        "matches_without_features": n_matches - n_features,
        "matches_without_predictions": n_matches - n_predictions,
        "predictions_without_explanations": n_predictions - n_explanations,
        "predictions_without_cache": n_predictions - n_cache,
        "missing_prediction_ids": missing_prediction_ids(),
    }


def get_cache_audit() -> dict[str, Any]:
    matches = _target_matches()
    ids = {int(m["id"]) for m in matches}
    items: list[dict[str, Any]] = []
    stale = orphan = missing = 0

    with get_connection() as conn:
        cache_rows = _execute(conn, "SELECT * FROM match_cards_cache").fetchall()
        pred_map = db.get_predictions_for_match_ids(list(ids)) if ids else {}

    for m in matches:
        mid = int(m["id"])
        pred = dict(pred_map[mid]) if mid in pred_map else None
        cache = next((dict(r) for r in cache_rows if int(dict(r)["match_id"]) == mid), None)
        pred_at = pred.get("generated_at") if pred else None
        cache_at = cache.get("computed_at") if cache else None
        status = "ok"
        if not cache:
            status = "missing"
            missing += 1
        elif pred_at and cache_at and cache_at < pred_at:
            status = "stale"
            stale += 1
        items.append({
            "match_id": mid,
            "home_team": m.get("home_team"),
            "away_team": m.get("away_team"),
            "source_table": "matches+predictions",
            "cache_table": "match_cards_cache",
            "cache_creation_time": cache_at,
            "cache_age_hours": _hours_since(cache_at),
            "source_data_age_hours": _hours_since(pred_at),
            "status": status,
        })

    for row in cache_rows:
        d = dict(row)
        mid = int(d["match_id"])
        if mid not in ids:
            orphan += 1
            items.append({
                "match_id": mid,
                "home_team": d.get("home_team"),
                "away_team": d.get("away_team"),
                "source_table": "matches",
                "cache_table": "match_cards_cache",
                "cache_creation_time": d.get("computed_at"),
                "cache_age_hours": _hours_since(d.get("computed_at")),
                "source_data_age_hours": None,
                "status": "orphan",
            })

    home = pipe_db.get_home_view_cache()
    team_count = 0
    with get_connection() as conn:
        row = _execute(conn, "SELECT COUNT(*) AS c FROM team_cards_cache").fetchone()
        team_count = int(dict(row)["c"])

    return {
        "match_cards": items,
        "summary": {
            "stale": stale,
            "orphan": orphan,
            "missing": missing,
            "ok": len([i for i in items if i["status"] == "ok"]),
        },
        "home_view_cache": {
            "source_table": "aggregated",
            "cache_creation_time": dict(home).get("computed_at") if home else None,
            "cache_age_hours": _hours_since(dict(home).get("computed_at") if home else None),
            "status": "ok" if home else "missing",
        },
        "team_cards_cache": {
            "count": team_count,
            "expected_min": 40,
            "status": "ok" if team_count >= 40 else "missing",
        },
    }


def get_data_quality_audit() -> dict[str, Any]:
    target = squad_size_target()
    teams_report: list[dict[str, Any]] = []
    thin_nations: list[str] = []
    missing_ratings = 0
    total_players = 0

    for row in ext.get_tournament_teams():
        tid = int(row["id"])
        name = row["name"]
        squad_n = ext.count_fc26_players_for_team(tid)
        with get_connection() as conn:
            inj_row = _execute(
                conn, "SELECT COUNT(*) AS c FROM injuries WHERE team = ?", (name,)
            ).fetchone()
            inj_n = int(dict(inj_row)["c"])
            rating_row = _execute(
                conn,
                "SELECT COUNT(*) AS c, AVG(rating) AS avg_r FROM players WHERE team_id = ? AND rating IS NOT NULL",
                (tid,),
            ).fetchone()
            rated_n = int(dict(rating_row)["c"])
            avg_rating = dict(rating_row).get("avg_r")
            cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()
            recent_row = _execute(
                conn,
                """
                SELECT COUNT(*) AS c FROM matches
                WHERE (home_team = ? OR away_team = ?)
                  AND status IN ('FT','AET','PEN','FINISHED')
                  AND date >= ?
                """,
                (name, name, cutoff),
            ).fetchone()
            recent_n = int(dict(recent_row)["c"])

        total_players += squad_n
        no_rating = squad_n - rated_n
        missing_ratings += max(0, no_rating)
        if squad_n < target:
            thin_nations.append(name)

        elo_rating = None
        try:
            from src.models.elo import EloModel
            elo_rating = EloModel().get_rating(name)
        except Exception:
            pass

        issues: list[str] = []
        if squad_n < target:
            issues.append(f"Squad thin ({squad_n}/{target})")
        if rated_n < squad_n * 0.8:
            issues.append("Missing player ratings")
        if inj_n == 0:
            issues.append("No injury records")
        if recent_n == 0:
            issues.append("No recent finished matches")

        teams_report.append({
            "team": name,
            "squad_size": squad_n,
            "squad_target": target,
            "avg_rating": round(float(avg_rating), 1) if avg_rating else None,
            "injuries": inj_n,
            "recent_matches_90d": recent_n,
            "elo_rating": round(elo_rating, 0) if elo_rating else None,
            "issues": issues,
            "status": "ok" if not issues else ("warn" if len(issues) <= 2 else "bad"),
        })

    with get_connection() as conn:
        fixture_row = _execute(
            conn,
            "SELECT COUNT(*) AS c FROM matches WHERE season = ?",
            (config.SEASON,),
        ).fetchone()
        fixture_n = int(dict(fixture_row)["c"])

    return {
        "teams": teams_report,
        "summary": {
            "teams_audited": len(teams_report),
            "thin_nations": thin_nations,
            "thin_nation_count": len(thin_nations),
            "total_players": total_players,
            "missing_ratings": missing_ratings,
            "fixtures_season": fixture_n,
            "missing_injuries_teams": sum(1 for t in teams_report if t["injuries"] == 0),
        },
        "reports": {
            "missing_players": thin_nations,
            "missing_injuries": [t["team"] for t in teams_report if t["injuries"] == 0],
            "missing_ratings": [t["team"] for t in teams_report if t["avg_rating"] is None],
            "missing_fixtures": fixture_n < 36,
        },
    }


def get_audit_summary() -> dict[str, Any]:
    audit = get_prediction_audit(limit=10000, offset=0)
    flow = get_data_flow()
    cache = get_cache_audit()
    quality = get_data_quality_audit()
    return {
        "predictions": audit["summary"],
        "data_flow": {
            "stages": flow["stages"],
            "missing_prediction_ids": len(flow["missing_prediction_ids"]),
        },
        "cache": cache["summary"],
        "data_quality": quality["summary"],
        "success_criteria": {
            "all_predictions_present": audit["summary"]["missing_predictions"] == 0,
            "all_explanations_present": audit["summary"]["empty_explanations"] == 0,
            "cache_valid": cache["summary"]["stale"] == 0 and cache["summary"]["missing"] == 0,
        },
    }


def repair_missing_predictions() -> dict[str, Any]:
    from src.services.prediction_generation_service import PredictionGenerationService
    from src.services.ui_cache_service import UICacheService

    before = len(missing_prediction_ids())
    result = PredictionGenerationService().generate_all(only_missing=False, run_simulation=False)
    cache = UICacheService().refresh_all()
    after = len(missing_prediction_ids())
    return {
        "missing_before": before,
        "missing_after": after,
        "generated": result.get("generated", 0),
        "errors": result.get("errors", 0),
        "cache_refreshed": cache.get("match_cards", 0),
    }
