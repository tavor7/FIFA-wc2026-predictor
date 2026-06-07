"""Generate and store match predictions (facade over services)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.match_status import LIVE_STATUSES
from src.models.ensemble import EnsemblePredictor

logger = logging.getLogger(__name__)


def predict_match(match_row: Any, ensemble: Optional[EnsemblePredictor] = None) -> dict[str, Any]:
    from src.services.prediction_generation_service import PredictionGenerationService

    return PredictionGenerationService(ensemble=ensemble).predict_match(match_row)


def generate_predictions(ensemble: Optional[EnsemblePredictor] = None) -> dict[str, Any]:
    from src.services.prediction_generation_service import PredictionGenerationService

    return PredictionGenerationService(ensemble=ensemble).generate_all()


def retrain_and_predict(ensemble: Optional[EnsemblePredictor] = None) -> dict[str, Any]:
    from src.services.model_training_service import ModelTrainingService

    return ModelTrainingService(ensemble=ensemble).retrain_and_predict()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(generate_predictions())
