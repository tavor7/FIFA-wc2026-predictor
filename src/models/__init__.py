"""Prediction models and ensemble."""

__all__ = ["EloModel", "EnsemblePredictor", "EnsembleResult"]


def __getattr__(name: str):
    if name == "EloModel":
        from src.models.elo import EloModel

        return EloModel
    if name in ("EnsemblePredictor", "EnsembleResult"):
        from src.models.ensemble import EnsemblePredictor, EnsembleResult

        return EnsemblePredictor if name == "EnsemblePredictor" else EnsembleResult
    raise AttributeError(name)
