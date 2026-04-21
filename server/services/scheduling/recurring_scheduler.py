"""Generic safe scheduler for auto-tick recurring workflows."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from server import config
from server.database import SessionLocal
from server.logging_utils import log_event
from server.services.scheduling.recurring_workflows import run_due_recurring_workflows

logger = logging.getLogger("ops-dashboard.recurring_workflow_scheduler")


class RecurringWorkflowScheduler:
    """Poll due, low-risk registry workflows and record real run history."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        poll_seconds: int | None = None,
        startup_delay_seconds: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._poll_seconds = max(30, int(poll_seconds or config.RECURRING_WORKFLOW_SCHEDULER_POLL_SECONDS))
        self._startup_delay_seconds = max(0, int(startup_delay_seconds or config.RECURRING_WORKFLOW_SCHEDULER_STARTUP_DELAY_SECONDS))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_tick_at: datetime | None = None
        self._last_run_at: datetime | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="ops-recurring-workflow-scheduler", daemon=True)
        self._thread.start()
        log_event(logger, "recurring_workflow_scheduler_started", poll_seconds=self._poll_seconds)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        log_event(logger, "recurring_workflow_scheduler_stopped")

    def status_snapshot(self) -> dict[str, object]:
        return {
            "enabled": bool(config.RECURRING_WORKFLOW_SCHEDULER_ENABLED),
            "running": bool(self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()),
            "poll_seconds": int(self._poll_seconds),
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
                results = run_due_recurring_workflows(db)
                if results:
                    self._last_run_at = datetime.now(timezone.utc)
                    self._last_error = None
                    log_event(
                        logger,
                        "recurring_workflow_scheduler_run",
                        workflow_keys=[str(item.get("workflow_key")) for item in results],
                    )
            except Exception as exc:
                self._last_error = str(exc)
                log_event(logger, "recurring_workflow_scheduler_failed", level=logging.ERROR, error_type=exc.__class__.__name__, error=str(exc))
            finally:
                if db is not None:
                    db.close()
            self._stop_event.wait(self._poll_seconds)
