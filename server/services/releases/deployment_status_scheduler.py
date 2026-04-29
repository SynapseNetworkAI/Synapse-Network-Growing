"""Lightweight scheduler for release deployment status reconciliation."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from server import config
from server.database import SessionLocal
from server.logging_utils import log_event
from server.services.result_objects import ServiceObjectResult, service_object_result
from server.services.scheduling.recurring_workflows import run_recurring_workflow, sync_recurring_workflows

logger = logging.getLogger("ops-dashboard.release_deployment_status_scheduler")


class ReleaseDeploymentStatusSweepScheduler:
    """Run `release_deployment_status_sweep` without creating per-release timers."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        interval_seconds: int | None = None,
        startup_delay_seconds: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        resolved_interval = config.RELEASE_DEPLOYMENT_STATUS_SWEEP_INTERVAL_SECONDS if interval_seconds is None else interval_seconds
        resolved_startup_delay = (
            config.RELEASE_DEPLOYMENT_STATUS_SWEEP_STARTUP_DELAY_SECONDS if startup_delay_seconds is None else startup_delay_seconds
        )
        self._interval_seconds = max(60, int(resolved_interval))
        self._startup_delay_seconds = max(0, int(resolved_startup_delay))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_tick_at: datetime | None = None
        self._last_run_at: datetime | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="ops-release-deployment-status-scheduler", daemon=True)
        self._thread.start()
        log_event(logger, "release_deployment_status_scheduler_started", interval_seconds=self._interval_seconds)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        log_event(logger, "release_deployment_status_scheduler_stopped")

    @service_object_result
    def status_snapshot(self) -> ServiceObjectResult:
        return {
            "enabled": bool(config.RELEASE_DEPLOYMENT_STATUS_SWEEP_SCHEDULER_ENABLED),
            "running": bool(self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()),
            "interval_seconds": int(self._interval_seconds),
            "startup_delay_seconds": int(self._startup_delay_seconds),
            "last_tick_at": self._last_tick_at.isoformat() if self._last_tick_at else None,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "last_error": self._last_error,
        }

    def _run_loop(self) -> None:
        if self._startup_delay_seconds and self._stop_event.wait(self._startup_delay_seconds):
            return
        while not self._stop_event.is_set():
            db: Session | None = None
            try:
                self._last_tick_at = datetime.now(timezone.utc)
                db = self._session_factory()
                sync_recurring_workflows(db)
                result = run_recurring_workflow(db, workflow_key="release_deployment_status_sweep", triggered_by="scheduler")
                self._last_run_at = datetime.now(timezone.utc)
                self._last_error = None
                payload = dict(result.get("result") or {})
                log_event(
                    logger,
                    "release_deployment_status_scheduler_run",
                    processed_count=int(payload.get("processed_count") or 0),
                    succeeded_count=len(payload.get("succeeded_ids") or []),
                    failed_count=len(payload.get("failed_ids") or []),
                    running_count=len(payload.get("running_ids") or []),
                    pending_count=len(payload.get("pending_ids") or []),
                )
            except Exception as exc:
                self._last_error = str(exc)
                log_event(logger, "release_deployment_status_scheduler_failed", level=logging.ERROR, error_type=exc.__class__.__name__, error=str(exc))
            finally:
                if db is not None:
                    db.close()
            self._stop_event.wait(self._interval_seconds)
