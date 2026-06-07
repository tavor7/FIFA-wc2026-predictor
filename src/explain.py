"""Deterministic template-based prediction explanations."""

from __future__ import annotations

from typing import Any

from src.features import MatchFeatures


def _form_phrase(team: str, form: float, other_form: float) -> str | None:
    diff = form - other_form
    if diff > 0.15:
        return f"{team} has stronger recent form"
    if diff < -0.15:
        return f"{team} has weaker recent form recently"
    return None


def _attack_phrase(team: str, avg_scored: float, other_conceded: float) -> str | None:
    if avg_scored > 1.8:
        return f"{team} has been scoring frequently in recent matches"
    if other_conceded > 1.8:
        return f"{team} faces a defense that has conceded regularly"
    return None


def _injury_phrase(team: str, count: int, impact: float, other_count: int) -> str | None:
    if count == 0 and other_count > 0:
        return f"{team} reports fewer injury concerns than their opponent"
    if impact > 0.2:
        return f"{team} is missing several key players through injury"
    if count > 3:
        return f"{team} has a lengthy injury list"
    return None


def _xi_phrase(team: str, strength: float, other_strength: float) -> str | None:
    diff = strength - other_strength
    if diff > 0.08:
        return f"{team}'s estimated starting XI strength is higher"
    if diff < -0.08:
        return f"{team}'s lineup appears weaker on paper"
    return None


def _rest_phrase(home_team: str, away_team: str, rest_diff: float) -> str | None:
    if rest_diff > 2:
        return f"{home_team} had more rest days than {away_team}"
    if rest_diff < -2:
        return f"{away_team} had more rest days than {home_team}"
    return None


def _red_card_phrase(team: str, risk: float) -> str | None:
    if risk > 0.3:
        return f"{team} has shown elevated disciplinary risk in recent games"
    return None


def generate_explanation(
    home_team: str,
    away_team: str,
    predicted_home: int,
    predicted_away: int,
    features: MatchFeatures,
    top_scorelines: list[dict[str, Any]],
    outcomes: dict[str, float],
) -> str:
    """
    Build a readable explanation from feature differences.
    Uses deterministic templates — no LLM.
    """
    f = features.features
    reasons: list[str] = []

    # Home team factors
    for phrase in [
        _form_phrase(home_team, f.get("recent_form_home", 0.5), f.get("recent_form_away", 0.5)),
        _attack_phrase(home_team, f.get("avg_goals_scored_home_last_5", 1.2), f.get("avg_goals_conceded_away_last_5", 1.2)),
        _injury_phrase(
            home_team,
            int(f.get("injured_players_home_count", 0)),
            f.get("injured_key_players_home_score", 0),
            int(f.get("injured_players_away_count", 0)),
        ),
        _xi_phrase(home_team, f.get("starting_xi_strength_home", 0.55), f.get("starting_xi_strength_away", 0.55)),
        _red_card_phrase(home_team, f.get("red_card_risk_recent_home", 0)),
    ]:
        if phrase:
            reasons.append(phrase)

    # Away team factors
    for phrase in [
        _form_phrase(away_team, f.get("recent_form_away", 0.5), f.get("recent_form_home", 0.5)),
        _attack_phrase(away_team, f.get("avg_goals_scored_away_last_5", 1.2), f.get("avg_goals_conceded_home_last_5", 1.2)),
        _injury_phrase(
            away_team,
            int(f.get("injured_players_away_count", 0)),
            f.get("injured_key_players_away_score", 0),
            int(f.get("injured_players_home_count", 0)),
        ),
        _xi_phrase(away_team, f.get("starting_xi_strength_away", 0.55), f.get("starting_xi_strength_home", 0.55)),
        _red_card_phrase(away_team, f.get("red_card_risk_recent_away", 0)),
    ]:
        if phrase and phrase not in reasons:
            reasons.append(phrase)

    rest = _rest_phrase(home_team, away_team, f.get("rest_days_diff", 0))
    if rest:
        reasons.append(rest)

    if f.get("home_advantage", 0) > 0:
        reasons.append(f"{home_team} benefits from a home-advantage adjustment")

    # Outcome context
    if outcomes.get("draw", 0) > 0.28:
        reasons.append("a draw remains a plausible outcome based on balanced probabilities")

    if outcomes.get("away_win", 0) > 0.4:
        reasons.append(f"{away_team} still has a meaningful chance of winning away")

    # Missing data notice
    missing_count = sum(1 for v in features.missing_flags.values() if v)
    if missing_count > 5:
        reasons.append("some inputs used default estimates due to limited available data")

    # Compose final text
    score_str = f"{predicted_home}-{predicted_away}"
    if not reasons:
        top = top_scorelines[0] if top_scorelines else {}
        alt = f"{top.get('home', 1)}-{top.get('away', 1)}"
        return (
            f"Predicted {score_str} based on balanced team metrics. "
            f"The most likely exact scoreline is {alt} "
            f"({top.get('probability', 0):.0%} probability). "
            "This is a probabilistic estimate, not a guaranteed outcome."
        )

    reason_text = ", ".join(reasons[:4])
    if len(reasons) > 4:
        reason_text += f", and {reasons[4].lower()}"

    top = top_scorelines[0] if top_scorelines else {}
    prob_pct = top.get("probability", 0)

    return (
        f"Predicted {score_str} because {reason_text}. "
        f"The most likely exact scoreline is {top.get('home', predicted_home)}-"
        f"{top.get('away', predicted_away)} ({prob_pct:.0%} probability). "
        "Probabilities reflect model estimates for research purposes only."
    )
