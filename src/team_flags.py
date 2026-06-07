"""National flag URLs and team slug helpers for WC 2026."""

from __future__ import annotations

import re
import unicodedata

from src.team_profiles import TEAM_ALIASES, normalize_team_name

# Normalized team name → ISO 3166-1 alpha-2 (flagcdn.com codes)
TEAM_TO_ISO: dict[str, str] = {
    "Argentina": "ar",
    "France": "fr",
    "England": "gb-eng",
    "Brazil": "br",
    "Spain": "es",
    "Germany": "de",
    "Portugal": "pt",
    "Netherlands": "nl",
    "Belgium": "be",
    "Croatia": "hr",
    "Colombia": "co",
    "Uruguay": "uy",
    "Mexico": "mx",
    "United States": "us",
    "Switzerland": "ch",
    "Japan": "jp",
    "Senegal": "sn",
    "Morocco": "ma",
    "Ecuador": "ec",
    "Austria": "at",
    "Norway": "no",
    "Canada": "ca",
    "South Korea": "kr",
    "Australia": "au",
    "Paraguay": "py",
    "Turkey": "tr",
    "Sweden": "se",
    "Tunisia": "tn",
    "Egypt": "eg",
    "Algeria": "dz",
    "Ivory Coast": "ci",
    "Ghana": "gh",
    "Cameroon": "cm",
    "Czech Republic": "cz",
    "Scotland": "gb-sct",
    "Wales": "gb-wls",
    "Serbia": "rs",
    "Poland": "pl",
    "Ukraine": "ua",
    "Denmark": "dk",
    "Qatar": "qa",
    "Saudi Arabia": "sa",
    "Iran": "ir",
    "Jordan": "jo",
    "Iraq": "iq",
    "Uzbekistan": "uz",
    "South Africa": "za",
    "Cape Verde": "cv",
    "New Zealand": "nz",
    "Panama": "pa",
    "Haiti": "ht",
    "Curaçao": "cw",
    "Congo DR": "cd",
    "Bosnia & Herzegovina": "ba",
}

# Alias keys → same ISO as canonical name
for alias, canonical in TEAM_ALIASES.items():
    if canonical in TEAM_TO_ISO:
        TEAM_TO_ISO[alias] = TEAM_TO_ISO[canonical]


def slugify(team_name: str) -> str:
    """Convert a team name to a URL-safe slug."""
    name = normalize_team_name(team_name)
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", ascii_name.lower())
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug or "unknown"


def get_country_code(team_name: str) -> str | None:
    """Return ISO country code for a team, or None if unknown."""
    canonical = normalize_team_name(team_name)
    if canonical in TEAM_TO_ISO:
        return TEAM_TO_ISO[canonical]
    lower = canonical.lower()
    for key, code in TEAM_TO_ISO.items():
        if key.lower() == lower:
            return code
    return None


def get_flag_url(team_name: str, size: int = 40) -> str | None:
    """Return flagcdn.com URL for a team flag, or None if code unknown."""
    code = get_country_code(team_name)
    if not code:
        return None
    return f"https://flagcdn.com/w{size}/{code.lower()}.png"
