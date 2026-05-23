"""Scheduler for the observable Secret Manager version cleanup workflow."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from server import config
from server.database import SessionLocal
from server.logging_utils import log_event
from server.services.scheduling.recurring_workflows import (
    recurring_workflow_to_dict,
    run_recurring_workflow,
    sync_recurring_workflows,
)

logger = logging.getLogger("ops-dashboard.secret_manager_cleanup_scheduler")


class SecretManagerCleanupSweepScheduler:  # pragma: no cover - daemon wrapper around tested schedule handler
    WORKFLOW_KEY = "secret_manager_version_cleanup_sweep"

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        poll_seconds: int | None = None,
        startup_delay_seconds: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._poll_seconds = max(
            300, int(poll_seconds or config.SECRET_MANAGER_CLEANUP_SWEEP_POLL_SECONDS)
        )
        self._startup_delay_seconds = max(
            0,
            int(
                startup_delay_seconds
                or config.SECRET_MANAGER_CLEANUP_SWEEP_STARTUP_DELAY_SECONDS
            ),
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_tick_at: datetime | None = None
        self._last_run_at: datetime | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ops-secret-manager-cleanup-scheduler",
            daemon=True,
        )
        self._thread.start()
        log_event(
            logger,
            "secret_manager_cleanup_scheduler_started",
            poll_seconds=self._poll_seconds,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        log_event(logger, "secret_manager_cleanup_scheduler_stopped")

    def _run_loop(self) -> None:
        if self._startup_delay_seconds and self._stop_event.wait(
            self._startup_delay_seconds
        ):
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
            row = next(
                (item for item in rows if str(item.workflow_key) == self.WORKFLOW_KEY),
                None,
            )
            if row is None:
                return
            snapshot = recurring_workflow_to_dict(row)
            if row.last_run_at is not None and not bool(snapshot.get("is_due")):
                return
            run_recurring_workflow(
                db, workflow_key=self.WORKFLOW_KEY, triggered_by="scheduler"
            )
            self._last_run_at = datetime.now(timezone.utc)
            self._last_error = None
            log_event(
                logger,
                "secret_manager_cleanup_scheduler_tick",
                workflow_key=self.WORKFLOW_KEY,
            )
        except Exception as exc:
            self._last_error = str(exc)
            log_event(
                logger,
                "secret_manager_cleanup_scheduler_failed",
                level=logging.ERROR,
                error_type=exc.__class__.__name__,
                error=str(exc),
            )
        finally:
            if db is not None:
                db.close()
