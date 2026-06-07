"""Feature generation with data-source priority and missingness tracking."""

from __future__ import annotations

from typing import Any, Optional

from src.features import FEATURE_COLUMNS, MatchFeatures, build_features_for_match

SOURCE_PRIORITY = [
    "official_match",
    "confirmed_lineup",
    "match_statistics",
    "historical_strength",
    "player_ratings_fc26",
    "heuristic_default",
]

SOURCE_RELIABILITY = {
    "official_match": 1.0,
    "confirmed_lineup": 0.95,
    "match_statistics": 0.9,
    "historical_strength": 0.75,
    "player_ratings_fc26": 0.35,
    "heuristic_default": 0.2,
}


class FeatureGenerationService:
    """Build match features respecting source priority."""

    def build(
        self,
        match_row: Any,
        as_of_date: Optional[str] = None,
        for_training: bool = False,
    ) -> MatchFeatures:
        mf = build_features_for_match(match_row, for_training=for_training)
        if as_of_date:
            mf.metadata["as_of_date"] = as_of_date
        mf.metadata["source_priority"] = SOURCE_PRIORITY
        missing_fields = [c for c in FEATURE_COLUMNS if mf.missing_flags.get(c)]
        mf.metadata["missing_fields"] = missing_fields
        lineup_srcs = [
            mf.metadata.get("starting_xi_strength_home_source", "heuristic_default"),
            mf.metadata.get("starting_xi_strength_away_source", "heuristic_default"),
        ]
        reliabilities = [SOURCE_RELIABILITY.get(s, 0.2) for s in lineup_srcs]
        mf.metadata["lineup_reliability"] = min(reliabilities) if reliabilities else 0.2
        mf.metadata["data_source_reliability"] = {
            "home_lineup": lineup_srcs[0],
            "away_lineup": lineup_srcs[1],
        }
        return mf

    @staticmethod
    def reliability_penalty(mf: MatchFeatures) -> float:
        """0–1 penalty from missing high-priority inputs."""
        missing = mf.metadata.get("missing_fields") or []
        if not missing:
            return 0.0
        return min(len(missing) / max(len(FEATURE_COLUMNS), 1), 1.0)
