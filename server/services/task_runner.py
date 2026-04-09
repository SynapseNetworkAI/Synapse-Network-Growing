"""Async task dispatcher — runs CrewEngine in background threads."""
import logging
import threading
from pathlib import Path

from server.database import SessionLocal, TaskRow, TaskLogRow, ApprovalRow, utcnow
from server.config import PROJECT_ROOT, ORCHESTRATION_BACKEND
from server.services.task_runtime import get_task_runtime, RuntimeEvent

logger = logging.getLogger("ops-dashboard.task_runner")


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
        output_dir = PROJECT_ROOT / "roles" / role_id / "outputs" / f"task-{task_id}"

        _log(db, task_id, "crew_started", f"skill={skill_name}")
        _log(
            db,
            task_id,
            "runtime_submitted",
            f"backend={ORCHESTRATION_BACKEND} agent={role_id} skill={skill_name}",
        )
        db.commit()

        # Parse context_files from task (JSON list stored as text)
        extra_files = None
        if task.context_files:
            import json
            try:
                extra_files = json.loads(task.context_files)
            except (json.JSONDecodeError, TypeError):
                pass

        runtime = get_task_runtime(PROJECT_ROOT)
        result = runtime.execute(
            persona=agent_persona,
            skill_name=skill_name,
            task_description=task.description,
            output_dir=output_dir,
            extra_context_files=extra_files,
        )

        task.runtime_backend = result.runtime_backend
        task.runtime_session_id = result.runtime_session_id
        task.runtime_selected_agent = result.runtime_selected_agent
        _persist_runtime_events(db, task_id, result.events)

        # Write results back to DB
        task.output_content = result.text
        task.execution_time_ms = result.execution_time_ms
        task.last_error_message = None
        if result.files:
            task.output_path = str(result.files[0])

        if result.error:
            task.status = "failed"
            task.last_error_message = result.error
            task.output_content = f"[ERROR] {result.error}"
            task.completed_at = utcnow()
            _log(db, task_id, "failed", result.error)
        elif task.requires_approval:
            task.status = "pending_approval"
            db.add(ApprovalRow(task_id=task.id))
            _log(db, task_id, "output", result.text[:500])
            _log(db, task_id, "approval_requested")
        else:
            task.status = "completed"
            task.completed_at = utcnow()
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
                task.status = "failed"
                task.last_error_message = str(e)
                task.output_content = f"[ERROR] {e}"
                task.completed_at = utcnow()
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
