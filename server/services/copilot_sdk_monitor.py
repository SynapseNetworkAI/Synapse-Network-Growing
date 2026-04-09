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
from server.services.task_runtime import CopilotSDKTaskRuntime, normalize_copilot_event_type

logger = logging.getLogger("ops-dashboard.copilot_sdk_monitor")


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
        cast(Any, task).status = "failed"
        cast(Any, task).last_error_message = error_message
        cast(Any, task).output_content = output_text or f"[ERROR] {error_message}"
        cast(Any, task).completed_at = utcnow()
        self._log(db, _task_id(task), "failed", error_message)
        logger.info("Copilot SDK task #%d failed via monitor: %s", _task_id(task), error_message)
        db.commit()
        self._sync_workflow_step(_task_id(task))

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