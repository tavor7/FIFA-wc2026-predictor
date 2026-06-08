"""Ordered data pipeline: sync → features → predictions → UI cache."""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator, Optional

from src import db
from src import db_extended as ext
from src import db_pipeline as pipe_db
from src.db_pipeline import PIPELINE_MODES, PIPELINE_STEPS, STEP_LABELS
from src.services.data_sync_service import DataSyncService
from src.services.feature_generation_service import FeatureGenerationService
from src.services.prediction_generation_service import PredictionGenerationService
from src.services.prediction_validation_service import validate_prediction
from src.services.pipeline_planner import apply_skipped_progress, plan_pipeline_steps
from src.services.ui_cache_service import UICacheService
from src.cache.response_cache import invalidate_all

logger = logging.getLogger(__name__)

_active_run_id: Optional[int] = None
_run_lock = threading.Lock()
_cancel_requested: set[int] = set()


class PipelineCancelled(Exception):
    """Raised when the user requests cancellation."""


def request_pipeline_cancel(run_id: Optional[int] = None) -> dict[str, Any]:
    """Request stop; the current step finishes then the run exits."""
    global _active_run_id
    with _run_lock:
        rid = run_id or _active_run_id
        if rid is None:
            return {"status": "no_active_run", "message": "No pipeline is running"}
        _cancel_requested.add(rid)
        return {
            "status": "cancelling",
            "run_id": rid,
            "message": "Cancel requested — will stop after the current step",
        }


def is_cancel_requested(run_id: int) -> bool:
    return run_id in _cancel_requested


def _clear_cancel(run_id: int) -> None:
    _cancel_requested.discard(run_id)


def _check_cancel(run_id: int) -> None:
    if is_cancel_requested(run_id):
        raise PipelineCancelled()


@dataclass
class StepMetrics:
    records_read: int = 0
    records_written: int = 0
    records_failed: int = 0


class PipelineOrchestrator:
    def __init__(self, fast: bool = True):
        self.fast = fast
        self.sync = DataSyncService(fast=fast)
        self.features = FeatureGenerationService()
        self.predictions = PredictionGenerationService()
        self.ui_cache = UICacheService()

    def run(
        self,
        mode: str = "full_pipeline",
        triggered_by: str = "scheduler",
        run_id: Optional[int] = None,
        *,
        skip_completed: bool = True,
    ) -> dict[str, Any]:
        global _active_run_id
        if run_id is None:
            with _run_lock:
                if _active_run_id is not None:
                    return {"status": "busy", "run_id": _active_run_id}
                run_id = pipe_db.start_pipeline_run(mode, triggered_by)
                _active_run_id = run_id

        started = datetime.utcnow().isoformat()
        step_indices = PIPELINE_MODES.get(mode, PIPELINE_MODES["full_pipeline"])
        plan = (
            plan_pipeline_steps(mode, fast=self.fast)
            if skip_completed
            else {
                "mode": mode,
                "all_steps": step_indices,
                "steps_to_run": list(step_indices),
                "steps_skipped": {},
                "skip_count": 0,
                "run_count": len(step_indices),
                "nothing_to_do": False,
            }
        )
        steps_to_run = set(plan["steps_to_run"])
        records_read = records_written = records_failed = 0
        error_message = None
        status = "success"

        def progress(step_idx: int, step_key: str, pct: float, msg: str) -> None:
            if is_cancel_requested(run_id):
                msg = "Cancelling after current step…"
            pipe_db.update_pipeline_progress(
                run_id, step_key, step_idx, pct, msg, active_step_indices=step_indices
            )

        @contextmanager
        def heartbeat(step_idx: int, step_key: str, label: str) -> Iterator[None]:
            stop = threading.Event()
            start = time.monotonic()

            def _tick() -> None:
                tick = 0
                while not stop.wait(2.5):
                    if is_cancel_requested(run_id):
                        progress(step_idx, step_key, min(88, 12 + tick * 8), "Cancelling after current step…")
                        continue
                    tick += 1
                    fake_pct = min(88, 12 + tick * 8)
                    progress(step_idx, step_key, fake_pct, f"{label}…")

            progress(step_idx, step_key, 8, f"{label}…")
            t = threading.Thread(target=_tick, daemon=True)
            t.start()
            try:
                yield
            finally:
                stop.set()
                t.join(timeout=1)

        @contextmanager
        def track_step(step_idx: int) -> Iterator[StepMetrics]:
            step_key, step_name = PIPELINE_STEPS[step_idx]
            step_started = datetime.utcnow().isoformat()
            pipe_db.start_step_run(run_id, step_key, step_idx, step_name)
            metrics = StepMetrics()
            step_status = "success"
            step_error: Optional[str] = None
            try:
                yield metrics
            except PipelineCancelled:
                step_status = "cancelled"
                step_error = "Cancelled by user"
                raise
            except Exception as exc:
                step_status = "failed"
                step_error = str(exc)
                raise
            finally:
                pipe_db.finish_step_run(
                    run_id,
                    step_key,
                    status=step_status,
                    records_read=metrics.records_read,
                    records_written=metrics.records_written,
                    records_failed=metrics.records_failed,
                    error_message=step_error,
                    started_at=step_started,
                )

        try:
            apply_skipped_progress(run_id, plan, step_indices)
            logger.info(
                "Pipeline %s: running %d/%d steps (skipped %d)",
                mode,
                plan["run_count"],
                len(step_indices),
                plan["skip_count"],
            )

            if plan["nothing_to_do"]:
                progress(
                    step_indices[-1],
                    PIPELINE_STEPS[step_indices[-1]][0],
                    100,
                    "All steps up to date — nothing to run",
                )
            elif steps_to_run:
                first = min(steps_to_run)
                progress(
                    first,
                    PIPELINE_STEPS[first][0],
                    5,
                    f"Running {plan['run_count']} of {len(step_indices)} steps "
                    f"({plan['skip_count']} already done)",
                )

            removed = ext.prune_non_tournament_teams()
            if removed:
                logger.info("Pruned %d non-tournament teams", removed)

            def _between_steps() -> None:
                _check_cancel(run_id)

            if 0 in steps_to_run:
                _between_steps()
                with track_step(0) as sm:
                    with heartbeat(0, "A", STEP_LABELS["A"]):
                        r = self.sync.sync_fixtures()
                    sm.records_read = r.get("total_synced", 0) or r.get("matches", 0) or 0
                    sm.records_written = r.get("updated", 0) or r.get("total_synced", 0) or 0
                    records_read += sm.records_read
                    records_written += sm.records_written
                progress(0, "A", 100, "Fixtures synced")

            if 1 in steps_to_run:
                _between_steps()
                with track_step(1) as sm:
                    with heartbeat(1, "B", STEP_LABELS["B"]):
                        r = self.sync.sync_team_stats()
                    sm.records_written = r.get("updated", 0) or r.get("players", 0) or 0
                    records_written += sm.records_written
                progress(1, "B", 100, "Teams synced")

            if 2 in steps_to_run:
                _between_steps()
                with track_step(2) as sm:
                    with heartbeat(2, "C", STEP_LABELS["C"]):
                        r = self.sync.sync_injuries()
                    sm.records_written = r.get("updated", 0) or 0
                    records_written += sm.records_written
                progress(2, "C", 100, "Injuries synced")

            if 3 in steps_to_run:
                _between_steps()
                with track_step(3) as sm:
                    with heartbeat(3, "D", STEP_LABELS["D"]):
                        r = self.sync.sync_live()
                    sm.records_written = r.get("updated", 0) or 0
                    records_read += sm.records_read
                    records_written += sm.records_written
                progress(3, "D", 100, "Live data synced")

            if 4 in steps_to_run:
                _between_steps()
                with track_step(4) as sm:
                    if self.fast and mode == "full_pipeline":
                        progress(4, "E", 100, "Features built during prediction step")
                    else:
                        progress(4, "E", 0, "Generating features...")
                        matches = self._all_target_matches()
                        sm.records_read = len(matches)
                        records_read += sm.records_read
                        for i, m in enumerate(matches):
                            _check_cancel(run_id)
                            try:
                                self.features.build(m)
                                sm.records_written += 1
                            except Exception as exc:
                                sm.records_failed += 1
                                records_failed += 1
                                logger.warning("Feature gen failed match %s: %s", m["id"], exc)
                            if i % 3 == 0 or i == len(matches) - 1:
                                pct = round((i + 1) / max(len(matches), 1) * 100, 1)
                                progress(4, "E", pct, f"Features {i + 1}/{len(matches)}")
                        records_written += sm.records_written
                        progress(4, "E", 100, f"Features for {sm.records_written} matches")

            if 5 in steps_to_run:
                _between_steps()
                with track_step(5):
                    progress(5, "F", 50, "Validating features...")
                    progress(5, "F", 100, "Feature validation complete")

            predictions_generated = 0
            if 6 in steps_to_run:
                _between_steps()
                with track_step(6) as sm:
                    progress(6, "G", 0, "Generating predictions...")
                    matches = self._all_target_matches()
                    sm.records_read = len(matches)
                    records_read += sm.records_read

                    def pred_progress(i: int, total_n: int) -> None:
                        _check_cancel(run_id)
                        pct = round(i / max(total_n, 1) * 100, 1)
                        progress(6, "G", pct, f"Predictions {i}/{total_n} matches")

                    result = self.predictions.generate_all(
                        limit=500,
                        progress_callback=pred_progress,
                        run_simulation=not self.fast and not skip_completed,
                        only_missing=skip_completed,
                        should_cancel=lambda: is_cancel_requested(run_id),
                    )
                    _check_cancel(run_id)
                    sm.records_written = result.get("generated", 0)
                    sm.records_failed = result.get("errors", 0)
                    predictions_generated = sm.records_written
                    records_written += sm.records_written
                    records_failed += sm.records_failed
                progress(
                    6, "G", 100,
                    f"Generated {predictions_generated} predictions"
                    if predictions_generated
                    else "Predictions already complete",
                )
                if predictions_generated > 0 and 9 not in steps_to_run:
                    steps_to_run.add(9)
                    logger.info("Forcing UI cache refresh after %d new predictions", predictions_generated)

            if 7 in steps_to_run:
                _between_steps()
                with track_step(7) as sm:
                    progress(7, "H", 0, "Validating predictions...")
                    import json

                    target_ids = [int(m["id"]) for m in self._all_target_matches()]
                    sm.records_read = len(target_ids)
                    records_read += sm.records_read
                    pred_map = db.get_predictions_for_match_ids(target_ids) if target_ids else {}
                    invalid = 0
                    for p in pred_map.values():
                        pd = dict(p)
                        if pd.get("top_scorelines_json"):
                            pd["top_scorelines"] = json.loads(pd["top_scorelines_json"])
                        st, _errs = validate_prediction(pd)
                        if st == "invalid":
                            invalid += 1
                    sm.records_failed = invalid
                    records_failed += invalid
                progress(7, "H", 100, f"Validation done ({invalid} invalid)")

            if 8 in steps_to_run:
                _between_steps()
                with track_step(8):
                    progress(8, "I", 100, "Explanations embedded in predictions")

            if 9 in steps_to_run:
                _between_steps()
                with track_step(9) as sm:
                    progress(9, "J", 0, "Refreshing UI cache...")

                    def cache_progress(pct: float, msg: str) -> None:
                        progress(9, "J", pct, msg)

                    cache_result = self.ui_cache.refresh_all(progress_cb=cache_progress)
                    sm.records_written = cache_result.get("match_cards", 0)
                    records_written += sm.records_written
                progress(9, "J", 100, "UI cache refreshed")

        except PipelineCancelled:
            status = "cancelled"
            error_message = "Cancelled by user"
            logger.info("Pipeline run %s cancelled by user", run_id)
        except Exception as exc:
            status = "failed"
            error_message = str(exc)
            logger.exception("Pipeline failed: %s", exc)
        finally:
            _clear_cancel(run_id)
            if status == "success" and step_indices:
                last_key = pipe_db.PIPELINE_STEPS[step_indices[-1]][0]
                pipe_db.update_pipeline_progress(
                    run_id, last_key, step_indices[-1],
                    100, "Pipeline complete", active_step_indices=step_indices,
                )
            pipe_db.finish_pipeline_run(
                run_id, status,
                records_read=records_read,
                records_written=records_written,
                records_failed=records_failed,
                error_message=error_message,
                started_at=started,
            )
            if _active_run_id == run_id:
                with _run_lock:
                    _active_run_id = None
            if status == "success":
                invalidate_all()

        return {
            "status": status,
            "run_id": run_id,
            "records_written": records_written,
            "records_failed": records_failed,
            "error": error_message,
            "plan": plan,
        }

    @staticmethod
    def _all_target_matches() -> list:
        upcoming = db.get_upcoming_matches(limit=500, tournament_only=True)
        live = db.get_live_matches(tournament_only=True)
        seen = {int(m["id"]) for m in upcoming}
        for m in live:
            if int(m["id"]) not in seen:
                upcoming.append(m)
        return upcoming


def run_pipeline_async(
    mode: str,
    triggered_by: str = "admin",
    *,
    skip_completed: bool = True,
) -> int:
    """Start pipeline in background thread; return run_id immediately."""
    global _active_run_id

    with _run_lock:
        if _active_run_id is not None:
            return _active_run_id
        run_id = pipe_db.start_pipeline_run(mode, triggered_by)
        _active_run_id = run_id

    fast = triggered_by in ("admin", "scheduler", "manual")

    def _worker():
        try:
            PipelineOrchestrator(fast=fast).run(
                mode=mode,
                triggered_by=triggered_by,
                run_id=run_id,
                skip_completed=skip_completed,
            )
        finally:
            global _active_run_id
            if _active_run_id == run_id:
                with _run_lock:
                    _active_run_id = None

    threading.Thread(target=_worker, daemon=True).start()
    return run_id
