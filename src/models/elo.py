"""Elo rating model for match outcome and expected-goals estimation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from src import config, db
from src.team_profiles import get_team_prior, normalize_team_name
from src.tournament import match_venue_advantage, max_regional_boost

logger = logging.getLogger(__name__)

ELO_STATE_PATH = config.MODEL_DIR / "elo_ratings.json"


class EloModel:
    """Standard Elo system with home advantage and draw probability."""

    def __init__(
        self,
        k_factor: float = 32.0,
        home_advantage: float = 0.0,
        initial_rating: float = None,
    ):
        self.k_factor = k_factor
        self.home_advantage = home_advantage
        self.initial_rating = initial_rating or config.DEFAULT_ELO
        self.ratings: dict[str, float] = {}

    def get_rating(self, team: str) -> float:
        team = normalize_team_name(team)
        if team not in self.ratings:
            attack, defense = get_team_prior(team)
            self.ratings[team] = self.initial_rating + (attack + defense - 2.0) * 120
        return self.ratings[team]

    def _expected_score(self, rating_a: float, rating_b: float) -> float:
        return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))

    def predict_match(
        self,
        home_team: str,
        away_team: str,
        apply_home_advantage: bool = True,
    ) -> dict[str, Any]:
        """Return outcome probabilities and implied expected goals."""
        home = normalize_team_name(home_team)
        away = normalize_team_name(away_team)
        if apply_home_advantage:
            host_pts = match_venue_advantage(home, away) * (
                config.ELO_HOST_BOOST_POINTS / max_regional_boost()
            )
            home_r = self.get_rating(home) + host_pts
        else:
            home_r = self.get_rating(home)
        away_r = self.get_rating(away)

        home_win = self._expected_score(home_r, away_r)
        away_win = self._expected_score(away_r, home_r)
        draw = max(0.12, 0.32 - abs(home_r - away_r) / 900.0)
        total = home_win + away_win + draw
        home_win /= total
        away_win /= total
        draw /= total

        avg_total_goals = 2.45
        share_home = home_win / max(home_win + away_win, 0.01)
        lambda_home = max(avg_total_goals * share_home * 1.05, 0.5)
        lambda_away = max(avg_total_goals * (1 - share_home) * 0.95, 0.5)

        return {
            "home_win": round(home_win, 4),
            "draw": round(draw, 4),
            "away_win": round(away_win, 4),
            "lambda_home": round(lambda_home, 3),
            "lambda_away": round(lambda_away, 3),
            "home_elo": round(home_r, 1),
            "away_elo": round(away_r, 1),
            "elo_diff": round(home_r - away_r, 1),
        }

    def update_from_result(
        self,
        home_team: str,
        away_team: str,
        home_goals: int,
        away_goals: int,
    ) -> None:
        home = normalize_team_name(home_team)
        away = normalize_team_name(away_team)
        home_r = self.get_rating(home)
        away_r = self.get_rating(away)

        if home_goals > away_goals:
            actual_home, actual_away = 1.0, 0.0
        elif home_goals < away_goals:
            actual_home, actual_away = 0.0, 1.0
        else:
            actual_home, actual_away = 0.5, 0.5

        exp_home = self._expected_score(
            home_r + match_venue_advantage(home, away) * (
                config.ELO_HOST_BOOST_POINTS / max_regional_boost()
            ),
            away_r,
        )
        exp_away = 1.0 - exp_home

        self.ratings[home] = home_r + self.k_factor * (actual_home - exp_home)
        self.ratings[away] = away_r + self.k_factor * (actual_away - exp_away)

    def fit_from_database(self) -> dict[str, Any]:
        """Replay finished matches chronologically to build ratings."""
        self.ratings = {}
        matches = db.get_all_finished_matches()
        for m in matches:
            self.update_from_result(
                m["home_team"],
                m["away_team"],
                int(m["home_goals"]),
                int(m["away_goals"]),
            )
        logger.info("Elo fitted on %d matches (%d teams)", len(matches), len(self.ratings))
        return {"matches": len(matches), "teams": len(self.ratings)}

    def save(self, path: Optional[Path] = None) -> None:
        path = path or ELO_STATE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.ratings, indent=2), encoding="utf-8")

    def load(self, path: Optional[Path] = None) -> bool:
        path = path or ELO_STATE_PATH
        if not path.exists():
            return False
        self.ratings = json.loads(path.read_text(encoding="utf-8"))
        return True

    def get_or_fit(self) -> "EloModel":
        if not self.load():
            self.fit_from_database()
            self.save()
        return self
