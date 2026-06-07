"""Import EA FC 26 player ratings (Kaggle) into squad tables."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests

from src import config, db
from src import db_extended as dbx
from src.seed.fc26_columns import FC26_CSV_USECOLS
from src.seed.load_seeds import SEED_DIR, _load_json
from src.seed.nationality_map import nationality_to_team
from src.team_flags import get_country_code, slugify
from src.team_names import normalize_team_name

logger = logging.getLogger(__name__)

FC26_CSV_PATH = SEED_DIR / "fc26_players.csv"
FC26_CSV_URL = (
    "https://raw.githubusercontent.com/ismailoksuz/EAFC26-DataHub/main/data/players.csv"
)
FC26_ID_OFFSET = 260_000_000
SQUAD_SIZE = 26


def _primary_position(raw: str) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    pos = raw.split(",")[0].strip().upper()
    if pos == "GK":
        return "G"
    if pos in {"LB", "RB", "CB", "LWB", "RWB", "LCB", "RCB", "SW"}:
        return "D"
    if pos in {"CM", "CDM", "CAM", "LM", "RM", "LCM", "RCM", "LDM", "RDM", "LAM", "RAM"}:
        return "M"
    return "F"


def _positions_detail(raw: str) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    return raw.strip().upper() or None


def _optional_int(val: Any) -> Optional[int]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _optional_float(val: Any) -> Optional[float]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _wc_team_names() -> set[str]:
    groups = _load_json("wc2026_groups.json").get("groups") or {}
    teams: set[str] = set()
    for members in groups.values():
        teams.update(members)
    return teams


def ensure_fc26_csv(path: Path = FC26_CSV_PATH) -> Path:
    """Download FC26 player CSV if not present locally."""
    if path.is_file() and path.stat().st_size > 1_000_000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading FC26 player data (~11MB)...")
    resp = requests.get(FC26_CSV_URL, timeout=120)
    resp.raise_for_status()
    path.write_bytes(resp.content)
    logger.info("Saved FC26 CSV to %s", path)
    return path


def _resolve_team_id(team_name: str) -> int:
    """Match existing WC team row (seed/API may use a different display name)."""
    canonical = normalize_team_name(team_name)
    slug = slugify(canonical)
    existing = dbx.get_team_by_slug(slug) or dbx.get_team_by_name(canonical) or dbx.get_team_by_name(team_name)
    if existing:
        return int(existing["id"])
    return dbx.upsert_team(
        canonical,
        slug=slug,
        country_code=get_country_code(canonical),
    )


def _clear_fc26_players() -> int:
    with db.get_connection() as conn:
        from src.db import _execute

        row = _execute(
            conn,
            "SELECT COUNT(*) AS c FROM players WHERE api_player_id >= ?",
            (FC26_ID_OFFSET,),
        ).fetchone()
        before = int(dict(row)["c"])
        _execute(conn, "DELETE FROM players WHERE api_player_id >= ?", (FC26_ID_OFFSET,))
    return before


def _row_to_player_kwargs(row: Any) -> dict[str, Any]:
    pos_raw = str(row.get("player_positions") or "")
    name = str(row.get("short_name") or row.get("long_name") or "Unknown").strip()
    foot = str(row.get("preferred_foot") or "").strip()
    photo = str(row.get("player_face_url") or "").strip()
    return {
        "name": name,
        "position": _primary_position(pos_raw),
        "positions_detail": _positions_detail(pos_raw),
        "rating": _optional_float(row.get("overall")),
        "potential": _optional_float(row.get("potential")),
        "age": _optional_int(row.get("age")),
        "club": str(row.get("club_name") or "").strip() or None,
        "preferred_foot": foot[:1].upper() if foot else None,
        "jersey_number": _optional_int(row.get("nation_jersey_number")),
        "stat_pace": _optional_float(row.get("pace")),
        "stat_shooting": _optional_float(row.get("shooting")),
        "stat_passing": _optional_float(row.get("passing")),
        "stat_dribbling": _optional_float(row.get("dribbling")),
        "stat_defending": _optional_float(row.get("defending")),
        "stat_physical": _optional_float(row.get("physic")),
        "int_reputation": _optional_int(row.get("international_reputation")),
        "photo_url": photo or None,
    }


def import_fc26_players(
    csv_path: Optional[Path] = None,
    squad_size: int = SQUAD_SIZE,
    download: bool = True,
) -> dict[str, Any]:
    """
    Load Kaggle / SoFIFA FC26 ratings for WC 2026 national teams.
    Uses short_name for display and six face stats for squad detail.
    """
    db.init_db()
    path = csv_path or FC26_CSV_PATH
    if download and not path.is_file():
        ensure_fc26_csv(path)

    if not path.is_file():
        raise FileNotFoundError(
            f"FC26 CSV not found at {path}. "
            "Download from Kaggle or run with download=True."
        )

    wc_teams = _wc_team_names()
    df = pd.read_csv(path, usecols=FC26_CSV_USECOLS)
    df["team"] = df["nationality_name"].map(nationality_to_team)
    df = df[df["team"].isin(wc_teams)].copy()
    df["overall"] = pd.to_numeric(df["overall"], errors="coerce")
    df = df.dropna(subset=["overall"])
    df = df.sort_values(["team", "overall"], ascending=[True, False])

    removed = _clear_fc26_players()
    written = 0
    teams_touched: set[str] = set()

    for team_name, group in df.groupby("team"):
        team_id = _resolve_team_id(team_name)
        teams_touched.add(team_name)
        for _, row in group.head(squad_size).iterrows():
            pid = int(row["player_id"])
            kwargs = _row_to_player_kwargs(row)
            dbx.upsert_player(
                team_id=team_id,
                api_player_id=FC26_ID_OFFSET + pid,
                **kwargs,
            )
            written += 1

    dbx.insert_sync_log(
        "import_fc26_players",
        "ok",
        source="kaggle_fc26",
        records_affected=written,
    )
    return {
        "source": "EA FC 26 (Kaggle / SoFIFA)",
        "csv": str(path),
        "teams": len(teams_touched),
        "players_written": written,
        "players_removed": removed,
        "squad_size": squad_size,
        "fields_imported": list(FC26_CSV_USECOLS),
        "note": "Game ratings for squads only; match goals/assists come from live sync during the tournament.",
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import json

    print(json.dumps(import_fc26_players(), indent=2))
