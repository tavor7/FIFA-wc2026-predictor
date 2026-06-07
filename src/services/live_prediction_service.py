"""In-game prediction model for live matches."""

from __future__ import annotations

from typing import Any, Optional

from src import db
from src import db_extended as ext
from src.model import GoalPredictionModel
from src.models.ensemble import EnsemblePredictor, get_or_create_ensemble
from src.models.live_match import LiveMatchModel
from src.services.feature_generation_service import FeatureGenerationService


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

        scorelines = GoalPredictionModel.scoreline_distribution(
            live_out["lambda_home"], live_out["lambda_away"]
        )
        top5 = GoalPredictionModel.top_scorelines(scorelines, n=5)
        best = top5[0] if top5 else {"home": 0, "away": 0, "probability": 0.1}

        return {
            "match_id": match_id,
            "prediction_type": "live",
            "predicted_home_goals": int(best["home"]),
            "predicted_away_goals": int(best["away"]),
            "home_win_prob": live_out["home_win"],
            "draw_prob": live_out["draw"],
            "away_win_prob": live_out["away_win"],
            "exact_score_prob": best["probability"],
            "top_scorelines": top5,
            "explanation": live_out.get("explanation", "Live in-game model"),
            "lambda_home": live_out["lambda_home"],
            "lambda_away": live_out["lambda_away"],
            "lambda_home_mean": live_out["lambda_home"],
            "lambda_home_std": live_out.get("lambda_home_std", 0.15),
            "lambda_away_mean": live_out["lambda_away"],
            "lambda_away_std": live_out.get("lambda_away_std", 0.15),
            "confidence_pct": live_out.get("confidence_pct", 55.0),
            "data_completeness_pct": 80.0,
            "model_agreement": "Live",
            "ensemble_json": {"prematch": prematch.to_dict(), "live": live_out},
            "factor_breakdown_json": live_out.get("factors", {}),
            "live_prediction_json": live_out,
        }
