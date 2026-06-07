"""Fallback predictions when full ensemble data is sparse."""

from __future__ import annotations

from typing import Any, Optional

from src.features import MatchFeatures
from src.model import GoalPredictionModel
from src.models.elo import EloModel
from src.models.stage_priors import apply_stage_prior


def baseline_predict(
    match_row: Any,
    features: MatchFeatures,
    elo: Optional[EloModel] = None,
) -> dict[str, Any]:
    """Elo + squad + stage prior baseline when ensemble is weak."""
    f = features.features
    elo_model = elo or EloModel().get_or_fit()
    home_elo = float(f.get("elo_home", 1500))
    away_elo = float(f.get("elo_away", 1500))
    diff = (home_elo - away_elo) / 400.0

    squad_h = float(f.get("starting_xi_strength_home", 0.55))
    squad_a = float(f.get("starting_xi_strength_away", 0.55))
    form_h = float(f.get("recent_form_home", 0.5))
    form_a = float(f.get("recent_form_away", 0.5))

    base_home = 1.1 + diff * 0.35 + (squad_h - 0.5) * 0.8 + (form_h - 0.5) * 0.5
    base_away = 1.0 - diff * 0.30 + (squad_a - 0.5) * 0.8 + (form_a - 0.5) * 0.5

    inj_h = float(f.get("injured_key_players_home_score", 0))
    inj_a = float(f.get("injured_key_players_away_score", 0))
    base_home *= max(0.7, 1.0 - inj_h * 0.25)
    base_away *= max(0.7, 1.0 - inj_a * 0.25)

    lh, la, _ = apply_stage_prior(
        max(0.3, base_home), max(0.3, base_away), match_row.get("stage")
    )

    scorelines = GoalPredictionModel.scoreline_distribution(lh, la)
    top5 = GoalPredictionModel.top_scorelines(scorelines, n=5)
    best = top5[0] if top5 else {"home": 1, "away": 1, "probability": 0.1}

    total = lh + la
    home_win = min(0.85, max(0.08, 0.35 + diff * 0.12 + (lh - la) * 0.08))
    away_win = min(0.85, max(0.08, 0.30 - diff * 0.12 + (la - lh) * 0.08))
    draw = max(0.05, 1.0 - home_win - away_win)

    missing = sum(1 for v in features.missing_flags.values() if v)
    mode = "baseline_only" if missing > 8 else "heuristic_plus_elo"

    return {
        "lambda_home": lh,
        "lambda_away": la,
        "lambda_home_mean": lh,
        "lambda_home_std": round(lh ** 0.5 * 0.15, 3),
        "lambda_away_mean": la,
        "lambda_away_std": round(la ** 0.5 * 0.15, 3),
        "home_win": round(home_win, 4),
        "draw": round(draw, 4),
        "away_win": round(away_win, 4),
        "top_scorelines": top5,
        "predicted_home_goals": int(best["home"]),
        "predicted_away_goals": int(best["away"]),
        "exact_score_prob": best["probability"],
        "prediction_source_mode": mode,
        "total_goals_hint": total,
    }
