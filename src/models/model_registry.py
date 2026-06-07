"""Model version registry and prediction metadata."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Optional

from src import config
from src.features import FEATURE_COLUMNS
from src import db_extended as ext


def feature_version_hash() -> str:
    payload = json.dumps(FEATURE_COLUMNS, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def get_active_model_info() -> dict[str, Any]:
    row = ext.get_latest_model_registry()
    if row:
        d = dict(row)
        for key in ("weights_json", "active_models_json", "metrics_json", "freshness_json"):
            if d.get(key) and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except json.JSONDecodeError:
                    pass
        return {
            "model_version": d.get("model_version"),
            "feature_version": d.get("feature_version"),
            "data_snapshot_timestamp": d.get("trained_at"),
            "weights_json": d.get("weights_json"),
            "freshness_json": ext.build_freshness_snapshot(),
        }
    return {
        "model_version": "bootstrap",
        "feature_version": feature_version_hash(),
        "data_snapshot_timestamp": datetime.utcnow().isoformat(),
        "weights_json": None,
        "freshness_json": ext.build_freshness_snapshot(),
    }


def register_model_run(
    weights: Optional[dict[str, float]] = None,
    active_models: Optional[list[str]] = None,
    metrics: Optional[dict[str, Any]] = None,
) -> str:
    version = datetime.utcnow().strftime("v%Y%m%d.%H%M")
    ext.insert_model_registry(
        model_version=version,
        feature_version=feature_version_hash(),
        weights_json=weights,
        active_models_json=active_models,
        metrics_json=metrics,
    )
    ext.upsert_data_freshness("models", 100.0, source="trained")
    return version


def attach_prediction_metadata(payload: dict[str, Any], mf: Any) -> dict[str, Any]:
    info = get_active_model_info()
    payload.setdefault("model_version", info.get("model_version"))
    payload.setdefault("feature_version", info.get("feature_version"))
    payload.setdefault("data_snapshot_timestamp", info.get("data_snapshot_timestamp"))
    payload.setdefault("model_weights_json", info.get("weights_json"))
    freshness = info.get("freshness_json") or {}
    warnings = ext.staleness_warnings(freshness)
    freshness["staleness_warnings"] = warnings
    payload["freshness_json"] = freshness
    payload["metadata"] = {
        "lineup_source_home": mf.metadata.get("starting_xi_strength_home_source"),
        "lineup_source_away": mf.metadata.get("starting_xi_strength_away_source"),
        "missing_fields": mf.metadata.get("missing_fields", []),
    }
    return payload
