"""Map EA FC 26 CSV nationality_name → WC 2026 team names in our database."""

from __future__ import annotations

# nationality_name (SoFIFA / Kaggle) → team name (matches wc2026_groups.json)
NATIONALITY_TO_TEAM: dict[str, str] = {
    "Korea Republic": "South Korea",
    "USA": "United States",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Czech Republic": "Czechia",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Cape Verde": "Cape Verde Islands",
    "Cabo Verde": "Cape Verde Islands",
    "DR Congo": "Congo DR",
    "Dem. Rep. of Congo": "Congo DR",
    "Turkiye": "Turkey",
    "Türkiye": "Turkey",
    "IR Iran": "Iran",
    "Curacao": "Curaçao",
    "Curaçao": "Curaçao",
}


def nationality_to_team(nationality: str) -> str:
    nat = (nationality or "").strip()
    return NATIONALITY_TO_TEAM.get(nat, nat)
