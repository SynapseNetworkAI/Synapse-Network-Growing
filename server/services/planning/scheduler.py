"""Built-in scheduler for the goal planner sweep."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from server import config
from server.database import SessionLocal
from server.logging_utils import log_event
from server.services.scheduling.recurring_workflows import get_recurring_workflow, run_recurring_workflow, sync_recurring_workflows

logger = logging.getLogger("ops-dashboard.goal_planner_scheduler")


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_hhmm(value: str) -> tuple[int, int]:
    try:
        hour, minute = str(value or "09:00").split(":", 1)
        return max(0, min(23, int(hour))), max(0, min(59, int(minute)))
    except Exception:
        return 9, 0


def _operator_zone(timezone_name: str | None = None) -> ZoneInfo:
    try:
        return ZoneInfo(str(timezone_name or config.OPERATOR_TIMEZONE or "UTC"))
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def goal_planner_sweep_slot_utc(
    *,
    now: datetime | None = None,
    local_time: str | None = None,
    timezone_name: str | None = None,
) -> datetime:
    current = _ensure_utc(now) or datetime.now(timezone.utc)
    hour, minute = _parse_hhmm(local_time or config.GOAL_PLANNER_SWEEP_LOCAL_TIME)
    zone = _operator_zone(timezone_name)
    local_now = current.astimezone(zone)
    local_slot = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return local_slot.astimezone(timezone.utc)


def goal_planner_sweep_due(
    *,
    last_run_at: datetime | None,
    now: datetime | None = None,
    local_time: str | None = None,
    timezone_name: str | None = None,
) -> bool:
    current = _ensure_utc(now) or datetime.now(timezone.utc)
    today_slot = goal_planner_sweep_slot_utc(now=current, local_time=local_time, timezone_name=timezone_name)
    previous = _ensure_utc(last_run_at)
    if previous is None:
        return current >= today_slot
    return previous < today_slot <= current


def maybe_run_goal_planner_sweep_once(db: Session, *, now: datetime | None = None) -> dict[str, object] | None:
    sync_recurring_workflows(db)
    row = get_recurring_workflow(db, "goal_planner_sweep")
    if not goal_planner_sweep_due(last_run_at=row.last_run_at, now=now):
        return None
    return run_recurring_workflow(db, workflow_key="goal_planner_sweep", triggered_by="scheduler")


class GoalPlannerSweepScheduler:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        poll_seconds: int | None = None,
        startup_delay_seconds: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._poll_seconds = max(30, int(poll_seconds or config.GOAL_PLANNER_SWEEP_SCHEDULER_POLL_SECONDS))
        self._startup_delay_seconds = max(0, int(startup_delay_seconds or config.GOAL_PLANNER_SWEEP_STARTUP_DELAY_SECONDS))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_tick_at: datetime | None = None
        self._last_run_at: datetime | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="ops-goal-planner-scheduler", daemon=True)
        self._thread.start()
        log_event(logger, "goal_planner_scheduler_started", poll_seconds=self._poll_seconds)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        log_event(logger, "goal_planner_scheduler_stopped")

    def status_snapshot(self) -> dict[str, object]:
        return {
            "enabled": bool(config.GOAL_PLANNER_SWEEP_SCHEDULER_ENABLED),
            "running": bool(self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()),
            "local_time": config.GOAL_PLANNER_SWEEP_LOCAL_TIME,
            "operator_timezone": config.OPERATOR_TIMEZONE,
            "today_slot_utc": goal_planner_sweep_slot_utc().isoformat(),
            "today_slot_local": goal_planner_sweep_slot_utc().astimezone(_operator_zone()).isoformat(),
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
                result = maybe_run_goal_planner_sweep_once(db)
                if result is not None:
                    self._last_run_at = datetime.now(timezone.utc)
                    self._last_error = None
                    payload = dict(result.get("result") or {})
                    log_event(
                        logger,
                        "goal_planner_scheduler_run",
                        created_candidate_count=len(payload.get("created_candidate_ids") or []),
                        auto_started_workflow_count=len(payload.get("auto_started_workflow_run_ids") or []),
                    )
            except Exception as exc:
                self._last_error = str(exc)
                log_event(logger, "goal_planner_scheduler_failed", level=logging.ERROR, error_type=exc.__class__.__name__, error=str(exc))
            finally:
                if db is not None:
                    db.close()
            self._stop_event.wait(self._poll_seconds)
