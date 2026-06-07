"""REST API routes for WC 2026 platform."""

from __future__ import annotations

import json
import logging
from typing import Any

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from src import db
from src import db_extended as ext
from src.analytics.momentum import MomentumEngine
from src.analytics.team_form import TeamFormAnalyzer
from src.api.admin_auth import require_admin, verify_password
from src.api.helpers import home_dashboard, match_with_prediction, matches_with_predictions, row_to_dict, team_meta
from src.api import screen_handlers
from src import db_pipeline as pipe_db
from src.cache.response_cache import (
    cache_key,
    get_cache_meta,
    get_cached,
    invalidate_all,
    set_cached,
    _ttl_for_path,
)
from src.services.pipeline_orchestrator import run_pipeline_async
from src.db import db_backend
from src.services.data_sync_service import DataSyncService
from src.services.model_training_service import ModelTrainingService
from src.services.prediction_generation_service import PredictionGenerationService
from src.services.explanation_service import ExplanationService
from src.analytics.computed_strength import recompute_and_persist
from src.sync_historical import sync_historical_seasons
from src.sync_injuries import sync_injuries
from src.sync_live_data import sync_live_data
from src.sync_matches import sync_all_matches
from src.bracket.knockout_view import build_knockout_view
from src.seed.load_seeds import api_keys_status, ensure_baseline_data, table_counts
from src.sync.sync_bracket import sync_bracket
from src.config import SEASON
from src.sync.sync_events import sync_events
from src.sync.sync_h2h import sync_h2h
from src.sync.sync_squads import sync_squads
from src.sync.sync_standings import sync_standings
from src.sync.sync_weather import sync_weather
from src.team_flags import slugify
from src.team_profiles import normalize_team_name, prior_metadata

AUTHOR = "Amit Tavor"


def _squad_player_payload(player: dict[str, Any], injured_names: set[str]) -> dict[str, Any]:
    """Serialize a squad row with injury flag and consistent rating scale."""
    d = row_to_dict(player) if not isinstance(player, dict) else dict(player)
    name = (d.get("name") or "").strip()
    d["injured"] = name.lower() in injured_names
    rating = d.get("rating")
    pid = d.get("api_player_id")
    if rating is not None and pid is not None and int(pid) < ext.FC26_ID_OFFSET and float(rating) <= 15:
        d["rating_scale"] = "api_match"
    else:
        d["rating_scale"] = "fc26"
    return d
DISCLAIMER = (
    "For educational and research purposes only. Not betting or financial advice. "
    "Not affiliated with FIFA. Use at your own discretion."
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _run_full_sync() -> None:
    sync_svc = DataSyncService()
    sync_svc.full_sync()
    PredictionGenerationService().generate_all()


def _run_data_sync_only() -> None:
    DataSyncService().full_sync()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "author": AUTHOR, "disclaimer": DISCLAIMER, "database": db_backend()}


@router.get("/meta")
def meta() -> dict[str, Any]:
    return {"author": AUTHOR, "disclaimer": DISCLAIMER, "disclaimer_short": "Research only. Not betting advice."}


@router.get("/meta/freshness")
def freshness() -> dict[str, Any]:
    rows = ext.get_all_data_freshness()
    snapshot = ext.build_freshness_snapshot()
    stale_msgs = ext.staleness_warnings(snapshot)
    warnings = [row_to_dict(r) for r in rows if float(dict(r).get("completeness_pct") or 100) < 70]
    latest_sync = ext.get_recent_sync_logs(limit=5)
    return {
        "entities": [row_to_dict(r) for r in rows],
        "warnings": [row_to_dict(r) for r in warnings],
        "staleness_warnings": stale_msgs,
        "recent_syncs": [row_to_dict(r) for r in latest_sync],
        "sources": ["api-football", "football-data.org", "open-meteo", "fc26-kaggle"],
    }


@router.get("/stats")
def stats() -> dict[str, int]:
    return db.get_platform_stats(tournament_only=True)


@router.get("/home")
def home(limit: int = 8) -> dict[str, Any]:
    """Home screen: stats + live + next N upcoming matches."""
    key = cache_key("/home", f"limit={limit}")
    hit = get_cached(key)
    if hit is not None:
        return hit
    payload = screen_handlers.get_home_screen(limit=limit)
    set_cached(key, payload, _ttl_for_path("/home"))
    return payload


@router.get("/matches")
def matches_list(
    status: str = "upcoming",
    stage: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Paginated matches list from read-model cache."""
    key = cache_key("/matches", f"status={status}&stage={stage}&page={page}&size={page_size}")
    hit = get_cached(key)
    if hit is not None:
        return hit
    payload = screen_handlers.get_matches_screen(status=status, stage=stage, page=page, page_size=page_size)
    set_cached(key, payload, _ttl_for_path("/matches"))
    return payload


@router.get("/matches/upcoming")
def upcoming_matches(limit: int = 72) -> list[dict[str, Any]]:
    return matches_with_predictions(db.get_upcoming_matches(limit=limit, tournament_only=True))


@router.get("/matches/live")
def live_matches() -> list[dict[str, Any]]:
    return matches_with_predictions(db.get_live_matches(tournament_only=True))


@router.get("/matches/recent")
def recent_matches(limit: int = 40) -> list[dict[str, Any]]:
    return matches_with_predictions(db.get_recent_matches(limit=limit, tournament_only=True))


@router.get("/teams")
def list_teams() -> list[dict[str, Any]]:
    teams = ext.get_tournament_teams()
    if not teams:
        from src.tournament_teams import get_wc2026_team_names

        for t in get_wc2026_team_names():
            ext.upsert_team(t, slug=slugify(t), country_code=team_meta(t)["country_code"])
        teams = ext.get_tournament_teams()
    out = []
    for t in teams:
        d = row_to_dict(t)
        d["flag_url"] = team_meta(d["name"])["flag_url"]
        out.append(d)
    return out


@router.get("/teams/{slug}")
def team_detail(slug: str) -> dict[str, Any]:
    team = ext.get_team_by_slug(slug)
    if not team:
        for m in db.get_upcoming_matches(limit=200):
            if slugify(m["home_team"]) == slug:
                ext.upsert_team(m["home_team"], slug=slugify(m["home_team"]))
                team = ext.get_team_by_slug(slug)
                break
            if slugify(m["away_team"]) == slug:
                ext.upsert_team(m["away_team"], slug=slugify(m["away_team"]))
                team = ext.get_team_by_slug(slug)
                break
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    name = team["name"]
    form = TeamFormAnalyzer().compute(name, datetime.utcnow().isoformat())
    momentum = MomentumEngine().compute(name, datetime.utcnow().isoformat()).to_dict()
    injuries = db.get_injuries_for_teams([name])
    injured_names = {(i["player_name"] or "").lower() for i in injuries}
    squad = ext.get_squad_players(int(team["id"])) if team.get("id") else []
    players = [_squad_player_payload(p, injured_names) for p in squad]

    return {
        "team": row_to_dict(team),
        "flag_url": team_meta(name)["flag_url"],
        "form": form.to_dict(),
        "momentum": momentum,
        "strength": prior_metadata(name),
        "players": players,
        "squad_source": "fc26" if ext.count_fc26_players_for_team(int(team["id"])) else "api",
        "injuries": [row_to_dict(i) for i in injuries],
        "history": row_to_dict(ext.get_team_history(name)) or {},
    }


@router.get("/teams/{slug}/squad")
def team_squad(slug: str) -> dict[str, Any]:
    detail = team_detail(slug)
    players = sorted(
        detail["players"],
        key=lambda p: (p.get("rating") or 0, p.get("form") or 0),
        reverse=True,
    )
    key_players = players[:5]
    return {"team": detail["team"], "squad": players, "key_players": key_players}


@router.get("/teams/{slug}/history")
def team_history(slug: str) -> dict[str, Any]:
    team = ext.get_team_by_slug(slug)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    hist = ext.get_team_history(team["name"])
    return {"team": row_to_dict(team), "history": row_to_dict(hist) if hist else {}}


@router.get("/matches/{match_id}/live-probs")
def match_live_probs(match_id: int) -> list[dict[str, Any]]:
    rows = ext.get_live_prob_history(match_id)
    return [row_to_dict(r) for r in rows]


@router.get("/matches/{match_id}/history")
def prediction_history(match_id: int) -> dict[str, Any]:
    svc = ExplanationService()
    summary = svc.match_change_summary(match_id)
    rows = ext.get_prediction_history(match_id)
    history = [row_to_dict(r) for r in rows]
    for row in history:
        if row.get("change_bullets_json") and isinstance(row["change_bullets_json"], str):
            try:
                row["change_bullets"] = json.loads(row["change_bullets_json"])
            except json.JSONDecodeError:
                row["change_bullets"] = []
    what_changed = summary.get("what_changed") or {}
    return {
        "match_id": match_id,
        "history": history,
        "what_changed": {
            "reason": summary.get("reason") or what_changed.get("summary"),
            "bullets": what_changed.get("bullets") or [],
            "previous_version": summary.get("previous_version"),
            "current_version": summary.get("current_version"),
        },
    }


@router.get("/matches/{match_id}")
def match_detail(match_id: int) -> dict[str, Any]:
    detail = screen_handlers.get_match_detail_screen(match_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Match not found")
    return detail


@router.get("/matches/{match_id}/legacy")
def match_detail_legacy(match_id: int) -> dict[str, Any]:
    row = db.get_match_by_id(match_id)
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")
    m = match_with_prediction(row)
    m["injuries"] = [row_to_dict(i) for i in db.get_injuries_for_teams([m["home_team"], m["away_team"]])]
    m["lineups"] = [row_to_dict(l) for l in db.get_lineups(match_id)]
    m["team_stats"] = [row_to_dict(s) for s in db.get_team_match_stats(match_id)]
    m["events"] = [row_to_dict(e) for e in ext.get_match_events(match_id)]
    m["weather"] = row_to_dict(ext.get_weather_forecast(match_id))
    fs = db.get_feature_store(match_id)
    if fs:
        fs_d = row_to_dict(fs)
        m["features"] = {
            "features": json.loads(fs_d.get("features_json") or "{}"),
            "missing_flags": json.loads(fs_d.get("missing_flags_json") or "{}"),
            "metadata": json.loads(fs_d.get("metadata_json") or "{}"),
        }
    return m


@router.get("/matches/{match_id}/timeline")
def match_timeline(match_id: int) -> list[dict[str, Any]]:
    events = ext.get_match_events(match_id)
    return [row_to_dict(e) for e in sorted(events, key=lambda x: dict(x).get("minute") or 0)]


@router.get("/matches/{match_id}/full")
def match_full(match_id: int) -> dict[str, Any]:
    return match_detail(match_id)


@router.get("/h2h/{team_a}/{team_b}")
def head_to_head(team_a: str, team_b: str) -> dict[str, Any]:
    a, b = normalize_team_name(team_a.replace("-", " ")), normalize_team_name(team_b.replace("-", " "))
    cached = ext.get_head_to_head(a, b)
    if cached:
        data = row_to_dict(cached)
        data["summary_json"] = json.loads(data.get("summary_json") or "{}")
        return data
    return {"team_a": a, "team_b": b, "summary_json": {}, "message": "No H2H cached yet"}


@router.get("/tournament/overview")
def tournament_overview() -> dict[str, Any]:
    standings = ext.get_all_standings(SEASON)
    groups: dict[str, list] = {}
    for s in standings:
        sd = row_to_dict(s)
        g = sd.get("group_name") or "Unknown"
        groups.setdefault(g, []).append(sd)
    return {
        "standings": groups,
        "upcoming": [match_with_prediction(m) for m in db.get_upcoming_matches(limit=50)],
        "simulation": db.get_latest_tournament_simulation(),
    }


@router.get("/tournament/knockout-bracket")
def knockout_bracket_view() -> dict[str, Any]:
    """Current-cup knockout view: round lists when scheduled, else next group matches."""
    return build_knockout_view()


@router.get("/tournament/bracket")
def tournament_bracket() -> list[dict[str, Any]]:
    nodes = ext.get_bracket_nodes()
    out = []
    for n in nodes:
        d = row_to_dict(n)
        if d.get("match_id"):
            m = db.get_match_by_id(int(d["match_id"]))
            if m:
                d["match"] = match_with_prediction(m)
        out.append(d)
    return out


@router.get("/players/leaders")
def player_leaders() -> dict[str, Any]:
    top_scorers = ext.get_player_leaderboard("goals", limit=20)
    top_assists = ext.get_player_leaderboard("assists", limit=20)
    top_ratings = ext.get_player_leaderboard("rating", limit=20)
    ratings_source = "match_stats"
    if not top_ratings:
        top_ratings = ext.get_squad_rating_leaders(limit=20)
        ratings_source = "fc26"
    return {
        "top_scorers": top_scorers,
        "top_assists": top_assists,
        "top_ratings": top_ratings,
        "ratings_source": ratings_source,
    }


@router.get("/players/{player_id}/trends")
def player_trends(player_id: int) -> dict[str, Any]:
    stats = ext.get_player_match_stats_history(player_id, limit=20)
    return {
        "player_id": player_id,
        "matches": [row_to_dict(s) for s in stats],
    }


@router.get("/reports/summary")
def reports_summary() -> dict[str, Any]:
    teams = ext.get_tournament_teams()
    momentum_rank = []
    for t in teams:
        snap = MomentumEngine().compute(t["name"], datetime.utcnow().isoformat())
        momentum_rank.append({"team": t["name"], "momentum": snap.score, "details": snap.to_dict()})
    momentum_rank.sort(key=lambda x: x["momentum"], reverse=True)
    return {
        "most_momentum": momentum_rank[:5],
        "least_momentum": momentum_rank[-5:][::-1] if len(momentum_rank) >= 5 else [],
        "prediction_count": len(db.get_all_predictions()),
        "upcoming_count": len(db.get_upcoming_matches(limit=200)),
    }


@router.get("/monitor/status")
def monitor_status() -> dict[str, Any]:
    key = cache_key("/monitor/status")
    hit = get_cached(key)
    if hit is not None:
        return hit
    logs = ext.get_recent_sync_logs(limit=10)
    keys = api_keys_status()
    payload = screen_handlers.get_monitor_screen()
    payload["api_keys"] = keys
    payload["recent_jobs"] = [row_to_dict(l) for l in logs]
    payload["models"] = {"ensemble": True, "elo": True, "xgboost_optional": True}
    payload["hints"] = _data_feed_hints(keys, payload.get("counts", {}))
    set_cached(key, payload, _ttl_for_path("/monitor/status"))
    return payload


@router.post("/admin/auth")
def admin_auth(body: dict[str, str]) -> dict[str, Any]:
    password = body.get("password", "")
    result = verify_password(password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid admin password")
    return result


@router.get("/admin/pipeline/status")
def admin_pipeline_status(_auth: None = Depends(require_admin)) -> dict[str, Any]:
    return {
        "runs": pipe_db.get_latest_pipeline_runs_per_service(),
        "active": pipe_db.get_active_pipeline_progress(),
    }


@router.get("/admin/pipeline/progress")
def admin_pipeline_progress() -> dict[str, Any]:
    return pipe_db.get_active_pipeline_progress()


@router.post("/admin/pipeline/run")
def admin_pipeline_run(
    mode: str = "full_pipeline",
    _auth: None = Depends(require_admin),
) -> dict[str, Any]:
    if mode not in ("full_pipeline", "data_sync_only", "features_only", "predictions_only"):
        raise HTTPException(status_code=400, detail="Invalid pipeline mode")
    run_id = run_pipeline_async(mode=mode, triggered_by="admin")
    invalidate_all()
    return {"status": "started", "run_id": run_id, "mode": mode}


def _data_feed_hints(keys: dict[str, Any], counts: dict[str, int]) -> list[str]:
    hints: list[str] = []
    if counts.get("matches", 0) < 10:
        hints.append("Run POST /seed to load bundled WC 2026 fixtures and group tables.")
    if not keys.get("any_configured"):
        hints.append("Set API_FOOTBALL_KEY and/or FOOTBALL_DATA_KEY in .env for live updates (players, events, injuries).")
    elif counts.get("players", 0) == 0:
        hints.append("Run POST /seed/players to load EA FC 26 squad ratings (Kaggle dataset).")
    if counts.get("standings", 0) == 0:
        hints.append("Run POST /seed to populate group standings from the official draw.")
    return hints


@router.post("/sync/historical")
def sync_historical() -> dict[str, Any]:
    """Sync 2018+2022 WC results and recompute data-driven team strength."""
    return sync_historical_seasons()


@router.post("/sync/matches")
def sync_matches(bg: BackgroundTasks) -> dict[str, Any]:
    result = sync_all_matches(days_ahead=120, days_back=30)
    bg.add_task(sync_standings)
    bg.add_task(sync_bracket)
    return {"status": "ok", "result": result}


@router.post("/sync/live")
def sync_live() -> dict[str, Any]:
    return sync_live_data()


@router.post("/sync/injuries")
def sync_inj() -> dict[str, Any]:
    return sync_injuries()


@router.post("/sync/full")
def sync_full(
    bg: BackgroundTasks,
    include_predictions: bool = False,
    _auth: None = Depends(require_admin),
) -> dict[str, str]:
    bg.add_task(_run_full_sync if include_predictions else _run_data_sync_only)
    return {
        "status": "started",
        "message": "Full sync running in background"
        + (" (with predictions)" if include_predictions else " (data only)"),
    }


@router.post("/admin/predictions/refresh")
def admin_refresh_predictions(bg: BackgroundTasks, _auth: None = Depends(require_admin)) -> dict[str, str]:
    def _job() -> None:
        PredictionGenerationService().generate_all()

    bg.add_task(_job)
    return {"status": "started", "message": "Regenerating all predictions in background"}


@router.post("/predictions/generate")
def gen_predictions(bg: BackgroundTasks) -> dict[str, Any]:
    def _job() -> None:
        if len(db.get_all_finished_matches()) < 10:
            sync_historical_seasons()
        PredictionGenerationService().generate_all()

    bg.add_task(_job)
    return {"status": "started", "message": "Prediction generation started"}


@router.post("/model/retrain")
def retrain() -> dict[str, Any]:
    return ModelTrainingService().retrain_and_predict()


@router.get("/evaluation/calibration")
def evaluation_calibration(limit: int = 50) -> dict[str, Any]:
    from src.evaluation.calibration import evaluate_stored_predictions

    return evaluate_stored_predictions(limit=limit)


@router.get("/evaluation/backtest/latest")
def evaluation_backtest_latest() -> dict[str, Any]:
    """Return last stored backtest run — no live computation."""
    row = ext.get_latest_backtest_run()
    if not row:
        return {"matches": 0, "message": "No backtest run yet. POST /model/retrain to generate one."}
    data = dict(row)
    metrics = data.get("metrics_json")
    if isinstance(metrics, str):
        try:
            metrics = json.loads(metrics)
        except json.JSONDecodeError:
            metrics = {}
    return metrics or {}


@router.get("/evaluation/backtest")
def evaluation_backtest(league: str = "World Cup", limit: int = 500) -> dict[str, Any]:
    """On-demand backtest (slow — admin/research only)."""
    from src.evaluation.backtest import backtest_tournament

    return backtest_tournament(league_filter=league, limit=limit)


@router.post("/seed/players")
def seed_players(bg: BackgroundTasks) -> dict[str, Any]:
    """Import EA FC 26 player ratings for WC squads (Kaggle dataset)."""
    from src.seed.import_fc26_players import import_fc26_players

    def _job() -> None:
        try:
            import_fc26_players(download=True)
        except Exception as exc:
            logger.exception("FC26 player import failed: %s", exc)

    bg.add_task(_job)
    return {
        "status": "started",
        "message": "Importing FC26 player squads in background (~1–2 min).",
    }


@router.post("/seed")
def seed_database(
    bg: BackgroundTasks,
    force: bool = False,
    quick: bool = False,
) -> dict[str, Any]:
    """Load bundled WC 2026 data. Full seed runs in background (avoids Render timeout)."""
    from src.seed.load_seeds import _run_seed_job, load_standings_only

    if quick:
        return load_standings_only()

    bg.add_task(_run_seed_job, force)
    return {
        "status": "started",
        "message": "Seed running in background (fixtures, standings, predictions). Refresh Monitor in 1–2 min.",
        "force": force,
    }


@router.get("/meta/data-status")
def data_status() -> dict[str, Any]:
    keys = api_keys_status()
    counts = table_counts()
    return {
        "api_keys": keys,
        "table_counts": counts,
        "hints": _data_feed_hints(keys, counts),
    }


@router.post("/bootstrap")
def bootstrap(bg: BackgroundTasks) -> dict[str, Any]:
    bg.add_task(_run_full_sync)
    return {
        "status": "started",
        "message": "Bootstrap running in background (sync + predictions)",
    }
