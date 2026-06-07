"""Generate and store match predictions."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src import db
from src import db_extended as ext
from src.analytics.monte_carlo import TournamentSimulator
from src.model_storage import save_models_after_train
from src.explain import compute_confidence, generate_explanation
from src.features import build_features_for_match
from src.model import GoalPredictionModel
from src.models.ensemble import EnsemblePredictor, get_or_create_ensemble

logger = logging.getLogger(__name__)


LIVE_STATUSES = {"1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY", "PAUSED"}


def _maybe_record_live_prob(match_row: Any, pred: dict[str, Any]) -> None:
    if match_row["status"] not in LIVE_STATUSES:
        return
    ext.insert_live_prob_snapshot(
        match_id=int(match_row["id"]),
        home_win_prob=pred["home_win_prob"],
        draw_prob=pred["draw_prob"],
        away_win_prob=pred["away_win_prob"],
    )


def _reason_changed(prev: dict[str, Any] | None, pred: dict[str, Any]) -> str | None:
    if not prev:
        return "Initial prediction"
    parts: list[str] = []
    dh = pred["home_win_prob"] - float(prev.get("home_win_prob") or 0)
    if abs(dh) >= 0.03:
        parts.append(f"Home win prob {'+' if dh > 0 else ''}{dh * 100:.1f}pp")
    if pred["predicted_home_goals"] != float(prev.get("predicted_home_goals") or 0) or pred[
        "predicted_away_goals"
    ] != float(prev.get("predicted_away_goals") or 0):
        parts.append(
            f"Score pick {int(prev.get('predicted_home_goals', 0))}–{int(prev.get('predicted_away_goals', 0))} → "
            f"{int(pred['predicted_home_goals'])}–{int(pred['predicted_away_goals'])}"
        )
    return "; ".join(parts) if parts else None


def _store_prediction_history(match_id: int, pred: dict[str, Any], features: dict[str, Any]) -> None:
    prev = ext.get_latest_prediction_history(match_id)
    version = ext.next_prediction_version(match_id)
    reason = _reason_changed(dict(prev) if prev else None, pred)
    if prev and not reason:
        return
    ext.insert_prediction_history(
        match_id=match_id,
        version=version,
        home_win_prob=pred["home_win_prob"],
        draw_prob=pred["draw_prob"],
        away_win_prob=pred["away_win_prob"],
        predicted_home_goals=pred["predicted_home_goals"],
        predicted_away_goals=pred["predicted_away_goals"],
        features=features,
        reason_changed=reason,
    )


def predict_match(
    match_row: Any,
    ensemble: Optional[EnsemblePredictor] = None,
) -> dict[str, Any]:
    """Generate ensemble prediction for a single match."""
    ensemble = ensemble or get_or_create_ensemble()
    mf = build_features_for_match(match_row)

    result = ensemble.predict(mf)
    lambda_home = result.lambda_home
    lambda_away = result.lambda_away

    scorelines = GoalPredictionModel.scoreline_distribution(lambda_home, lambda_away)
    outcomes = {
        "home_win": result.home_win,
        "draw": result.draw,
        "away_win": result.away_win,
    }
    top5 = GoalPredictionModel.top_scorelines(scorelines, n=5)

    confidence = compute_confidence(mf, result)
    best = top5[0] if top5 else {"home": 1, "away": 1, "probability": 0.1}
    pred_home = round(lambda_home, 2)
    pred_away = round(lambda_away, 2)

    explanation = generate_explanation(
        home_team=match_row["home_team"],
        away_team=match_row["away_team"],
        predicted_home=int(round(lambda_home)),
        predicted_away=int(round(lambda_away)),
        features=mf,
        top_scorelines=top5,
        outcomes=outcomes,
    )

    db.upsert_feature_store(
        match_id=int(match_row["id"]),
        features=mf.features,
        missing_flags=mf.missing_flags,
        metadata=mf.metadata,
    )

    result_payload = {
        "match_id": int(match_row["id"]),
        "predicted_home_goals": pred_home,
        "predicted_away_goals": pred_away,
        "home_win_prob": round(outcomes["home_win"], 4),
        "draw_prob": round(outcomes["draw"], 4),
        "away_win_prob": round(outcomes["away_win"], 4),
        "exact_score_prob": best["probability"],
        "top_scorelines": top5,
        "explanation": explanation,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "confidence_pct": confidence.confidence_pct,
        "data_completeness_pct": confidence.data_completeness_pct,
        "model_agreement": confidence.model_agreement,
        "ensemble_json": result.to_dict(),
        "factor_breakdown_json": confidence.to_dict(),
    }
    _store_prediction_history(int(match_row["id"]), result_payload, mf.features)
    _maybe_record_live_prob(match_row, result_payload)
    return result_payload


def generate_predictions(ensemble: Optional[EnsemblePredictor] = None) -> dict[str, Any]:
    """Generate predictions for all upcoming matches and store in DB."""
    db.init_db()
    ensemble = ensemble or get_or_create_ensemble()
    upcoming = db.get_upcoming_matches(limit=100)

    generated = 0
    errors = 0
    for match in upcoming:
        try:
            pred = predict_match(match, ensemble)
            db.upsert_prediction(
                match_id=pred["match_id"],
                predicted_home_goals=pred["predicted_home_goals"],
                predicted_away_goals=pred["predicted_away_goals"],
                home_win_prob=pred["home_win_prob"],
                draw_prob=pred["draw_prob"],
                away_win_prob=pred["away_win_prob"],
                exact_score_prob=pred["exact_score_prob"],
                top_scorelines=pred["top_scorelines"],
                explanation=pred["explanation"],
                confidence_pct=pred["confidence_pct"],
                data_completeness_pct=pred["data_completeness_pct"],
                model_agreement=pred["model_agreement"],
                ensemble_json=pred["ensemble_json"],
                factor_breakdown_json=pred["factor_breakdown_json"],
            )
            generated += 1
        except Exception as exc:
            logger.error("Prediction failed for match %s: %s", match["id"], exc)
            errors += 1

    sim_result = None
    if generated > 0:
        try:
            sim_result = TournamentSimulator(elo=ensemble.elo).run(n_simulations=2000, store=True)
        except Exception as exc:
            logger.warning("Tournament simulation skipped: %s", exc)

    return {
        "matches": len(upcoming),
        "generated": generated,
        "errors": errors,
        "tournament_simulation": sim_result.to_dict() if sim_result else None,
    }


def retrain_and_predict(ensemble: Optional[EnsemblePredictor] = None) -> dict[str, Any]:
    """Retrain ensemble models, save, and regenerate predictions."""
    ensemble = ensemble or EnsemblePredictor()
    train_result = ensemble.train_all()
    save_models_after_train()
    pred_result = generate_predictions(ensemble)
    return {"training": train_result, "predictions": pred_result}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(generate_predictions())
