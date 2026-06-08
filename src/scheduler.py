"""Refactored scheduler using pipeline orchestrator."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src import db
from src.api.screen_handlers import set_scheduler_heartbeat
from src.services.pipeline_orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None
_orch = PipelineOrchestrator()


def _heartbeat() -> None:
    set_scheduler_heartbeat()


def _sync_fixtures_job() -> None:
    from src.services.pipeline_orchestrator import is_scheduler_suppressed, pipeline_is_busy

    if is_scheduler_suppressed() or pipeline_is_busy():
        logger.info("Skipping scheduled fixture sync (suppressed or busy)")
        return
    try:
        result = _orch.run(mode="data_sync_only", triggered_by="scheduler")
        if result.get("status") == "skipped":
            return
        if is_scheduler_suppressed() or pipeline_is_busy():
            return
        _orch.run(mode="predictions_only", triggered_by="scheduler")
        set_scheduler_heartbeat()
        logger.info("Fixture sync pipeline completed")
    except Exception as exc:
        logger.error("Fixture sync failed: %s", exc)


def _sync_live_job() -> None:
    from src.services.pipeline_orchestrator import is_scheduler_suppressed, pipeline_is_busy

    if is_scheduler_suppressed() or pipeline_is_busy():
        return
    try:
        live = db.get_live_matches()
        _orch.sync.sync_live()
        if live and not is_scheduler_suppressed() and not pipeline_is_busy():
            _orch.run(mode="predictions_only", triggered_by="scheduler")
        set_scheduler_heartbeat()
        logger.info("Live sync completed")
    except Exception as exc:
        logger.error("Live sync failed: %s", exc)


def _daily_full_job() -> None:
    from src.services.pipeline_orchestrator import is_scheduler_suppressed, pipeline_is_busy

    if is_scheduler_suppressed() or pipeline_is_busy():
        logger.info("Skipping daily full pipeline (suppressed or busy)")
        return
    try:
        _orch.run(mode="full_pipeline", triggered_by="scheduler")
        set_scheduler_heartbeat()
        logger.info("Daily full pipeline completed")
    except Exception as exc:
        logger.error("Daily pipeline failed: %s", exc)


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
    live_interval = 1 if db.get_live_matches() else 5
    _scheduler.add_job(
        _sync_live_job, IntervalTrigger(minutes=live_interval), id="sync_live",
        replace_existing=True, next_run_time=soon, **job_defaults,
    )
    _scheduler.add_job(
        _daily_full_job, IntervalTrigger(hours=24), id="daily_full_pipeline",
        replace_existing=True, next_run_time=soon + timedelta(hours=1), **job_defaults,
    )
    _scheduler.add_job(
        _heartbeat, IntervalTrigger(minutes=5), id="scheduler_heartbeat",
        replace_existing=True, next_run_time=soon, **job_defaults,
    )

    _scheduler.start()
    logger.info("Scheduler started")
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
