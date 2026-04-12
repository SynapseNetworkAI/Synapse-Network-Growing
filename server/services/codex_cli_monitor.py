"""Monitor detached Codex CLI tasks, sync status, and attempt resume on stalls."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, cast

from server import config
from server.database import ApprovalRow, SessionLocal, TaskLogRow, TaskRow, utcnow
from server.services.codex_cli import (
    codex_runtime_paths,
    load_codex_state,
    pid_is_running,
    save_codex_state,
    start_codex_exec_async,
    terminate_pid,
    _parse_codex_exec_stdout,
)
from server.services.codex_session_registry import update_session_state, validate_codex_session_registry
from server.services.copilot_sdk_state import read_text_if_exists, seconds_since_timestamp, task_output_dir

logger = logging.getLogger("ops-dashboard.codex_cli_monitor")


def _task_id(task: TaskRow) -> int:
    return int(cast(Any, task).id)


def _task_bool(task: TaskRow, name: str) -> bool:
    return bool(getattr(cast(Any, task), name, False))


class CodexCLITaskMonitor:
    def __init__(
        self,
        project_root: Path | None = None,
        session_factory=SessionLocal,
        poll_interval_sec: float | None = None,
    ) -> None:
        self.project_root = (project_root or config.PROJECT_ROOT).resolve()
        self.session_factory = session_factory
        self.poll_interval_sec = poll_interval_sec if poll_interval_sec is not None else config.CODEX_CLI_POLL_INTERVAL_SEC
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> threading.Thread:
        if self._thread and self._thread.is_alive():
            return self._thread
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="codex-cli-monitor")
        self._thread.start()
        logger.info("Started Codex CLI task monitor")
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
                    TaskRow.runtime_backend == "codex_cli",
                ).all()
            ]
        finally:
            db.close()

        for task_id in task_ids:
            try:
                self.sync_task(task_id)
            except Exception:
                logger.exception("Codex CLI monitor failed while syncing task #%d", task_id)

    def sync_task(self, task_id: int) -> None:
        db = self.session_factory()
        try:
            task = db.query(TaskRow).filter(TaskRow.id == task_id).first()
            if not task or str(task.status or "") != "running" or str(task.runtime_backend or "") != "codex_cli":
                return

            output_dir = self._resolve_output_dir(task)
            paths = codex_runtime_paths(output_dir)
            metadata = self._load_json(paths["metadata"])
            state = load_codex_state(paths["state"]) or {}
            stdout = read_text_if_exists(paths["stdout"]) or ""
            stderr = read_text_if_exists(paths["stderr"]) or ""
            passthrough_stdout, final_text, discovered_thread_id, json_event_count = _parse_codex_exec_stdout(stdout)
            del passthrough_stdout
            if discovered_thread_id and str(task.runtime_session_id or "") != discovered_thread_id:
                cast(Any, task).runtime_session_id = discovered_thread_id
                self._log(db, _task_id(task), "runtime_session_created", f"thread={discovered_thread_id}")
                self._touch_registry(db, task, metadata, status="active", thread_id=discovered_thread_id)
                db.commit()

            thread_id = discovered_thread_id or str(task.runtime_session_id or "") or str(state.get("thread_id") or "")
            resume_count = int(state.get("resume_count") or metadata.get("resume_count") or 0)

            if self._should_resume_terminal_state(state, thread_id=thread_id, resume_count=resume_count):
                self._attempt_resume_or_pause(
                    db,
                    task,
                    paths,
                    metadata,
                    state,
                    thread_id=thread_id,
                    resume_count=resume_count,
                    reason="Codex CLI process exited unexpectedly before producing a terminal result",
                )
                return

            if self._is_terminal_state(state, paths["output"]):
                self._finalize_task(db, task, paths, state, stderr, final_text, discovered_thread_id, json_event_count, metadata)
                return

            activity_age = self._activity_age_seconds(paths)
            started_age = seconds_since_timestamp(str(state.get("started_at") or task.started_at or ""))
            timeout_seconds = int(metadata.get("timeout_seconds") or config.CODEX_CLI_TASK_TIMEOUT)

            if started_age is not None and started_age >= timeout_seconds:
                self._attempt_resume_or_pause(
                    db,
                    task,
                    paths,
                    metadata,
                    state,
                    thread_id=thread_id,
                    resume_count=resume_count,
                    reason=f"Codex CLI task exceeded timeout {timeout_seconds}s",
                )
                return

            if activity_age is not None and activity_age >= config.CODEX_CLI_STALE_AFTER_SEC:
                grace = max(config.CODEX_CLI_MONITOR_STARTUP_GRACE_SEC, 1.0)
                if started_age is None or started_age >= grace:
                    self._attempt_resume_or_pause(
                        db,
                        task,
                        paths,
                        metadata,
                        state,
                        thread_id=thread_id,
                        resume_count=resume_count,
                        reason=f"Codex CLI task stalled for {int(activity_age)}s",
                    )
                    return

            self._touch_registry(db, task, metadata, status="active", thread_id=thread_id or None, heartbeat=True)
            if json_event_count:
                self._update_metadata(paths["metadata"], metadata, {"json_event_count": json_event_count})
            db.commit()
        finally:
            db.close()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self.poll_interval_sec)

    def _finalize_task(
        self,
        db,
        task: TaskRow,
        paths: dict[str, Path],
        state: dict[str, object],
        stderr: str,
        final_text: str,
        thread_id: str | None,
        json_event_count: int,
        metadata: dict[str, Any],
    ) -> None:
        exit_code = int(state.get("exit_code") or 0)
        output_text = read_text_if_exists(paths["output"]) or final_text
        if output_text and not paths["output"].exists():
            paths["output"].write_text(output_text, encoding="utf-8")
        cast(Any, task).runtime_session_id = thread_id or cast(Any, task).runtime_session_id
        cast(Any, task).output_path = str(paths["output"])
        cast(Any, task).execution_time_ms = int((seconds_since_timestamp(str(state.get("started_at") or "")) or 0) * 1000)
        self._update_metadata(paths["metadata"], metadata, {"thread_id": thread_id or "", "json_event_count": json_event_count})
        if exit_code == 0 and output_text:
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
            self._touch_registry(db, task, metadata, status="completed", thread_id=thread_id or None, heartbeat=True)
        else:
            error = (stderr or output_text or "Codex CLI execution failed").strip()[:4000]
            cast(Any, task).status = "failed"
            cast(Any, task).last_error_message = error
            cast(Any, task).output_content = output_text or f"[ERROR] {error}"
            cast(Any, task).completed_at = utcnow()
            self._log(db, _task_id(task), "failed", error)
            self._touch_registry(db, task, metadata, status="failed", thread_id=thread_id or None, heartbeat=True)
        db.commit()
        self._sync_workflow_step(_task_id(task))

    def _attempt_resume_or_pause(
        self,
        db,
        task: TaskRow,
        paths: dict[str, Path],
        metadata: dict[str, Any],
        state: dict[str, object],
        *,
        thread_id: str,
        resume_count: int,
        reason: str,
    ) -> None:
        from server.services.workflow_orchestrator import pause_task

        pid = int(state.get("pid") or metadata.get("pid") or 0)
        if pid and pid_is_running(pid):
            terminate_pid(pid)
        if not thread_id or resume_count >= config.CODEX_CLI_RESUME_MAX_ATTEMPTS:
            pause_task(db, _task_id(task), reason=reason, event_detail="Paused after Codex CLI monitor recovery failed")
            self._touch_registry(db, task, metadata, status="failed", thread_id=thread_id or None, heartbeat=True, resume_count=resume_count)
            return

        prompt = read_text_if_exists(paths["prompt"]) or "Continue the task and finish it using the current repository state."
        cwd = Path(str(metadata.get("cwd") or self.project_root)).resolve()
        add_dirs = [Path(item).resolve() for item in (metadata.get("add_dirs") or []) if str(item).strip()]
        model = str(metadata.get("model") or task.runtime_model or config.CODEX_CLI_MODEL or "").strip() or None
        launched = start_codex_exec_async(
            prompt=prompt,
            cwd=cwd,
            output_dir=paths["output"].parent,
            model=model,
            add_dirs=add_dirs,
            resume_thread_id=thread_id,
            append_logs=True,
        )
        self._update_metadata(
            paths["metadata"],
            metadata,
            {
                "pid": launched.pid,
                "thread_id": thread_id,
                "resume_count": resume_count + 1,
                "state_path": str(launched.state_path),
                "stdout_path": str(launched.stdout_path),
                "stderr_path": str(launched.stderr_path),
                "prompt_path": str(launched.prompt_path),
            },
        )
        save_codex_state(
            paths["state"],
            {
                **state,
                "status": "running",
                "pid": int(launched.pid),
                "thread_id": thread_id,
                "resume_count": resume_count + 1,
                "started_at": str(state.get("started_at") or utcnow().isoformat()),
                "resumed_at": utcnow().isoformat(),
            },
        )
        cast(Any, task).runtime_session_id = thread_id
        self._log(db, _task_id(task), "runtime_resume_requested", f"thread={thread_id}")
        self._touch_registry(db, task, metadata, status="active", thread_id=thread_id, heartbeat=True, resume_count=resume_count + 1)
        db.commit()

    @staticmethod
    def _is_terminal_state(state: dict[str, object], output_path: Path) -> bool:
        status = str(state.get("status") or "")
        if status in {"completed", "failed"}:
            return True
        pid = int(state.get("pid") or 0)
        if pid and not pid_is_running(pid):
            return True
        return output_path.exists() and status not in {"running", ""}

    @staticmethod
    def _should_resume_terminal_state(state: dict[str, object], *, thread_id: str, resume_count: int) -> bool:
        if not thread_id or resume_count >= config.CODEX_CLI_RESUME_MAX_ATTEMPTS:
            return False
        status = str(state.get("status") or "")
        if status == "failed":
            return True
        pid = int(state.get("pid") or 0)
        if status in {"running", ""} and pid and not pid_is_running(pid):
            return True
        return False

    def _resolve_output_dir(self, task: TaskRow) -> Path:
        output_path = str(task.output_path or "").strip()
        if output_path:
            return Path(output_path).resolve().parent
        return task_output_dir(self.project_root, str(task.agent_id or "unknown"), _task_id(task))

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _update_metadata(path: Path, metadata: dict[str, Any], patch: dict[str, Any]) -> None:
        next_payload = dict(metadata or {})
        next_payload.update(patch)
        path.write_text(json.dumps(next_payload, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def _activity_age_seconds(paths: dict[str, Path]) -> float | None:
        timestamps: list[float] = []
        for key in ("output", "stdout", "stderr", "state"):
            path = paths[key]
            if path.exists():
                timestamps.append(path.stat().st_mtime)
        if not timestamps:
            return None
        return max(0.0, utcnow().timestamp() - max(timestamps))

    def _touch_registry(
        self,
        db,
        task: TaskRow,
        metadata: dict[str, Any],
        *,
        status: str,
        thread_id: str | None,
        heartbeat: bool = False,
        resume_count: int | None = None,
    ) -> None:
        if not task.workflow_steps:
            return
        step = task.workflow_steps[0]
        update_session_state(
            db=db,
            role_key=str(task.agent_id or ""),
            project_root=str(metadata.get("cwd") or self.project_root),
            requirement_id=int(getattr(cast(Any, step), "requirement_id", 0) or 0) or None,
            thread_id=thread_id,
            status=status,
            heartbeat=heartbeat,
            current_task_id=_task_id(task),
            resume_count=resume_count,
            metadata_patch={"last_task_id": _task_id(task)},
        )

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

    def validate_registry(self) -> dict[str, Any]:
        """Expose session registry diagnostics for downstream tooling/tests."""
        db = self.session_factory()
        try:
            return validate_codex_session_registry(db, project_root=self.project_root)
        finally:
            db.close()
