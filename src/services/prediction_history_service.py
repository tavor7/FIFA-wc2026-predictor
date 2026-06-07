"""Prediction version history and change tracking."""

from __future__ import annotations

import json
from typing import Any, Optional

from src import db_extended as ext
from src.explain.change_engine import explain_prediction_change


class PredictionHistoryService:
    def record(
        self,
        match_id: int,
        pred: dict[str, Any],
        features: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        prev = ext.get_latest_prediction_history(match_id)
        prev_dict = dict(prev) if prev else None
        change = explain_prediction_change(
            prev_dict,
            pred,
            current_features=features,
            previous_features=_parse_features(prev_dict.get("features_json") if prev_dict else None),
        )
        if prev_dict and change.get("bullets") == ["Minor internal model adjustment"]:
            return

        version = ext.next_prediction_version(match_id)
        ext.insert_prediction_history(
            match_id=match_id,
            version=version,
            home_win_prob=pred["home_win_prob"],
            draw_prob=pred["draw_prob"],
            away_win_prob=pred["away_win_prob"],
            predicted_home_goals=pred["predicted_home_goals"],
            predicted_away_goals=pred["predicted_away_goals"],
            features=features,
            reason_changed=change.get("summary"),
            explanation_json=pred.get("explanation"),
            ensemble_json=pred.get("ensemble_json"),
            change_bullets_json=change.get("bullets"),
            model_version=pred.get("model_version"),
        )

    def get_change_summary(self, match_id: int) -> dict[str, Any]:
        rows = ext.get_prediction_history(match_id, limit=2)
        if not rows:
            return {}
        latest = dict(rows[0])
        prev = dict(rows[1]) if len(rows) > 1 else None
        change = explain_prediction_change(
            prev,
            latest,
            previous_features=_parse_features(prev.get("features_json") if prev else None),
            current_features=_parse_features(latest.get("features_json")),
        )
        return {
            "what_changed": change,
            "previous_version": prev.get("version") if prev else None,
            "current_version": latest.get("version"),
            "reason": change.get("summary"),
        }


def _parse_features(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}
