"""Pre-match and batch prediction generation."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from src import db
from src.analytics.monte_carlo import TournamentSimulator
from src.explain import build_structured_explanation, compute_confidence, generate_explanation
from src.explain.confidence import ConfidenceReport, feature_contributions
from src.model import GoalPredictionModel
from src.models.baseline_predictor import baseline_predict
from src.models.ensemble import EnsemblePredictor, EnsembleResult, get_or_create_ensemble
from src.models.model_registry import attach_prediction_metadata, get_active_model_info
from src.models.stage_priors import apply_stage_prior
from src.match_status import LIVE_STATUSES
from src.services.feature_generation_service import FeatureGenerationService
from src.services.live_prediction_service import LivePredictionService
from src.services.prediction_history_service import PredictionHistoryService
from src.services.prediction_validation_service import (
    build_completeness_flags,
    validate_prediction,
)

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBRegressor  # noqa: F401
    HAS_XGB = True
except ImportError:
    HAS_XGB = False


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
        try:
            result = self.ensemble.predict(mf)
            source_mode = self._resolve_source_mode(result, mf)
            confidence = compute_confidence(mf, result)
            use_baseline = (
                confidence.data_completeness_pct < 35
                or confidence.confidence_pct < 25
            )

            if use_baseline:
                reasons = []
                if confidence.data_completeness_pct < 35:
                    reasons.append("data completeness below 35%")
                if confidence.confidence_pct < 25:
                    reasons.append("confidence below 25%")
                baseline = baseline_predict(match_row, mf, self.ensemble.elo)
                return self._build_payload_from_baseline(
                    match_row, mf, baseline, result, fallback_reason="; ".join(reasons) or "low confidence",
                )
            return self._build_payload(match_row, mf, result, source_mode)
        except Exception as exc:
            logger.warning("Ensemble failed for %s, using baseline: %s", match_row["id"], exc)
            baseline = baseline_predict(match_row, mf, self.ensemble.elo)
            return self._build_payload_from_baseline(
                match_row, mf, baseline, None, fallback_reason=f"ensemble error: {exc}",
            )

    def _resolve_source_mode(self, result: EnsembleResult, mf: Any) -> str:
        models = [m.name for m in result.models]
        if "xgboost" in models and HAS_XGB:
            return "full_model"
        if "poisson_rf" in models:
            return "ensemble_without_xgb"
        missing = sum(1 for v in mf.missing_flags.values() if v)
        if missing > 10:
            return "insufficient_data"
        return "heuristic_plus_elo"

    def _build_payload(
        self,
        match_row: Any,
        mf: Any,
        result: EnsembleResult,
        source_mode: str,
    ) -> dict[str, Any]:
        lh, la, _ = apply_stage_prior(
            result.lambda_home, result.lambda_away, match_row.get("stage")
        )
        scorelines = GoalPredictionModel.scoreline_distribution(lh, la)
        top5 = GoalPredictionModel.top_scorelines(scorelines, n=5)
        best = top5[0] if top5 else {"home": 0, "away": 0, "probability": 0.1}

        confidence: ConfidenceReport = compute_confidence(mf, result)
        model_info = get_active_model_info()
        outcomes = {
            "home_win": result.home_win,
            "draw": result.draw,
            "away_win": result.away_win,
        }

        explanation = generate_explanation(
            home_team=match_row["home_team"],
            away_team=match_row["away_team"],
            predicted_home=int(best["home"]),
            predicted_away=int(best["away"]),
            features=mf,
            top_scorelines=top5,
            outcomes=outcomes,
        )

        explanation_json = build_structured_explanation(
            home_team=match_row["home_team"],
            away_team=match_row["away_team"],
            predicted_home=int(best["home"]),
            predicted_away=int(best["away"]),
            features=mf,
            top_scorelines=top5,
            outcomes=outcomes,
            positive_factors=confidence.positive_factors,
            negative_factors=confidence.risk_factors,
            lambda_home=lh,
            lambda_away=la,
            lambda_home_std=result.lambda_home_std,
            lambda_away_std=result.lambda_away_std,
        )

        contributions = feature_contributions(mf, result)
        completeness = build_completeness_flags(mf, True, True)

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
            "explanation_json": explanation_json,
            "lambda_home": lh,
            "lambda_away": la,
            "lambda_home_mean": lh,
            "lambda_home_std": result.lambda_home_std,
            "lambda_away_mean": la,
            "lambda_away_std": result.lambda_away_std,
            "confidence_pct": confidence.confidence_pct,
            "data_completeness_pct": confidence.data_completeness_pct,
            "model_agreement": confidence.model_agreement,
            "ensemble_json": result.to_dict(),
            "factor_breakdown_json": confidence.to_dict(),
            "feature_contributions_json": contributions,
            "prediction_source_mode": source_mode,
            "completeness_flags_json": completeness,
            "model_version": model_info.get("model_version"),
            "feature_version": model_info.get("feature_version"),
            "data_snapshot_timestamp": model_info.get("data_snapshot_timestamp"),
            "model_weights_json": model_info.get("weights_json"),
            "freshness_json": model_info.get("freshness_json"),
        }
        payload = attach_prediction_metadata(payload, mf)
        val_status, val_errors = validate_prediction(payload)
        payload["validation_status"] = val_status
        payload["validation_errors_json"] = val_errors
        self.history.record(int(match_row["id"]), payload, mf.features, mf.metadata)
        return payload

    def _build_payload_from_baseline(
        self,
        match_row: Any,
        mf: Any,
        baseline: dict[str, Any],
        result: Optional[EnsembleResult],
        *,
        fallback_reason: str = "insufficient model data",
    ) -> dict[str, Any]:
        top5 = baseline["top_scorelines"]
        best = top5[0]
        model_info = get_active_model_info()
        outcomes = {
            "home_win": baseline["home_win"],
            "draw": baseline["draw"],
            "away_win": baseline["away_win"],
        }
        confidence = compute_confidence(mf, result) if result else None
        positives = confidence.positive_factors if confidence else []
        negatives = confidence.risk_factors if confidence else ["Limited model data — baseline estimate used"]

        explanation_json = build_structured_explanation(
            home_team=match_row["home_team"],
            away_team=match_row["away_team"],
            predicted_home=baseline["predicted_home_goals"],
            predicted_away=baseline["predicted_away_goals"],
            features=mf,
            top_scorelines=top5,
            outcomes=outcomes,
            positive_factors=positives,
            negative_factors=negatives,
            lambda_home=baseline["lambda_home_mean"],
            lambda_away=baseline["lambda_away_mean"],
            lambda_home_std=baseline["lambda_home_std"],
            lambda_away_std=baseline["lambda_away_std"],
        )
        explanation_json["fallback_reason"] = fallback_reason
        explanation_json["prediction_source_mode"] = baseline.get("prediction_source_mode", "baseline_only")

        explanation = generate_explanation(
            home_team=match_row["home_team"],
            away_team=match_row["away_team"],
            predicted_home=baseline["predicted_home_goals"],
            predicted_away=baseline["predicted_away_goals"],
            features=mf,
            top_scorelines=top5,
            outcomes=outcomes,
        )

        contributions = feature_contributions(mf, result) if result else {}
        completeness = build_completeness_flags(mf, True, True)
        db.upsert_feature_store(
            match_id=int(match_row["id"]),
            features=mf.features,
            missing_flags=mf.missing_flags,
            metadata=mf.metadata,
        )

        payload = {
            "match_id": int(match_row["id"]),
            "prediction_type": "prematch",
            "predicted_home_goals": baseline["predicted_home_goals"],
            "predicted_away_goals": baseline["predicted_away_goals"],
            "home_win_prob": baseline["home_win"],
            "draw_prob": baseline["draw"],
            "away_win_prob": baseline["away_win"],
            "exact_score_prob": baseline["exact_score_prob"],
            "top_scorelines": top5,
            "explanation": explanation,
            "explanation_json": explanation_json,
            "lambda_home_mean": baseline["lambda_home_mean"],
            "lambda_home_std": baseline["lambda_home_std"],
            "lambda_away_mean": baseline["lambda_away_mean"],
            "lambda_away_std": baseline["lambda_away_std"],
            "confidence_pct": confidence.confidence_pct if confidence else 30.0,
            "data_completeness_pct": confidence.data_completeness_pct if confidence else 25.0,
            "model_agreement": confidence.model_agreement if confidence else "Low",
            "ensemble_json": result.to_dict() if result else {},
            "factor_breakdown_json": confidence.to_dict() if confidence else {},
            "feature_contributions_json": contributions,
            "prediction_source_mode": baseline["prediction_source_mode"],
            "completeness_flags_json": completeness,
            "model_version": model_info.get("model_version") or "baseline-v1",
            "feature_version": model_info.get("feature_version") or "baseline-v1",
        }
        val_status, val_errors = validate_prediction(payload)
        payload["validation_status"] = val_status
        payload["validation_errors_json"] = val_errors
        self.history.record(int(match_row["id"]), payload, mf.features, mf.metadata)
        return payload

    def generate_all(
        self,
        limit: int = 500,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        *,
        run_simulation: bool = True,
        only_missing: bool = False,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> dict[str, Any]:
        db.init_db()
        upcoming = db.get_upcoming_matches(limit=limit, tournament_only=True)
        live = db.get_live_matches(tournament_only=True)
        seen = {int(m["id"]) for m in upcoming}
        for m in live:
            if int(m["id"]) not in seen:
                upcoming.append(m)
                seen.add(int(m["id"]))

        if only_missing and upcoming:
            have = set(db.get_predictions_for_match_ids([int(m["id"]) for m in upcoming]).keys())
            upcoming = [m for m in upcoming if int(m["id"]) not in have]

        total = len(upcoming)
        generated = errors = skipped = 0
        if total == 0:
            return {
                "matches": 0,
                "generated": 0,
                "errors": 0,
                "skipped": 0,
                "tournament_simulation": None,
            }

        for i, match in enumerate(upcoming):
            if should_cancel and should_cancel():
                break
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
                logger.error("Prediction failed for match %s, forcing baseline: %s", match["id"], exc)
                try:
                    mf = self.features.build(match)
                    baseline = baseline_predict(match, mf, self.ensemble.elo)
                    pred = self._build_payload_from_baseline(
                        match, mf, baseline, None,
                        fallback_reason=f"prediction error: {exc}",
                    )
                    db.upsert_prediction(**self._upsert_kwargs(pred))
                    generated += 1
                except Exception as exc2:
                    logger.error("Baseline fallback failed for match %s: %s", match["id"], exc2)
                    errors += 1
            if progress_callback:
                progress_callback(i + 1, total)

        sim_result = None
        if run_simulation and generated > 0:
            try:
                sim_result = TournamentSimulator(elo=self.ensemble.elo).run(n_simulations=2000, store=True)
            except Exception as exc:
                logger.warning("Tournament simulation skipped: %s", exc)

        from src import db_extended as ext

        ext.upsert_data_freshness("predictions", source="computed")

        return {
            "matches": total,
            "generated": generated,
            "errors": errors,
            "skipped": skipped,
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
            "feature_contributions_json": pred.get("feature_contributions_json"),
            "prediction_source_mode": pred.get("prediction_source_mode"),
            "explanation_json": pred.get("explanation_json"),
            "completeness_flags_json": pred.get("completeness_flags_json"),
            "validation_status": pred.get("validation_status", "valid"),
            "validation_errors_json": pred.get("validation_errors_json"),
        }
