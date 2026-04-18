"""Built-in scheduler for recurring bug log sweep."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from server import config
from server.database import SessionLocal
from server.logging_utils import log_event
from server.services.scheduling.recurring_workflows import get_recurring_workflow, run_recurring_workflow, sync_recurring_workflows

logger = logging.getLogger("ops-dashboard.bug_log_scheduler")


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def bug_log_sweep_due(
    *,
    last_run_at: datetime | None,
    now: datetime | None = None,
    interval_minutes: int | None = None,
) -> bool:
    current = _ensure_utc(now) or datetime.now(timezone.utc)
    interval = max(1, int(interval_minutes or config.BUG_LOG_SWEEP_INTERVAL_MINUTES))
    previous = _ensure_utc(last_run_at)
    if previous is None:
        return True
    return current >= previous + timedelta(minutes=interval)


def maybe_run_bug_log_sweep_once(
    db: Session,
    *,
    now: datetime | None = None,
    auto_start: bool | None = None,
    min_score: float | None = None,
    max_created: int | None = None,
) -> dict[str, object] | None:
    sync_recurring_workflows(db)
    row = get_recurring_workflow(db, "bug_log_sweep")
    current = _ensure_utc(now) or datetime.now(timezone.utc)
    if not bug_log_sweep_due(
        last_run_at=row.last_run_at,
        now=current,
        interval_minutes=config.BUG_LOG_SWEEP_INTERVAL_MINUTES,
    ):
        return None
    return run_recurring_workflow(
        db,
        workflow_key="bug_log_sweep",
        auto_start=config.BUG_LOG_SWEEP_AUTO_START if auto_start is None else bool(auto_start),
        intake_min_score=config.BUG_LOG_SWEEP_MIN_SCORE if min_score is None else float(min_score),
        intake_max_created=config.BUG_LOG_SWEEP_MAX_CREATED if max_created is None else int(max_created),
    )


class BugLogSweepScheduler:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        poll_seconds: int | None = None,
        startup_delay_seconds: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._poll_seconds = max(5, int(poll_seconds or config.BUG_LOG_SWEEP_SCHEDULER_POLL_SECONDS))
        self._startup_delay_seconds = max(0, int(startup_delay_seconds or config.BUG_LOG_SWEEP_STARTUP_DELAY_SECONDS))
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
            name="ops-bug-log-scheduler",
            daemon=True,
        )
        self._thread.start()
        log_event(
            logger,
            "bug_log_scheduler_started",
            interval_minutes=config.BUG_LOG_SWEEP_INTERVAL_MINUTES,
            poll_seconds=self._poll_seconds,
            startup_delay_seconds=self._startup_delay_seconds,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        log_event(logger, "bug_log_scheduler_stopped")

    def status_snapshot(self) -> dict[str, object]:
        return {
            "enabled": bool(config.BUG_LOG_SWEEP_SCHEDULER_ENABLED),
            "running": bool(self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()),
            "interval_minutes": int(config.BUG_LOG_SWEEP_INTERVAL_MINUTES),
            "poll_seconds": int(self._poll_seconds),
            "startup_delay_seconds": int(self._startup_delay_seconds),
            "last_tick_at": self._last_tick_at.isoformat() if self._last_tick_at else None,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "last_error": self._last_error,
        }

    def _run_loop(self) -> None:
        if self._startup_delay_seconds:
            if self._stop_event.wait(self._startup_delay_seconds):
                return
        while not self._stop_event.is_set():
            db: Session | None = None
            try:
                self._last_tick_at = datetime.now(timezone.utc)
                db = self._session_factory()
                result = maybe_run_bug_log_sweep_once(db)
                if result is not None:
                    self._last_run_at = datetime.now(timezone.utc)
                    self._last_error = None
                    payload = dict(result.get("result") or {})
                    log_event(
                        logger,
                        "bug_log_scheduler_run",
                        workflow_key="bug_log_sweep",
                        created_bug_count=len(payload.get("created_bug_ids") or []),
                        materialized_requirement_count=len(payload.get("materialized_requirement_ids") or []),
                    )
            except Exception as exc:
                self._last_error = str(exc)
                log_event(
                    logger,
                    "bug_log_scheduler_failed",
                    level=logging.ERROR,
                    error_type=exc.__class__.__name__,
                    error=str(exc),
                )
            finally:
                if db is not None:
                    db.close()
            self._stop_event.wait(self._poll_seconds)
