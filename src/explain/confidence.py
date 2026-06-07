"""Confidence scoring and factor contribution breakdown."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

from src.features import FEATURE_COLUMNS, MatchFeatures
from src.models.ensemble import EnsembleResult


@dataclass
class ConfidenceReport:
    confidence_pct: float
    data_completeness_pct: float
    model_agreement: str
    model_agreement_score: float
    data_reliability_pct: float
    factor_breakdown: dict[str, float]
    risk_factors: list[str]
    positive_factors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _factor_breakdown(features: MatchFeatures, ensemble: EnsembleResult) -> dict[str, float]:
    f = features.features
    raw = {
        "recent_form": abs(f.get("recent_form_home", 0.5) - f.get("recent_form_away", 0.5)),
        "squad_strength": abs(
            f.get("starting_xi_strength_home", 0.55) - f.get("starting_xi_strength_away", 0.55)
        ),
        "injuries": (
            f.get("injured_key_players_home_score", 0) + f.get("injured_key_players_away_score", 0)
        ),
        "elo_rating": abs(f.get("elo_diff", 0)),
        "rest_days": abs(f.get("rest_days_diff", 0)) / 7.0,
        "head_to_head": 0.05,
        "momentum": abs(
            features.metadata.get("momentum_home", 50) - features.metadata.get("momentum_away", 50)
        )
        / 100.0,
    }
    total = sum(raw.values()) or 1.0
    pct = {k: round(v / total * 100, 1) for k, v in raw.items()}
    pct["head_to_head"] = max(pct.get("head_to_head", 5.0), 5.0)
    re_total = sum(pct.values()) or 1.0
    return {k: round(v / re_total * 100, 1) for k, v in pct.items()}


def compute_confidence(
    features: MatchFeatures,
    ensemble: EnsembleResult,
) -> ConfidenceReport:
    """Derive confidence, completeness, and explainability metrics."""
    missing = sum(1 for v in features.missing_flags.values() if v)
    total_flags = max(len(FEATURE_COLUMNS), 1)
    completeness = round((1.0 - missing / total_flags) * 100, 1)

    agreement_score = ensemble.agreement_score
    agreement_label = ensemble.consensus_label

    reliability = round(min(completeness, 100.0) * 0.6 + agreement_score * 40, 1)
    confidence = round(
        completeness * 0.35 + agreement_score * 100 * 0.35 + reliability * 0.30,
        1,
    )

    breakdown = _factor_breakdown(features, ensemble)
    f = features.features
    positives: list[str] = []
    risks: list[str] = []

    if f.get("recent_form_home", 0.5) > f.get("recent_form_away", 0.5) + 0.1:
        positives.append("Strong recent form for home team")
    elif f.get("recent_form_away", 0.5) > f.get("recent_form_home", 0.5) + 0.1:
        positives.append("Strong recent form for away team")

    if missing <= 2:
        positives.append("High data completeness")
    if missing > 6:
        risks.append("Several features used default estimates")

    if agreement_score < 0.5:
        risks.append("Models disagree on expected outcome")
    elif agreement_score >= 0.75:
        positives.append("Strong model consensus")

    if f.get("injured_key_players_home_score", 0) > 0.2 or f.get("injured_key_players_away_score", 0) > 0.2:
        risks.append("Key player injuries may shift expectations")

    meta = features.metadata
    if meta.get("form_home_source") == "prior" or meta.get("form_away_source") == "prior":
        risks.append("Limited recent match history for form calculation")

    return ConfidenceReport(
        confidence_pct=confidence,
        data_completeness_pct=completeness,
        model_agreement=agreement_label,
        model_agreement_score=round(agreement_score, 3),
        data_reliability_pct=reliability,
        factor_breakdown=breakdown,
        risk_factors=risks,
        positive_factors=positives,
    )
