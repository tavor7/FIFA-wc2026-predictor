"""Load bundled historical international match seeds."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.seed.load_seeds import SEED_DIR, _upsert_seed_match

logger = logging.getLogger(__name__)

HISTORICAL_DIR = SEED_DIR / "historical"

COMPETITION_WEIGHTS = {
    "FIFA World Cup": 1.0,
    "UEFA Euro": 1.0,
    "Copa America": 0.95,
    "AFCON": 0.9,
    "Asian Cup": 0.9,
    "World Cup Qualifier": 0.6,
    "Nations League": 0.7,
    "International Friendly": 0.3,
}


def _weight_for_league(league: str) -> float:
    for key, weight in COMPETITION_WEIGHTS.items():
        if key.lower() in (league or "").lower():
            return weight
    return 0.5


def load_historical_seeds() -> dict[str, Any]:
    from src import db
    from src.db import _execute, get_connection

    if not HISTORICAL_DIR.is_dir():
        return {"files": 0, "matches": 0}

    total = 0
    files = 0
    candidates = list(HISTORICAL_DIR.glob("*.json")) if HISTORICAL_DIR.is_dir() else []
    if not candidates:
        candidates = [SEED_DIR / "wc2022_results.json"] if (SEED_DIR / "wc2022_results.json").is_file() else []

    for path in candidates:
        payload = json.loads(path.read_text()) if path.is_file() else []
        if isinstance(payload, dict):
            rows = payload.get("matches", [])
        else:
            rows = payload
        for row in rows:
            league = row.get("league") or path.stem.replace("_", " ")
            row["league"] = league
            match_id = _upsert_seed_match(row, {})
            if match_id:
                weight = _weight_for_league(league)
                with get_connection() as conn:
                    _execute(
                        conn,
                        """
                        UPDATE matches SET competition_weight = ?, competition_type = ?
                        WHERE id = ?
                        """,
                        (weight, league, match_id),
                    )
                total += 1
        files += 1
    logger.info("Loaded %d historical matches from %d seed files", total, files)
    return {"files": files, "matches": total}
