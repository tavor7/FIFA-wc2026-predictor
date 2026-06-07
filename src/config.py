"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    """Read config from Streamlit secrets (cloud) or environment (.env)."""
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


# API keys
API_FOOTBALL_KEY: str = _env("API_FOOTBALL_KEY")
FOOTBALL_DATA_KEY: str = _env("FOOTBALL_DATA_KEY")

# Target competition (FIFA World Cup)
LEAGUE_ID: int = int(_env("LEAGUE_ID", "1"))
SEASON: int = int(_env("SEASON", "2026"))
# football-data.org uses competition id 2000 for FIFA World Cup (not 1)
FOOTBALL_DATA_COMPETITION_ID: int = int(_env("FOOTBALL_DATA_COMPETITION_ID", "2000"))

# Database
DB_PATH: Path = PROJECT_ROOT / _env("DB_PATH", "data/football.db")

# API settings
API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"
FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"

REQUEST_TIMEOUT: int = 30
MAX_RETRIES: int = 3
RETRY_BACKOFF: float = 1.5

# Rate limiting (API-Football free tier: ~10 req/min)
MIN_REQUEST_INTERVAL: float = 6.0

# Model artifacts
MODEL_DIR: Path = PROJECT_ROOT / "data" / "models"
HOME_MODEL_PATH: Path = MODEL_DIR / "home_goals_model.joblib"
AWAY_MODEL_PATH: Path = MODEL_DIR / "away_goals_model.joblib"

# Feature defaults
DEFAULT_ELO: float = 1500.0
DEFAULT_FORM: float = 0.5
DEFAULT_GOALS: float = 1.2
HOME_ADVANTAGE: float = 0.15

# Position importance weights for player strength
POSITION_IMPORTANCE: dict[str, float] = {
    "G": 0.6,
    "D": 0.7,
    "M": 0.85,
    "F": 1.0,
    "Goalkeeper": 0.6,
    "Defender": 0.7,
    "Midfielder": 0.85,
    "Attacker": 1.0,
}
