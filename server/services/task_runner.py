from __future__ import annotations

"""Async task dispatcher — runs CrewEngine in background threads."""
import json
import logging
import threading
from typing import Any, cast

from server.database import SessionLocal, TaskRow, TaskLogRow, ApprovalRow, utcnow
from server.config import PROJECT_ROOT, ORCHESTRATION_BACKEND, E2E_SYNC_DISPATCH
from server.services.copilot_sdk_state import task_output_dir
from server.services.task_runtime import (
    RuntimeEvent,
    estimate_runtime_budget_points,
    get_task_runtime,
    resolve_runtime_selection,
)
from server.services.runtime_guards import is_openai_runtime_guard_error

logger = logging.getLogger("ops-dashboard.task_runner")


def _task_str(task: TaskRow, name: str) -> str | None:
    value = getattr(cast(Any, task), name, None)
    if value is None:
        return None
    return str(value)


def _task_bool(task: TaskRow, name: str) -> bool:
    return bool(getattr(cast(Any, task), name, False))


def _load_task_context_files(task: TaskRow) -> list[str] | None:
    context_files = _task_str(task, "context_files")
    if not context_files:
        return None

    import json

    try:
        return json.loads(context_files)
    except (json.JSONDecodeError, TypeError):
        return None


def _task_execution_profile(task: TaskRow) -> tuple[dict[str, Any], str]:
    if not task.workflow_steps:
        return {}, ""
    step = task.workflow_steps[0]
    raw = getattr(cast(Any, step), "execution_profile_json", None)
    if not raw:
        return {}, str(getattr(cast(Any, step), "step_type", "") or "")
    try:
        payload = json.loads(str(raw))
        if isinstance(payload, dict):
            return payload, str(getattr(cast(Any, step), "step_type", "") or "")
    except (json.JSONDecodeError, TypeError):
        pass
    return {}, str(getattr(cast(Any, step), "step_type", "") or "")


def dispatch(task_id: int, agent_persona: dict, skill_name: str) -> threading.Thread:
    """Launch task execution in a background thread. Returns the thread."""
    if E2E_SYNC_DISPATCH:
        logger.info("Dispatching task #%d inline for E2E mode (skill=%s)", task_id, skill_name)
        _run_task_sync(task_id, agent_persona, skill_name)
        return threading.current_thread()

    thread = threading.Thread(
        target=_run_task_sync,
        args=(task_id, agent_persona, skill_name),
        daemon=True,
        name=f"task-{task_id}",
    )
    thread.start()
    logger.info("Dispatched task #%d to background thread (skill=%s)", task_id, skill_name)
    return thread


def _run_task_sync(task_id: int, agent_persona: dict, skill_name: str):
    """Execute a task synchronously — called from a background thread."""
    db = SessionLocal()
    try:
        task = db.query(TaskRow).filter(TaskRow.id == task_id).first()
        if not task:
            logger.error("Task #%d not found in DB", task_id)
            return

        # Output directory
        role_id = agent_persona.get("role", agent_persona.get("id", "unknown"))
        output_dir = task_output_dir(PROJECT_ROOT, role_id, task_id)

        _log(db, task_id, "crew_started", f"skill={skill_name}")
        execution_profile, step_type = _task_execution_profile(task)
        selection = resolve_runtime_selection(execution_profile, step_type=step_type, preferred_backend=ORCHESTRATION_BACKEND)
        _log(
            db,
            task_id,
            "runtime_submitted",
            f"backend={selection.backend} provider={selection.provider} model={selection.model} tier={selection.complexity_tier} agent={role_id} skill={skill_name}",
        )
        _log(db, task_id, "runtime_selection", selection.reason)
        cast(Any, task).runtime_backend = selection.backend
        cast(Any, task).runtime_provider = selection.provider
        cast(Any, task).runtime_model = selection.model
        db.commit()

        # Parse context_files from task (JSON list stored as text)
        extra_files = _load_task_context_files(task)

        runtime = get_task_runtime(PROJECT_ROOT, backend=selection.backend)
        result = runtime.execute(
            persona=agent_persona,
            skill_name=skill_name,
            task_description=_task_str(task, "description") or "",
            output_dir=output_dir,
            extra_context_files=extra_files,
            runtime_selection=selection,
        )

        cast(Any, task).runtime_backend = result.runtime_backend
        cast(Any, task).runtime_provider = result.runtime_provider or selection.provider
        cast(Any, task).runtime_model = result.model or selection.model
        cast(Any, task).tokens_used = int(result.tokens_used or 0)
        cast(Any, task).budget_cost_points = estimate_runtime_budget_points(
            tier=selection.complexity_tier,
            runtime_backend=result.runtime_backend or selection.backend,
            execution_time_ms=int(result.execution_time_ms or 0),
            tokens_used=int(result.tokens_used or 0),
        )
        cast(Any, task).runtime_session_id = result.runtime_session_id
        cast(Any, task).runtime_selected_agent = result.runtime_selected_agent
        _persist_runtime_events(db, task_id, result.events)

        # Write results back to DB
        cast(Any, task).output_content = result.text
        cast(Any, task).execution_time_ms = result.execution_time_ms
        cast(Any, task).last_error_message = None
        if result.files:
            cast(Any, task).output_path = str(result.files[0])

        if result.error:
            if result.runtime_backend == "openai_responses" and is_openai_runtime_guard_error(result.error):
                from server.services.openai_responses_monitor import OpenAIResponsesTaskMonitor

                if str(getattr(cast(Any, task), "status", "") or "") != "running":
                    cast(Any, task).status = "running"
                    db.flush()
                monitor = OpenAIResponsesTaskMonitor(project_root=PROJECT_ROOT)
                monitor._alert_and_pause_for_runtime_guard(db, task, result.error)  # noqa: SLF001
                logger.info(
                    "Task #%d paused by OpenAI runtime guard before terminal failure writeback",
                    task_id,
                )
                return
            cast(Any, task).status = "failed"
            cast(Any, task).last_error_message = result.error
            cast(Any, task).output_content = f"[ERROR] {result.error}"
            cast(Any, task).completed_at = utcnow()
            _log(db, task_id, "failed", result.error)
        elif _task_bool(task, "requires_approval"):
            cast(Any, task).status = "pending_approval"
            db.add(ApprovalRow(task_id=task.id))
            _log(db, task_id, "output", result.text[:500])
            _log(db, task_id, "approval_requested")
        elif result.deferred:
            cast(Any, task).status = "running"
            _log(db, task_id, "runtime_detached", result.runtime_session_id or result.runtime_backend)
        else:
            cast(Any, task).status = "completed"
            cast(Any, task).completed_at = utcnow()
            _log(db, task_id, "output", result.text[:500])
            _log(db, task_id, "completed")

        db.commit()
        logger.info(
            "Task #%d finished: status=%s, output=%d chars, time=%dms",
            task_id, task.status, len(result.text), result.execution_time_ms,
        )
        from server.services.workflow_orchestrator import sync_workflow_for_task

        sync_workflow_for_task(task_id)

    except Exception as e:
        logger.exception("Task #%d crashed", task_id)
        try:
            task = db.query(TaskRow).filter(TaskRow.id == task_id).first()
            if task:
                cast(Any, task).status = "failed"
                cast(Any, task).last_error_message = str(e)
                cast(Any, task).output_content = f"[ERROR] {e}"
                cast(Any, task).completed_at = utcnow()
                _log(db, task_id, "failed", str(e))
                db.commit()
                from server.services.workflow_orchestrator import sync_workflow_for_task

                sync_workflow_for_task(task_id)
        except Exception:
            logger.exception("Failed to update task #%d status after crash", task_id)
    finally:
        db.close()


def _log(db, task_id: int, event_type: str, detail: str | None = None):
    db.add(TaskLogRow(task_id=task_id, event_type=event_type, detail=detail))
    db.flush()


def _persist_runtime_events(db, task_id: int, events: list[RuntimeEvent]):
    for event in events:
        _log(db, task_id, event.event_type, event.detail)
