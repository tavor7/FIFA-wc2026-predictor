"""Refactored scheduler using backend services."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src import db
from src.services.data_sync_service import DataSyncService
from src.services.model_training_service import ModelTrainingService
from src.services.prediction_generation_service import PredictionGenerationService

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None
_sync = DataSyncService()
_predict = PredictionGenerationService()
_train = ModelTrainingService()


def _sync_fixtures_job() -> None:
    try:
        _sync.sync_fixtures()
        _predict.generate_all()
        logger.info("Fixture sync + predictions completed")
    except Exception as exc:
        logger.error("Fixture sync failed: %s", exc)


def _sync_injuries_job() -> None:
    try:
        _sync.sync_injuries()
        _predict.generate_all()
        logger.info("Injury sync + predictions completed")
    except Exception as exc:
        logger.error("Injury sync failed: %s", exc)


def _sync_team_stats_job() -> None:
    try:
        _sync.sync_team_stats()
        _predict.generate_all()
        logger.info("Team stats sync + predictions completed")
    except Exception as exc:
        logger.error("Team stats sync failed: %s", exc)


def _sync_live_job() -> None:
    try:
        live = db.get_live_matches()
        _sync.sync_live()
        if live:
            _predict.generate_all()
        logger.info("Live sync completed")
    except Exception as exc:
        logger.error("Live sync failed: %s", exc)


def _daily_retrain_job() -> None:
    try:
        _train.retrain_and_predict()
        logger.info("Daily retrain completed")
    except Exception as exc:
        logger.error("Daily retrain failed: %s", exc)


def _daily_predict_job() -> None:
    try:
        _predict.generate_all()
        logger.info("Daily prediction refresh completed")
    except Exception as exc:
        logger.error("Daily prediction refresh failed: %s", exc)


def start_scheduler(client=None) -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler()
    job_defaults = {"max_instances": 1, "coalesce": True}
    soon = datetime.utcnow() + timedelta(minutes=3)

    _scheduler.add_job(
        _sync_fixtures_job, IntervalTrigger(hours=6), id="sync_fixtures",
        replace_existing=True, next_run_time=soon, **job_defaults,
    )
    _scheduler.add_job(
        _sync_injuries_job, IntervalTrigger(hours=3), id="sync_injuries",
        replace_existing=True, next_run_time=soon, **job_defaults,
    )
    _scheduler.add_job(
        _sync_team_stats_job, IntervalTrigger(hours=3), id="sync_team_stats",
        replace_existing=True, next_run_time=soon, **job_defaults,
    )
    live_interval = 1 if db.get_live_matches() else 5
    _scheduler.add_job(
        _sync_live_job, IntervalTrigger(minutes=live_interval), id="sync_live",
        replace_existing=True, next_run_time=soon, **job_defaults,
    )
    _scheduler.add_job(
        _daily_retrain_job, IntervalTrigger(hours=24), id="daily_retrain",
        replace_existing=True, next_run_time=soon, **job_defaults,
    )
    _scheduler.add_job(
        _daily_predict_job, IntervalTrigger(hours=24), id="daily_predict",
        replace_existing=True, next_run_time=soon, **job_defaults,
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
