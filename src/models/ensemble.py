"""Weighted ensemble combining Elo, Poisson/RF, and optional XGBoost."""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np

from src import config
from src.analytics.injury_impact import InjuryImpactEngine
from src.features import MatchFeatures
from src.model import GoalPredictionModel
from src.models.elo import EloModel

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBRegressor

    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    XGBRegressor = None  # type: ignore


@dataclass
class ModelPrediction:
    name: str
    lambda_home: float
    lambda_away: float
    home_win: float
    draw: float
    away_win: float
    weight: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EnsembleResult:
    lambda_home: float
    lambda_away: float
    lambda_home_mean: float
    lambda_home_std: float
    lambda_away_mean: float
    lambda_away_std: float
    home_win: float
    draw: float
    away_win: float
    models: list[ModelPrediction]
    agreement_score: float
    consensus_label: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["models"] = [m.to_dict() for m in self.models]
        return data


class EnsemblePredictor:
    """Combine multiple engines into a consensus prediction."""

    BASE_WEIGHTS = {
        "elo": 0.20,
        "poisson_rf": 0.35,
        "poisson_heuristic": 0.25,
        "xgboost": 0.20,
    }

    def __init__(
        self,
        goal_model: Optional[GoalPredictionModel] = None,
        elo: Optional[EloModel] = None,
    ):
        self.goal_model = goal_model or GoalPredictionModel()
        self.elo = elo or EloModel()
        self.injury_engine = InjuryImpactEngine()
        self.xgb_home: Any = None
        self.xgb_away: Any = None
        self._xgb_trained = False
        if HAS_XGBOOST:
            self.xgb_home = XGBRegressor(
                n_estimators=80, max_depth=5, learning_rate=0.08, random_state=44, n_jobs=-1
            )
            self.xgb_away = XGBRegressor(
                n_estimators=80, max_depth=5, learning_rate=0.08, random_state=45, n_jobs=-1
            )

    def _weights(self) -> dict[str, float]:
        w = dict(self.BASE_WEIGHTS)
        if self.goal_model.is_trained:
            w["poisson_heuristic"] = 0.0
            w["poisson_rf"] = w["poisson_rf"] + w.pop("poisson_heuristic", 0.0)
        else:
            w["poisson_rf"] = 0.0
            w["poisson_heuristic"] = w["poisson_heuristic"] + w.pop("poisson_rf", 0.0)
        if not (HAS_XGBOOST and self._xgb_trained):
            extra = w.pop("xgboost", 0.0)
            total_other = sum(v for v in w.values() if v > 0) or 1.0
            for key in w:
                w[key] += extra * (w[key] / total_other)
        total = sum(w.values()) or 1.0
        return {k: v / total for k, v in w.items()}

    def train_xgboost(self, min_samples: int = 10) -> dict[str, Any]:
        if not HAS_XGBOOST:
            return {"trained": False, "message": "xgboost not installed"}
        from src.features import build_training_dataset

        X, y_home, y_away, _ids, _weights = build_training_dataset()
        if len(X) < min_samples:
            self._xgb_trained = False
            return {"trained": False, "samples": len(X)}

        self.xgb_home.fit(X, y_home)
        self.xgb_away.fit(X, y_away)
        self._xgb_trained = True
        self.save_xgboost()
        return {"trained": True, "samples": len(X)}

    def save_xgboost(self) -> None:
        if not self._xgb_trained or not HAS_XGBOOST:
            return
        config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.xgb_home, config.XGB_HOME_MODEL_PATH)
        joblib.dump(self.xgb_away, config.XGB_AWAY_MODEL_PATH)

    def load_xgboost(self) -> bool:
        if not HAS_XGBOOST:
            return False
        if not config.XGB_HOME_MODEL_PATH.exists() or not config.XGB_AWAY_MODEL_PATH.exists():
            return False
        self.xgb_home = joblib.load(config.XGB_HOME_MODEL_PATH)
        self.xgb_away = joblib.load(config.XGB_AWAY_MODEL_PATH)
        self._xgb_trained = True
        return True

    def _outcomes_from_lambdas(self, lh: float, la: float) -> tuple[float, float, float]:
        scorelines = GoalPredictionModel.scoreline_distribution(lh, la)
        outcomes = GoalPredictionModel.outcome_probabilities(scorelines)
        return outcomes["home_win"], outcomes["draw"], outcomes["away_win"]

    def predict(self, match_features: MatchFeatures) -> EnsembleResult:
        self.elo.get_or_fit()
        weights = self._weights()
        preds: list[ModelPrediction] = []

        elo_out = self.elo.predict_match(match_features.home_team, match_features.away_team)
        preds.append(
            ModelPrediction(
                name="elo",
                lambda_home=elo_out["lambda_home"],
                lambda_away=elo_out["lambda_away"],
                home_win=elo_out["home_win"],
                draw=elo_out["draw"],
                away_win=elo_out["away_win"],
                weight=weights.get("elo", 0.2),
            )
        )

        rf_lh, rf_la = self.goal_model.predict_expected_goals(match_features)
        rf_hw, rf_d, rf_aw = self._outcomes_from_lambdas(rf_lh, rf_la)
        rf_key = "poisson_rf" if self.goal_model.is_trained else "poisson_heuristic"
        preds.append(
            ModelPrediction(
                name=rf_key,
                lambda_home=rf_lh,
                lambda_away=rf_la,
                home_win=rf_hw,
                draw=rf_d,
                away_win=rf_aw,
                weight=weights.get(rf_key, 0.3),
            )
        )

        if HAS_XGBOOST and self._xgb_trained:
            X = match_features.to_array().reshape(1, -1)
            xgb_lh = max(float(self.xgb_home.predict(X)[0]), 0.1)
            xgb_la = max(float(self.xgb_away.predict(X)[0]), 0.1)
            xgb_hw, xgb_d, xgb_aw = self._outcomes_from_lambdas(xgb_lh, xgb_la)
            preds.append(
                ModelPrediction(
                    name="xgboost",
                    lambda_home=xgb_lh,
                    lambda_away=xgb_la,
                    home_win=xgb_hw,
                    draw=xgb_d,
                    away_win=xgb_aw,
                    weight=weights.get("xgboost", 0.2),
                )
            )

        lh_vals = np.array([p.lambda_home for p in preds])
        la_vals = np.array([p.lambda_away for p in preds])
        w_vals = np.array([p.weight for p in preds])
        lambda_home_mean = float(np.average(lh_vals, weights=w_vals))
        lambda_away_mean = float(np.average(la_vals, weights=w_vals))
        lambda_home_std = float(np.std(lh_vals))
        lambda_away_std = float(np.std(la_vals))

        lambda_home = lambda_home_mean
        lambda_away = lambda_away_mean

        home_imp = self.injury_engine.team_impact(match_features.home_team)
        away_imp = self.injury_engine.team_impact(match_features.away_team)
        if self.goal_model.is_trained:
            scale = 0.35
            home_imp = {
                **home_imp,
                "attack_delta": home_imp.get("attack_delta", 0) * scale,
                "defense_delta": home_imp.get("defense_delta", 0) * scale,
            }
            away_imp = {
                **away_imp,
                "attack_delta": away_imp.get("attack_delta", 0) * scale,
                "defense_delta": away_imp.get("defense_delta", 0) * scale,
            }
        lambda_home, lambda_away = self.injury_engine.adjust_lambdas(
            lambda_home, lambda_away, home_imp, away_imp
        )

        home_win, draw, away_win = self._outcomes_from_lambdas(lambda_home, lambda_away)
        agreement = self._agreement_score(preds)
        label = "High" if agreement >= 0.75 else ("Medium" if agreement >= 0.5 else "Low")

        return EnsembleResult(
            lambda_home=round(lambda_home, 3),
            lambda_away=round(lambda_away, 3),
            lambda_home_mean=round(lambda_home_mean, 3),
            lambda_home_std=round(lambda_home_std, 3),
            lambda_away_mean=round(lambda_away_mean, 3),
            lambda_away_std=round(lambda_away_std, 3),
            home_win=round(home_win, 4),
            draw=round(draw, 4),
            away_win=round(away_win, 4),
            models=preds,
            agreement_score=round(agreement, 3),
            consensus_label=label,
        )

    @staticmethod
    def _agreement_score(models: list[ModelPrediction]) -> float:
        if len(models) < 2:
            return 1.0
        lh = np.array([m.lambda_home for m in models])
        la = np.array([m.lambda_away for m in models])
        spread = float(np.std(lh) + np.std(la))
        return max(0.0, min(1.0, 1.0 - spread / 1.2))

    def train_all(self, min_samples: int = 10) -> dict[str, Any]:
        rf_result = self.goal_model.train_model(min_samples=min_samples)
        if rf_result.get("trained"):
            self.goal_model.save_model()
        xgb_result = self.train_xgboost(min_samples=min_samples)
        self.elo.fit_from_database()
        self.elo.save()
        return {"random_forest": rf_result, "xgboost": xgb_result, "elo": {"teams": len(self.elo.ratings)}}


def get_or_create_ensemble() -> EnsemblePredictor:
    ensemble = EnsemblePredictor()
    ensemble.goal_model.load_model()
    ensemble.load_xgboost()
    return ensemble
