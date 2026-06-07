"""Team momentum score (0-100) from recent performance signals."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

from src.analytics.injury_impact import estimate_team_injury_xg
from src.analytics.team_form import TeamFormAnalyzer, opponent_strength
from src import db
from src.team_profiles import normalize_team_name


@dataclass
class MomentumSnapshot:
    team: str
    score: float
    recent_results: float
    goal_difference: float
    opponent_quality: float
    scoring_trend: float
    squad_availability: float
    tournament_performance: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MomentumEngine:
    """Composite momentum index on a 0-100 scale."""

    WEIGHTS = {
        "recent_results": 0.30,
        "goal_difference": 0.20,
        "opponent_quality": 0.20,
        "scoring_trend": 0.15,
        "squad_availability": 0.10,
        "tournament_performance": 0.05,
    }

    def __init__(self, form_analyzer: Optional[TeamFormAnalyzer] = None):
        self.form_analyzer = form_analyzer or TeamFormAnalyzer()

    def compute(self, team: str, before_date: str, match_id: Optional[int] = None) -> MomentumSnapshot:
        team = normalize_team_name(team)
        form = self.form_analyzer.compute(team, before_date)
        recent = self.form_analyzer.team_matches_before(team, before_date, limit=5)

        recent_results = self._scale(form.opponent_adjusted_form, 0.0, 1.0)
        goal_diff = self._goal_diff_score(team, recent)
        opp_quality = self._opponent_quality_score(team, recent)
        scoring_trend = self._scale(
            form.goals_scored_last_5 - form.goals_conceded_last_5, -2.0, 2.0
        )
        squad_avail = self._squad_availability(team)
        tournament = self._tournament_score(team, before_date)

        weighted = (
            self.WEIGHTS["recent_results"] * recent_results
            + self.WEIGHTS["goal_difference"] * goal_diff
            + self.WEIGHTS["opponent_quality"] * opp_quality
            + self.WEIGHTS["scoring_trend"] * scoring_trend
            + self.WEIGHTS["squad_availability"] * squad_avail
            + self.WEIGHTS["tournament_performance"] * tournament
        )
        score = round(min(max(weighted * 100, 0.0), 100.0), 1)

        return MomentumSnapshot(
            team=team,
            score=score,
            recent_results=round(recent_results * 100, 1),
            goal_difference=round(goal_diff * 100, 1),
            opponent_quality=round(opp_quality * 100, 1),
            scoring_trend=round(scoring_trend * 100, 1),
            squad_availability=round(squad_avail * 100, 1),
            tournament_performance=round(tournament * 100, 1),
        )

    @staticmethod
    def _scale(value: float, low: float, high: float) -> float:
        if high <= low:
            return 0.5
        return min(max((value - low) / (high - low), 0.0), 1.0)

    @staticmethod
    def _goal_diff_score(team: str, recent: list[Any]) -> float:
        if not recent:
            return 0.5
        diffs = []
        for m in recent:
            is_home = m["home_team"] == team
            hg, ag = int(m["home_goals"]), int(m["away_goals"])
            diffs.append((hg - ag) if is_home else (ag - hg))
        return MomentumEngine._scale(sum(diffs) / len(diffs), -2.0, 2.0)

    @staticmethod
    def _opponent_quality_score(team: str, recent: list[Any]) -> float:
        if not recent:
            return 0.5
        strengths = []
        for m in recent:
            opp = m["away_team"] if m["home_team"] == team else m["home_team"]
            strengths.append(opponent_strength(normalize_team_name(opp)))
        avg = sum(strengths) / len(strengths)
        return MomentumEngine._scale(avg, 0.85, 1.35)

    @staticmethod
    def _squad_availability(team: str) -> float:
        impact = estimate_team_injury_xg(team)
        total_xg = float(impact.get("total_xg_impact", 0.0))
        return max(0.0, 1.0 - min(total_xg / 0.8, 1.0))

    @staticmethod
    def _tournament_score(team: str, before_date: str) -> float:
        team = normalize_team_name(team)
        rows = db.get_team_recent_matches(team, before_date, limit=20)
        if not rows:
            return 0.5
        wc_rows = [r for r in rows if "world" in str(r["league"] or "").lower()]
        sample = wc_rows or rows
        points = []
        for m in sample:
            is_home = m["home_team"] == team
            hg, ag = int(m["home_goals"]), int(m["away_goals"])
            if hg == ag:
                points.append(0.5)
            elif (is_home and hg > ag) or (not is_home and ag > hg):
                points.append(1.0)
            else:
                points.append(0.0)
        return sum(points) / len(points)
