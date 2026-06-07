"""
EA FC 26 / Kaggle player CSV — column reference and import mapping.

Source: https://www.kaggle.com/datasets/rovnez/fc-26-fifa-26-player-data
110 columns total. We import a focused subset for WC squad pages and analytics.
"""

from __future__ import annotations

# Columns we read from CSV → DB field (see import_fc26_players.py)
FC26_IMPORT_MAP: dict[str, str] = {
    "player_id": "api_player_id",  # stored as FC26_ID_OFFSET + id
    "short_name": "name",  # display name (not long_name)
    "player_positions": "positions_detail",  # e.g. "CM, CDM"
    "overall": "rating",
    "potential": "potential",
    "age": "age",
    "club_name": "club",
    "nationality_name": "_nationality",  # mapped to WC team
    "preferred_foot": "preferred_foot",
    "nation_jersey_number": "jersey_number",
    "pace": "stat_pace",
    "shooting": "stat_shooting",
    "passing": "stat_passing",
    "dribbling": "stat_dribbling",
    "defending": "stat_defending",
    "physic": "stat_physical",
    "international_reputation": "int_reputation",
    "player_face_url": "photo_url",
}

FC26_CSV_USECOLS = list(FC26_IMPORT_MAP.keys())

# Full column inventory (grouped) — for reference / future use
FC26_COLUMN_GROUPS: dict[str, list[str]] = {
    "id_meta": [
        "player_id",
        "player_url",
        "fifa_version",
        "fifa_update",
        "fifa_update_date",
    ],
    "identity": [
        "short_name",
        "long_name",
        "player_positions",
        "player_tags",
        "player_traits",
        "real_face",
        "player_face_url",
    ],
    "ratings_core": [
        "overall",
        "potential",
        "international_reputation",
    ],
    "club": [
        "league_id",
        "league_name",
        "league_level",
        "club_team_id",
        "club_name",
        "club_position",
        "club_jersey_number",
        "club_loaned_from",
        "club_joined_date",
        "club_contract_valid_until_year",
        "value_eur",
        "wage_eur",
        "release_clause_eur",
    ],
    "national_team": [
        "nationality_id",
        "nationality_name",
        "nation_team_id",
        "nation_position",
        "nation_jersey_number",
    ],
    "physical": [
        "age",
        "dob",
        "height_cm",
        "weight_kg",
        "body_type",
        "preferred_foot",
        "weak_foot",
        "skill_moves",
        "work_rate",
    ],
    "face_stats": [
        "pace",
        "shooting",
        "passing",
        "dribbling",
        "defending",
        "physic",
    ],
    "detailed_attacking": [
        "attacking_crossing",
        "attacking_finishing",
        "attacking_heading_accuracy",
        "attacking_short_passing",
        "attacking_volleys",
    ],
    "detailed_skill": [
        "skill_dribbling",
        "skill_curve",
        "skill_fk_accuracy",
        "skill_long_passing",
        "skill_ball_control",
    ],
    "detailed_movement": [
        "movement_acceleration",
        "movement_sprint_speed",
        "movement_agility",
        "movement_reactions",
        "movement_balance",
    ],
    "detailed_power": [
        "power_shot_power",
        "power_jumping",
        "power_stamina",
        "power_strength",
        "power_long_shots",
    ],
    "detailed_mentality": [
        "mentality_aggression",
        "mentality_interceptions",
        "mentality_positioning",
        "mentality_vision",
        "mentality_penalties",
        "mentality_composure",
    ],
    "detailed_defending": [
        "defending_marking_awareness",
        "defending_standing_tackle",
        "defending_sliding_tackle",
    ],
    "goalkeeping": [
        "goalkeeping_diving",
        "goalkeeping_handling",
        "goalkeeping_kicking",
        "goalkeeping_positioning",
        "goalkeeping_reflexes",
        "goalkeeping_speed",
    ],
    "position_ratings": [
        "ls", "st", "rs", "lw", "lf", "cf", "rf", "rw",
        "lam", "cam", "ram", "lm", "lcm", "cm", "rcm", "rm",
        "lwb", "ldm", "cdm", "rdm", "rwb", "lb", "lcb", "cb", "rcb", "rb", "gk",
    ],
}

# Recommended later (not imported yet)
FC26_FUTURE_CANDIDATES: dict[str, str] = {
    "player_traits": "Special traits text (Finesse Shot, etc.) — needs parsing",
    "height_cm": "Squad physical profile",
    "weak_foot": "1–5 weak foot rating",
    "skill_moves": "1–5 skill moves",
    "nation_position": "National-team role (sparse in CSV)",
    "attacking_finishing": "Finisher profile for FWD",
    "mentality_composure": "Penalty / clutch proxy",
    "goalkeeping_*": "GK-specific when position is GK",
    "position_ratings": "Per-slot OVR (27 cols) — redundant with overall for most UI",
    "value_eur": "Club market value — not relevant for national teams",
}
