"""Download FC 26 player CSV from the official Kaggle dataset."""

from __future__ import annotations

import logging
import os
import shutil
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# https://www.kaggle.com/datasets/rovnez/fc-26-fifa-26-player-data
KAGGLE_DATASET = "rovnez/fc-26-fifa-26-player-data"
KAGGLE_DATASET_URL = f"https://www.kaggle.com/datasets/{KAGGLE_DATASET}"


def kaggle_credentials_configured() -> bool:
    if os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY"):
        return True
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    return kaggle_json.is_file()


def download_kaggle_fc26_csv(dest: Path) -> Path:
    """
    Download players.csv from Kaggle and copy to dest.
    Requires KAGGLE_USERNAME + KAGGLE_KEY env vars or ~/.kaggle/kaggle.json.
    """
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError as exc:
        raise RuntimeError(
            "Install the kaggle package: pip install kaggle"
        ) from exc

    if not kaggle_credentials_configured():
        raise RuntimeError(
            f"Kaggle credentials required. Set KAGGLE_USERNAME and KAGGLE_KEY in .env "
            f"or place kaggle.json in ~/.kaggle/. Dataset: {KAGGLE_DATASET_URL}"
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = dest.parent / ".kaggle_download"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    logger.info("Downloading Kaggle dataset %s ...", KAGGLE_DATASET)
    api = KaggleApi()
    api.authenticate()
    api.dataset_download_files(KAGGLE_DATASET, path=str(tmp_dir), unzip=True, quiet=False)

    csv_candidates = list(tmp_dir.rglob("*.csv"))
    if not csv_candidates:
        raise FileNotFoundError(f"No CSV found in Kaggle dataset {KAGGLE_DATASET}")

    # Prefer players.csv (official Kaggle export name)
    source = next((p for p in csv_candidates if p.name.lower() == "players.csv"), None)
    if source is None:
        source = max(csv_candidates, key=lambda p: p.stat().st_size)

    shutil.copy2(source, dest)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    logger.info("Saved Kaggle FC26 CSV to %s (%d bytes)", dest, dest.stat().st_size)
    return dest
