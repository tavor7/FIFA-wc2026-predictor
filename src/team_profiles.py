"""Data-driven team strength accessors (no hand-tuned ratings)."""

from __future__ import annotations

from typing import Any

from src.analytics.computed_strength import StrengthRating, get_strength_rating
from src.team_names import TEAM_ALIASES, normalize_team_name

__all__ = [
    "TEAM_ALIASES",
    "normalize_team_name",
    "get_team_prior",
    "get_team_prior_detail",
    "prior_to_goal_rates",
    "prior_form",
    "prior_metadata",
]


def get_team_prior(team: str) -> tuple[float, float]:
    """
    Return (attack, defense) from finished-match data in the database.
    1.0 = tournament average. Unknown teams with no history → (1.0, 1.0).
    """
    rating = get_strength_rating(team)
    return rating.attack, rating.defense


def get_team_prior_detail(team: str) -> StrengthRating:
    """Full strength rating with match count and data source."""
    return get_strength_rating(normalize_team_name(team))


def prior_to_goal_rates(attack: float, defense: float) -> tuple[float, float]:
    """Convert strength ratios to expected goals scored/conceded per match."""
    league_avg = 1.2
    scored = max(0.4, attack * league_avg)
    conceded = max(0.4, league_avg / defense if defense > 0 else league_avg)
    return round(scored, 2), round(conceded, 2)


def prior_form(attack: float, defense: float) -> float:
    """Derive a 0–1 form proxy from empirical strength ratios."""
    return min(max((attack + defense - 1.6) / 1.2, 0.15), 0.85)


def prior_metadata(team: str) -> dict[str, Any]:
    """Transparency payload for UI / feature store."""
    r = get_team_prior_detail(team)
    return {
        "attack": r.attack,
        "defense": r.defense,
        "matches": r.matches,
        "source": r.source,
        "avg_scored": r.avg_scored,
        "avg_conceded": r.avg_conceded,
    }
