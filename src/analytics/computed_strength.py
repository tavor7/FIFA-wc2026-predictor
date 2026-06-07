"""Data-driven team attack/defense ratings from finished matches in the database."""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any, Optional

from src import db
from src import db_extended as ext
from src.team_names import normalize_team_name

logger = logging.getLogger(__name__)

# Shrinkage toward league average when sample size is small (matches).
SHRINKAGE_K = 6.0
MIN_MATCHES_FOR_RATING = 1


@dataclass
class StrengthRating:
    team: str
    attack: float
    defense: float
    matches: int
    avg_scored: float
    avg_conceded: float
    source: str  # computed | insufficient_data

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _aggregate_team_stats(matches: list[Any]) -> dict[str, dict[str, float]]:
    """Goals for/against and match counts per team."""
    stats: dict[str, dict[str, float]] = {}
    for m in matches:
        home = normalize_team_name(m["home_team"])
        away = normalize_team_name(m["away_team"])
        hg, ag = int(m["home_goals"]), int(m["away_goals"])
        for team, gf, ga in ((home, hg, ag), (away, ag, hg)):
            if team not in stats:
                stats[team] = {"matches": 0, "scored": 0.0, "conceded": 0.0}
            stats[team]["matches"] += 1
            stats[team]["scored"] += gf
            stats[team]["conceded"] += ga
    return stats


def _league_averages(stats: dict[str, dict[str, float]]) -> tuple[float, float]:
    if not stats:
        return 1.2, 1.2
    n = sum(s["matches"] for s in stats.values())
    if n == 0:
        return 1.2, 1.2
    total_scored = sum(s["scored"] for s in stats.values())
    total_conceded = sum(s["conceded"] for s in stats.values())
    return total_scored / n, total_conceded / n


def _shrink(raw: float, n: int) -> float:
    """Pull raw ratio toward 1.0 when n is small."""
    w = n / (n + SHRINKAGE_K)
    return w * raw + (1.0 - w) * 1.0


def compute_all_strengths() -> dict[str, StrengthRating]:
    """
    Derive attack/defense (1.0 = tournament average) from all finished matches.
    No hand-tuned values — only empirical goals with Bayesian shrinkage.
    """
    matches = db.get_all_finished_matches()
    stats = _aggregate_team_stats(matches)
    avg_gf, avg_ga = _league_averages(stats)

    ratings: dict[str, StrengthRating] = {}
    for team, s in stats.items():
        n = int(s["matches"])
        if n < MIN_MATCHES_FOR_RATING:
            continue
        avg_scored = s["scored"] / n
        avg_conceded = s["conceded"] / n
        attack_raw = avg_scored / avg_gf if avg_gf > 0 else 1.0
        defense_raw = avg_ga / avg_conceded if avg_conceded > 0 else 1.0
        ratings[team] = StrengthRating(
            team=team,
            attack=round(_shrink(attack_raw, n), 3),
            defense=round(_shrink(defense_raw, n), 3),
            matches=n,
            avg_scored=round(avg_scored, 2),
            avg_conceded=round(avg_conceded, 2),
            source="computed",
        )

    logger.info(
        "Computed strength for %d teams from %d finished matches",
        len(ratings),
        len(matches),
    )
    return ratings


def recompute_and_persist() -> dict[str, Any]:
    """Recompute ratings from DB and persist on teams table."""
    ratings = compute_all_strengths()
    for rating in ratings.values():
        ext.upsert_team(rating.team)
        ext.update_team_strength(
            rating.team,
            attack=rating.attack,
            defense=rating.defense,
            matches=rating.matches,
            source=rating.source,
            avg_scored=rating.avg_scored,
            avg_conceded=rating.avg_conceded,
        )
    TeamStrengthStore.get().invalidate()
    return {
        "teams_rated": len(ratings),
        "finished_matches": len(db.get_all_finished_matches()),
    }


class TeamStrengthStore:
    """In-memory cache backed by DB-persisted ratings."""

    _instance: Optional["TeamStrengthStore"] = None
    _cache: dict[str, StrengthRating]

    def __init__(self) -> None:
        self._cache = {}

    @classmethod
    def get(cls) -> "TeamStrengthStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def invalidate(self) -> None:
        self._cache.clear()

    def load(self) -> None:
        rows = ext.get_all_team_strengths()
        self._cache = {}
        for row in rows:
            d = dict(row)
            name = normalize_team_name(d["name"])
            attack = d.get("attack_strength")
            if attack is None:
                continue
            self._cache[name] = StrengthRating(
                team=name,
                attack=float(attack),
                defense=float(d.get("defense_strength") or 1.0),
                matches=int(d.get("strength_matches") or 0),
                avg_scored=float(d.get("strength_avg_scored") or 0),
                avg_conceded=float(d.get("strength_avg_conceded") or 0),
                source=str(d.get("strength_source") or "computed"),
            )

    def get_rating(self, team: str) -> StrengthRating:
        team = normalize_team_name(team)
        if not self._cache:
            self.load()
        if team in self._cache:
            return self._cache[team]
        # Case-insensitive
        for key, rating in self._cache.items():
            if key.lower() == team.lower():
                return rating
        return StrengthRating(
            team=team,
            attack=1.0,
            defense=1.0,
            matches=0,
            avg_scored=0.0,
            avg_conceded=0.0,
            source="insufficient_data",
        )


def get_strength_rating(team: str) -> StrengthRating:
    return TeamStrengthStore.get().get_rating(team)
