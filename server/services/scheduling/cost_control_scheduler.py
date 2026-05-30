"""Scheduler loop for high-risk cost-control workflows."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from server import config
from server.database import SessionLocal
from server.logging_utils import log_event
from server.services.result_objects import ServiceObjectResult, service_object_result
from server.services.scheduling.recurring_workflows import (
    recurring_workflow_to_dict,
    run_recurring_workflow,
    sync_recurring_workflows,
)

logger = logging.getLogger("ops-dashboard.cost_control_scheduler")


class CostControlScheduler:
    """Run allowlisted cleanup/shutdown workflows when their schedule is due."""

    WORKFLOW_KEYS = (
        "artifact_registry_cleanup_sweep",
        "secret_manager_version_cleanup_sweep",
        "staging_environment_shutdown_sweep",
    )

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        poll_seconds: int | None = None,
        startup_delay_seconds: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._poll_seconds = max(
            300, int(poll_seconds or config.COST_CONTROL_SCHEDULER_POLL_SECONDS)
        )
        self._startup_delay_seconds = max(
            0,
            int(
                startup_delay_seconds
                if startup_delay_seconds is not None
                else config.COST_CONTROL_STARTUP_DELAY_SECONDS
            ),
        )
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
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ops-cost-control-scheduler",
            daemon=True,
        )
        self._thread.start()
        log_event(
            logger, "cost_control_scheduler_started", poll_seconds=self._poll_seconds
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        log_event(logger, "cost_control_scheduler_stopped")

    @service_object_result
    def status_snapshot(self) -> ServiceObjectResult:
        return {
            "enabled": bool(config.COST_CONTROL_SCHEDULER_ENABLED),
            "running": bool(
                self._thread is not None
                and self._thread.is_alive()
                and not self._stop_event.is_set()
            ),
            "poll_seconds": int(self._poll_seconds),
            "startup_delay_seconds": int(self._startup_delay_seconds),
            "workflow_keys": list(self.WORKFLOW_KEYS),
            "last_tick_at": self._last_tick_at.isoformat()
            if self._last_tick_at
            else None,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "last_error": self._last_error,
            "last_results": dict(self._last_results),
        }

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
            row_by_key = {str(row.workflow_key): row for row in rows}
            ran: dict[str, object] = {}
            for workflow_key in self.WORKFLOW_KEYS:
                row = row_by_key.get(workflow_key)
                if row is None:
                    continue
                if not _should_run_cost_control_workflow(row, now=self._last_tick_at):
                    continue
                result = run_recurring_workflow(
                    db,
                    workflow_key=workflow_key,
                    triggered_by="scheduler",
                )
                ran[workflow_key] = dict(result.get("result") or {})
            if ran:
                self._last_run_at = datetime.now(timezone.utc)
                self._last_results = ran
            self._last_error = None
            log_event(
                logger,
                "cost_control_scheduler_tick",
                ran_workflow_keys=list(ran.keys()),
            )
        except Exception as exc:
            self._last_error = str(exc)
            log_event(
                logger,
                "cost_control_scheduler_failed",
                level=logging.ERROR,
                error_type=exc.__class__.__name__,
                error=str(exc),
            )
        finally:
            if db is not None:
                db.close()


def _should_run_cost_control_workflow(row, *, now: datetime | None = None) -> bool:
    if str(getattr(row, "status", "") or "") != "active":
        return False
    current = now or datetime.now(timezone.utc)
    schedule = _json_object(getattr(row, "schedule_json", None))
    cadence = str(schedule.get("cadence") or "").strip().lower()
    if cadence == "daily":
        return _daily_schedule_due(row, schedule=schedule, now=current)
    snapshot = recurring_workflow_to_dict(row)
    if getattr(row, "last_run_at", None) is None and cadence == "interval":
        return True
    return bool(snapshot.get("is_due"))


def _daily_schedule_due(row, *, schedule: dict[str, object], now: datetime) -> bool:
    zone = _operator_zone()
    local_now = now.astimezone(zone)
    hour, minute = _parse_local_time(
        str(schedule.get("suggested_local_time") or "23:00")
    )
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local_now < candidate:
        return False
    last_run = getattr(row, "last_run_at", None)
    if last_run is None:
        return True
    local_last_run = _ensure_utc(last_run).astimezone(zone)
    return local_last_run.date() < local_now.date() or local_last_run < candidate


def _parse_local_time(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = str(value).split(":", 1)
        return max(0, min(23, int(hour_text))), max(0, min(59, int(minute_text)))
    except Exception:
        return 23, 0


def _operator_zone() -> ZoneInfo:
    try:
        return ZoneInfo(config.OPERATOR_TIMEZONE)
    except Exception:
        return ZoneInfo("UTC")


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_object(raw: str | None) -> dict[str, object]:
    try:
        value = json.loads(raw or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}
