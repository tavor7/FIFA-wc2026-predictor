"""Sanity checks for stored predictions."""

from __future__ import annotations

from typing import Any


def validate_prediction(pred: dict[str, Any]) -> tuple[str, list[str]]:
    errors: list[str] = []

    hw = float(pred.get("home_win_prob") or 0)
    dr = float(pred.get("draw_prob") or 0)
    aw = float(pred.get("away_win_prob") or 0)
    total = hw + dr + aw
    if abs(total - 1.0) > 0.05:
        errors.append(f"Outcome probabilities sum to {total:.2f}, expected ~1.0")

    top = pred.get("top_scorelines") or []
    if isinstance(top, str):
        import json
        try:
            top = json.loads(top)
        except json.JSONDecodeError:
            top = []
    for i, sl in enumerate(top[:5]):
        p = sl.get("probability")
        if p is not None and (p < 0 or p > 1):
            errors.append(f"Scoreline {i} probability {p} out of range [0,1]")

    ph = pred.get("predicted_home_goals")
    pa = pred.get("predicted_away_goals")
    if ph is not None and int(ph) != ph:
        errors.append("predicted_home_goals is not an integer")
    if pa is not None and int(pa) != pa:
        errors.append("predicted_away_goals is not an integer")

    for key in ("lambda_home_mean", "lambda_away_mean"):
        lam = pred.get(key)
        if lam is not None and (lam < 0.2 or lam > 4.0):
            errors.append(f"{key}={lam} outside reasonable range [0.2, 4.0]")

    if not pred.get("explanation") and not pred.get("explanation_json"):
        errors.append("Missing explanation")
    if not pred.get("model_version") and pred.get("prediction_source_mode") not in (
        "baseline_only", "heuristic_plus_elo", "insufficient_data"
    ):
        errors.append("Missing model_version")

    status = "invalid" if errors else "valid"
    return status, errors


def build_completeness_flags(
    features: Any,
    has_prediction: bool,
    has_explanation: bool,
) -> dict[str, Any]:
    f = features.features if hasattr(features, "features") else {}
    meta = features.metadata if hasattr(features, "metadata") else {}
    missing = features.missing_flags if hasattr(features, "missing_flags") else {}

    flags = {
        "has_features": bool(f),
        "has_prediction": has_prediction,
        "has_explanation": has_explanation,
        "has_injury_data": int(f.get("injured_players_home_count", 0) + f.get("injured_players_away_count", 0)) >= 0
            and not missing.get("injured_key_players_home_score"),
        "has_squad_data": meta.get("starting_xi_strength_home_source") not in (None, "heuristic_default"),
        "has_recent_form_data": meta.get("form_home_source") not in (None, "prior", "insufficient_data"),
        "confidence_penalty_reasons": [],
    }
    if meta.get("form_home_source") == "prior":
        flags["confidence_penalty_reasons"].append("Limited recent form history")
    if meta.get("starting_xi_strength_home_source") == "heuristic_default":
        flags["confidence_penalty_reasons"].append("Squad strength estimated from defaults")
    if sum(1 for v in missing.values() if v) > 4:
        flags["confidence_penalty_reasons"].append("Multiple features used default estimates")
    return flags
