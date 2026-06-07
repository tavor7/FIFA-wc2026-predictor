"""Optimize ensemble weights on validation data."""

from __future__ import annotations

from typing import Any

import numpy as np

from src.features import build_training_dataset
from src.model import GoalPredictionModel
from src.models.ensemble import EnsemblePredictor


def optimize_ensemble_weights(ensemble: EnsemblePredictor) -> dict[str, float]:
    """Simple grid search minimizing multiclass Brier on training fold."""
    try:
        X, _, _, match_ids, _weights = build_training_dataset()
        if len(match_ids) < 15:
            return ensemble._weights()
    except Exception:
        return ensemble._weights()

    from src import db

    finished = {int(m["id"]): m for m in db.get_all_finished_matches()}
    base = ensemble._weights()
    best = dict(base)
    best_score = float("inf")

    for elo_w in (0.15, 0.20, 0.25):
        for rf_w in (0.30, 0.35, 0.40):
            xgb_w = max(0.0, 1.0 - elo_w - rf_w)
            trial = {"elo": elo_w, "poisson_rf": rf_w, "xgboost": xgb_w}
            score = _validation_brier(ensemble, trial, finished, match_ids[: min(40, len(match_ids))])
            if score < best_score:
                best_score = score
                best = trial
    return best


def _validation_brier(
    ensemble: EnsemblePredictor,
    weights: dict[str, float],
    finished: dict[int, Any],
    match_ids: list[int],
) -> float:
    total = 0.0
    n = 0
    for mid in match_ids:
        m = finished.get(int(mid))
        if not m:
            continue
        from src.services.feature_generation_service import FeatureGenerationService

        svc = FeatureGenerationService()
        mf = svc.build(m, for_training=True)
        orig = ensemble.BASE_WEIGHTS
        try:
            ensemble.BASE_WEIGHTS = weights
            result = ensemble.predict(mf)
        finally:
            ensemble.BASE_WEIGHTS = orig
        hg, ag = int(m["home_goals"]), int(m["away_goals"])
        if hg > ag:
            actual = [1, 0, 0]
        elif hg == ag:
            actual = [0, 1, 0]
        else:
            actual = [0, 0, 1]
        pred = [result.home_win, result.draw, result.away_win]
        total += float(np.sum((np.array(pred) - np.array(actual)) ** 2))
        n += 1
    return total / max(n, 1)
