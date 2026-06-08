"""Background model retrain with progress for Monitor UI."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Callable, Optional

from src.services.model_training_service import ModelTrainingService

logger = logging.getLogger(__name__)

TRAIN_STEPS: list[tuple[str, str, float]] = [
    ("prepare", "Preparing training data", 5.0),
    ("rf", "Training Random Forest", 18.0),
    ("xgb", "Training XGBoost", 12.0),
    ("elo", "Fitting Elo ratings", 8.0),
    ("registry", "Saving model registry", 8.0),
    ("predictions", "Regenerating predictions", 30.0),
    ("cache", "Refreshing UI cache", 14.0),
    ("backtest", "Running backtest", 5.0),
]

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "status": None,
    "error": None,
    "result": None,
    "overall_progress_pct": 0.0,
    "step_progress_pct": 0.0,
    "step_index": 0,
    "step_key": "",
    "step_label": "",
    "message": "",
    "updated_at": None,
}


def get_model_training_progress() -> dict[str, Any]:
    with _lock:
        d = dict(_state)
    if not d.get("running") and not d.get("finished_at"):
        return {"running": False}

    started = d.get("started_at")
    elapsed = 0.0
    if started:
        try:
            elapsed = round(
                (datetime.utcnow() - datetime.fromisoformat(str(started).replace("Z", ""))).total_seconds(),
                1,
            )
        except ValueError:
            pass

    overall = float(d.get("overall_progress_pct") or 0)
    step_idx = int(d.get("step_index") or 0)
    step_progress = float(d.get("step_progress_pct") or 0)
    steps_left = max(len(TRAIN_STEPS) - step_idx - 1, 0)

    return {
        "running": bool(d.get("running")),
        "status": d.get("status"),
        "error": d.get("error"),
        "result": d.get("result"),
        "overall_progress_pct": overall,
        "step_progress_pct": step_progress,
        "step_index": step_idx,
        "step_number": step_idx + 1 if step_idx >= 0 else 1,
        "steps_total": len(TRAIN_STEPS),
        "step_key": d.get("step_key") or "",
        "step_label": d.get("step_label") or "Model training",
        "mode_label": "Model training",
        "phase_label": d.get("step_label") or "Training",
        "message": d.get("message") or "",
        "elapsed_seconds": elapsed,
        # No extrapolated ETA — it rises when remote DB is slow and misleads users.
        "estimated_remaining_seconds": None,
        "timing_hint": (
            f"Step {step_idx + 1}/{len(TRAIN_STEPS)} · typically 10–20 min total on remote DB"
            if d.get("running")
            else None
        ),
        "steps_remaining": steps_left if d.get("running") else 0,
        "model_version": (d.get("result") or {}).get("model_version") if isinstance(d.get("result"), dict) else None,
    }


def model_training_is_busy() -> bool:
    with _lock:
        return bool(_state.get("running"))


def _update(
    step_index: int,
    step_key: str,
    step_label: str,
    step_pct: float,
    message: str,
) -> None:
    """Map step progress into overall 0–100."""
    weights = [w for _, _, w in TRAIN_STEPS]
    total_w = sum(weights) or 1.0
    completed = sum(weights[:step_index])
    current_w = weights[step_index] if step_index < len(weights) else 0.0
    frac = max(0.0, min(1.0, step_pct / 100.0))
    overall = (completed + current_w * frac) / total_w * 100.0
    if step_index >= len(TRAIN_STEPS) - 1 and step_pct >= 100:
        overall = 100.0
    else:
        overall = min(99.0, overall)

    with _lock:
        _state.update({
            "step_index": step_index,
            "step_key": step_key,
            "step_label": step_label,
            "step_progress_pct": round(step_pct, 1),
            "overall_progress_pct": round(overall, 1),
            "message": message,
            "updated_at": datetime.utcnow().isoformat(),
        })


def _finish(status: str, *, error: Optional[str] = None, result: Optional[dict] = None) -> None:
    with _lock:
        _state["running"] = False
        _state["status"] = status
        _state["error"] = error
        _state["result"] = result
        _state["finished_at"] = datetime.utcnow().isoformat()
        if status == "success":
            _state["overall_progress_pct"] = 100.0
            _state["message"] = "Training complete"


def start_model_retrain_async() -> dict[str, Any]:
    with _lock:
        if _state.get("running"):
            return {"status": "busy", "message": "Model training already in progress"}

    from src.services.pipeline_orchestrator import pipeline_is_busy

    if pipeline_is_busy():
        return {"status": "busy", "message": "A pipeline is running — wait or cancel it first"}

    now = datetime.utcnow().isoformat()
    with _lock:
        _state.clear()
        _state.update({
            "running": True,
            "started_at": now,
            "finished_at": None,
            "status": "running",
            "error": None,
            "result": None,
            "overall_progress_pct": 1.0,
            "step_index": 0,
            "step_key": TRAIN_STEPS[0][0],
            "step_label": TRAIN_STEPS[0][1],
            "message": "Starting model training…",
        })

    def _worker() -> None:
        try:
            svc = ModelTrainingService()
            result = svc.retrain_and_predict(progress_cb=_make_progress_cb())
            _finish("success", result=result)
            logger.info("Model retrain finished: %s", result.get("model_version"))
        except Exception as exc:
            logger.exception("Model retrain failed: %s", exc)
            _finish("failed", error=str(exc))

    threading.Thread(target=_worker, daemon=True, name="model-retrain").start()
    return {"status": "started", "message": "Model training started"}


def _make_progress_cb() -> Callable[[int, str, float, str], None]:
    key_to_index = {k: i for i, (k, _, _) in enumerate(TRAIN_STEPS)}

    def progress(step_key: str, step_pct: float, message: str) -> None:
        idx = key_to_index.get(step_key, 0)
        label = TRAIN_STEPS[idx][1] if idx < len(TRAIN_STEPS) else step_key
        _update(idx, step_key, label, step_pct, message)

    return progress
