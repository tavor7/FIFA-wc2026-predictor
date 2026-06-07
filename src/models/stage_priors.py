"""Stage-based goal priors for tournament matches."""

from __future__ import annotations

from typing import Any, Optional

from src import db_pipeline as pipe_db

DEFAULT_PRIOR = {"avg_total_goals": 2.5, "avg_home_goals": 1.3, "avg_away_goals": 1.2}
PRIOR_WEIGHT = 0.15


def get_stage_prior(stage: Optional[str]) -> dict[str, Any]:
    row = pipe_db.get_stage_goal_prior(stage)
    if row:
        return row
    return {**DEFAULT_PRIOR, "stage_key": "group", "stage_label": "Group stage"}


def apply_stage_prior(
    lambda_home: float,
    lambda_away: float,
    stage: Optional[str],
    weight: float = PRIOR_WEIGHT,
) -> tuple[float, float, float]:
    """
    Soft blend of model lambdas with historical stage averages.
    Returns (lambda_home, lambda_away, contribution_strength).
    """
    prior = get_stage_prior(stage)
    p_home = float(prior.get("avg_home_goals") or prior["avg_total_goals"] / 2)
    p_away = float(prior.get("avg_away_goals") or prior["avg_total_goals"] / 2)
    blended_h = lambda_home * (1 - weight) + p_home * weight
    blended_a = lambda_away * (1 - weight) + p_away * weight
    return round(blended_h, 4), round(blended_a, 4), weight
