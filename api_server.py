"""FastAPI REST backend for the Expo mobile app."""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src import db
from src.db import db_backend
from src.predict import generate_predictions, retrain_and_predict
from src.sync_injuries import sync_injuries
from src.sync_live_data import sync_live_data
from src.sync_matches import sync_all_matches
from src.sync_historical import sync_historical_seasons

AUTHOR = "Amit Tavor"
DISCLAIMER = (
    "For educational and research purposes only. Not betting or financial advice. "
    "Not affiliated with FIFA. Use at your own discretion."
)

app = FastAPI(
    title="WC 2026 Research API",
    description=f"Designed by {AUTHOR}. {DISCLAIMER}",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()


def _row(row) -> dict[str, Any]:
    return dict(row) if row else {}


def _match_with_prediction(row) -> dict[str, Any]:
    m = _row(row)
    if not m:
        return {}
    pred = db.get_prediction(int(m["id"]))
    if pred:
        m["prediction"] = {
            "predicted_home_goals": pred["predicted_home_goals"],
            "predicted_away_goals": pred["predicted_away_goals"],
            "home_win_prob": pred["home_win_prob"],
            "draw_prob": pred["draw_prob"],
            "away_win_prob": pred["away_win_prob"],
            "exact_score_prob": pred["exact_score_prob"],
            "top_scorelines": json.loads(pred["top_scorelines_json"] or "[]"),
            "explanation": pred["explanation"],
            "generated_at": pred["generated_at"],
        }
    return m


@app.get("/")
@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "author": AUTHOR,
        "disclaimer": DISCLAIMER,
        "database": db_backend(),
    }


@app.get("/meta")
def meta() -> dict[str, Any]:
    return {
        "author": AUTHOR,
        "disclaimer": DISCLAIMER,
        "disclaimer_short": "Research only. Not betting advice.",
    }


@app.get("/stats")
def stats() -> dict[str, int]:
    return {
        "upcoming": len(db.get_upcoming_matches(limit=200)),
        "live": len(db.get_live_matches()),
        "predictions": len(db.get_all_predictions()),
    }


@app.get("/matches/upcoming")
def upcoming_matches() -> list[dict[str, Any]]:
    return [_match_with_prediction(m) for m in db.get_upcoming_matches(limit=100)]


@app.get("/matches/live")
def live_matches() -> list[dict[str, Any]]:
    return [_match_with_prediction(m) for m in db.get_live_matches()]


@app.get("/matches/recent")
def recent_matches(limit: int = 40) -> list[dict[str, Any]]:
    return [_row(m) for m in db.get_recent_matches(limit=limit)]


@app.get("/matches/{match_id}")
def match_detail(match_id: int) -> dict[str, Any]:
    row = db.get_match_by_id(match_id)
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")
    m = _match_with_prediction(row)
    m["injuries"] = [
        _row(i) for i in db.get_injuries_for_teams([m["home_team"], m["away_team"]])
    ]
    m["lineups"] = [_row(l) for l in db.get_lineups(match_id)]
    m["team_stats"] = [_row(s) for s in db.get_team_match_stats(match_id)]
    return m


@app.post("/sync/matches")
def sync_matches() -> dict[str, Any]:
    return sync_all_matches()


@app.post("/sync/live")
def sync_live() -> dict[str, Any]:
    return sync_live_data()


@app.post("/sync/injuries")
def sync_inj() -> dict[str, Any]:
    return sync_injuries()


@app.post("/predictions/generate")
def gen_predictions() -> dict[str, Any]:
    """Regenerate predictions for all upcoming matches."""
    # Ensure historical context exists for team differentiation
    if len(db.get_all_finished_matches()) < 10:
        sync_historical_seasons()
    return generate_predictions()


@app.post("/model/retrain")
def retrain() -> dict[str, Any]:
    return retrain_and_predict()


@app.post("/bootstrap")
def bootstrap() -> dict[str, Any]:
    """Sync fixtures, historical data, and regenerate all predictions."""
    result: dict[str, Any] = {}

    if len(db.get_all_finished_matches()) < 10:
        result["historical"] = sync_historical_seasons()

    result["sync"] = sync_all_matches()
    result["predictions"] = generate_predictions()
    result["stats"] = {
        "upcoming": len(db.get_upcoming_matches(limit=200)),
        "finished": len(db.get_all_finished_matches()),
        "predictions": len(db.get_all_predictions()),
    }
    return result
