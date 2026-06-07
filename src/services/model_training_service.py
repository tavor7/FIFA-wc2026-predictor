"""Model training, weight optimization, and registry."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.model_storage import save_models_after_train
from src.models.ensemble import EnsemblePredictor
from src.models.model_registry import register_model_run
from src.models.weight_optimizer import optimize_ensemble_weights

logger = logging.getLogger(__name__)


class ModelTrainingService:
    def __init__(self, ensemble: Optional[EnsemblePredictor] = None):
        self.ensemble = ensemble or EnsemblePredictor()

    def retrain_and_predict(self) -> dict[str, Any]:
        train_result = self.ensemble.train_all()
        save_models_after_train()
        weights = optimize_ensemble_weights(self.ensemble)
        version = register_model_run(
            weights=weights,
            active_models=[m for m in weights.keys()],
            metrics=train_result,
        )
        from src.services.prediction_generation_service import PredictionGenerationService

        pred_result = PredictionGenerationService(ensemble=self.ensemble).generate_all()
        return {"training": train_result, "model_version": version, "weights": weights, "predictions": pred_result}
