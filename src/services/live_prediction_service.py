"""In-game prediction model for live matches."""

from __future__ import annotations

from typing import Any, Optional

from src import db
from src import db_extended as ext
from src.explain import build_structured_explanation, generate_explanation
from src.explain.confidence import compute_confidence, feature_contributions
from src.model import GoalPredictionModel
from src.models.ensemble import EnsemblePredictor, get_or_create_ensemble
from src.models.live_match import LiveMatchModel
from src.models.model_registry import get_active_model_info
from src.services.feature_generation_service import FeatureGenerationService
from src.services.prediction_validation_service import build_completeness_flags, validate_prediction


class LivePredictionService:
    def __init__(
        self,
        live_model: Optional[LiveMatchModel] = None,
        feature_service: Optional[FeatureGenerationService] = None,
    ):
        self.live_model = live_model or LiveMatchModel()
        self.features = feature_service or FeatureGenerationService()

    def predict_live_match(
        self,
        match_row: Any,
        ensemble: Optional[EnsemblePredictor] = None,
    ) -> dict[str, Any]:
        ensemble = ensemble or get_or_create_ensemble()
        mf = self.features.build(match_row)
        prematch = ensemble.predict(mf)

        match_id = int(match_row["id"])
        stats = {s["team"]: dict(s) for s in db.get_team_match_stats(match_id)}
        events = [dict(e) for e in ext.get_match_events(match_id)]

        live_out = self.live_model.predict(
            prematch_lambda_home=prematch.lambda_home,
            prematch_lambda_away=prematch.lambda_away,
            match_row=match_row,
            team_stats=stats,
            events=events,
        )

        lh = live_out["lambda_home"]
        la = live_out["lambda_away"]
        scorelines = GoalPredictionModel.scoreline_distribution(lh, la)
        top5 = GoalPredictionModel.top_scorelines(scorelines, n=5)
        best = top5[0] if top5 else {"home": 0, "away": 0, "probability": 0.1}
        outcomes = {
            "home_win": live_out["home_win"],
            "draw": live_out["draw"],
            "away_win": live_out["away_win"],
        }
        confidence = compute_confidence(mf, prematch)
        model_info = get_active_model_info()

        explanation_json = build_structured_explanation(
            home_team=match_row["home_team"],
            away_team=match_row["away_team"],
            predicted_home=int(best["home"]),
            predicted_away=int(best["away"]),
            features=mf,
            top_scorelines=top5,
            outcomes=outcomes,
            positive_factors=confidence.positive_factors,
            negative_factors=confidence.risk_factors + ["Live in-game adjustments"],
            lambda_home=lh,
            lambda_away=la,
            lambda_home_std=live_out.get("lambda_home_std", 0.15),
            lambda_away_std=live_out.get("lambda_away_std", 0.15),
        )
        explanation_json["prediction_source_mode"] = "live_model"
        explanation_json["fallback_reason"] = "Live match — in-game model active"

        explanation = generate_explanation(
            home_team=match_row["home_team"],
            away_team=match_row["away_team"],
            predicted_home=int(best["home"]),
            predicted_away=int(best["away"]),
            features=mf,
            top_scorelines=top5,
            outcomes=outcomes,
        )

        contributions = feature_contributions(mf, prematch)
        completeness = build_completeness_flags(mf, True, True)

        payload = {
            "match_id": match_id,
            "prediction_type": "live",
            "predicted_home_goals": int(best["home"]),
            "predicted_away_goals": int(best["away"]),
            "home_win_prob": live_out["home_win"],
            "draw_prob": live_out["draw"],
            "away_win_prob": live_out["away_win"],
            "exact_score_prob": best["probability"],
            "top_scorelines": top5,
            "explanation": explanation or live_out.get("explanation", "Live in-game model"),
            "explanation_json": explanation_json,
            "lambda_home": lh,
            "lambda_away": la,
            "lambda_home_mean": lh,
            "lambda_home_std": live_out.get("lambda_home_std", 0.15),
            "lambda_away_mean": la,
            "lambda_away_std": live_out.get("lambda_away_std", 0.15),
            "confidence_pct": live_out.get("confidence_pct", confidence.confidence_pct),
            "data_completeness_pct": max(80.0, confidence.data_completeness_pct),
            "model_agreement": "Live",
            "ensemble_json": {"prematch": prematch.to_dict(), "live": live_out},
            "factor_breakdown_json": confidence.to_dict(),
            "feature_contributions_json": contributions,
            "prediction_source_mode": "live_model",
            "completeness_flags_json": completeness,
            "model_version": model_info.get("model_version"),
            "feature_version": model_info.get("feature_version"),
            "live_prediction_json": live_out,
        }
        val_status, val_errors = validate_prediction(payload)
        payload["validation_status"] = val_status
        payload["validation_errors_json"] = val_errors
        return payload
