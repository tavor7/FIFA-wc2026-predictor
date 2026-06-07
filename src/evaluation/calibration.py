"""Probability calibration metrics."""

from __future__ import annotations

from typing import Any

import numpy as np

from src import db


def multiclass_brier(probs: list[float], actual_index: int) -> float:
    actual = np.zeros(3)
    actual[actual_index] = 1.0
    return float(np.sum((np.array(probs) - actual) ** 2))


def multiclass_log_loss(probs: list[float], actual_index: int, eps: float = 1e-15) -> float:
    p = max(min(probs[actual_index], 1 - eps), eps)
    return float(-np.log(p))


def expected_calibration_error(probs: list[float], outcomes: list[int], n_bins: int = 10) -> float:
    if not probs:
        return 0.0
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = [(bins[i] <= p < bins[i + 1]) for p in probs]
        if not any(mask):
            continue
        avg_conf = np.mean([probs[j] for j, m in enumerate(mask) if m])
        avg_acc = np.mean([outcomes[j] for j, m in enumerate(mask) if m])
        ece += abs(avg_conf - avg_acc) * sum(mask) / len(probs)
    return float(ece)


def calibration_curve(probs: list[float], outcomes: list[int], n_bins: int = 10) -> list[dict[str, float]]:
    bins = np.linspace(0, 1, n_bins + 1)
    curve = []
    for i in range(n_bins):
        mask = [(bins[i] <= p < bins[i + 1]) for p in probs]
        if not any(mask):
            continue
        curve.append({
            "bin_start": float(bins[i]),
            "bin_end": float(bins[i + 1]),
            "avg_predicted": float(np.mean([probs[j] for j, m in enumerate(mask) if m])),
            "avg_actual": float(np.mean([outcomes[j] for j, m in enumerate(mask) if m])),
            "count": int(sum(mask)),
        })
    return curve


def evaluate_stored_predictions(limit: int = 200) -> dict[str, Any]:
    finished = db.get_all_finished_matches()[:limit]
    briers, loglosses, home_probs, home_outcomes = [], [], [], []

    for m in finished:
        pred = db.get_prediction(int(m["id"]))
        if not pred:
            continue
        hg, ag = int(m["home_goals"]), int(m["away_goals"])
        if hg > ag:
            idx = 0
            home_outcomes.append(1)
        elif hg == ag:
            idx = 1
            home_outcomes.append(0)
        else:
            idx = 2
            home_outcomes.append(0)
        probs = [float(pred["home_win_prob"]), float(pred["draw_prob"]), float(pred["away_win_prob"])]
        briers.append(multiclass_brier(probs, idx))
        loglosses.append(multiclass_log_loss(probs, idx))
        home_probs.append(float(pred["home_win_prob"]))

    return {
        "samples": len(briers),
        "brier_score": round(float(np.mean(briers)), 4) if briers else None,
        "log_loss": round(float(np.mean(loglosses)), 4) if loglosses else None,
        "ece_home_win": round(expected_calibration_error(home_probs, home_outcomes), 4) if home_probs else None,
        "calibration_curve": calibration_curve(home_probs, home_outcomes) if home_probs else [],
    }
