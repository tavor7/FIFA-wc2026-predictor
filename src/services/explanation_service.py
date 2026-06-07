"""Explanation wrappers."""

from __future__ import annotations

from src.explain import generate_explanation
from src.explain.change_engine import explain_prediction_change
from src.services.prediction_history_service import PredictionHistoryService


class ExplanationService:
    def __init__(self):
        self.history = PredictionHistoryService()

    generate = staticmethod(generate_explanation)
    explain_change = staticmethod(explain_prediction_change)

    def match_change_summary(self, match_id: int) -> dict:
        return self.history.get_change_summary(match_id)
