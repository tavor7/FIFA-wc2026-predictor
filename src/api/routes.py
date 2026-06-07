"""REST API routes for WC 2026 platform."""

from __future__ import annotations

import json
from typing import Any

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException

from src import db
from src import db_extended as ext
from src.analytics.momentum import MomentumEngine
from src.analytics.team_form import TeamFormAnalyzer
from src.api.helpers import match_with_prediction, row_to_dict, team_meta
from src.db import db_backend
from src.predict import generate_predictions, retrain_and_predict
from src.sync_historical import sync_historical_seasons
from src.sync_injuries import sync_injuries
from src.sync_live_data import sync_live_data
from src.sync_matches import sync_all_matches
from src.sync.sync_bracket import sync_bracket
from src.config import SEASON
from src.sync.sync_events import sync_events
from src.sync.sync_h2h import sync_h2h
from src.sync.sync_squads import sync_squads
from src.sync.sync_standings import sync_standings
from src.sync.sync_weather import sync_weather
from src.team_flags import slugify
from src.team_profiles import normalize_team_name

AUTHOR = "Amit Tavor"
DISCLAIMER = (
    "For educational and research purposes only. Not betting or financial advice. "
    "Not affiliated with FIFA. Use at your own discretion."
)

router = APIRouter()


def _run_full_sync() -> None:
    if len(db.get_all_finished_matches()) < 10:
        sync_historical_seasons()
    sync_all_matches(days_ahead=120, days_back=30)
    sync_standings()
    sync_bracket()
    sync_squads()
    sync_h2h()
    sync_weather()
    sync_injuries()
    sync_events()
    generate_predictions()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "author": AUTHOR, "disclaimer": DISCLAIMER, "database": db_backend()}


@router.get("/meta")
def meta() -> dict[str, Any]:
    return {"author": AUTHOR, "disclaimer": DISCLAIMER, "disclaimer_short": "Research only. Not betting advice."}


@router.get("/meta/freshness")
def freshness() -> dict[str, Any]:
    rows = ext.get_all_data_freshness()
    warnings = [r for r in rows if float(r.get("completeness_pct") or 100) < 70]
    latest_sync = ext.get_recent_sync_logs(limit=5)
    return {
        "entities": [row_to_dict(r) for r in rows],
        "warnings": [row_to_dict(r) for r in warnings],
        "recent_syncs": [row_to_dict(r) for r in latest_sync],
        "sources": ["api-football", "football-data.org", "open-meteo"],
    }


@router.get("/stats")
def stats() -> dict[str, int]:
    return {
        "upcoming": len(db.get_upcoming_matches(limit=200)),
        "live": len(db.get_live_matches()),
        "predictions": len(db.get_all_predictions()),
        "teams": len(ext.get_all_teams()),
    }


@router.get("/teams")
def list_teams() -> list[dict[str, Any]]:
    teams = ext.get_all_teams()
    if not teams:
        seen: set[str] = set()
        for m in db.get_upcoming_matches(limit=200):
            for t in (m["home_team"], m["away_team"]):
                if t not in seen:
                    seen.add(t)
                    ext.upsert_team(t, slug=slugify(t), country_code=team_meta(t)["country_code"])
        teams = ext.get_all_teams()
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
    players = ext.get_players_by_team_id(int(team["id"])) if team.get("id") else []
    injuries = db.get_injuries_for_teams([name])

    return {
        "team": row_to_dict(team),
        "flag_url": team_meta(name)["flag_url"],
        "form": form.to_dict(),
        "momentum": momentum,
        "players": [row_to_dict(p) for p in players],
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


@router.get("/matches/upcoming")
def upcoming_matches() -> list[dict[str, Any]]:
    return [match_with_prediction(m) for m in db.get_upcoming_matches(limit=100)]


@router.get("/matches/live")
def live_matches() -> list[dict[str, Any]]:
    return [match_with_prediction(m) for m in db.get_live_matches()]


@router.get("/matches/recent")
def recent_matches(limit: int = 40) -> list[dict[str, Any]]:
    return [match_with_prediction(m) for m in db.get_recent_matches(limit=limit)]


@router.get("/matches/{match_id}/live-probs")
def match_live_probs(match_id: int) -> list[dict[str, Any]]:
    rows = ext.get_live_prob_history(match_id)
    return [row_to_dict(r) for r in rows]


@router.get("/matches/{match_id}/history")
def prediction_history(match_id: int) -> dict[str, Any]:
    rows = ext.get_prediction_history(match_id)
    history = [row_to_dict(r) for r in rows]
    what_changed = None
    if len(history) >= 2:
        latest, prev = history[0], history[1]
        what_changed = {
            "home_win_delta": (latest.get("home_win_prob") or 0) - (prev.get("home_win_prob") or 0),
            "reason": latest.get("reason_changed"),
            "previous_version": prev.get("version"),
            "current_version": latest.get("version"),
        }
    return {"match_id": match_id, "history": history, "what_changed": what_changed}


@router.get("/matches/{match_id}")
def match_detail(match_id: int) -> dict[str, Any]:
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
        m["features"] = {
            "features": json.loads(fs["features_json"] or "{}"),
            "missing_flags": json.loads(fs.get("missing_flags_json") or "{}"),
            "metadata": json.loads(fs.get("metadata_json") or "{}"),
        }
    return m


@router.get("/matches/{match_id}/timeline")
def match_timeline(match_id: int) -> list[dict[str, Any]]:
    events = ext.get_match_events(match_id)
    return [row_to_dict(e) for e in sorted(events, key=lambda x: x.get("minute") or 0)]


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
        g = s.get("group_name") or "Unknown"
        groups.setdefault(g, []).append(row_to_dict(s))
    return {
        "standings": groups,
        "upcoming": [match_with_prediction(m) for m in db.get_upcoming_matches(limit=50)],
        "simulation": db.get_latest_tournament_simulation(),
    }


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
    return {
        "top_scorers": ext.get_player_leaderboard("goals", limit=20),
        "top_assists": ext.get_player_leaderboard("assists", limit=20),
        "top_ratings": ext.get_player_leaderboard("rating", limit=20),
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
    teams = ext.get_all_teams()
    momentum_rank = []
    for t in teams[:30]:
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
    logs = ext.get_recent_sync_logs(limit=10)
    return {
        "database": db_backend(),
        "health": "ok",
        "recent_jobs": [row_to_dict(l) for l in logs],
        "stats": {
            "upcoming": len(db.get_upcoming_matches(limit=200)),
            "predictions": len(db.get_all_predictions()),
            "teams": len(ext.get_all_teams()),
        },
        "models": {"ensemble": True, "elo": True, "xgboost_optional": True},
    }


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
def sync_full(bg: BackgroundTasks) -> dict[str, str]:
    bg.add_task(_run_full_sync)
    return {"status": "started", "message": "Full sync running in background"}


@router.post("/predictions/generate")
def gen_predictions(bg: BackgroundTasks) -> dict[str, Any]:
    if len(db.get_all_finished_matches()) < 10:
        sync_historical_seasons()
    return generate_predictions()


@router.post("/model/retrain")
def retrain() -> dict[str, Any]:
    return retrain_and_predict()


@router.post("/bootstrap")
def bootstrap(bg: BackgroundTasks) -> dict[str, Any]:
    bg.add_task(_run_full_sync)
    return {
        "status": "started",
        "message": "Bootstrap running in background (sync + predictions)",
    }
