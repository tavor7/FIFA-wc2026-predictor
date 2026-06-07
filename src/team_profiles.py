"""Team name normalization and pre-tournament strength priors for WC 2026."""

from __future__ import annotations

# Canonical name aliases (API / football-data variants → standard)
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
}

# Pre-tournament attack / defense strength (1.0 = average). Research estimates only.
# attack: expected scoring tendency | defense: higher = stronger defense (concedes less)
TEAM_STRENGTH: dict[str, tuple[float, float]] = {
    "Argentina": (1.48, 1.38),
    "France": (1.45, 1.40),
    "England": (1.40, 1.35),
    "Brazil": (1.42, 1.32),
    "Spain": (1.38, 1.36),
    "Germany": (1.35, 1.34),
    "Portugal": (1.36, 1.30),
    "Netherlands": (1.37, 1.28),
    "Belgium": (1.33, 1.28),
    "Croatia": (1.28, 1.32),
    "Colombia": (1.26, 1.22),
    "Uruguay": (1.24, 1.26),
    "Mexico": (1.22, 1.18),
    "United States": (1.20, 1.20),
    "Switzerland": (1.18, 1.28),
    "Japan": (1.16, 1.24),
    "Senegal": (1.14, 1.22),
    "Morocco": (1.12, 1.26),
    "Ecuador": (1.10, 1.18),
    "Austria": (1.12, 1.20),
    "Norway": (1.14, 1.22),
    "Canada": (1.08, 1.16),
    "South Korea": (1.10, 1.20),
    "Australia": (1.06, 1.18),
    "Paraguay": (1.04, 1.16),
    "Turkey": (1.08, 1.14),
    "Sweden": (1.10, 1.18),
    "Tunisia": (1.02, 1.14),
    "Egypt": (1.04, 1.12),
    "Algeria": (1.06, 1.14),
    "Ivory Coast": (1.08, 1.16),
    "Ghana": (1.06, 1.12),
    "Cameroon": (1.04, 1.12),
    "Czech Republic": (1.10, 1.18),
    "Scotland": (1.06, 1.16),
    "Wales": (1.04, 1.14),
    "Serbia": (1.08, 1.14),
    "Poland": (1.06, 1.16),
    "Ukraine": (1.08, 1.14),
    "Denmark": (1.10, 1.20),
    "Qatar": (0.92, 1.08),
    "Saudi Arabia": (0.94, 1.06),
    "Iran": (0.96, 1.10),
    "Jordan": (0.90, 1.06),
    "Iraq": (0.88, 1.04),
    "Uzbekistan": (0.92, 1.02),
    "South Africa": (0.88, 1.04),
    "Cape Verde": (0.90, 1.06),
    "New Zealand": (0.86, 1.02),
    "Panama": (0.88, 1.00),
    "Haiti": (0.78, 0.92),
    "Curaçao": (0.76, 0.90),
    "Congo DR": (0.94, 1.04),
    "Bosnia & Herzegovina": (1.00, 1.08),
}


def normalize_team_name(name: str) -> str:
    """Map API variants to a canonical team name."""
    name = name.strip()
    return TEAM_ALIASES.get(name, name)


def get_team_prior(team: str) -> tuple[float, float]:
    """
    Return (attack, defense) strength priors.
    Falls back to average (1.0, 1.0) for unknown teams.
    """
    canonical = normalize_team_name(team)
    if canonical in TEAM_STRENGTH:
        return TEAM_STRENGTH[canonical]
    # Case-insensitive lookup
    lower = canonical.lower()
    for key, val in TEAM_STRENGTH.items():
        if key.lower() == lower:
            return val
    return 1.0, 1.0


def prior_to_goal_rates(attack: float, defense: float) -> tuple[float, float]:
    """Convert strength priors to expected goals scored/conceded per match."""
    scored = max(0.5, attack * 1.12)
    conceded = max(0.4, 2.15 - defense * 0.85)
    return round(scored, 2), round(conceded, 2)


def prior_form(attack: float, defense: float) -> float:
    """Derive a 0–1 form proxy from strength priors."""
    return min(max((attack + defense - 1.6) / 1.2, 0.15), 0.85)
