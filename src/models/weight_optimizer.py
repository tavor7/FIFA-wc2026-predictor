"""Optimize ensemble weights on validation data."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import numpy as np

from src import config
from src.features import MatchFeatures
from src.models.ensemble import EnsemblePredictor

logger = logging.getLogger(__name__)

CancelFn = Callable[[], bool]


def _weight_optimization_enabled() -> bool:
    flag = (config._env("ENABLE_WEIGHT_OPTIMIZATION") or "").lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    # Remote Postgres: each validation match triggers dozens of DB round-trips.
    return not config.USE_POSTGRES


def optimize_ensemble_weights(
    ensemble: EnsemblePredictor,
    *,
    match_ids: Optional[list[int]] = None,
    should_cancel: Optional[CancelFn] = None,
) -> dict[str, float]:
    """
    Grid search minimizing multiclass Brier on a small validation fold.

    Reuses match_ids from training when provided — avoids rebuilding the full
    feature matrix (very slow on remote Supabase).
    """
    from src import db
    from src.services.pipeline_cancel import ModelTrainingCancelled

    def _check() -> None:
        if should_cancel and should_cancel():
            raise ModelTrainingCancelled()

    base = ensemble._weights()
    if not _weight_optimization_enabled():
        logger.info("Using default ensemble weights (weight grid search disabled on remote DB)")
        return base

    try:
        finished_list = db.get_all_finished_matches()
        finished = {int(m["id"]): m for m in finished_list}
        ids = match_ids or [int(m["id"]) for m in finished_list]
        if len(ids) < 15:
            return base
    except Exception as exc:
        logger.warning("Weight optimization skipped: %s", exc)
        return base

    max_val = 12 if config.USE_POSTGRES else 40
    val_ids = ids[: min(max_val, len(ids))]

    _check()
    cached = _cache_validation_features(finished, val_ids, should_cancel=should_cancel)
    if len(cached) < 10:
        logger.info("Weight optimization skipped — only %d validation features", len(cached))
        return base

    if config.USE_POSTGRES:
        elo_vals = (0.20, 0.25)
        rf_vals = (0.35, 0.40)
    else:
        elo_vals = (0.15, 0.20, 0.25)
        rf_vals = (0.30, 0.35, 0.40)

    best = dict(base)
    best_score = float("inf")
    trials = 0

    for elo_w in elo_vals:
        for rf_w in rf_vals:
            _check()
            xgb_w = max(0.0, 1.0 - elo_w - rf_w)
            trial = {"elo": elo_w, "poisson_rf": rf_w, "xgboost": xgb_w}
            score = _validation_brier(ensemble, trial, cached)
            trials += 1
            if score < best_score:
                best_score = score
                best = trial

    logger.info("Weight optimization: %d trials on %d matches, best Brier %.4f", trials, len(cached), best_score)
    return best


def _cache_validation_features(
    finished: dict[int, Any],
    match_ids: list[int],
    *,
    should_cancel: Optional[CancelFn] = None,
) -> dict[int, tuple[Any, MatchFeatures]]:
    """Build features once per validation match (reused across grid trials)."""
    from src.services.feature_generation_service import FeatureGenerationService
    from src.services.pipeline_cancel import ModelTrainingCancelled

    svc = FeatureGenerationService()
    cached: dict[int, tuple[Any, MatchFeatures]] = {}
    for mid in match_ids:
        if should_cancel and should_cancel():
            raise ModelTrainingCancelled()
        m = finished.get(int(mid))
        if not m:
            continue
        try:
            cached[int(mid)] = (m, svc.build(m, for_training=True))
        except Exception as exc:
            logger.debug("Skip validation match %s: %s", mid, exc)
    return cached


def _validation_brier(
    ensemble: EnsemblePredictor,
    weights: dict[str, float],
    cached: dict[int, tuple[Any, MatchFeatures]],
) -> float:
    total = 0.0
    n = 0
    orig = ensemble.BASE_WEIGHTS
    try:
        ensemble.BASE_WEIGHTS = weights
        for _mid, (m, mf) in cached.items():
            result = ensemble.predict(mf)
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
    finally:
        ensemble.BASE_WEIGHTS = orig
    return total / max(n, 1)
