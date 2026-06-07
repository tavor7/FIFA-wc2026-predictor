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

    adv = f.get("home_advantage", 0)
    if adv > 0.01:
        reasons.append(
            f"{home_team} gets a small regional boost for 2026 venues in the Americas"
        )
    elif adv < -0.01:
        reasons.append(
            f"{away_team} gets a small regional boost for 2026 venues in the Americas"
        )

    if outcomes.get("draw", 0) > 0.28:
        reasons.append("a draw remains a plausible outcome based on balanced probabilities")

    if outcomes.get("away_win", 0) > 0.4:
        reasons.append(f"{away_team} still has a meaningful chance of winning away")

    missing_count = sum(1 for v in features.missing_flags.values() if v)
    if missing_count > 5:
        reasons.append("some inputs used default estimates due to limited available data")

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
        "Research estimate only — not betting advice. Not affiliated with FIFA."
    )


def build_structured_explanation(
    home_team: str,
    away_team: str,
    predicted_home: int,
    predicted_away: int,
    features: MatchFeatures,
    top_scorelines: list[dict[str, Any]],
    outcomes: dict[str, float],
    positive_factors: list[str] | None = None,
    negative_factors: list[str] | None = None,
    lambda_home: float | None = None,
    lambda_away: float | None = None,
    lambda_home_std: float | None = None,
    lambda_away_std: float | None = None,
) -> dict[str, Any]:
    """Structured explanation for API/UI — separates outcome vs exact-score interpretation."""
    best = top_scorelines[0] if top_scorelines else {"home": predicted_home, "away": predicted_away, "probability": 0.1}
    best_prob = float(best.get("probability", 0))
    draw_pct = round(float(outcomes.get("draw", 0)) * 100, 1)

    positives = list(positive_factors or [])
    negatives = list(negative_factors or [])
    missing: list[str] = []

    meta = features.metadata
    if meta.get("starting_xi_strength_home_source") == "heuristic_default":
        missing.append("confirmed lineups unavailable")
    if not meta.get("referee_data"):
        missing.append("referee data unavailable")
    if meta.get("form_home_source") in ("prior", "insufficient_data"):
        missing.append("limited recent form history")

    for flag, val in features.missing_flags.items():
        if val and len(missing) < 6:
            missing.append(flag.replace("_", " ") + " unavailable")

    probability_note = (
        f"Most likely exact score: {best.get('home', predicted_home)}–{best.get('away', predicted_away)}, "
        f"probability {best_prob * 100:.0f}%. "
        f"Draw probability: {draw_pct}%. "
        "Exact-score probability is naturally low (often 8–15%) — it is the single most likely line, "
        "not overall match confidence."
    )

    return {
        "predicted_score": f"{home_team} {predicted_home}–{predicted_away} {away_team}",
        "predicted_home": predicted_home,
        "predicted_away": predicted_away,
        "top_scorelines": top_scorelines[:5],
        "outcome_probs": {
            "home_win": round(float(outcomes.get("home_win", 0)) * 100, 1),
            "draw": draw_pct,
            "away_win": round(float(outcomes.get("away_win", 0)) * 100, 1),
        },
        "expected_goals": {
            "home": {"mean": lambda_home, "std": lambda_home_std},
            "away": {"mean": lambda_away, "std": lambda_away_std},
        },
        "positive_factors": positives[:5],
        "negative_factors": negatives[:5],
        "missing_data": list(dict.fromkeys(missing))[:6],
        "probability_note": probability_note,
    }
