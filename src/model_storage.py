"""Persist ML model artifacts — local disk with optional Supabase Storage sync."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import requests

from src import config

logger = logging.getLogger(__name__)

BUCKET = "models"
MODEL_FILES = (
    config.HOME_MODEL_PATH,
    config.AWAY_MODEL_PATH,
    config.XGB_HOME_MODEL_PATH,
    config.XGB_AWAY_MODEL_PATH,
)


def _supabase_url() -> Optional[str]:
    url = config._env("SUPABASE_URL") or config._env("NEXT_PUBLIC_SUPABASE_URL")
    return url.rstrip("/") if url else None


def _service_key() -> Optional[str]:
    return config._env("SUPABASE_SERVICE_ROLE_KEY") or config._env("SUPABASE_SERVICE_KEY")


def _storage_enabled() -> bool:
    return bool(_supabase_url() and _service_key())


def _upload(path: Path) -> bool:
    base = _supabase_url()
    key = _service_key()
    if not base or not key or not path.is_file():
        return False
    url = f"{base}/storage/v1/object/{BUCKET}/{path.name}"
    try:
        with path.open("rb") as fh:
            resp = requests.post(
                url,
                data=fh.read(),
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/octet-stream",
                    "x-upsert": "true",
                },
                timeout=60,
            )
        if resp.status_code in (200, 201):
            logger.info("Uploaded model %s to Supabase Storage", path.name)
            return True
        logger.warning("Model upload failed for %s: %s", path.name, resp.text[:200])
    except Exception as exc:
        logger.warning("Model upload error for %s: %s", path.name, exc)
    return False


def _download(path: Path) -> bool:
    base = _supabase_url()
    key = _service_key()
    if not base or not key:
        return False
    url = f"{base}/storage/v1/object/{BUCKET}/{path.name}"
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=60)
        if resp.status_code != 200:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
        logger.info("Downloaded model %s from Supabase Storage", path.name)
        return True
    except Exception as exc:
        logger.warning("Model download error for %s: %s", path.name, exc)
    return False


def load_models_on_startup() -> None:
    """Pull models from Supabase when local copies are missing (Render ephemeral FS)."""
    if not _storage_enabled():
        return
    config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for path in MODEL_FILES:
        if not path.is_file():
            _download(path)


def save_models_after_train() -> None:
    """Push trained models to Supabase Storage after retrain."""
    if not _storage_enabled():
        return
    for path in MODEL_FILES:
        _upload(path)
