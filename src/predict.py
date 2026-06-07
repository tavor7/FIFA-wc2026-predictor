"""Generate and store match predictions."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src import db
from src.explain import generate_explanation
from src.features import build_features_for_match
from src.model import GoalPredictionModel, get_or_create_model

logger = logging.getLogger(__name__)


def predict_match(
    match_row: Any,
    model: Optional[GoalPredictionModel] = None,
) -> dict[str, Any]:
    """Generate prediction for a single match."""
    model = model or get_or_create_model()
    mf = build_features_for_match(match_row)

    lambda_home, lambda_away = model.predict_expected_goals(mf)
    scorelines = model.scoreline_distribution(lambda_home, lambda_away)
    outcomes = model.outcome_probabilities(scorelines)
    top5 = model.top_scorelines(scorelines, n=5)

    # Most likely exact score
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

    return {
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
    }


def generate_predictions(model: Optional[GoalPredictionModel] = None) -> dict[str, Any]:
    """Generate predictions for all upcoming matches and store in DB."""
    db.init_db()
    model = model or get_or_create_model()
    upcoming = db.get_upcoming_matches(limit=100)

    generated = 0
    errors = 0
    for match in upcoming:
        try:
            pred = predict_match(match, model)
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
            )
            generated += 1
        except Exception as exc:
            logger.error("Prediction failed for match %s: %s", match["id"], exc)
            errors += 1

    return {"matches": len(upcoming), "generated": generated, "errors": errors}


def retrain_and_predict(model: Optional[GoalPredictionModel] = None) -> dict[str, Any]:
    """Retrain model, save, and regenerate predictions."""
    model = model or GoalPredictionModel()
    train_result = model.train_model()
    if train_result.get("trained"):
        model.save_model()
    pred_result = generate_predictions(model)
    return {"training": train_result, "predictions": pred_result}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(generate_predictions())
