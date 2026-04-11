from __future__ import annotations

"""Tasks API router."""
import json
import logging
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import Any, Optional, cast

import yaml

from server.database import get_db, TaskRow, AgentRow, TaskLogRow, ApprovalRow, WorkflowStepRow, RequirementRow, utcnow
from server.schemas import (
    TaskCreate,
    TaskOut,
    TaskPage,
    TaskLogOut,
    TaskHistoryOut,
    TaskBulkRetryRequest,
    TaskExecutionSuggestionRequest,
    TaskExecutionSuggestion,
    TaskPatch,
)
from server.config import PROJECT_ROOT, ORCHESTRATION_BACKEND
from server.services.task_metadata import task_metadata_for_agent, project_for_group
from server.services.execution_resolver import suggest_task_execution

logger = logging.getLogger("ops-dashboard.tasks")
router = APIRouter(prefix="/api/tasks", tags=["tasks"])

VALID_STATUSES = {"pending", "running", "pending_approval", "approved", "rejected", "completed", "failed", "paused", "cancelled", "deleted"}
TASK_NOT_FOUND = "Task not found"


def _add_log(db: Session, task_id: int, event_type: str, detail: str | None = None):
    db.add(TaskLogRow(task_id=task_id, event_type=event_type, detail=detail))


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _require_task_id(row: TaskRow) -> int:
    task_id = _as_int(row.id)
    if task_id is None:
        raise RuntimeError("Task row is missing id")
    return task_id


def _task_agent_group(row: TaskRow) -> str:
    return _as_text(row.agent_group) or (_as_text(row.agent.group) if row.agent else "") or ""


def _task_project_id(row: TaskRow) -> str | None:
    return _as_text(row.project_id) or project_for_group(_task_agent_group(row))


def _list_output_files(row: TaskRow) -> list[str] | None:
    """List files in the task's output directory (relative paths)."""
    from pathlib import Path
    output_path = _as_text(row.output_path)
    if not output_path:
        return None
    output_dir = Path(output_path).parent
    if not output_dir.is_dir():
        return None
    try:
        files = sorted(
            str(f.relative_to(output_dir))
            for f in output_dir.iterdir()
            if f.is_file() and not f.name.startswith("copilot-session")
        )
        return files if files else None
    except OSError:
        return None


def _task_to_out(row: TaskRow) -> TaskOut:
    agent_group = _task_agent_group(row)
    project_id = _task_project_id(row)

    # Resolve requirement via workflow_steps relationship
    requirement_id = None
    requirement_title = None
    if row.workflow_steps:
        step = row.workflow_steps[0]
        requirement_id = _as_int(step.requirement_id)
        if step.requirement:
            requirement_title = _as_text(step.requirement.title)

    output_files = _list_output_files(row)

    return TaskOut(
        id=_require_task_id(row),
        description=_as_text(row.description) or "",
        agent_id=_as_text(row.agent_id) or "",
        status=_as_text(row.status) or "pending",
        requires_approval=cast(bool, row.requires_approval),
        priority=_as_text(row.priority) or "normal",
        project_id=project_id or None,
        project_label=project_id or None,
        agent_group=agent_group or None,
        skill_name=_as_text(row.skill_name),
        context_files=_as_text(row.context_files),
        retry_of_task_id=_as_int(row.retry_of_task_id),
        attempt_no=_as_int(row.attempt_no) or 1,
        last_error_message=_as_text(row.last_error_message),
        runtime_backend=_as_text(row.runtime_backend),
        runtime_session_id=_as_text(row.runtime_session_id),
        runtime_selected_agent=_as_text(row.runtime_selected_agent),
        output_path=_as_text(row.output_path),
        output_content=_as_text(row.output_content),
        execution_time_ms=_as_int(row.execution_time_ms),
        requirement_id=requirement_id,
        requirement_title=requirement_title,
        output_files=output_files,
        created_at=cast(Any, row.created_at),
        started_at=cast(Any, row.started_at),
        completed_at=cast(Any, row.completed_at),
    )


def _task_to_history_out(row: TaskRow) -> TaskHistoryOut:
    agent_group = _task_agent_group(row)
    project_id = _task_project_id(row)
    return TaskHistoryOut(
        task_id=_require_task_id(row),
        retry_of_task_id=_as_int(row.retry_of_task_id),
        attempt_no=_as_int(row.attempt_no) or 1,
        status=_as_text(row.status) or "pending",
        project_id=project_id or None,
        agent_group=agent_group or None,
        agent_id=_as_text(row.agent_id) or "",
        skill_name=_as_text(row.skill_name),
        last_error_message=_as_text(row.last_error_message),
        runtime_backend=_as_text(row.runtime_backend),
        created_at=cast(Any, row.created_at),
        started_at=cast(Any, row.started_at),
        completed_at=cast(Any, row.completed_at),
    )


def _retry_root_id(row: TaskRow, by_id: dict[int, TaskRow]) -> int:
    current = row
    seen: set[int] = set()
    current_retry_of = _as_int(current.retry_of_task_id)
    while current_retry_of and current_retry_of in by_id and current_retry_of not in seen:
        seen.add(_require_task_id(current))
        current = by_id[current_retry_of]
        current_retry_of = _as_int(current.retry_of_task_id)
    return _require_task_id(current)


def _retry_history_for_task(task_id: int, db: Session) -> list[TaskRow]:
    rows = db.query(TaskRow).order_by(TaskRow.created_at.asc(), TaskRow.id.asc()).all()
    by_id = {_require_task_id(row): row for row in rows}
    row = by_id.get(task_id)
    if not row:
        return []

    root_id = _retry_root_id(row, by_id)
    history = [candidate for candidate in rows if _retry_root_id(candidate, by_id) == root_id]
    history.sort(key=lambda candidate: (_as_int(candidate.attempt_no) or 1, candidate.created_at or utcnow(), _require_task_id(candidate)))
    return history


def _validate_retry_source(source: TaskRow, mode: str):
    if _as_text(source.status) not in {"failed", "rejected"}:
        raise HTTPException(status_code=400, detail="Only failed or rejected tasks can be retried")
    if mode not in {"run_now", "edit_first"}:
        raise HTTPException(status_code=400, detail="mode must be run_now|edit_first")
    if mode == "run_now" and not _as_text(source.skill_name):
        raise HTTPException(status_code=400, detail="Cannot retry immediately without a skill")


def _build_retry_task(source: TaskRow, mode: str, db: Session) -> tuple[TaskRow, tuple[int, dict, str] | None]:
    _validate_retry_source(source, mode)

    row = TaskRow(
        description=source.description,
        agent_id=source.agent_id,
        status="pending",
        requires_approval=source.requires_approval,
        priority=source.priority,
        project_id=source.project_id,
        agent_group=source.agent_group,
        skill_name=source.skill_name,
        context_files=source.context_files,
        retry_of_task_id=source.id,
        attempt_no=(source.attempt_no or 1) + 1,
    )
    db.add(row)
    db.flush()
    _add_log(db, _require_task_id(row), "created", _as_text(row.description))
    _add_log(db, _require_task_id(row), "retried_from", f"task={_require_task_id(source)}")

    if mode == "run_now":
        cast(Any, row).status = "running"
        cast(Any, row).started_at = utcnow()
        cast(Any, row).runtime_backend = ORCHESTRATION_BACKEND
        _add_log(db, _require_task_id(row), "started", f"skill={_as_text(row.skill_name)}")
        return row, (_require_task_id(row), _load_full_persona(_as_text(row.agent_id) or ""), _as_text(row.skill_name) or "")

    return row, None


def _load_full_persona(agent_id: str) -> dict:
    """Load full persona from persona.md: YAML frontmatter + body text."""
    persona_path = PROJECT_ROOT / "roles" / agent_id / "prompts" / "persona.md"
    if not persona_path.exists():
        return {"role": agent_id, "display_name": agent_id, "goal": "", "body": ""}

    text = persona_path.read_text(encoding="utf-8")
    fm = {}
    body = text
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            fm = yaml.safe_load(text[3:end]) or {}
            body = text[end + 3:].strip()

    return {
        "role": fm.get("role", agent_id),
        "id": fm.get("role", agent_id),
        "display_name": fm.get("display_name", agent_id),
        "goal": fm.get("goal", ""),
        "skills": fm.get("skills", []),
        "body": body,
    }


@router.get("", response_model=TaskPage)
def list_tasks(
    status: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    agent_group: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    requirement_id: Optional[int] = Query(None),
    only_anomalies: bool = Query(False),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(TaskRow)
    if status:
        q = q.filter(TaskRow.status == status)
    if agent_id:
        q = q.filter(TaskRow.agent_id == agent_id)
    if requirement_id is not None:
        task_ids = [
            _as_int(s.compatibility_task_id)
            for s in db.query(WorkflowStepRow).filter(WorkflowStepRow.requirement_id == requirement_id).all()
            if s.compatibility_task_id is not None
        ]
        q = q.filter(TaskRow.id.in_(task_ids or [-1]))
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                TaskRow.description.ilike(pattern),
                TaskRow.output_content.ilike(pattern),
            )
        )
    rows = q.order_by(TaskRow.created_at.desc(), TaskRow.id.desc()).all()

    if only_anomalies:
        rows = [r for r in rows if _as_text(r.status) in {"failed", "pending_approval", "running"}]
    if agent_group:
        rows = [r for r in rows if _task_agent_group(r) == agent_group]
    if project_id:
        rows = [r for r in rows if _task_project_id(r) == project_id]

    # Status counts across all filtered rows (not just current page)
    status_counts: dict[str, int] = {}
    for r in rows:
        s = _as_text(r.status) or "pending"
        status_counts[s] = status_counts.get(s, 0) + 1

    total = len(rows)
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    start = (page - 1) * page_size
    page_rows = rows[start: start + page_size]

    return TaskPage(
        items=[_task_to_out(r) for r in page_rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        status_counts=status_counts,
    )


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND)
    return _task_to_out(row)


@router.patch("/{task_id}", response_model=TaskOut)
def patch_task(
    task_id: int,
    body: TaskPatch,
    db: Session = Depends(get_db),
):
    """Edit task description and/or priority (only for pending or paused tasks)."""
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND)
    row_status = _as_text(row.status) or "pending"
    if row_status not in {"pending", "paused"}:
        raise HTTPException(status_code=400, detail=f"Cannot edit task in '{row_status}' status. Only pending or paused tasks can be edited.")
    if body.description is not None:
        if not body.description.strip():
            raise HTTPException(status_code=400, detail="description cannot be blank")
        cast(Any, row).description = body.description.strip()
        _add_log(db, _require_task_id(row), "edited", "description updated")
    if body.priority is not None:
        if body.priority not in {"low", "normal", "high"}:
            raise HTTPException(status_code=400, detail="priority must be low|normal|high")
        cast(Any, row).priority = body.priority
    db.commit()
    db.refresh(row)
    return _task_to_out(row)


@router.post("/{task_id}/pause", response_model=TaskOut)
def pause_task_endpoint(
    task_id: int,
    db: Session = Depends(get_db),
):
    """Pause a running task and cascade the pause to parent requirement."""
    from server.services.workflow_orchestrator import pause_task
    try:
        row = pause_task(db, task_id)
        return _task_to_out(row)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/suggest-execution", response_model=TaskExecutionSuggestion)
def suggest_execution(body: TaskExecutionSuggestionRequest, db: Session = Depends(get_db)):
    return suggest_task_execution(
        db=db,
        description=body.description,
        preferred_agent_id=body.agent_id,
        preferred_skill_name=body.skill_name,
        limit=body.limit,
    )


@router.post("", response_model=TaskOut, status_code=201)
def create_task(body: TaskCreate, db: Session = Depends(get_db)):
    if body.priority not in ("low", "normal", "high"):
        raise HTTPException(status_code=400, detail="priority must be low|normal|high")

    resolved_agent_id = body.agent_id
    resolved_skill_name = body.skill_name

    if not resolved_agent_id or not resolved_skill_name:
        suggestion = suggest_task_execution(
            db=db,
            description=body.description,
            preferred_agent_id=body.agent_id,
            preferred_skill_name=body.skill_name,
        )
        if not resolved_agent_id and suggestion.requires_confirmation and not body.confirm_auto_selection:
            raise HTTPException(status_code=409, detail={
                "message": "Auto-selection confidence is low. Please confirm the suggested Agent / Skill.",
                "suggestion": suggestion.model_dump(),
            })
        resolved_agent_id = resolved_agent_id or suggestion.agent_id
        if not resolved_skill_name and suggestion.skill_name and (
            not suggestion.requires_confirmation or suggestion.agent_id == resolved_agent_id
        ):
            resolved_skill_name = suggestion.skill_name

    if not resolved_agent_id:
        raise HTTPException(status_code=400, detail="Unable to resolve an agent for this task.")

    agent = db.query(AgentRow).filter(AgentRow.id == resolved_agent_id).first()
    if not agent:
        raise HTTPException(status_code=400, detail=f"Agent '{resolved_agent_id}' not found. Sync agents first.")

    row = TaskRow(
        description=body.description,
        agent_id=resolved_agent_id,
        requires_approval=body.requires_approval,
        priority=body.priority,
        project_id=task_metadata_for_agent(_as_text(agent.group))[0],
        agent_group=task_metadata_for_agent(_as_text(agent.group))[1],
        skill_name=resolved_skill_name,
        context_files=json.dumps(body.context_files) if body.context_files else None,
    )
    db.add(row)
    db.flush()
    _add_log(db, _require_task_id(row), "created", body.description)
    db.commit()
    db.refresh(row)
    logger.info("Task #%d created: agent=%s, skill=%s, desc=%s",
                _require_task_id(row), _as_text(row.agent_id), _as_text(row.skill_name), body.description[:60])
    return _task_to_out(row)


@router.post("/{task_id}/run", response_model=TaskOut)
def run_task(
    task_id: int,
    skill: Optional[str] = Query(None, description="Skill to execute (e.g. seo-audit). Overrides task's skill_name."),
    db: Session = Depends(get_db),
):
    """Transition task to 'running' and dispatch to background CrewEngine."""
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND)
    row_status = _as_text(row.status) or "pending"
    if row_status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot run task in '{row_status}' status")

    # Determine skill
    effective_skill = skill or _as_text(row.skill_name)
    if not effective_skill:
        suggestion = suggest_task_execution(
            db=db,
            description=_as_text(row.description) or "",
            preferred_agent_id=_as_text(row.agent_id),
        )
        if suggestion.requires_confirmation:
            raise HTTPException(status_code=409, detail={
                "message": "Skill auto-selection confidence is low. Please confirm the suggested Skill.",
                "suggestion": suggestion.model_dump(),
            })
        effective_skill = suggestion.skill_name

    if not effective_skill:
        raise HTTPException(status_code=400, detail="No skill specified. Pass ?skill=... or set skill_name on task.")

    # Load persona
    persona = _load_full_persona(_as_text(row.agent_id) or "")

    # Mark as running
    cast(Any, row).status = "running"
    cast(Any, row).skill_name = effective_skill
    cast(Any, row).started_at = utcnow()
    cast(Any, row).runtime_backend = ORCHESTRATION_BACKEND
    _add_log(db, _require_task_id(row), "started", f"skill={effective_skill}")
    db.commit()
    db.refresh(row)

    # Dispatch to background thread
    from server.services.task_runner import dispatch
    dispatch(task_id=_require_task_id(row), agent_persona=persona, skill_name=effective_skill)

    return _task_to_out(row)  # returns status=running immediately


@router.post("/{task_id}/retry", response_model=TaskOut)
def retry_task(
    task_id: int,
    mode: str = Query("run_now", description="Retry mode: run_now | edit_first"),
    db: Session = Depends(get_db),
):
    source = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND)
    row, dispatch_payload = _build_retry_task(source, mode, db)
    db.commit()
    db.refresh(row)

    if dispatch_payload:
        from server.services.task_runner import dispatch

        retry_task_id, persona, skill_name = dispatch_payload
        dispatch(task_id=retry_task_id, agent_persona=persona, skill_name=skill_name)

    return _task_to_out(row)


@router.post("/bulk-retry", response_model=list[TaskOut])
def bulk_retry_tasks(body: TaskBulkRetryRequest, db: Session = Depends(get_db)):
    if not body.task_ids:
        raise HTTPException(status_code=400, detail="task_ids is required")

    unique_ids = list(dict.fromkeys(body.task_ids))
    rows = db.query(TaskRow).filter(TaskRow.id.in_(unique_ids)).all()
    by_id = {_require_task_id(row): row for row in rows}
    missing_ids = [task_id for task_id in unique_ids if task_id not in by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Tasks not found: {missing_ids}")

    created_rows: list[TaskRow] = []
    dispatch_payloads: list[tuple[int, dict, str]] = []
    for task_id in unique_ids:
        row, dispatch_payload = _build_retry_task(by_id[task_id], body.mode, db)
        created_rows.append(row)
        if dispatch_payload:
            dispatch_payloads.append(dispatch_payload)

    db.commit()
    for row in created_rows:
        db.refresh(row)

    if dispatch_payloads:
        from server.services.task_runner import dispatch

        for retry_task_id, persona, skill_name in dispatch_payloads:
            dispatch(task_id=retry_task_id, agent_persona=persona, skill_name=skill_name)

    return [_task_to_out(row) for row in created_rows]


@router.get("/{task_id}/history", response_model=list[TaskHistoryOut])
def get_task_history(task_id: int, db: Session = Depends(get_db)):
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND)
    return [_task_to_history_out(item) for item in _retry_history_for_task(task_id, db)]


@router.get("/{task_id}/logs", response_model=list[TaskLogOut])
def get_task_logs(task_id: int, db: Session = Depends(get_db)):
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND)
    return db.query(TaskLogRow).filter(TaskLogRow.task_id == task_id).order_by(TaskLogRow.created_at).all()


# ---------------------------------------------------------------------------
# File changes (git diff) endpoint
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: str, timeout: int = 15) -> str:
    result = subprocess.run(
        ["git"] + args, cwd=cwd,
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout


def _parse_git_diff(diff_text: str) -> list[dict]:
    """Split a unified diff into per-file objects with additions/deletions counts."""
    files: list[dict] = []
    current: dict | None = None
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current:
                files.append(current)
            current = {"filename": "", "additions": 0, "deletions": 0, "patch": ""}
        elif current is not None:
            if line.startswith("+++ b/"):
                current["filename"] = line[6:].rstrip("\n")
            elif line.startswith("+") and not line.startswith("+++"):
                current["additions"] += 1
                current["patch"] += line
            elif line.startswith("-") and not line.startswith("---"):
                current["deletions"] += 1
                current["patch"] += line
            else:
                current["patch"] += line
    if current:
        files.append(current)
    return [f for f in files if f["filename"]]


def _get_target_project_path(row: TaskRow) -> str | None:
    """Resolve target_project_path via task → workflow_step → requirement."""
    if not row.workflow_steps:
        return None
    step = row.workflow_steps[0]
    req = step.requirement if step.requirement else None
    if req is None:
        return None
    return str(req.target_project_path) if req.target_project_path else None


@router.get("/{task_id}/file-changes")
def get_task_file_changes(task_id: int, db: Session = Depends(get_db)):
    """Return git diff for files changed by this task in the target project."""
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail=TASK_NOT_FOUND)

    # 1. Try reading cached snapshot first (written at step completion)
    output_path = _as_text(row.output_path)
    if output_path:
        cache_file = Path(output_path).parent / "file-changes.json"
        if cache_file.is_file():
            try:
                return json.loads(cache_file.read_text())
            except Exception:
                pass  # fall through to live diff

    # 2. Live diff from target project
    target_path = _get_target_project_path(row)
    if not target_path or not Path(target_path).is_dir():
        return {"changed_files": [], "target_project_path": target_path, "source": "live"}

    try:
        diff_text = _run_git(["diff", "HEAD", "--unified=5"], cwd=target_path)
        changed_files = _parse_git_diff(diff_text)
        return {
            "changed_files": changed_files,
            "target_project_path": target_path,
            "source": "live",
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.warning("Git diff failed for task %s: %s", task_id, exc)
        return {"changed_files": [], "target_project_path": target_path, "source": "live", "error": str(exc)}
