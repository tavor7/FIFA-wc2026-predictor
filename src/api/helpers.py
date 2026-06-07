"""Shared API response helpers."""

from __future__ import annotations

import json
from typing import Any

from src import db
from src.team_flags import get_country_code, get_flag_url, slugify


def row_to_dict(row) -> dict[str, Any]:
    return dict(row) if row else {}


def team_meta(name: str) -> dict[str, str]:
    return {
        "name": name,
        "slug": slugify(name),
        "country_code": get_country_code(name) or "",
        "flag_url": get_flag_url(name),
    }


def prediction_payload(pred: dict[str, Any] | None) -> dict[str, Any] | None:
    if not pred:
        return None
    p = dict(pred)
    if p.get("top_scorelines_json"):
        p["top_scorelines"] = json.loads(p["top_scorelines_json"])
    if p.get("ensemble_json") and isinstance(p["ensemble_json"], str):
        p["ensemble_json"] = json.loads(p["ensemble_json"])
    if p.get("factor_breakdown_json") and isinstance(p["factor_breakdown_json"], str):
        p["factor_breakdown_json"] = json.loads(p["factor_breakdown_json"])
    return p


def match_with_prediction(row) -> dict[str, Any]:
    m = row_to_dict(row)
    if not m:
        return {}
    pred = db.get_prediction(int(m["id"]))
    if pred:
        p = prediction_payload(dict(pred))
        m["prediction"] = {
            "predicted_home_goals": p["predicted_home_goals"],
            "predicted_away_goals": p["predicted_away_goals"],
            "home_win_prob": p["home_win_prob"],
            "draw_prob": p["draw_prob"],
            "away_win_prob": p["away_win_prob"],
            "exact_score_prob": p["exact_score_prob"],
            "top_scorelines": p.get("top_scorelines") or json.loads(p.get("top_scorelines_json") or "[]"),
            "explanation": p["explanation"],
            "generated_at": p["generated_at"],
            "confidence_pct": p.get("confidence_pct"),
            "data_completeness_pct": p.get("data_completeness_pct"),
            "model_agreement": p.get("model_agreement"),
            "ensemble": p.get("ensemble_json"),
            "factor_breakdown": p.get("factor_breakdown_json"),
        }
    m["home"] = team_meta(m["home_team"])
    m["away"] = team_meta(m["away_team"])
    return m
