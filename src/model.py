"""Machine learning models for expected goals and scoreline probabilities."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
from scipy.stats import poisson
from sklearn.ensemble import RandomForestRegressor

from src import config, db
from src.features import MatchFeatures, build_training_dataset

logger = logging.getLogger(__name__)


class GoalPredictionModel:
    """Dual RandomForest regressors with Poisson scoreline distribution."""

    def __init__(self):
        self.home_model = RandomForestRegressor(
            n_estimators=100,
            max_depth=8,
            random_state=42,
            n_jobs=-1,
        )
        self.away_model = RandomForestRegressor(
            n_estimators=100,
            max_depth=8,
            random_state=43,
            n_jobs=-1,
        )
        self._is_trained = False

    def train_model(self, min_samples: int = 10) -> dict[str, Any]:
        """Train on finished matches in the database."""
        X, y_home, y_away, match_ids = build_training_dataset()

        if len(X) < min_samples:
            logger.warning(
                "Only %d samples available (min %d); using heuristic defaults",
                len(X),
                min_samples,
            )
            self._is_trained = False
            return {
                "trained": False,
                "samples": len(X),
                "message": f"Insufficient data ({len(X)} matches). Using heuristic predictions.",
            }

        self.home_model.fit(X, y_home)
        self.away_model.fit(X, y_away)
        self._is_trained = True

        home_preds = self.home_model.predict(X)
        away_preds = self.away_model.predict(X)
        home_mae = float(np.mean(np.abs(home_preds - y_home)))
        away_mae = float(np.mean(np.abs(away_preds - y_away)))

        logger.info("Model trained on %d matches. Home MAE=%.3f, Away MAE=%.3f", len(X), home_mae, away_mae)
        return {
            "trained": True,
            "samples": len(X),
            "home_mae": home_mae,
            "away_mae": away_mae,
            "match_ids": match_ids,
        }

    def save_model(self, home_path: Optional[Path] = None, away_path: Optional[Path] = None) -> None:
        """Persist trained models to disk."""
        home_path = home_path or config.HOME_MODEL_PATH
        away_path = away_path or config.AWAY_MODEL_PATH
        home_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.home_model, home_path)
        joblib.dump(self.away_model, away_path)
        logger.info("Models saved to %s and %s", home_path, away_path)

    def load_model(self, home_path: Optional[Path] = None, away_path: Optional[Path] = None) -> bool:
        """Load models from disk; return True if successful."""
        home_path = home_path or config.HOME_MODEL_PATH
        away_path = away_path or config.AWAY_MODEL_PATH
        if not home_path.exists() or not away_path.exists():
            return False
        self.home_model = joblib.load(home_path)
        self.away_model = joblib.load(away_path)
        self._is_trained = True
        logger.info("Models loaded from disk")
        return True

    def predict_expected_goals(self, match_features: MatchFeatures) -> tuple[float, float]:
        """
        Predict expected home and away goals.
        Falls back to heuristic if model not trained.
        """
        if self._is_trained:
            X = match_features.to_array().reshape(1, -1)
            home = max(float(self.home_model.predict(X)[0]), 0.1)
            away = max(float(self.away_model.predict(X)[0]), 0.1)
            return home, away

        return self._heuristic_expected_goals(match_features)

    @staticmethod
    def _heuristic_expected_goals(mf: MatchFeatures) -> tuple[float, float]:
        """Simple heuristic when ML model is unavailable."""
        f = mf.features
        home_lambda = (
            0.30 * f.get("avg_goals_scored_home_last_5", config.DEFAULT_GOALS)
            + 0.22 * (1.0 - f.get("avg_goals_conceded_away_last_5", config.DEFAULT_GOALS) / 3)
            + 0.15 * f.get("recent_form_home", config.DEFAULT_FORM)
            + 0.10 * f.get("starting_xi_strength_home", 0.55)
            + 0.10 * f.get("home_advantage", config.HOME_ADVANTAGE)
            + 0.08 * max(f.get("elo_diff", 0), 0)
            - 0.05 * f.get("injured_key_players_home_score", 0)
        )
        away_lambda = (
            0.30 * f.get("avg_goals_scored_away_last_5", config.DEFAULT_GOALS)
            + 0.22 * (1.0 - f.get("avg_goals_conceded_home_last_5", config.DEFAULT_GOALS) / 3)
            + 0.15 * f.get("recent_form_away", config.DEFAULT_FORM)
            + 0.10 * f.get("starting_xi_strength_away", 0.55)
            + 0.08 * max(-f.get("elo_diff", 0), 0)
            - 0.05 * f.get("injured_key_players_away_score", 0)
        )
        return max(home_lambda, 0.35), max(away_lambda, 0.35)

    @staticmethod
    def scoreline_distribution(
        lambda_home: float,
        lambda_away: float,
        max_goals: int = 6,
    ) -> dict[tuple[int, int], float]:
        """
        Compute probability of each scoreline using independent Poisson distributions.
        Returns dict mapping (home_goals, away_goals) -> probability.
        """
        dist: dict[tuple[int, int], float] = {}
        for h in range(max_goals + 1):
            for a in range(max_goals + 1):
                prob = poisson.pmf(h, lambda_home) * poisson.pmf(a, lambda_away)
                dist[(h, a)] = float(prob)
        total = sum(dist.values())
        if total > 0:
            dist = {k: v / total for k, v in dist.items()}
        return dist

    @staticmethod
    def outcome_probabilities(scorelines: dict[tuple[int, int], float]) -> dict[str, float]:
        """Derive home win, draw, away win probabilities from scoreline distribution."""
        home_win = draw = away_win = 0.0
        for (h, a), prob in scorelines.items():
            if h > a:
                home_win += prob
            elif h == a:
                draw += prob
            else:
                away_win += prob
        return {"home_win": home_win, "draw": draw, "away_win": away_win}

    @staticmethod
    def top_scorelines(
        scorelines: dict[tuple[int, int], float], n: int = 5
    ) -> list[dict[str, Any]]:
        """Return top N most likely scorelines."""
        sorted_lines = sorted(scorelines.items(), key=lambda x: x[1], reverse=True)[:n]
        return [
            {"home": h, "away": a, "probability": round(prob, 4)}
            for (h, a), prob in sorted_lines
        ]

    @property
    def is_trained(self) -> bool:
        return self._is_trained


def get_or_create_model() -> GoalPredictionModel:
    """Load existing model or return fresh instance."""
    model = GoalPredictionModel()
    if not model.load_model():
        logger.info("No saved model found; will use heuristics until trained")
    return model
