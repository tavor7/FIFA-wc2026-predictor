"""Model training, weight optimization, and registry."""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

from src import db
from src.features import build_training_dataset
from src.model_storage import save_models_after_train
from src.models.ensemble import EnsemblePredictor, get_or_create_ensemble
from src.models.model_registry import register_model_run
from src.models.weight_optimizer import optimize_ensemble_weights
from src.services.pipeline_cancel import ModelTrainingCancelled

logger = logging.getLogger(__name__)

ProgressCb = Callable[[str, float, str], None]
CancelFn = Callable[[], bool]


def _check_cancel(should_cancel: Optional[CancelFn]) -> None:
    if should_cancel and should_cancel():
        raise ModelTrainingCancelled()


@contextmanager
def _step_heartbeat(
    report: Callable[[str, float, str], None],
    step: str,
    start_pct: float,
    end_pct: float,
    label: str,
    *,
    interval_s: float = 4.0,
    should_cancel: Optional[CancelFn] = None,
) -> Iterator[None]:
    """Keep progress messages fresh during blocking work (no rising ETA math)."""
    stop = threading.Event()
    start = start_pct

    def _tick() -> None:
        tick = 0
        span = max(end_pct - start_pct - 1, 1)
        while not stop.wait(interval_s):
            if should_cancel and should_cancel():
                stop.set()
                return
            tick += 1
            pct = min(end_pct - 1, start + span * (1 - 0.85**tick))
            elapsed = int(tick * interval_s)
            report(step, pct, f"{label}… ({elapsed}s)")

    report(step, start_pct, f"{label}…")
    thread = threading.Thread(target=_tick, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1.0)
        _check_cancel(should_cancel)


class ModelTrainingService:
    def __init__(self, ensemble: Optional[EnsemblePredictor] = None):
        self.ensemble = ensemble or get_or_create_ensemble()

    def retrain_and_predict(
        self,
        progress_cb: Optional[ProgressCb] = None,
        should_cancel: Optional[CancelFn] = None,
    ) -> dict[str, Any]:
        def report(step: str, pct: float, msg: str) -> None:
            _check_cancel(should_cancel)
            if progress_cb:
                progress_cb(step, pct, msg)

        report("prepare", 5, "Loading finished matches for training…")
        finished = len(db.get_all_finished_matches())
        report("prepare", 100, f"Found {finished} finished matches")

        report("rf", 2, "Building training features from historical matches…")

        def feature_progress(done: int, total: int) -> None:
            pct = round(done / max(total, 1) * 75, 1)
            report("rf", pct, f"Building training features {done}/{total}")

        dataset = build_training_dataset(
            progress_cb=feature_progress,
            should_cancel=should_cancel,
        )
        _check_cancel(should_cancel)

        with _step_heartbeat(
            report, "rf", 78, 95, "Fitting Random Forest", should_cancel=should_cancel,
        ):
            rf_result = self.ensemble.goal_model.train_model(dataset=dataset)
        _check_cancel(should_cancel)
        if rf_result.get("trained"):
            self.ensemble.goal_model.save_model()
            report("rf", 100, f"Random Forest trained on {rf_result.get('samples', '?')} matches")
        else:
            report("rf", 100, rf_result.get("message") or "Using heuristic Poisson (insufficient samples)")

        report("xgb", 15, "Training XGBoost on same dataset…")
        with _step_heartbeat(
            report, "xgb", 15, 95, "Fitting XGBoost", should_cancel=should_cancel,
        ):
            xgb_result = self.ensemble.train_xgboost(dataset=dataset)
        _check_cancel(should_cancel)
        if xgb_result.get("trained"):
            report("xgb", 100, f"XGBoost trained on {xgb_result.get('samples', '?')} matches")
        else:
            report("xgb", 100, xgb_result.get("message") or "XGBoost skipped")

        report("elo", 30, "Fitting Elo ratings…")
        self.ensemble.elo.fit_from_database()
        self.ensemble.elo.save()
        train_result = {
            "random_forest": rf_result,
            "xgboost": xgb_result,
            "elo": {"teams": len(self.ensemble.elo.ratings)},
        }
        report("elo", 100, f"Elo fitted for {train_result['elo']['teams']} teams")
        _check_cancel(should_cancel)

        report("registry", 10, "Uploading model files…")
        with _step_heartbeat(
            report, "registry", 10, 35, "Saving models to storage", should_cancel=should_cancel,
        ):
            save_models_after_train()
        _check_cancel(should_cancel)

        report("registry", 40, "Tuning ensemble weights on validation sample…")
        with _step_heartbeat(
            report, "registry", 40, 85, "Optimizing weights", should_cancel=should_cancel,
        ):
            weights = optimize_ensemble_weights(
                self.ensemble,
                match_ids=list(dataset[3]),
                should_cancel=should_cancel,
            )
        _check_cancel(should_cancel)
        version = register_model_run(
            weights=weights,
            active_models=[m for m in weights.keys()],
            metrics=train_result,
        )
        report("registry", 100, f"Registered model {version}")
        _check_cancel(should_cancel)

        from src.services.prediction_generation_service import PredictionGenerationService

        def pred_progress(done: int, total: int) -> None:
            pct = round(done / max(total, 1) * 100, 1)
            report("predictions", pct, f"Regenerating predictions {done}/{total}")

        report("predictions", 0, "Regenerating all predictions…")
        pred_result = PredictionGenerationService(ensemble=self.ensemble).generate_all(
            progress_callback=pred_progress,
            should_cancel=should_cancel,
        )
        _check_cancel(should_cancel)
        total_matches = int(pred_result.get("matches") or 0)
        report(
            "predictions",
            100,
            f"Generated {pred_result.get('generated', 0)} predictions for {total_matches} matches",
        )

        report("cache", 5, "Refreshing UI cache…")
        from src.cache.response_cache import invalidate_all
        from src.services.ui_cache_service import UICacheService

        def cache_progress(pct: float, msg: str) -> None:
            report("cache", pct, msg)

        with _step_heartbeat(
            report, "cache", 5, 95, "Refreshing UI cache", should_cancel=should_cancel,
        ):
            from src.services.pipeline_cancel import PipelineCancelled

            try:
                UICacheService().refresh_all(
                    progress_cb=cache_progress,
                    fast=True,
                    should_cancel=should_cancel,
                )
            except PipelineCancelled:
                raise ModelTrainingCancelled()
        invalidate_all()
        report("cache", 100, "UI cache refreshed")
        _check_cancel(should_cancel)

        backtest_metrics = None
        report("backtest", 5, "Running tournament backtest…")
        try:
            from src.evaluation.backtest import backtest_tournament

            with _step_heartbeat(
                report, "backtest", 5, 95, "Running backtest", should_cancel=should_cancel,
            ):
                backtest_metrics = backtest_tournament(league_filter="World Cup", limit=500)
            report("backtest", 100, "Backtest complete")
        except ModelTrainingCancelled:
            raise
        except Exception as exc:
            logger.warning("Post-retrain backtest skipped: %s", exc)
            report("backtest", 100, "Backtest skipped")

        return {
            "training": train_result,
            "model_version": version,
            "weights": weights,
            "predictions": pred_result,
            "backtest": backtest_metrics,
        }
