"""Position- and importance-aware injury impact on expected goals."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

from src import db
from src import db_extended as dbx
from src.team_profiles import normalize_team_name


POSITION_XG_IMPACT: dict[str, float] = {
    "G": 0.04,
    "D": 0.07,
    "M": 0.12,
    "F": 0.22,
}


@dataclass
class PlayerInjuryImpact:
    player_id: Optional[int]
    player_name: str
    team: str
    position: str
    xg_impact: float
    attack_delta: float
    defense_delta: float

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
        ("GOAL", "G"), ("DEF", "D"), ("MID", "M"), ("ATT", "F"), ("ST", "F"), ("STRIK", "F"),
    ):
        if name in pos:
            return bucket
    return "M"


def _player_importance_multiplier(player_id: Optional[int], player_name: str, team: str) -> float:
    """Scale impact by FC26/API rating when available."""
    if player_id:
        row = dbx.get_player_by_api_id(int(player_id))
        if row and row["rating"]:
            return min(float(row["rating"]) / 80.0, 1.4)
    team_row = dbx.resolve_team(team)
    if team_row:
        for p in dbx.get_players_by_team_id(int(team_row["id"])):
            if p["name"] and p["name"].lower() == player_name.lower() and p["rating"]:
                return min(float(p["rating"]) / 80.0, 1.4)
    return 0.85


def _lookup_player_position(
    player_id: Optional[int], player_name: str, team: str
) -> Optional[str]:
    if player_id:
        row = dbx.get_player_by_api_id(int(player_id))
        if row and row.get("position"):
            return row["position"]
    team_row = dbx.resolve_team(team)
    if team_row:
        for p in dbx.get_players_by_team_id(int(team_row["id"])):
            if p["name"] and p["name"].lower() == player_name.lower():
                return p.get("positions_detail") or p.get("position")
    return None


def _severity_from_reason(reason: Optional[str]) -> float:
    if not reason:
        return 1.0
    text = reason.lower()
    if any(w in text for w in ("season", "long", "acl", "rupture", "surgery")):
        return 1.3
    if any(w in text for w in ("doubt", "minor", "knock")):
        return 0.7
    return 1.0


def estimate_player_xg_impact(
    player_name: str,
    team: str,
    position: Optional[str] = None,
    player_id: Optional[int] = None,
    severity: float = 1.0,
) -> PlayerInjuryImpact:
    bucket = _position_bucket(position)
    base = POSITION_XG_IMPACT.get(bucket, 0.10)
    importance = _player_importance_multiplier(player_id, player_name, team)
    xg = round(base * min(max(severity, 0.5), 1.5) * importance, 3)

    if bucket == "F":
        attack_delta, defense_delta = xg, 0.0
    elif bucket in ("G", "D"):
        attack_delta, defense_delta = 0.0, xg
    else:
        attack_delta, defense_delta = xg * 0.55, xg * 0.45

    return PlayerInjuryImpact(
        player_id=player_id,
        player_name=player_name,
        team=normalize_team_name(team),
        position=bucket,
        xg_impact=xg,
        attack_delta=round(attack_delta, 3),
        defense_delta=round(defense_delta, 3),
    )


def estimate_team_injury_xg(team: str) -> dict[str, Any]:
    team = normalize_team_name(team)
    injuries = db.get_injuries_for_teams([team])
    players: list[dict[str, Any]] = []
    total_attack = total_defense = 0.0

    for row in injuries:
        severity = _severity_from_reason(row["reason"] or row["injury_type"])
        position = _lookup_player_position(row.get("player_id"), row["player_name"], team)
        impact = estimate_player_xg_impact(
            player_name=row["player_name"],
            team=team,
            position=position,
            player_id=row.get("player_id"),
            severity=severity,
        )
        players.append(impact.to_dict())
        total_attack += impact.attack_delta
        total_defense += impact.defense_delta

    total_attack = min(total_attack, 0.55)
    total_defense = min(total_defense, 0.55)
    total_xg = min(total_attack + total_defense, 0.75)
    return {
        "team": team,
        "injured_count": len(injuries),
        "total_xg_impact": round(total_xg, 3),
        "attack_delta": round(total_attack, 3),
        "defense_delta": round(total_defense, 3),
        "players": players,
    }


class InjuryImpactEngine:
    def team_impact(self, team: str) -> dict[str, Any]:
        return estimate_team_injury_xg(team)

    def match_impact(self, home_team: str, away_team: str) -> dict[str, Any]:
        return {"home": estimate_team_injury_xg(home_team), "away": estimate_team_injury_xg(away_team)}

    @staticmethod
    def adjust_lambdas(
        lambda_home: float,
        lambda_away: float,
        home_impact: dict[str, Any],
        away_impact: dict[str, Any],
    ) -> tuple[float, float]:
        """Asymmetric: injuries reduce own attack and weaken own defense."""
        lh = max(
            lambda_home
            - float(home_impact.get("attack_delta", 0))
            + float(away_impact.get("defense_delta", 0)) * 0.5,
            0.5,
        )
        la = max(
            lambda_away
            - float(away_impact.get("attack_delta", 0))
            + float(home_impact.get("defense_delta", 0)) * 0.5,
            0.5,
        )
        return lh, la
