"""Import EA FC 26 player ratings (Kaggle) into squad tables."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src import db
from src import db_extended as dbx
from src.seed.fc26_columns import FC26_CSV_USECOLS
from src.seed.kaggle_fc26 import (
    KAGGLE_DATASET,
    KAGGLE_DATASET_URL,
    download_kaggle_fc26_csv,
    kaggle_credentials_configured,
)
from src.seed.nationality_map import nationality_to_team
from src.team_flags import get_country_code, slugify
from src.team_names import normalize_team_name

logger = logging.getLogger(__name__)

FC26_CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "seeds" / "fc26_players.csv"
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
    from src.tournament_teams import get_wc2026_team_names

    return set(get_wc2026_team_names())


def ensure_fc26_csv(path: Path = FC26_CSV_PATH, *, allow_download: bool = True) -> Path:
    """
    Resolve FC26 CSV from bundled file or official Kaggle dataset.
    Source: https://www.kaggle.com/datasets/rovnez/fc-26-fifa-26-player-data
    """
    if path.is_file() and path.stat().st_size > 1_000_000:
        return path

    if not allow_download:
        raise FileNotFoundError(
            f"Kaggle FC26 CSV missing at {path}. "
            f"Bundle data/seeds/fc26_players.csv from {KAGGLE_DATASET_URL}"
        )

    if kaggle_credentials_configured():
        return download_kaggle_fc26_csv(path)

    raise FileNotFoundError(
        f"Kaggle FC26 CSV not found at {path}. "
        f"Download manually from {KAGGLE_DATASET_URL} "
        f"or set KAGGLE_USERNAME + KAGGLE_KEY to auto-download."
    )


def _resolve_team_id(team_name: str) -> int:
    """Match existing WC team row (seed/API may use a different display name)."""
    existing = dbx.resolve_team(team_name)
    if existing:
        return int(existing["id"])
    canonical = normalize_team_name(team_name)
    return dbx.upsert_team(
        team_name,
        slug=slugify(team_name),
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
    Load Kaggle FC26 ratings for WC 2026 national teams.
    Dataset: rovnez/fc-26-fifa-26-player-data (110 columns, ~18k players).
    """
    db.init_db()
    path = csv_path or FC26_CSV_PATH
    if not path.is_file():
        ensure_fc26_csv(path, allow_download=download)

    if not path.is_file():
        raise FileNotFoundError(
            f"FC26 CSV not found at {path}. Source: {KAGGLE_DATASET_URL}"
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
    thin_teams: list[str] = []

    for team_name, group in df.groupby("team"):
        team_id = _resolve_team_id(team_name)
        teams_touched.add(team_name)
        squad = group.head(squad_size)
        if len(squad) < squad_size:
            thin_teams.append(team_name)
        for _, row in squad.iterrows():
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
        "source": f"Kaggle: {KAGGLE_DATASET}",
        "dataset_url": KAGGLE_DATASET_URL,
        "csv": str(path),
        "teams": len(teams_touched),
        "players_written": written,
        "players_removed": removed,
        "squad_size": squad_size,
        "thin_teams": thin_teams,
        "fields_imported": list(FC26_CSV_USECOLS),
        "note": (
            "Squad ratings from Kaggle FC26. Nations with <26 players in the dataset "
            "are topped up from API-Football during pipeline sync."
        ),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import json

    print(json.dumps(import_fc26_players(), indent=2))
