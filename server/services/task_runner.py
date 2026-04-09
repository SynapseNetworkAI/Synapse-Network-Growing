"""Async task dispatcher — runs CrewEngine in background threads."""
import logging
import threading
from typing import Any, cast

from server.database import SessionLocal, TaskRow, TaskLogRow, ApprovalRow, utcnow
from server.config import PROJECT_ROOT, ORCHESTRATION_BACKEND
from server.services.copilot_sdk_state import task_output_dir
from server.services.task_runtime import get_task_runtime, RuntimeEvent

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


def dispatch(task_id: int, agent_persona: dict, skill_name: str) -> threading.Thread:
    """Launch task execution in a background thread. Returns the thread."""
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
        _log(
            db,
            task_id,
            "runtime_submitted",
            f"backend={ORCHESTRATION_BACKEND} agent={role_id} skill={skill_name}",
        )
        db.commit()

        # Parse context_files from task (JSON list stored as text)
        extra_files = _load_task_context_files(task)

        runtime = get_task_runtime(PROJECT_ROOT)
        result = runtime.execute(
            persona=agent_persona,
            skill_name=skill_name,
            task_description=_task_str(task, "description") or "",
            output_dir=output_dir,
            extra_context_files=extra_files,
        )

        cast(Any, task).runtime_backend = result.runtime_backend
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
