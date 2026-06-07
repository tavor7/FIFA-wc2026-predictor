"""Monte Carlo tournament simulation with stored probability outputs."""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Any, Optional

from src import db
from src.models.elo import EloModel
from src.team_profiles import normalize_team_name

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    n_simulations: int
    team_win_probabilities: dict[str, float]
    team_advancement_probabilities: dict[str, dict[str, float]]
    most_likely_winner: str
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TournamentSimulator:
    """Simulate remaining fixtures to estimate tournament outcomes."""

    FINISHED = frozenset({"FT", "AET", "PEN", "FINISHED"})

    def __init__(self, elo: Optional[EloModel] = None, seed: Optional[int] = 42):
        self.elo = elo or EloModel()
        self.seed = seed

    def _fixtures(self) -> list[Any]:
        upcoming = db.get_upcoming_matches(limit=500)
        finished = db.get_all_finished_matches()
        return list(finished) + list(upcoming)

    def _teams(self, fixtures: list[Any]) -> list[str]:
        teams: set[str] = set()
        for m in fixtures:
            teams.add(normalize_team_name(m["home_team"]))
            teams.add(normalize_team_name(m["away_team"]))
        return sorted(teams)

    def _simulate_match(self, home: str, away: str) -> tuple[int, int]:
        probs = self.elo.predict_match(home, away)
        r = random.random()
        if r < probs["home_win"]:
            return (2, 1) if random.random() > 0.35 else (1, 0)
        if r < probs["home_win"] + probs["draw"]:
            return (1, 1) if random.random() > 0.5 else (0, 0)
        return (0, 1) if random.random() > 0.35 else (1, 2)

    def run(self, n_simulations: int = 5000, store: bool = True) -> SimulationResult:
        """Run Monte Carlo simulations and optionally persist results."""
        from datetime import datetime

        random.seed(self.seed)
        self.elo.fit_from_database()

        fixtures = self._fixtures()
        teams = self._teams(fixtures)
        upcoming = [m for m in fixtures if m["status"] not in self.FINISHED]

        win_counts: dict[str, int] = defaultdict(int)
        knockout_counts: dict[str, int] = defaultdict(int)
        group_top_counts: dict[str, int] = defaultdict(int)

        for _ in range(n_simulations):
            points: dict[str, float] = defaultdict(float)
            for m in fixtures:
                home = normalize_team_name(m["home_team"])
                away = normalize_team_name(m["away_team"])
                if m["status"] in self.FINISHED and m["home_goals"] is not None:
                    hg, ag = int(m["home_goals"]), int(m["away_goals"])
                else:
                    hg, ag = self._simulate_match(home, away)

                if hg > ag:
                    points[home] += 3
                elif hg == ag:
                    points[home] += 1
                    points[away] += 1
                else:
                    points[away] += 3

            ranked = sorted(points.items(), key=lambda x: (-x[1], x[0]))
            if ranked:
                group_top_counts[ranked[0][0]] += 1
            top_half = max(1, len(ranked) // 2)
            for team, _ in ranked[:top_half]:
                knockout_counts[team] += 1
            if ranked:
                win_counts[ranked[0][0]] += 1

        n = max(n_simulations, 1)
        win_probs = {t: round(win_counts.get(t, 0) / n, 4) for t in teams}
        advance_probs = {
            t: {
                "group_leader": round(group_top_counts.get(t, 0) / n, 4),
                "knockout_stage": round(knockout_counts.get(t, 0) / n, 4),
            }
            for t in teams
        }
        winner = max(win_probs, key=win_probs.get) if win_probs else ""
        now = datetime.utcnow().isoformat()

        result = SimulationResult(
            n_simulations=n_simulations,
            team_win_probabilities=win_probs,
            team_advancement_probabilities=advance_probs,
            most_likely_winner=winner,
            generated_at=now,
        )

        if store:
            db.upsert_tournament_simulation(
                n_simulations=n_simulations,
                results={
                    "team_win_probabilities": win_probs,
                    "team_advancement_probabilities": advance_probs,
                    "most_likely_winner": winner,
                    "fixtures_used": len(upcoming),
                    "teams": len(teams),
                },
            )
            logger.info(
                "Stored tournament simulation (%d runs, %d teams, leader=%s)",
                n_simulations,
                len(teams),
                winner,
            )

        return result

    @staticmethod
    def latest() -> Optional[dict[str, Any]]:
        return db.get_latest_tournament_simulation()
