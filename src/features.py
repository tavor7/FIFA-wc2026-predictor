"""Feature engineering for match prediction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import numpy as np

from src import config, db
from src.team_profiles import (
    get_team_prior,
    normalize_team_name,
    prior_form,
    prior_to_goal_rates,
)

FEATURE_COLUMNS = [
    "elo_diff",
    "recent_form_home",
    "recent_form_away",
    "avg_goals_scored_home_last_5",
    "avg_goals_scored_away_last_5",
    "avg_goals_conceded_home_last_5",
    "avg_goals_conceded_away_last_5",
    "home_advantage",
    "rest_days_diff",
    "injured_players_home_count",
    "injured_players_away_count",
    "injured_key_players_home_score",
    "injured_key_players_away_score",
    "starting_xi_strength_home",
    "starting_xi_strength_away",
    "red_card_risk_recent_home",
    "red_card_risk_recent_away",
]

MISSING_FLAGS = [f"missing_{col}" for col in FEATURE_COLUMNS]


@dataclass
class MatchFeatures:
    """Feature vector for a single match."""

    match_id: int
    home_team: str
    away_team: str
    features: dict[str, float] = field(default_factory=dict)
    missing_flags: dict[str, bool] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_array(self) -> np.ndarray:
        """Return numeric feature array including missingness flags."""
        values = [self.features.get(col, 0.0) for col in FEATURE_COLUMNS]
        flags = [1.0 if self.missing_flags.get(col, False) else 0.0 for col in FEATURE_COLUMNS]
        return np.array(values + flags, dtype=float)

    @staticmethod
    def feature_names() -> list[str]:
        return FEATURE_COLUMNS + MISSING_FLAGS


def _safe_mean(values: list[float], default: float) -> tuple[float, bool]:
    """Compute mean with missingness flag."""
    if not values:
        return default, True
    return float(np.mean(values)), False


def _compute_form(team: str, before_date: str) -> tuple[float, bool]:
    """Points-based form over last 5 matches (win=1, draw=0.5, loss=0)."""
    team = normalize_team_name(team)
    recent = db.get_team_recent_matches(team, before_date, limit=5)
    if recent:
        points: list[float] = []
        for m in recent:
            is_home = m["home_team"] == team
            hg, ag = m["home_goals"], m["away_goals"]
            if hg == ag:
                points.append(0.5)
            elif (is_home and hg > ag) or (not is_home and ag > hg):
                points.append(1.0)
            else:
                points.append(0.0)
        return float(np.mean(points)), False

    all_time = db.get_team_all_time_averages(team)
    if all_time["matches"] >= 2:
        return all_time["form"], False

    attack, defense = get_team_prior(team)
    return prior_form(attack, defense), True


def _compute_goal_averages(
    team: str, before_date: str
) -> tuple[float, float, bool, bool]:
    """Return avg goals scored and conceded over last 5 matches."""
    team = normalize_team_name(team)
    recent = db.get_team_recent_matches(team, before_date, limit=5)
    if recent:
        scored, conceded = [], []
        for m in recent:
            is_home = m["home_team"] == team
            scored.append(float(m["home_goals"] if is_home else m["away_goals"]))
            conceded.append(float(m["away_goals"] if is_home else m["home_goals"]))
        avg_scored, miss_s = _safe_mean(scored, config.DEFAULT_GOALS)
        avg_conceded, miss_c = _safe_mean(conceded, config.DEFAULT_GOALS)
        return avg_scored, avg_conceded, miss_s, miss_c

    all_time = db.get_team_all_time_averages(team)
    if all_time["matches"] >= 2:
        return all_time["scored"], all_time["conceded"], False, False

    attack, defense = get_team_prior(team)
    scored, conceded = prior_to_goal_rates(attack, defense)
    return scored, conceded, True, True


def _compute_rest_days(team: str, before_date: str) -> tuple[float, bool]:
    """Days since last match."""
    recent = db.get_team_recent_matches(team, before_date, limit=1)
    if not recent:
        return 7.0, True
    try:
        last = datetime.fromisoformat(recent[0]["date"].replace("Z", "+00:00"))
        current = datetime.fromisoformat(before_date.replace("Z", "+00:00"))
        return max((current - last).days, 0), False
    except (ValueError, TypeError):
        return 7.0, True


def _position_importance(position: Optional[str]) -> float:
    if not position:
        return 0.75
    pos = position.upper()
    for key, val in config.POSITION_IMPORTANCE.items():
        if key.upper() in pos or pos.startswith(key.upper()):
            return val
    return 0.75


def _player_strength(
    minutes: Optional[float],
    rating: Optional[float],
    goals: float = 0.0,
    assists: float = 0.0,
    position: Optional[str] = None,
    ref_minutes: float = 900.0,
    ref_rating: float = 7.0,
    ref_contribution: float = 5.0,
) -> float:
    """
    Composite player strength score.
    player_strength = 0.40 * norm_minutes + 0.25 * norm_rating
                    + 0.20 * norm_goal_contribution + 0.15 * position_importance
    """
    norm_minutes = min((minutes or 0) / ref_minutes, 1.0)
    norm_rating = min((rating or 6.5) / ref_rating, 1.0)
    norm_contribution = min((goals + assists) / ref_contribution, 1.0)
    pos_imp = _position_importance(position)
    return (
        0.40 * norm_minutes
        + 0.25 * norm_rating
        + 0.20 * norm_contribution
        + 0.15 * pos_imp
    )


def _lineup_strength(match_id: int, team: str) -> tuple[float, bool]:
    """Average strength of confirmed/expected starting XI."""
    lineups = db.get_lineups(match_id)
    starters = [
        row for row in lineups
        if row["team"] == team and row["is_starting"]
    ]
    if starters:
        strengths = [
            _player_strength(
                minutes=row["minutes"],
                rating=row["rating"],
                position=row["position"],
            )
            for row in starters
        ]
        return float(np.mean(strengths)), False
    # No lineup: use default mid-strength
    return 0.55, True


def _injury_impact(team: str) -> tuple[int, float, bool]:
    """Count injuries and estimated impact on key players."""
    injuries = db.get_injuries_for_teams([team])
    if not injuries:
        return 0, 0.0, True

    count = len(injuries)
    # Estimate key player impact from injury records (higher for attackers/midfielders)
    impact = min(count * 0.08, 0.5)
    return count, impact, False


def _red_card_risk(team: str, before_date: str) -> tuple[float, bool]:
    """Recent red card rate from team match stats."""
    recent = db.get_team_recent_matches(team, before_date, limit=5)
    if not recent:
        return 0.05, True

    reds = 0
    for m in recent:
        stats = db.get_team_match_stats(int(m["id"]))
        for s in stats:
            if s["team"] == team and s["red_cards"]:
                reds += int(s["red_cards"])
    return min(reds / len(recent), 1.0), False


def build_features_for_match(match_row: Any) -> MatchFeatures:
    """Build full feature set for a single match."""
    match_id = int(match_row["id"])
    home = normalize_team_name(match_row["home_team"])
    away = normalize_team_name(match_row["away_team"])
    match_date = match_row["date"]

    mf = MatchFeatures(match_id=match_id, home_team=home, away_team=away)
    missing: dict[str, bool] = {}

    # Elo proxy from pre-tournament strength priors
    home_atk, home_def = get_team_prior(home)
    away_atk, away_def = get_team_prior(away)
    mf.features["elo_diff"] = (home_atk + home_def) - (away_atk + away_def)
    missing["elo_diff"] = False

    form_home, miss_fh = _compute_form(home, match_date)
    form_away, miss_fa = _compute_form(away, match_date)
    mf.features["recent_form_home"] = form_home
    mf.features["recent_form_away"] = form_away
    missing["recent_form_home"] = miss_fh
    missing["recent_form_away"] = miss_fa

    hs, hc, miss_hs, miss_hc = _compute_goal_averages(home, match_date)
    as_, ac, miss_as, miss_ac = _compute_goal_averages(away, match_date)
    mf.features["avg_goals_scored_home_last_5"] = hs
    mf.features["avg_goals_scored_away_last_5"] = as_
    mf.features["avg_goals_conceded_home_last_5"] = hc
    mf.features["avg_goals_conceded_away_last_5"] = ac
    missing["avg_goals_scored_home_last_5"] = miss_hs
    missing["avg_goals_scored_away_last_5"] = miss_as
    missing["avg_goals_conceded_home_last_5"] = miss_hc
    missing["avg_goals_conceded_away_last_5"] = miss_ac

    mf.features["home_advantage"] = config.HOME_ADVANTAGE
    missing["home_advantage"] = False

    rest_home, miss_rh = _compute_rest_days(home, match_date)
    rest_away, miss_ra = _compute_rest_days(away, match_date)
    mf.features["rest_days_diff"] = rest_home - rest_away
    missing["rest_days_diff"] = miss_rh or miss_ra

    inj_h_count, inj_h_score, miss_ih = _injury_impact(home)
    inj_a_count, inj_a_score, miss_ia = _injury_impact(away)
    mf.features["injured_players_home_count"] = float(inj_h_count)
    mf.features["injured_players_away_count"] = float(inj_a_count)
    mf.features["injured_key_players_home_score"] = inj_h_score
    mf.features["injured_key_players_away_score"] = inj_a_score
    missing["injured_players_home_count"] = miss_ih
    missing["injured_players_away_count"] = miss_ia
    missing["injured_key_players_home_score"] = miss_ih
    missing["injured_key_players_away_score"] = miss_ia

    xi_home, miss_xih = _lineup_strength(match_id, home)
    xi_away, miss_xia = _lineup_strength(match_id, away)
    mf.features["starting_xi_strength_home"] = xi_home
    mf.features["starting_xi_strength_away"] = xi_away
    missing["starting_xi_strength_home"] = miss_xih
    missing["starting_xi_strength_away"] = miss_xia

    rc_home, miss_rc_h = _red_card_risk(home, match_date)
    rc_away, miss_rc_a = _red_card_risk(away, match_date)
    mf.features["red_card_risk_recent_home"] = rc_home
    mf.features["red_card_risk_recent_away"] = rc_away
    missing["red_card_risk_recent_home"] = miss_rc_h
    missing["red_card_risk_recent_away"] = miss_rc_a

    mf.missing_flags = missing
    mf.metadata = {
        "form_home": form_home,
        "form_away": form_away,
        "injuries_home": inj_h_count,
        "injuries_away": inj_a_count,
    }
    return mf


def build_training_dataset() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[int]]:
    """
    Build feature matrix and target vectors from finished matches.
    Returns X, y_home, y_away, match_ids.
    """
    finished = db.get_all_finished_matches()
    if not finished:
        return np.empty((0, len(MatchFeatures.feature_names()))), np.array([]), np.array([]), []

    X_rows, y_home, y_away, ids = [], [], [], []
    for m in finished:
        mf = build_features_for_match(m)
        X_rows.append(mf.to_array())
        y_home.append(float(m["home_goals"]))
        y_away.append(float(m["away_goals"]))
        ids.append(int(m["id"]))

    return np.array(X_rows), np.array(y_home), np.array(y_away), ids
