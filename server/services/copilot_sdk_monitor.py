"""Poll detached Copilot SDK workers, persist runtime events, and recover stale sessions."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, cast

from server import config
from server.database import ApprovalRow, SessionLocal, TaskLogRow, TaskRow, utcnow
from server.services.copilot_sdk_bridge import CopilotSDKBridge
from server.services.copilot_sdk_state import (
    copilot_runtime_paths,
    load_runtime_events_after,
    load_runtime_state,
    read_text_if_exists,
    save_runtime_state,
    seconds_since_timestamp,
    task_output_dir,
)
from server.services.task_runtime import CopilotSDKTaskRuntime, get_copilot_sdk_runtime, normalize_copilot_event_type
from server.services.alerting import send_lark_text_alert

logger = logging.getLogger("ops-dashboard.copilot_sdk_monitor")


def _is_copilot_authorization_error(message: str) -> bool:
    text = message.strip().lower()
    return (
        "not authorized to use this copilot feature" in text
        or "requires an enterprise or organization policy to be enabled" in text
    )


def _task_id(task: TaskRow) -> int:
    return int(cast(Any, task).id)


def _task_str(task: TaskRow, name: str) -> str:
    value = getattr(cast(Any, task), name, "")
    return "" if value is None else str(value)


def _task_int(task: TaskRow, name: str) -> int:
    value = getattr(cast(Any, task), name, 0)
    return int(value or 0)


def _task_bool(task: TaskRow, name: str) -> bool:
    return bool(getattr(cast(Any, task), name, False))


class CopilotSDKTaskMonitor:
    def __init__(
        self,
        project_root: Path | None = None,
        session_factory=SessionLocal,
        bridge: CopilotSDKBridge | None = None,
        poll_interval_sec: float | None = None,
        stale_after_sec: float | None = None,
    ):
        self.project_root = (project_root or config.PROJECT_ROOT).resolve()
        self.session_factory = session_factory
        self.bridge = bridge or CopilotSDKBridge(cwd=self.project_root)
        self.runtime = CopilotSDKTaskRuntime(project_root=self.project_root, bridge=self.bridge)
        self.poll_interval_sec = poll_interval_sec if poll_interval_sec is not None else config.COPILOT_SDK_POLL_INTERVAL_SEC
        self.stale_after_sec = stale_after_sec if stale_after_sec is not None else config.COPILOT_SDK_STALE_AFTER_SEC
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> threading.Thread:
        if self._thread and self._thread.is_alive():
            return self._thread
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="copilot-sdk-monitor")
        self._thread.start()
        logger.info("Started Copilot SDK task monitor")
        return self._thread

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self.poll_interval_sec * 2))
        self._thread = None

    def poll_once(self) -> None:
        db = self.session_factory()
        try:
            task_ids = [int(row.id) for row in db.query(TaskRow.id).filter(
                TaskRow.status == "running",
                TaskRow.runtime_backend == "copilot_sdk",
            ).all()]
        finally:
            db.close()

        for task_id in task_ids:
            try:
                self.sync_task(task_id)
            except Exception:
                logger.exception("Copilot SDK monitor failed while syncing task #%d", task_id)

        self._recover_orphaned_dispatches()

    def sync_task(self, task_id: int) -> None:
        db = self.session_factory()
        try:
            task = db.query(TaskRow).filter(TaskRow.id == task_id).first()
            if not task or _task_str(task, "status") != "running" or _task_str(task, "runtime_backend") != "copilot_sdk":
                return

            output_dir = task_output_dir(self.project_root, _task_str(task, "agent_id"), _task_id(task))
            paths = copilot_runtime_paths(output_dir)
            state = load_runtime_state(paths["state"])
            if not state:
                return

            self._persist_runtime_events(db, task, paths["events"])
            self._sync_runtime_metadata(task, state, paths)

            status = str(state.get("status") or "")
            if status == "completed":
                self._complete_task(db, task, state, paths)
            elif status == "failed":
                self._fail_task(db, task, state, paths)
            elif status == "running":
                self._resume_stale_task(db, task, state, output_dir, paths)

            db.commit()
        finally:
            db.close()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self.poll_interval_sec)

    # ------------------------------------------------------------------
    # Orphaned-dispatch recovery
    # ------------------------------------------------------------------
    _ORPHAN_THRESHOLD_SEC = 300  # 5 minutes without a runtime session → orphaned

    def _recover_orphaned_dispatches(self) -> None:
        """Detect tasks marked 'running' but never assigned a runtime session.

        This happens when dispatch() fails after the DB commit or when the
        server restarts between commit and dispatch.  The step is reset to
        'ready' so the next scheduling pass can retry.
        """
        db = self.session_factory()
        try:
            orphans = db.query(TaskRow).filter(
                TaskRow.status == "running",
                TaskRow.runtime_session_id.is_(None),
                TaskRow.runtime_backend.in_(("", None)),
            ).all()
            for task in orphans:
                started = getattr(cast(Any, task), "started_at", None)
                if not started:
                    continue
                age = seconds_since_timestamp(str(started))
                if age is None or age < self._ORPHAN_THRESHOLD_SEC:
                    continue
                logger.warning(
                    "Task #%d has been running for %.0fs with no session — marking as failed (orphaned dispatch)",
                    _task_id(task), age,
                )
                cast(Any, task).status = "failed"
                cast(Any, task).last_error_message = "dispatch never completed (orphaned)"
                cast(Any, task).completed_at = utcnow()
                db.add(TaskLogRow(
                    task_id=_task_id(task),
                    event_type="failed",
                    detail="orphaned dispatch recovery: no runtime session after %.0fs" % age,
                ))
                db.commit()
                self._sync_workflow_step(_task_id(task))
        except Exception:
            logger.exception("Orphaned-dispatch recovery failed")
        finally:
            db.close()

    def _persist_runtime_events(self, db, task: TaskRow, events_path: Path) -> None:
        cursor = _task_int(task, "runtime_event_cursor")
        for event in load_runtime_events_after(events_path, after_seq=cursor):
            event_type = normalize_copilot_event_type(str(event.get("type") or "runtime_event"))
            detail = event.get("detail")
            db.add(TaskLogRow(task_id=_task_id(task), event_type=event_type, detail=str(detail) if detail else None))
            cursor = int(event.get("seq", cursor) or cursor)
        cast(Any, task).runtime_event_cursor = cursor

    def _sync_runtime_metadata(self, task: TaskRow, state: dict, paths: dict[str, Path]) -> None:
        session_id = state.get("sessionId")
        if session_id:
            cast(Any, task).runtime_session_id = str(session_id)
        selected_agent = state.get("selectedAgent")
        if selected_agent:
            cast(Any, task).runtime_selected_agent = str(selected_agent)
        # Only persist execution_time_ms for terminal states.
        # While running, the frontend computes elapsed time dynamically from started_at.
        status = str(state.get("status") or "")
        if status in {"completed", "failed"}:
            execution_time_ms = state.get("executionTimeMs")
            if execution_time_ms is not None:
                cast(Any, task).execution_time_ms = int(execution_time_ms)
        if paths["output"].exists():
            cast(Any, task).output_path = str(paths["output"])

    def _complete_task(self, db, task: TaskRow, _state: dict, paths: dict[str, Path]) -> None:
        output_text = read_text_if_exists(paths["output"]) or ""
        cast(Any, task).output_content = output_text
        cast(Any, task).last_error_message = None
        cast(Any, task).completed_at = utcnow()
        if _task_bool(task, "requires_approval"):
            cast(Any, task).status = "pending_approval"
            if not db.query(ApprovalRow).filter(ApprovalRow.task_id == _task_id(task)).first():
                db.add(ApprovalRow(task_id=_task_id(task)))
            self._log(db, _task_id(task), "output", output_text[:500])
            self._log(db, _task_id(task), "approval_requested")
        else:
            cast(Any, task).status = "completed"
            self._log(db, _task_id(task), "output", output_text[:500])
            self._log(db, _task_id(task), "completed")
        logger.info("Copilot SDK task #%d completed via monitor", _task_id(task))
        db.commit()
        self._sync_workflow_step(_task_id(task))

    def _fail_task(self, db, task: TaskRow, state: dict, paths: dict[str, Path]) -> None:
        error_message = str(state.get("error") or "Copilot SDK session failed")
        output_text = read_text_if_exists(paths["output"]) or ""

        if config.RUNTIME_AUTH_ALERTS_ENABLED and _is_copilot_authorization_error(error_message):
            self._alert_and_pause_for_runtime_auth(db, task, error_message)
            return

        cast(Any, task).status = "failed"
        cast(Any, task).last_error_message = error_message
        cast(Any, task).output_content = output_text or f"[ERROR] {error_message}"
        cast(Any, task).completed_at = utcnow()
        self._log(db, _task_id(task), "failed", error_message)
        logger.info("Copilot SDK task #%d failed via monitor: %s", _task_id(task), error_message)

        # If the failure is caused by orphaned tool_use blocks (session crashed
        # mid-tool-execution), the stored conversation is permanently broken.
        # Clear the singleton role-session cache so the next dispatch starts a
        # fresh session instead of trying to resume the corrupted one.
        if (
            ("tool_use" in error_message and "tool_result" in error_message)
            or "session not found" in error_message.lower()
            or "session.resume failed" in error_message.lower()
        ):
            runtime = get_copilot_sdk_runtime()
            if runtime is not None:
                runtime.clear_role_sessions()
                logger.warning(
                    "Cleared role sessions after unrecoverable Copilot SDK failure on task #%d",
                    _task_id(task),
                )

        db.commit()
        self._sync_workflow_step(_task_id(task))

    def _alert_and_pause_for_runtime_auth(self, db, task: TaskRow, error_message: str) -> None:
        from server.services.workflow_orchestrator import pause_task

        requirement_id = _task_int(task, "requirement_id")
        alert_text = (
            f"告警\n"
            f"Copilot runtime authorization blocked task execution.\n"
            f"task_id={_task_id(task)}\n"
            f"requirement_id={requirement_id or '-'}\n"
            f"agent_id={_task_str(task, 'agent_id') or '-'}\n"
            f"skill={_task_str(task, 'skill_name') or '-'}\n"
            f"runtime_backend={_task_str(task, 'runtime_backend') or 'copilot_sdk'}\n"
            f"error={error_message}"
        )
        sent, detail = send_lark_text_alert(alert_text)
        db.add(
            TaskLogRow(
                task_id=_task_id(task),
                event_type="runtime_auth_alert",
                detail="sent" if sent else f"failed: {detail or 'unknown error'}",
            )
        )
        logger.warning(
            "Copilot SDK task #%d hit authorization guard; lark_alert_sent=%s detail=%s",
            _task_id(task),
            sent,
            (detail or "")[:300],
        )
        pause_task(
            db,
            _task_id(task),
            reason=error_message,
            event_detail="Paused after Copilot runtime authorization guard",
        )

    def _resume_stale_task(self, db, task: TaskRow, state: dict, output_dir: Path, paths: dict[str, Path]) -> None:
        heartbeat_age = seconds_since_timestamp(state.get("heartbeatAt") or state.get("updatedAt"))
        if heartbeat_age is None or heartbeat_age <= self.stale_after_sec:
            return

        resume_age = seconds_since_timestamp(state.get("resumeRequestedAt"))
        if resume_age is not None and resume_age < self.stale_after_sec:
            return

        session_id = str(task.runtime_session_id or state.get("sessionId") or "")
        if not session_id:
            error_message = "Missing Copilot SDK session id for stale task recovery"
            cast(Any, task).status = "failed"
            cast(Any, task).last_error_message = error_message
            cast(Any, task).output_content = f"[ERROR] {error_message}"
            cast(Any, task).completed_at = utcnow()
            self._log(db, _task_id(task), "failed", error_message)
            return

        state["resumeRequestedAt"] = utcnow().isoformat()
        save_runtime_state(paths["state"], state)

        payload = self.runtime.build_worker_payload(
            action="resume",
            session_id=session_id,
            output_dir=output_dir,
            preferred_agent=str(task.runtime_selected_agent or "") or None,
            assume_already_idle=self._assume_already_idle(state),
        )
        self.bridge.resume_session(payload)
        self._log(db, _task_id(task), "runtime_resume_requested", f"session={session_id}")
        logger.warning("Requested Copilot SDK session resume for stale task #%d", _task_id(task))

    def _assume_already_idle(self, state: dict) -> bool:
        last_event_type = str(state.get("lastEventType") or "")
        return last_event_type in {"assistant.message", "assistant.usage", "session.error", "tool.execution_complete"}

    def _log(self, db, task_id: int, event_type: str, detail: str | None = None) -> None:
        db.add(TaskLogRow(task_id=task_id, event_type=event_type, detail=detail))
        db.flush()

    @staticmethod
    def _sync_workflow_step(task_id: int) -> None:
        """Trigger workflow orchestrator to advance step/requirement state after task terminal."""
        try:
            from server.services.workflow_orchestrator import sync_workflow_for_task
            sync_workflow_for_task(task_id)
        except Exception:
            logger.exception("Failed to sync workflow step for task #%d", task_id)
