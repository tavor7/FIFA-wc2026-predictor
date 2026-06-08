"""Feature engineering for match prediction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

import numpy as np

from src import config, db
from src.analytics.injury_impact import estimate_team_injury_xg
from src.analytics.momentum import MomentumEngine
from src.analytics.team_form import TeamFormAnalyzer
from src.team_profiles import (
    get_team_prior,
    get_team_prior_detail,
    normalize_team_name,
    prior_metadata,
    prior_to_goal_rates,
)
from src.tournament import match_venue_advantage

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

_form_analyzer = TeamFormAnalyzer()
_momentum_engine = MomentumEngine(_form_analyzer)


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
    """Points-based form; prefers DB-computed opponent-adjusted form."""
    snap = _form_analyzer.compute(team, before_date)
    if snap.source == "computed":
        return snap.opponent_adjusted_form, False
    return snap.form_last_5, True


def _compute_goal_averages(
    team: str, before_date: str
) -> tuple[float, float, bool, bool]:
    """Return avg goals scored/conceded; prefers computed last-5 from DB."""
    snap = _form_analyzer.compute(team, before_date)
    if snap.source == "computed" and snap.matches_used >= 2:
        return snap.goals_scored_last_5, snap.goals_conceded_last_5, False, False

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


def _fc26_expected_xi_strength(team: str) -> tuple[float, str]:
    """Top-11 FC26 ratings as proxy lineup (low reliability)."""
    from src import db_extended as dbx

    team_row = dbx.resolve_team(team)
    if not team_row:
        return 0.55, "heuristic_default"
    players = dbx.get_squad_players(int(team_row["id"]))
    if not players:
        return 0.55, "heuristic_default"
    top = sorted(players, key=lambda p: (p["rating"] or 0), reverse=True)[:11]
    strengths = [
        _player_strength(minutes=900, rating=(p["rating"] or 65) / 10.0, position=p["position"])
        for p in top
    ]
    raw = float(np.mean(strengths))
    capped = 0.55 + (raw - 0.55) * config.FC26_WEIGHT_CAP
    return capped, "player_ratings_fc26"


def _lineup_strength(match_id: int, team: str) -> tuple[float, bool, str]:
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
        return float(np.mean(strengths)), False, "confirmed_lineup"
    fc26_strength, source = _fc26_expected_xi_strength(team)
    if source == "player_ratings_fc26":
        return fc26_strength, False, source
    return 0.55, True, "heuristic_default"


def _injury_impact(team: str) -> tuple[int, float, bool]:
    """Count injuries and xG impact from injury analytics engine."""
    report = estimate_team_injury_xg(team)
    count = int(report.get("injured_count", 0))
    # Zero injuries is valid data (synced or none reported), not missing.
    return count, float(report.get("total_xg_impact", 0.0)), False


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


def build_features_for_match(match_row: Any, for_training: bool = False) -> MatchFeatures:
    """Build full feature set for a single match."""
    match_id = int(match_row["id"])
    home = normalize_team_name(match_row["home_team"])
    away = normalize_team_name(match_row["away_team"])
    match_date = match_row["date"]

    mf = MatchFeatures(match_id=match_id, home_team=home, away_team=away)
    missing: dict[str, bool] = {}
    meta_extra: dict[str, Any] = {}

    home_form_snap = _form_analyzer.compute(home, match_date)
    away_form_snap = _form_analyzer.compute(away, match_date)

    # Elo from fitted ratings when enough history exists, else strength priors
    home_atk, home_def = get_team_prior(home)
    away_atk, away_def = get_team_prior(away)
    prior_elo_diff = (home_atk + home_def) - (away_atk + away_def)
    finished_count = len(db.get_all_finished_matches())
    if finished_count >= 5:
        from src.models.elo import EloModel

        elo_model = EloModel().get_or_fit()
        mf.features["elo_diff"] = (
            elo_model.get_rating(home) - elo_model.get_rating(away)
        ) / 400.0
        missing["elo_diff"] = False
    else:
        mf.features["elo_diff"] = prior_elo_diff
        missing["elo_diff"] = True

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

    mf.features["home_advantage"] = match_venue_advantage(home, away)
    missing["home_advantage"] = False

    rest_home, miss_rh = _compute_rest_days(home, match_date)
    rest_away, miss_ra = _compute_rest_days(away, match_date)
    mf.features["rest_days_diff"] = rest_home - rest_away
    missing["rest_days_diff"] = miss_rh or miss_ra

    if for_training:
        inj_h_count, inj_h_score, _ = _injury_impact(home)
        inj_a_count, inj_a_score, _ = _injury_impact(away)
        mf.features["injured_players_home_count"] = float(inj_h_count)
        mf.features["injured_players_away_count"] = float(inj_a_count)
        mf.features["injured_key_players_home_score"] = inj_h_score
        mf.features["injured_key_players_away_score"] = inj_a_score
        missing["injured_players_home_count"] = False
        missing["injured_players_away_count"] = False
        missing["injured_key_players_home_score"] = False
        missing["injured_key_players_away_score"] = False
        meta_extra["injuries_home"] = inj_h_count
        meta_extra["injuries_away"] = inj_a_count
        meta_extra["injury_source"] = "historical_training"
    else:
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
        meta_extra["injuries_home"] = inj_h_count
        meta_extra["injuries_away"] = inj_a_count

    xi_home, miss_xih, src_home = _lineup_strength(match_id, home)
    xi_away, miss_xia, src_away = _lineup_strength(match_id, away)
    mf.features["starting_xi_strength_home"] = xi_home
    mf.features["starting_xi_strength_away"] = xi_away
    missing["starting_xi_strength_home"] = miss_xih
    missing["starting_xi_strength_away"] = miss_xia
    mf.metadata["starting_xi_strength_home_source"] = src_home
    mf.metadata["starting_xi_strength_away_source"] = src_away

    rc_home, miss_rc_h = _red_card_risk(home, match_date)
    rc_away, miss_rc_a = _red_card_risk(away, match_date)
    mf.features["red_card_risk_recent_home"] = rc_home
    mf.features["red_card_risk_recent_away"] = rc_away
    missing["red_card_risk_recent_home"] = miss_rc_h
    missing["red_card_risk_recent_away"] = miss_rc_a

    mom_home = _momentum_engine.compute(home, match_date, match_id=match_id)
    mom_away = _momentum_engine.compute(away, match_date, match_id=match_id)

    mf.missing_flags = missing
    mf.metadata.update({
        "form_home": form_home,
        "form_away": form_away,
        "form_home_source": home_form_snap.source,
        "form_away_source": away_form_snap.source,
        "form_home_last_5": home_form_snap.form_last_5,
        "form_home_last_10": home_form_snap.form_last_10,
        "form_away_last_5": away_form_snap.form_last_5,
        "form_away_last_10": away_form_snap.form_last_10,
        "home_form_home_split": home_form_snap.home_form,
        "home_form_away_split": home_form_snap.away_form,
        "away_form_home_split": away_form_snap.home_form,
        "away_form_away_split": away_form_snap.away_form,
        "momentum_home": mom_home.score,
        "momentum_away": mom_away.score,
        "momentum_home_detail": mom_home.to_dict(),
        "momentum_away_detail": mom_away.to_dict(),
        "team_form_home": home_form_snap.to_dict(),
        "team_form_away": away_form_snap.to_dict(),
        "strength_home": prior_metadata(home),
        "strength_away": prior_metadata(away),
        "starting_xi_strength_home_source": src_home,
        "starting_xi_strength_away_source": src_away,
        **meta_extra,
    })
    return mf


def build_training_dataset(
    progress_cb: Optional[Callable[[int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[int], list[float]]:
    """
    Build feature matrix and target vectors from finished matches.
    Returns X, y_home, y_away, match_ids, sample_weights.
    """
    from src.services.feature_generation_service import FeatureGenerationService

    finished = db.get_all_finished_matches()
    if not finished:
        return np.empty((0, len(MatchFeatures.feature_names()))), np.array([]), np.array([]), [], []

    from src.services.pipeline_cancel import ModelTrainingCancelled

    svc = FeatureGenerationService()
    X_rows, y_home, y_away, ids, weights = [], [], [], [], []
    total = len(finished)
    for i, m in enumerate(finished):
        if should_cancel and should_cancel():
            raise ModelTrainingCancelled()
        mf = svc.build(m, for_training=True)
        X_rows.append(mf.to_array())
        y_home.append(float(m["home_goals"]))
        y_away.append(float(m["away_goals"]))
        ids.append(int(m["id"]))
        weights.append(float(m.get("competition_weight") or 1.0))
        if progress_cb and (i % 3 == 0 or i == total - 1):
            progress_cb(i + 1, total)

    return np.array(X_rows), np.array(y_home), np.array(y_away), ids, weights
