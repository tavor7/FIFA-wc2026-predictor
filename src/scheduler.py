"""Background scheduler for automatic data sync and predictions."""

from __future__ import annotations

import logging
from typing import Optional

from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src import db
from src.api_client import APIClient
from src.model_storage import save_models_after_train
from src.predict import generate_predictions, retrain_and_predict
from src.sync.sync_bracket import sync_bracket
from src.sync.sync_events import sync_events
from src.sync.sync_standings import sync_standings
from src.sync_injuries import sync_injuries
from src.sync_live_data import sync_live_data
from src.sync_matches import sync_all_matches

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def _sync_upcoming_job() -> None:
    try:
        result = sync_all_matches(days_ahead=120, days_back=30)
        sync_standings()
        sync_bracket()
        sync_events()
        generate_predictions()
        logger.info("Scheduled match sync: %s", result)
    except Exception as exc:
        logger.error("Scheduled match sync failed: %s", exc)


def _sync_injuries_job() -> None:
    try:
        result = sync_injuries()
        generate_predictions()
        logger.info("Scheduled injury sync: %s", result)
    except Exception as exc:
        logger.error("Scheduled injury sync failed: %s", exc)


def _sync_live_job() -> None:
    try:
        live = db.get_live_matches()
        api_live = sync_live_data()
        if live or api_live.get("live_from_api", 0) > 0:
            sync_events()
            generate_predictions()
            logger.info("Live sync completed: %s", api_live)
    except Exception as exc:
        logger.error("Scheduled live sync failed: %s", exc)


def _daily_retrain_job() -> None:
    try:
        retrain_and_predict()
        save_models_after_train()
        logger.info("Daily retrain completed")
    except Exception as exc:
        logger.error("Daily retrain failed: %s", exc)


def start_scheduler(client: Optional[APIClient] = None) -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler()
    job_defaults = {"max_instances": 1, "coalesce": True}
    soon = datetime.utcnow() + timedelta(minutes=3)

    _scheduler.add_job(
        _sync_upcoming_job,
        IntervalTrigger(hours=6),
        id="sync_upcoming",
        replace_existing=True,
        next_run_time=soon,
        **job_defaults,
    )
    _scheduler.add_job(
        _sync_injuries_job,
        IntervalTrigger(hours=3),
        id="sync_injuries",
        replace_existing=True,
        next_run_time=soon,
        **job_defaults,
    )
    _scheduler.add_job(
        _sync_live_job,
        IntervalTrigger(minutes=5),
        id="sync_live",
        replace_existing=True,
        next_run_time=soon,
        **job_defaults,
    )
    _scheduler.add_job(
        _daily_retrain_job,
        IntervalTrigger(hours=24),
        id="daily_retrain",
        replace_existing=True,
        next_run_time=soon,
        **job_defaults,
    )
    _scheduler.start()
    logger.info("Scheduler started")
    return _scheduler


def stop_scheduler() -> None:
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
