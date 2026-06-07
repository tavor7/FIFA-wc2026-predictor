"""Pre-match and batch prediction generation."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src import db
from src.analytics.monte_carlo import TournamentSimulator
from src.explain import compute_confidence, generate_explanation
from src.explain.confidence import ConfidenceReport
from src.model import GoalPredictionModel
from src.models.ensemble import EnsemblePredictor, EnsembleResult, get_or_create_ensemble
from src.models.model_registry import attach_prediction_metadata, get_active_model_info
from src.match_status import LIVE_STATUSES
from src.services.feature_generation_service import FeatureGenerationService
from src.services.live_prediction_service import LivePredictionService
from src.services.prediction_history_service import PredictionHistoryService

logger = logging.getLogger(__name__)


class PredictionGenerationService:
    def __init__(
        self,
        ensemble: Optional[EnsemblePredictor] = None,
        feature_service: Optional[FeatureGenerationService] = None,
        history_service: Optional[PredictionHistoryService] = None,
        live_service: Optional[LivePredictionService] = None,
    ):
        self.ensemble = ensemble or get_or_create_ensemble()
        self.features = feature_service or FeatureGenerationService()
        self.history = history_service or PredictionHistoryService()
        self.live = live_service or LivePredictionService()

    def predict_match(self, match_row: Any) -> dict[str, Any]:
        status = match_row.get("status") or ""
        if status in LIVE_STATUSES:
            return self.live.predict_live_match(match_row, self.ensemble)

        mf = self.features.build(match_row)
        result = self.ensemble.predict(mf)
        return self._build_payload(match_row, mf, result)

    def _build_payload(self, match_row: Any, mf: Any, result: EnsembleResult) -> dict[str, Any]:
        scorelines = GoalPredictionModel.scoreline_distribution(result.lambda_home, result.lambda_away)
        top5 = GoalPredictionModel.top_scorelines(scorelines, n=5)
        best = top5[0] if top5 else {"home": 0, "away": 0, "probability": 0.1}

        confidence: ConfidenceReport = compute_confidence(mf, result)
        model_info = get_active_model_info()

        explanation = generate_explanation(
            home_team=match_row["home_team"],
            away_team=match_row["away_team"],
            predicted_home=int(best["home"]),
            predicted_away=int(best["away"]),
            features=mf,
            top_scorelines=top5,
            outcomes={"home_win": result.home_win, "draw": result.draw, "away_win": result.away_win},
        )

        db.upsert_feature_store(
            match_id=int(match_row["id"]),
            features=mf.features,
            missing_flags=mf.missing_flags,
            metadata=mf.metadata,
        )

        payload = {
            "match_id": int(match_row["id"]),
            "prediction_type": "prematch",
            "predicted_home_goals": int(best["home"]),
            "predicted_away_goals": int(best["away"]),
            "home_win_prob": round(result.home_win, 4),
            "draw_prob": round(result.draw, 4),
            "away_win_prob": round(result.away_win, 4),
            "exact_score_prob": best["probability"],
            "top_scorelines": top5,
            "explanation": explanation,
            "lambda_home": result.lambda_home,
            "lambda_away": result.lambda_away,
            "lambda_home_mean": result.lambda_home_mean,
            "lambda_home_std": result.lambda_home_std,
            "lambda_away_mean": result.lambda_away_mean,
            "lambda_away_std": result.lambda_away_std,
            "confidence_pct": confidence.confidence_pct,
            "data_completeness_pct": confidence.data_completeness_pct,
            "model_agreement": confidence.model_agreement,
            "ensemble_json": result.to_dict(),
            "factor_breakdown_json": confidence.to_dict(),
            "model_version": model_info.get("model_version"),
            "feature_version": model_info.get("feature_version"),
            "data_snapshot_timestamp": model_info.get("data_snapshot_timestamp"),
            "model_weights_json": model_info.get("weights_json"),
            "freshness_json": model_info.get("freshness_json"),
        }
        payload = attach_prediction_metadata(payload, mf)
        self.history.record(int(match_row["id"]), payload, mf.features, mf.metadata)
        return payload

    def generate_all(self, limit: int = 100) -> dict[str, Any]:
        db.init_db()
        upcoming = db.get_upcoming_matches(limit=limit)
        live = db.get_live_matches()
        seen = {int(m["id"]) for m in upcoming}
        for m in live:
            if int(m["id"]) not in seen:
                upcoming.append(m)
                seen.add(int(m["id"]))

        generated = errors = 0
        for match in upcoming:
            try:
                pred = self.predict_match(match)
                db.upsert_prediction(**self._upsert_kwargs(pred))
                if match.get("status") in LIVE_STATUSES:
                    from src import db_extended as ext

                    ext.insert_live_prob_snapshot(
                        match_id=pred["match_id"],
                        home_win_prob=pred["home_win_prob"],
                        draw_prob=pred["draw_prob"],
                        away_win_prob=pred["away_win_prob"],
                    )
                generated += 1
            except Exception as exc:
                logger.error("Prediction failed for match %s: %s", match["id"], exc)
                errors += 1

        sim_result = None
        if generated > 0:
            try:
                sim_result = TournamentSimulator(elo=self.ensemble.elo).run(n_simulations=2000, store=True)
            except Exception as exc:
                logger.warning("Tournament simulation skipped: %s", exc)

        from src import db_extended as ext

        ext.upsert_data_freshness("predictions", 100.0, source="computed")

        return {
            "matches": len(upcoming),
            "generated": generated,
            "errors": errors,
            "tournament_simulation": sim_result.to_dict() if sim_result else None,
        }

    @staticmethod
    def _upsert_kwargs(pred: dict[str, Any]) -> dict[str, Any]:
        return {
            "match_id": pred["match_id"],
            "predicted_home_goals": pred["predicted_home_goals"],
            "predicted_away_goals": pred["predicted_away_goals"],
            "home_win_prob": pred["home_win_prob"],
            "draw_prob": pred["draw_prob"],
            "away_win_prob": pred["away_win_prob"],
            "exact_score_prob": pred["exact_score_prob"],
            "top_scorelines": pred["top_scorelines"],
            "explanation": pred["explanation"],
            "confidence_pct": pred["confidence_pct"],
            "data_completeness_pct": pred["data_completeness_pct"],
            "model_agreement": pred["model_agreement"],
            "ensemble_json": pred["ensemble_json"],
            "factor_breakdown_json": pred["factor_breakdown_json"],
            "lambda_home_mean": pred.get("lambda_home_mean"),
            "lambda_home_std": pred.get("lambda_home_std"),
            "lambda_away_mean": pred.get("lambda_away_mean"),
            "lambda_away_std": pred.get("lambda_away_std"),
            "prediction_type": pred.get("prediction_type", "prematch"),
            "model_version": pred.get("model_version"),
            "feature_version": pred.get("feature_version"),
            "data_snapshot_timestamp": pred.get("data_snapshot_timestamp"),
            "model_weights_json": pred.get("model_weights_json"),
            "freshness_json": pred.get("freshness_json"),
            "live_prediction_json": pred.get("live_prediction_json"),
        }
