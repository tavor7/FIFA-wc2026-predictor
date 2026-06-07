"""Team form analytics from finished matches in the database."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

from src import db
from src.team_profiles import get_team_prior, get_team_prior_detail, normalize_team_name, prior_form


@dataclass
class TeamFormSnapshot:
    """Computed form metrics for a team before a given date."""

    team: str
    form_last_5: float
    form_last_10: float
    home_form: float
    away_form: float
    goals_scored_last_5: float
    goals_conceded_last_5: float
    goals_scored_last_10: float
    goals_conceded_last_10: float
    clean_sheets_last_5: int
    opponent_adjusted_form: float
    matches_used: int
    source: str  # "computed" | "prior"

    def to_dict(self) -> dict[str, Any]:
        from src.tournament import host_region_boost, regional_advantage_type

        d = asdict(self)
        for key in (
            "goals_scored_last_5",
            "goals_conceded_last_5",
            "goals_scored_last_10",
            "goals_conceded_last_10",
        ):
            if d.get(key) is not None:
                d[key] = round(float(d[key]), 2)
        adv = regional_advantage_type(self.team)
        d["regional_advantage"] = adv
        d["regional_boost"] = host_region_boost(self.team)
        d["host_region"] = adv is not None
        d["host_region_boost"] = d["regional_boost"]
        return d


def _match_points(team: str, match_row: Any) -> float:
    is_home = match_row["home_team"] == team
    hg, ag = int(match_row["home_goals"]), int(match_row["away_goals"])
    if hg == ag:
        return 0.5
    if (is_home and hg > ag) or (not is_home and ag > hg):
        return 1.0
    return 0.0


def _goals_for_against(team: str, match_row: Any) -> tuple[int, int]:
    is_home = match_row["home_team"] == team
    hg, ag = int(match_row["home_goals"]), int(match_row["away_goals"])
    if is_home:
        return hg, ag
    return ag, hg


def opponent_strength(team: str) -> float:
    """Proxy opponent quality from pre-tournament priors (1.0 = average)."""
    attack, defense = get_team_prior(team)
    return (attack + defense) / 2.0


class TeamFormAnalyzer:
    """Compute rolling form, splits, and opponent-adjusted metrics."""

    def __init__(self, finished_matches: Optional[list[Any]] = None):
        self._finished = finished_matches

    def _finished_matches(self) -> list[Any]:
        if self._finished is not None:
            return self._finished
        return db.get_all_finished_matches()

    def team_matches_before(self, team: str, before_date: str, limit: int = 10) -> list[Any]:
        team = normalize_team_name(team)
        return db.get_team_recent_matches(team, before_date, limit=limit)

    def compute(self, team: str, before_date: str) -> TeamFormSnapshot:
        """Build full form snapshot, falling back to priors when data is sparse."""
        team = normalize_team_name(team)
        recent_10 = self.team_matches_before(team, before_date, limit=10)
        recent_5 = recent_10[:5]

        if len(recent_5) >= 2:
            return self._from_matches(team, recent_5, recent_10)

        all_time = db.get_team_all_time_averages(team)
        if all_time["matches"] >= 2:
            return self._from_all_time(team, all_time)

        rating = get_team_prior_detail(team)
        if rating.matches > 0:
            form = prior_form(rating.attack, rating.defense)
            return TeamFormSnapshot(
                team=team,
                form_last_5=form,
                form_last_10=form,
                home_form=form,
                away_form=form,
                goals_scored_last_5=rating.avg_scored,
                goals_conceded_last_5=rating.avg_conceded,
                goals_scored_last_10=rating.avg_scored,
                goals_conceded_last_10=rating.avg_conceded,
                clean_sheets_last_5=0,
                opponent_adjusted_form=form,
                matches_used=rating.matches,
                source="strength_ratings",
            )

        return TeamFormSnapshot(
            team=team,
            form_last_5=0.5,
            form_last_10=0.5,
            home_form=0.5,
            away_form=0.5,
            goals_scored_last_5=1.2,
            goals_conceded_last_5=1.2,
            goals_scored_last_10=1.2,
            goals_conceded_last_10=1.2,
            clean_sheets_last_5=0,
            opponent_adjusted_form=0.5,
            matches_used=0,
            source="insufficient_data",
        )

    def _from_matches(
        self, team: str, recent_5: list[Any], recent_10: list[Any]
    ) -> TeamFormSnapshot:
        points_5 = [_match_points(team, m) for m in recent_5]
        points_10 = [_match_points(team, m) for m in recent_10]

        home_pts, away_pts = [], []
        for m in recent_10:
            pt = _match_points(team, m)
            if m["home_team"] == team:
                home_pts.append(pt)
            else:
                away_pts.append(pt)

        scored_5, conceded_5, clean_5 = [], [], 0
        for m in recent_5:
            gf, ga = _goals_for_against(team, m)
            scored_5.append(float(gf))
            conceded_5.append(float(ga))
            if ga == 0:
                clean_5 += 1

        scored_10, conceded_10 = [], []
        for m in recent_10:
            gf, ga = _goals_for_against(team, m)
            scored_10.append(float(gf))
            conceded_10.append(float(ga))

        adj_num, adj_den = 0.0, 0.0
        for m in recent_5:
            opp = m["away_team"] if m["home_team"] == team else m["home_team"]
            weight = opponent_strength(normalize_team_name(opp))
            adj_num += _match_points(team, m) * weight
            adj_den += weight
        adj_form = adj_num / adj_den if adj_den > 0 else sum(points_5) / len(points_5)

        def _avg(vals: list[float], default: float = 0.5) -> float:
            return sum(vals) / len(vals) if vals else default

        return TeamFormSnapshot(
            team=team,
            form_last_5=_avg(points_5),
            form_last_10=_avg(points_10),
            home_form=_avg(home_pts),
            away_form=_avg(away_pts),
            goals_scored_last_5=_avg(scored_5, 1.2),
            goals_conceded_last_5=_avg(conceded_5, 1.2),
            goals_scored_last_10=_avg(scored_10, 1.2),
            goals_conceded_last_10=_avg(conceded_10, 1.2),
            clean_sheets_last_5=clean_5,
            opponent_adjusted_form=adj_form,
            matches_used=len(recent_5),
            source="computed",
        )

    @staticmethod
    def _from_all_time(team: str, stats: dict[str, float]) -> TeamFormSnapshot:
        form = float(stats["form"])
        scored = float(stats["scored"])
        conceded = float(stats["conceded"])
        return TeamFormSnapshot(
            team=team,
            form_last_5=form,
            form_last_10=form,
            home_form=form,
            away_form=form,
            goals_scored_last_5=scored,
            goals_conceded_last_5=conceded,
            goals_scored_last_10=scored,
            goals_conceded_last_10=conceded,
            clean_sheets_last_5=0,
            opponent_adjusted_form=form,
            matches_used=int(stats["matches"]),
            source="computed",
        )
