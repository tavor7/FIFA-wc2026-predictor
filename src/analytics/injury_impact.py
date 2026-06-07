"""Estimate expected-goals impact from player injuries."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

from src import db
from src.team_profiles import normalize_team_name


POSITION_XG_IMPACT: dict[str, float] = {
    "G": 0.04,
    "D": 0.07,
    "M": 0.12,
    "F": 0.22,
    "Goalkeeper": 0.04,
    "Defender": 0.07,
    "Midfielder": 0.12,
    "Attacker": 0.22,
}


@dataclass
class PlayerInjuryImpact:
    player_id: Optional[int]
    player_name: str
    team: str
    position: str
    xg_impact: float
    attacking_pct: float
    defensive_pct: float
    midfield_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _position_bucket(position: Optional[str]) -> str:
    if not position:
        return "M"
    pos = position.upper()
    for key in ("G", "D", "M", "F"):
        if pos.startswith(key) or key in pos:
            return key
    for name, bucket in (
        ("GOAL", "G"),
        ("DEF", "D"),
        ("MID", "M"),
        ("ATT", "F"),
        ("STRIK", "F"),
        ("FORW", "F"),
    ):
        if name in pos:
            return bucket
    return "M"


def estimate_player_xg_impact(
    player_name: str,
    team: str,
    position: Optional[str] = None,
    player_id: Optional[int] = None,
    severity: float = 1.0,
) -> PlayerInjuryImpact:
    """Estimate per-player xG delta when unavailable."""
    bucket = _position_bucket(position)
    base = POSITION_XG_IMPACT.get(bucket, 0.10)
    xg = round(base * min(max(severity, 0.5), 1.5), 3)

    attacking = xg if bucket == "F" else (xg * 0.35 if bucket == "M" else 0.0)
    defensive = xg if bucket in ("G", "D") else (xg * 0.25 if bucket == "M" else 0.0)
    midfield = xg if bucket == "M" else (xg * 0.2 if bucket == "F" else xg * 0.15)

    return PlayerInjuryImpact(
        player_id=player_id,
        player_name=player_name,
        team=normalize_team_name(team),
        position=bucket,
        xg_impact=xg,
        attacking_pct=round(-attacking / max(base, 0.01) * 100, 1),
        defensive_pct=round(-defensive / max(base, 0.01) * 100, 1),
        midfield_pct=round(-midfield / max(base, 0.01) * 100, 1),
    )


def _severity_from_reason(reason: Optional[str]) -> float:
    if not reason:
        return 1.0
    text = reason.lower()
    if any(w in text for w in ("season", "long", "acl", "rupture", "surgery")):
        return 1.3
    if any(w in text for w in ("doubt", "minor", "knock")):
        return 0.7
    return 1.0


def estimate_team_injury_xg(team: str) -> dict[str, Any]:
    """Aggregate injury xG impact for a team."""
    team = normalize_team_name(team)
    injuries = db.get_injuries_for_teams([team])
    players: list[dict[str, Any]] = []
    total_xg = 0.0
    total_attack = 0.0
    total_defense = 0.0
    total_mid = 0.0

    for row in injuries:
        severity = _severity_from_reason(row["reason"] or row["injury_type"])
        impact = estimate_player_xg_impact(
            player_name=row["player_name"],
            team=team,
            position=None,
            player_id=row["player_id"],
            severity=severity,
        )
        players.append(impact.to_dict())
        total_xg += impact.xg_impact
        bucket = impact.position
        if bucket == "F":
            total_attack += impact.xg_impact
        elif bucket in ("G", "D"):
            total_defense += impact.xg_impact
        else:
            total_mid += impact.xg_impact

    total_xg = min(total_xg, 0.75)
    return {
        "team": team,
        "injured_count": len(injuries),
        "total_xg_impact": round(total_xg, 3),
        "attacking_strength_pct": round(-min(total_attack / max(total_xg, 0.01), 1.0) * 100, 1),
        "defensive_strength_pct": round(-min(total_defense / max(total_xg, 0.01), 1.0) * 100, 1),
        "midfield_strength_pct": round(-min(total_mid / max(total_xg, 0.01), 1.0) * 100, 1),
        "players": players,
    }


class InjuryImpactEngine:
    """Facade for per-match injury adjustments."""

    def team_impact(self, team: str) -> dict[str, Any]:
        return estimate_team_injury_xg(team)

    def match_impact(self, home_team: str, away_team: str) -> dict[str, Any]:
        return {
            "home": estimate_team_injury_xg(home_team),
            "away": estimate_team_injury_xg(away_team),
        }

    @staticmethod
    def adjust_lambdas(
        lambda_home: float,
        lambda_away: float,
        home_impact: dict[str, Any],
        away_impact: dict[str, Any],
    ) -> tuple[float, float]:
        """Subtract estimated xG from each side's expected goals."""
        lh = max(lambda_home - float(home_impact.get("total_xg_impact", 0)), 0.5)
        la = max(lambda_away - float(away_impact.get("total_xg_impact", 0)), 0.5)
        return lh, la
