"""Compare prediction versions and explain what changed."""

from __future__ import annotations

import json
from typing import Any, Optional


def _parse_features(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def explain_prediction_change(
    previous: Optional[dict[str, Any]],
    current: dict[str, Any],
    current_features: Optional[dict[str, Any]] = None,
    previous_features: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Return structured change bullets between two prediction snapshots."""
    bullets: list[str] = []
    if not previous:
        return {"summary": "Initial prediction", "bullets": ["First prediction generated"]}

    cf = current_features or {}
    pf = previous_features or _parse_features(previous.get("features_json"))

    dh = float(current.get("home_win_prob") or 0) - float(previous.get("home_win_prob") or 0)
    if abs(dh) >= 0.03:
        bullets.append(
            f"Home win probability {'increased' if dh > 0 else 'decreased'} by {abs(dh * 100):.1f} percentage points"
        )

    ph, pa = int(previous.get("predicted_home_goals") or 0), int(previous.get("predicted_away_goals") or 0)
    ch, ca = int(current.get("predicted_home_goals") or 0), int(current.get("predicted_away_goals") or 0)
    if (ph, pa) != (ch, ca):
        bullets.append(f"Predicted scoreline changed from {ph}–{pa} to {ch}–{ca}")

    for key, label in (
        ("recent_form_home", "Home team recent form"),
        ("recent_form_away", "Away team recent form"),
        ("elo_diff", "Elo rating gap"),
        ("rest_days_diff", "Rest advantage"),
    ):
        if key in cf and key in pf:
            delta = float(cf[key]) - float(pf[key])
            if abs(delta) >= 0.05:
                bullets.append(f"{label} updated ({delta:+.2f})")

    ih = float(cf.get("injured_key_players_home_score") or 0) - float(
        pf.get("injured_key_players_home_score") or 0
    )
    ia = float(cf.get("injured_key_players_away_score") or 0) - float(
        pf.get("injured_key_players_away_score") or 0
    )
    if ih > 0.05:
        bullets.append("Home team injury impact increased")
    elif ih < -0.05:
        bullets.append("Home team injury situation improved")
    if ia > 0.05:
        bullets.append("Away team injury impact increased")
    elif ia < -0.05:
        bullets.append("Away team injury situation improved")

    xh = float(cf.get("starting_xi_strength_home") or 0) - float(pf.get("starting_xi_strength_home") or 0)
    xa = float(cf.get("starting_xi_strength_away") or 0) - float(pf.get("starting_xi_strength_away") or 0)
    if abs(xh) >= 0.03:
        bullets.append("Home lineup strength estimate changed")
    if abs(xa) >= 0.03:
        bullets.append("Away lineup strength estimate changed")

    if current.get("model_version") and previous.get("model_version"):
        if current["model_version"] != previous["model_version"]:
            bullets.append("Models were retrained with newer match data")

    summary = "; ".join(bullets[:3]) if bullets else "Minor internal model adjustment"
    return {"summary": summary, "bullets": bullets or ["Minor internal model adjustment"]}
