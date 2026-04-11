"""Poll detached OpenAI Responses background tasks and persist terminal state."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, cast

from server import config
from server.database import ApprovalRow, SessionLocal, TaskLogRow, TaskRow, utcnow
from server.services.copilot_sdk_state import task_output_dir
from server.services.llm_adapter import OpenAIProvider

logger = logging.getLogger("ops-dashboard.openai_responses_monitor")

_RUNNING_RESPONSE_STATUSES = {"queued", "in_progress"}
_FAILED_RESPONSE_STATUSES = {"failed", "cancelled", "incomplete"}


def _task_id(task: TaskRow) -> int:
    return int(cast(Any, task).id)


def _task_bool(task: TaskRow, name: str) -> bool:
    return bool(getattr(cast(Any, task), name, False))


class OpenAIResponsesTaskMonitor:
    def __init__(
        self,
        project_root: Path | None = None,
        session_factory=SessionLocal,
        provider: OpenAIProvider | None = None,
        poll_interval_sec: float | None = None,
    ):
        self.project_root = (project_root or config.PROJECT_ROOT).resolve()
        self.session_factory = session_factory
        self.provider = provider or OpenAIProvider()
        self.poll_interval_sec = (
            poll_interval_sec if poll_interval_sec is not None else config.OPENAI_RESPONSES_POLL_INTERVAL_SEC
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> threading.Thread:
        if self._thread and self._thread.is_alive():
            return self._thread
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="openai-responses-monitor")
        self._thread.start()
        logger.info("Started OpenAI Responses task monitor")
        return self._thread

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self.poll_interval_sec * 2))
        self._thread = None

    def poll_once(self) -> None:
        db = self.session_factory()
        try:
            task_ids = [
                int(row.id)
                for row in db.query(TaskRow.id).filter(
                    TaskRow.status == "running",
                    TaskRow.runtime_backend == "openai_responses",
                ).all()
            ]
        finally:
            db.close()

        for task_id in task_ids:
            try:
                self.sync_task(task_id)
            except Exception:
                logger.exception("OpenAI Responses monitor failed while syncing task #%d", task_id)

    def sync_task(self, task_id: int) -> None:
        db = self.session_factory()
        try:
            task = db.query(TaskRow).filter(TaskRow.id == task_id).first()
            if not task or str(task.status or "") != "running" or str(task.runtime_backend or "") != "openai_responses":
                return

            response_id = str(task.runtime_session_id or "")
            if not response_id:
                cast(Any, task).status = "failed"
                cast(Any, task).last_error_message = "Missing OpenAI response id"
                cast(Any, task).output_content = "[ERROR] Missing OpenAI response id"
                cast(Any, task).completed_at = utcnow()
                self._log(db, _task_id(task), "failed", "Missing OpenAI response id")
                db.commit()
                self._sync_workflow_step(_task_id(task))
                return

            response = self.provider.retrieve_response(response_id, timeout=config.LLM_TIMEOUT)
            output_dir = task_output_dir(self.project_root, str(task.agent_id), _task_id(task))
            self._write_metadata(output_dir, response)

            status = str(response.get("status") or "")
            if status == "completed":
                self._complete_task(db, task, response, output_dir)
            elif status in _FAILED_RESPONSE_STATUSES:
                self._fail_task(db, task, response, output_dir, status)
            elif status in _RUNNING_RESPONSE_STATUSES:
                db.commit()
            else:
                logger.warning("Unknown OpenAI response status for task #%d: %s", _task_id(task), status)
                db.commit()
        finally:
            db.close()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self.poll_interval_sec)

    def _complete_task(self, db, task: TaskRow, response: dict, output_dir: Path) -> None:
        output_text = self.provider.extract_response_text(response)
        output_path = output_dir / "output.md"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text, encoding="utf-8")

        cast(Any, task).output_path = str(output_path)
        cast(Any, task).output_content = output_text
        cast(Any, task).last_error_message = None
        cast(Any, task).execution_time_ms = self._response_execution_ms(response)
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
        db.commit()
        self._sync_workflow_step(_task_id(task))

    def _fail_task(self, db, task: TaskRow, response: dict, output_dir: Path, status: str) -> None:
        error_message = self.provider.extract_response_error(response) or f"OpenAI response ended with status '{status}'"
        output_text = self.provider.extract_response_text(response)
        if output_text:
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / "output.md"
            output_path.write_text(output_text, encoding="utf-8")
            cast(Any, task).output_path = str(output_path)

        cast(Any, task).status = "failed"
        cast(Any, task).last_error_message = error_message
        cast(Any, task).output_content = output_text or f"[ERROR] {error_message}"
        cast(Any, task).execution_time_ms = self._response_execution_ms(response)
        cast(Any, task).completed_at = utcnow()
        self._log(db, _task_id(task), "failed", error_message)
        db.commit()
        self._sync_workflow_step(_task_id(task))

    @staticmethod
    def _response_execution_ms(response: dict) -> int:
        created_at = int(response.get("created_at") or 0)
        completed_at = int(response.get("completed_at") or 0)
        if created_at > 0 and completed_at >= created_at:
            return int((completed_at - created_at) * 1000)
        return 0

    @staticmethod
    def _write_metadata(output_dir: Path, response: dict) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "provider": "openai",
            "backend": "openai_responses",
            "response_id": response.get("id"),
            "conversation_id": (response.get("conversation") or {}).get("id") if isinstance(response.get("conversation"), dict) else None,
            "status": response.get("status"),
            "raw_response": response,
        }
        (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    @staticmethod
    def _log(db, task_id: int, event_type: str, detail: str | None = None) -> None:
        db.add(TaskLogRow(task_id=task_id, event_type=event_type, detail=detail))
        db.flush()

    @staticmethod
    def _sync_workflow_step(task_id: int) -> None:
        try:
            from server.services.workflow_orchestrator import sync_workflow_for_task

            sync_workflow_for_task(task_id)
        except Exception:
            logger.exception("Failed to sync workflow step for task #%d", task_id)
