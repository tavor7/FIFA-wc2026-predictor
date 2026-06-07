"""Ordered data pipeline: sync → features → predictions → UI cache."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Callable, Optional

from src import db
from src import db_pipeline as pipe_db
from src.services.data_sync_service import DataSyncService
from src.services.feature_generation_service import FeatureGenerationService
from src.services.prediction_generation_service import PredictionGenerationService
from src.services.prediction_validation_service import validate_prediction
from src.services.ui_cache_service import UICacheService

logger = logging.getLogger(__name__)

_active_run_id: Optional[int] = None
_run_lock = threading.Lock()

PIPELINE_MODES = {
    "full_pipeline": list(range(10)),
    "data_sync_only": [0, 1, 2, 3],
    "features_only": [4, 5],
    "predictions_only": [6, 7, 8, 9],
}


class PipelineOrchestrator:
    def __init__(self):
        self.sync = DataSyncService()
        self.features = FeatureGenerationService()
        self.predictions = PredictionGenerationService()
        self.ui_cache = UICacheService()

    def run(
        self,
        mode: str = "full_pipeline",
        triggered_by: str = "scheduler",
        run_id: Optional[int] = None,
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
        records_read = records_written = records_failed = 0
        error_message = None
        status = "success"

        def progress(step_idx: int, step_key: str, pct: float, msg: str) -> None:
            pipe_db.update_pipeline_progress(run_id, step_key, step_idx, pct, msg)

        try:
            if 0 in step_indices:
                progress(0, "A", 0, "Syncing fixtures...")
                r = self.sync.sync_fixtures()
                records_written += r.get("updated", 0) or r.get("total_synced", 0)
                progress(0, "A", 100, "Fixtures synced")

            if 1 in step_indices:
                progress(1, "B", 0, "Syncing teams and squads...")
                r = self.sync.sync_team_stats()
                records_written += r.get("updated", 0) or 0
                progress(1, "B", 100, "Teams/squads synced")

            if 2 in step_indices:
                progress(2, "C", 0, "Syncing injuries...")
                r = self.sync.sync_injuries()
                records_written += r.get("updated", 0) or 0
                progress(2, "C", 100, "Injuries synced")

            if 3 in step_indices:
                progress(3, "D", 0, "Syncing recent results...")
                r = self.sync.sync_live()
                records_written += r.get("updated", 0) or 0
                progress(3, "D", 100, "Recent results synced")

            if 4 in step_indices:
                progress(4, "E", 0, "Generating features...")
                matches = self._all_target_matches()
                for i, m in enumerate(matches):
                    try:
                        self.features.build(m)
                        records_written += 1
                    except Exception as exc:
                        records_failed += 1
                        logger.warning("Feature gen failed match %s: %s", m["id"], exc)
                    if i % 5 == 0:
                        pct = round(i / max(len(matches), 1) * 100, 1)
                        progress(4, "E", pct, f"Features {i}/{len(matches)}")
                progress(4, "E", 100, f"Features for {records_written} matches")

            if 5 in step_indices:
                progress(5, "F", 50, "Validating features...")
                progress(5, "F", 100, "Feature validation complete")

            if 6 in step_indices:
                progress(6, "G", 0, "Generating predictions...")
                matches = self._all_target_matches()
                total = len(matches)

                def pred_progress(i: int, total_n: int) -> None:
                    pct = round(i / max(total_n, 1) * 100, 1)
                    progress(6, "G", pct, f"Predictions {i}/{total_n}")

                result = self.predictions.generate_all(
                    limit=500, progress_callback=pred_progress
                )
                records_written += result.get("generated", 0)
                records_failed += result.get("errors", 0)
                progress(6, "G", 100, f"Generated {result.get('generated', 0)} predictions")

            if 7 in step_indices:
                progress(7, "H", 0, "Validating predictions...")
                invalid = 0
                for p in db.get_all_predictions():
                    pd = dict(p)
                    if pd.get("top_scorelines_json"):
                        import json
                        pd["top_scorelines"] = json.loads(pd["top_scorelines_json"])
                    st, errs = validate_prediction(pd)
                    if st == "invalid":
                        invalid += 1
                progress(7, "H", 100, f"Validation done ({invalid} invalid)")

            if 8 in step_indices:
                progress(8, "I", 100, "Explanations embedded in predictions")

            if 9 in step_indices:
                progress(9, "J", 0, "Refreshing UI cache...")

                def cache_progress(pct: float, msg: str) -> None:
                    progress(9, "J", pct, msg)

                cache_result = self.ui_cache.refresh_all(progress_cb=cache_progress)
                records_written += cache_result.get("match_cards", 0)
                progress(9, "J", 100, "UI cache refreshed")

        except Exception as exc:
            status = "failed"
            error_message = str(exc)
            logger.exception("Pipeline failed: %s", exc)
        finally:
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

        return {
            "status": status,
            "run_id": run_id,
            "records_written": records_written,
            "records_failed": records_failed,
            "error": error_message,
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


def run_pipeline_async(mode: str, triggered_by: str = "admin") -> int:
    """Start pipeline in background thread; return run_id immediately."""
    global _active_run_id

    with _run_lock:
        if _active_run_id is not None:
            return _active_run_id
        run_id = pipe_db.start_pipeline_run(mode, triggered_by)
        _active_run_id = run_id

    def _worker():
        try:
            PipelineOrchestrator().run(
                mode=mode, triggered_by=triggered_by, run_id=run_id
            )
        finally:
            global _active_run_id
            if _active_run_id == run_id:
                with _run_lock:
                    _active_run_id = None

    threading.Thread(target=_worker, daemon=True).start()
    return run_id
