"""Optional background scheduler for automatic data sync and predictions."""

from __future__ import annotations

import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src import db
from src.api_client import APIClient
from src.predict import generate_predictions, retrain_and_predict
from src.sync_injuries import sync_injuries
from src.sync_live_data import sync_live_data
from src.sync_matches import sync_all_matches

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def _sync_upcoming_job() -> None:
    try:
        result = sync_all_matches()
        logger.info("Scheduled match sync: %s", result)
        generate_predictions()
    except Exception as exc:
        logger.error("Scheduled match sync failed: %s", exc)


def _sync_injuries_job() -> None:
    try:
        result = sync_injuries()
        logger.info("Scheduled injury sync: %s", result)
        generate_predictions()
    except Exception as exc:
        logger.error("Scheduled injury sync failed: %s", exc)


def _sync_live_job() -> None:
    try:
        live = db.get_live_matches()
        api_live = sync_live_data()
        if live or api_live.get("live_from_api", 0) > 0:
            generate_predictions()
            logger.info("Live sync completed: %s", api_live)
    except Exception as exc:
        logger.error("Scheduled live sync failed: %s", exc)


def start_scheduler(client: Optional[APIClient] = None) -> BackgroundScheduler:
    """
    Start background jobs:
    - upcoming matches every 6 hours
    - injuries every 3 hours
    - live matches every 60 seconds (only runs prediction if live games exist)
    """
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _sync_upcoming_job,
        IntervalTrigger(hours=6),
        id="sync_upcoming",
        replace_existing=True,
    )
    _scheduler.add_job(
        _sync_injuries_job,
        IntervalTrigger(hours=3),
        id="sync_injuries",
        replace_existing=True,
    )
    _scheduler.add_job(
        _sync_live_job,
        IntervalTrigger(seconds=60),
        id="sync_live",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started")
    return _scheduler


def stop_scheduler() -> None:
    """Stop the background scheduler if running."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    _scheduler = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db.init_db()
    start_scheduler()
    try:
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        stop_scheduler()
