"""Lightweight scheduler for human-gated X social ops recurring workflows."""
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
from server.services.scheduling.recurring_workflows import recurring_workflow_to_dict, run_recurring_workflow, sync_recurring_workflows

logger = logging.getLogger("ops-dashboard.x_social_scheduler")


class XSocialSweepScheduler:
    """Run X social draft/trend/repost sweeps without creating per-task timers."""

    WORKFLOW_KEYS = (
        "x_social_daily_content_planner",
        "x_social_trend_radar_sweep",
        "x_social_repost_candidate_sweep",
        "x_social_reply_candidate_sweep",
        "x_social_daily_reply_block_publisher",
        "x_social_post_observer_sweep",
    )

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        poll_seconds: int | None = None,
        startup_delay_seconds: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._poll_seconds = max(60, int(poll_seconds or config.X_SOCIAL_SWEEP_SCHEDULER_POLL_SECONDS))
        self._startup_delay_seconds = max(0, int(startup_delay_seconds or config.X_SOCIAL_SWEEP_STARTUP_DELAY_SECONDS))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_tick_at: datetime | None = None
        self._last_run_at: datetime | None = None
        self._last_error: str | None = None
        self._last_results: dict[str, object] = {}

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="ops-x-social-scheduler", daemon=True)
        self._thread.start()
        log_event(logger, "x_social_scheduler_started", poll_seconds=self._poll_seconds)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        log_event(logger, "x_social_scheduler_stopped")

    @service_object_result
    def status_snapshot(self) -> ServiceObjectResult:
        return {
            "enabled": bool(config.X_SOCIAL_SWEEP_SCHEDULER_ENABLED),
            "running": bool(self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()),
            "poll_seconds": int(self._poll_seconds),
            "startup_delay_seconds": int(self._startup_delay_seconds),
            "workflow_keys": list(self.WORKFLOW_KEYS),
            "last_tick_at": self._last_tick_at.isoformat() if self._last_tick_at else None,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "last_error": self._last_error,
            "last_results": dict(self._last_results),
        }

    def _run_loop(self) -> None:
        if self._startup_delay_seconds and self._stop_event.wait(self._startup_delay_seconds):
            return
        while not self._stop_event.is_set():
            self._tick()
            self._stop_event.wait(self._poll_seconds)

    def _tick(self) -> None:
        db: Session | None = None
        try:
            self._last_tick_at = datetime.now(timezone.utc)
            db = self._session_factory()
            rows = sync_recurring_workflows(db)
            row_by_key = {str(row.workflow_key): row for row in rows}
            ran: dict[str, object] = {}
            for workflow_key in self.WORKFLOW_KEYS:
                row = row_by_key.get(workflow_key)
                if row is None:
                    continue
                snapshot = recurring_workflow_to_dict(row)
                if row.last_run_at is not None and not bool(snapshot.get("is_due")):
                    continue
                try:
                    result = run_recurring_workflow(
                        db,
                        workflow_key=workflow_key,
                        triggered_by="scheduler",
                    )
                except ValueError as exc:
                    if not _is_missing_x_oauth_client_config(exc):
                        raise
                    diagnostic = {
                        "status": "blocked",
                        "diagnostic": str(exc),
                        "requires_configuration": True,
                    }
                    ran[workflow_key] = diagnostic
                    log_event(
                        logger,
                        "x_social_scheduler_workflow_blocked",
                        level=logging.WARNING,
                        workflow_key=workflow_key,
                        reason="missing_x_oauth_client_config",
                        error=str(exc),
                    )
                    continue
                ran[workflow_key] = dict(result.get("result") or {})
            if ran:
                self._last_run_at = datetime.now(timezone.utc)
                self._last_results = ran
            self._last_error = None
            log_event(logger, "x_social_scheduler_tick", ran_workflow_keys=list(ran.keys()))
        except Exception as exc:
            self._last_error = str(exc)
            log_event(logger, "x_social_scheduler_failed", level=logging.ERROR, error_type=exc.__class__.__name__, error=str(exc))
        finally:
            if db is not None:
                db.close()


def _is_missing_x_oauth_client_config(exc: ValueError) -> bool:
    summary = str(exc).lower()
    return "x_oauth_client_id" in summary or "x_oauth_client_secret" in summary
