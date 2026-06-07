"""Canonical team name normalization (shared across analytics and API)."""

from __future__ import annotations

TEAM_ALIASES: dict[str, str] = {
    "Czechia": "Czech Republic",
    "Czech Rep.": "Czech Republic",
    "Bosnia-Herzegovina": "Bosnia & Herzegovina",
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",
    "USA": "United States",
    "US": "United States",
    "Korea Republic": "South Korea",
    "Korea, Republic of": "South Korea",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "DR Congo": "Congo DR",
    "Congo DR": "Congo DR",
    "Cape Verde Islands": "Cape Verde",
    "IR Iran": "Iran",
    "Iran, Islamic Republic of": "Iran",
    "Curaçao": "Curacao",
}


def normalize_team_name(name: str) -> str:
    """Map API variants to a canonical team name."""
    name = name.strip()
    return TEAM_ALIASES.get(name, name)
