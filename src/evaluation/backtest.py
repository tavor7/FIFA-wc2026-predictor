"""Walk-forward backtesting on historical tournaments."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src import db
from src import db_extended as ext
from src.evaluation.calibration import (
    calibration_curve,
    expected_calibration_error,
    multiclass_brier,
    multiclass_log_loss,
)
from src.model import GoalPredictionModel
from src.models.ensemble import EnsemblePredictor
from src.features import build_features_for_match
from src.services.feature_generation_service import FeatureGenerationService

logger = logging.getLogger(__name__)


def backtest_tournament(
    league_filter: Optional[str] = None,
    limit: int = 500,
) -> dict[str, Any]:
    finished = [dict(m) for m in db.get_all_finished_matches()]
    if league_filter:
        finished = [m for m in finished if league_filter.lower() in (m.get("league") or "").lower()]
    finished = sorted(finished, key=lambda m: m["date"])[:limit]

    ensemble = EnsemblePredictor()
    feature_svc = FeatureGenerationService()
    exact = top3 = top5 = outcome = 0
    briers, loglosses, home_probs, home_outcomes = [], [], [], []

    for m in finished:
        mf = feature_svc.build(m, for_training=True)
        result = ensemble.predict(mf)
        scorelines = GoalPredictionModel.scoreline_distribution(result.lambda_home, result.lambda_away)
        top = GoalPredictionModel.top_scorelines(scorelines, n=5)
        best = top[0] if top else {"home": 0, "away": 0}
        hg, ag = int(m["home_goals"]), int(m["away_goals"])

        if int(best["home"]) == hg and int(best["away"]) == ag:
            exact += 1
        top3_set = {(t["home"], t["away"]) for t in top[:3]}
        top5_set = {(t["home"], t["away"]) for t in top[:5]}
        if (hg, ag) in top3_set:
            top3 += 1
        if (hg, ag) in top5_set:
            top5 += 1

        if hg > ag:
            idx, actual_outcome = 0, "home"
            home_outcomes.append(1)
        elif hg == ag:
            idx, actual_outcome = 1, "draw"
            home_outcomes.append(0)
        else:
            idx, actual_outcome = 2, "away"
            home_outcomes.append(0)

        probs = [result.home_win, result.draw, result.away_win]
        if (actual_outcome == "home" and result.home_win == max(probs)) or (
            actual_outcome == "draw" and result.draw == max(probs)
        ) or (actual_outcome == "away" and result.away_win == max(probs)):
            outcome += 1

        briers.append(multiclass_brier(probs, idx))
        loglosses.append(multiclass_log_loss(probs, idx))
        home_probs.append(result.home_win)

    n = max(len(finished), 1)
    metrics = {
        "matches": len(finished),
        "outcome_accuracy": round(outcome / n, 4),
        "exact_score_accuracy": round(exact / n, 4),
        "top3_scoreline_accuracy": round(top3 / n, 4),
        "top5_scoreline_accuracy": round(top5 / n, 4),
        "brier_score": round(sum(briers) / n, 4) if briers else None,
        "log_loss": round(sum(loglosses) / n, 4) if loglosses else None,
        "ece_home_win": round(expected_calibration_error(home_probs, home_outcomes), 4) if home_probs else None,
        "calibration_curve": calibration_curve(home_probs, home_outcomes) if home_probs else [],
    }
    ext.insert_backtest_run(league_filter or "all", metrics)
    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(backtest_tournament("World Cup"))
