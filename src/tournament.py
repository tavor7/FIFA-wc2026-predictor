"""FIFA World Cup 2026 tournament context (neutral venues, regional boosts)."""

from __future__ import annotations

from typing import Optional

from src import config
from src.team_names import normalize_team_name

# Co-host nations — small regional familiarity boost, not traditional home advantage
WC_2026_HOSTS = frozenset({"United States", "Mexico", "Canada"})

# CONMEBOL — closer travel / climate familiarity for 2026 venues in the Americas
SOUTH_AMERICA = frozenset({
    "Argentina",
    "Bolivia",
    "Brazil",
    "Chile",
    "Colombia",
    "Ecuador",
    "Paraguay",
    "Peru",
    "Uruguay",
    "Venezuela",
})


def regional_advantage_type(team: str) -> Optional[str]:
    """Return co_host, south_america, or None."""
    name = normalize_team_name(team)
    if name in WC_2026_HOSTS:
        return "co_host"
    if name in SOUTH_AMERICA:
        return "south_america"
    return None


def is_regional_advantage_team(team: str) -> bool:
    return regional_advantage_type(team) is not None


def is_host_region_team(team: str) -> bool:
    """True if team gets any Americas regional boost (co-host or South America)."""
    return is_regional_advantage_team(team)


def regional_boost(team: str) -> float:
    """Small edge for co-hosts and South American teams at 2026 venues."""
    name = normalize_team_name(team)
    if name in WC_2026_HOSTS:
        return config.HOST_REGION_BOOST
    if name in SOUTH_AMERICA:
        return config.SOUTH_AMERICA_BOOST
    return 0.0


def host_region_boost(team: str) -> float:
    """Alias for regional_boost (kept for API compatibility)."""
    return regional_boost(team)


def max_regional_boost() -> float:
    return max(config.HOST_REGION_BOOST, config.SOUTH_AMERICA_BOOST, 0.001)


def match_venue_advantage(home_team: str, away_team: str) -> float:
    """
    Net venue adjustment for the designated home slot in the fixture list.
    WC is neutral-site; only regional familiarity in the Americas applies.
    """
    return regional_boost(home_team) - regional_boost(away_team)
