"""In-game win/draw/loss and remaining-goals model."""

from __future__ import annotations

from typing import Any

from src.model import GoalPredictionModel


def _event_counts(events: list[dict[str, Any]], team: str) -> dict[str, int]:
    out = {"yellow": 0, "red": 0, "subs": 0}
    for e in events:
        if e.get("team") != team:
            continue
        detail = (e.get("detail") or e.get("type") or "").lower()
        if "red" in detail:
            out["red"] += 1
        elif "yellow" in detail:
            out["yellow"] += 1
        elif "subst" in detail:
            out["subs"] += 1
    return out


class LiveMatchModel:
    """Adjust pre-match lambdas using live match state."""

    def predict(
        self,
        prematch_lambda_home: float,
        prematch_lambda_away: float,
        match_row: dict[str, Any],
        team_stats: dict[str, dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        home = match_row["home_team"]
        away = match_row["away_team"]
        hg = int(match_row.get("home_goals") or 0)
        ag = int(match_row.get("away_goals") or 0)
        minute = self._estimate_minute(match_row.get("status") or "")

        time_factor = max(0.08, 1.0 - minute / 95.0)
        lh = max(prematch_lambda_home * time_factor, 0.15)
        la = max(prematch_lambda_away * time_factor, 0.15)

        hs = team_stats.get(home, {})
        as_ = team_stats.get(away, {})
        h_sot = float(hs.get("shots_on_target") or 0)
        a_sot = float(as_.get("shots_on_target") or 0)
        h_poss = float(hs.get("possession") or 50)
        shot_edge = (h_sot - a_sot) * 0.04
        poss_edge = (h_poss - 50) / 100 * 0.08
        lh += max(shot_edge, -0.2) + max(poss_edge, -0.05)
        la += max(-shot_edge, -0.2) + max(-poss_edge, -0.05)

        h_cards = _event_counts(events, home)
        a_cards = _event_counts(events, away)
        lh -= a_cards["red"] * 0.18 + a_cards["yellow"] * 0.02
        la -= h_cards["red"] * 0.18 + h_cards["yellow"] * 0.02

        score_diff = hg - ag
        if score_diff > 0:
            la *= 1.08
            lh *= 0.92
        elif score_diff < 0:
            lh *= 1.08
            la *= 0.92

        lh = max(lh, 0.1)
        la = max(la, 0.1)

        scorelines = GoalPredictionModel.scoreline_distribution(lh, la, max_goals=8)
        outcomes = GoalPredictionModel.outcome_probabilities(scorelines)

        return {
            "minute": minute,
            "current_score": f"{hg}-{ag}",
            "lambda_home": round(lh, 3),
            "lambda_away": round(la, 3),
            "lambda_home_std": 0.2,
            "lambda_away_std": 0.18,
            "home_win": round(outcomes["home_win"], 4),
            "draw": round(outcomes["draw"], 4),
            "away_win": round(outcomes["away_win"], 4),
            "confidence_pct": 60.0 if minute < 70 else 72.0,
            "explanation": f"Live model at ~{minute}' with score {hg}–{ag}",
            "factors": {
                "time_remaining_factor": round(time_factor, 2),
                "shot_edge": round(shot_edge, 3),
                "possession_edge": round(poss_edge, 3),
            },
        }

    @staticmethod
    def _estimate_minute(status: str) -> int:
        mapping = {"1H": 25, "HT": 45, "2H": 67, "ET": 100, "P": 115, "LIVE": 50}
        return mapping.get(status, 30)
