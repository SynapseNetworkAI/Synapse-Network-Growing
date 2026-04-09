"""Tasks API router."""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

import yaml

from server.database import get_db, TaskRow, AgentRow, TaskLogRow, ApprovalRow, utcnow
from server.schemas import (
    TaskCreate,
    TaskOut,
    TaskLogOut,
    TaskHistoryOut,
    TaskBulkRetryRequest,
    TaskExecutionSuggestionRequest,
    TaskExecutionSuggestion,
)
from server.config import PROJECT_ROOT
from server.services.task_metadata import task_metadata_for_agent, project_for_group
from server.services.execution_resolver import suggest_task_execution

logger = logging.getLogger("ops-dashboard.tasks")
router = APIRouter(prefix="/api/tasks", tags=["tasks"])

VALID_STATUSES = {"pending", "running", "pending_approval", "approved", "rejected", "completed", "failed"}


def _add_log(db: Session, task_id: int, event_type: str, detail: str = None):
    db.add(TaskLogRow(task_id=task_id, event_type=event_type, detail=detail))


def _task_to_out(row: TaskRow) -> TaskOut:
    agent_group = row.agent_group or (row.agent.group if row.agent else "")
    project_id = row.project_id or project_for_group(agent_group)
    return TaskOut(
        id=row.id,
        description=row.description,
        agent_id=row.agent_id,
        status=row.status,
        requires_approval=row.requires_approval,
        priority=row.priority,
        project_id=project_id or None,
        project_label=project_id or None,
        agent_group=agent_group or None,
        skill_name=row.skill_name,
        context_files=row.context_files,
        retry_of_task_id=row.retry_of_task_id,
        attempt_no=row.attempt_no or 1,
        last_error_message=row.last_error_message,
        output_path=row.output_path,
        output_content=row.output_content,
        execution_time_ms=row.execution_time_ms,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _task_to_history_out(row: TaskRow) -> TaskHistoryOut:
    agent_group = row.agent_group or (row.agent.group if row.agent else "")
    project_id = row.project_id or project_for_group(agent_group)
    return TaskHistoryOut(
        task_id=row.id,
        retry_of_task_id=row.retry_of_task_id,
        attempt_no=row.attempt_no or 1,
        status=row.status,
        project_id=project_id or None,
        agent_group=agent_group or None,
        agent_id=row.agent_id,
        skill_name=row.skill_name,
        last_error_message=row.last_error_message,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _retry_root_id(row: TaskRow, by_id: dict[int, TaskRow]) -> int:
    current = row
    seen: set[int] = set()
    while current.retry_of_task_id and current.retry_of_task_id in by_id and current.retry_of_task_id not in seen:
        seen.add(current.id)
        current = by_id[current.retry_of_task_id]
    return current.id


def _retry_history_for_task(task_id: int, db: Session) -> list[TaskRow]:
    rows = db.query(TaskRow).order_by(TaskRow.created_at.asc(), TaskRow.id.asc()).all()
    by_id = {row.id: row for row in rows}
    row = by_id.get(task_id)
    if not row:
        return []

    root_id = _retry_root_id(row, by_id)
    history = [candidate for candidate in rows if _retry_root_id(candidate, by_id) == root_id]
    history.sort(key=lambda candidate: (candidate.attempt_no or 1, candidate.created_at or utcnow(), candidate.id))
    return history


def _validate_retry_source(source: TaskRow, mode: str):
    if source.status not in {"failed", "rejected"}:
        raise HTTPException(status_code=400, detail="Only failed or rejected tasks can be retried")
    if mode not in {"run_now", "edit_first"}:
        raise HTTPException(status_code=400, detail="mode must be run_now|edit_first")
    if mode == "run_now" and not source.skill_name:
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
    _add_log(db, row.id, "created", row.description)
    _add_log(db, row.id, "retried_from", f"task={source.id}")

    if mode == "run_now":
        row.status = "running"
        row.started_at = utcnow()
        _add_log(db, row.id, "started", f"skill={row.skill_name}")
        return row, (row.id, _load_full_persona(row.agent_id), row.skill_name)

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


@router.get("", response_model=list[TaskOut])
def list_tasks(
    status: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    agent_group: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    only_anomalies: bool = Query(False),
    db: Session = Depends(get_db),
):
    q = db.query(TaskRow)
    if status:
        q = q.filter(TaskRow.status == status)
    if agent_id:
        q = q.filter(TaskRow.agent_id == agent_id)
    rows = q.order_by(TaskRow.created_at.desc(), TaskRow.id.desc()).all()

    if only_anomalies:
        rows = [r for r in rows if r.status in {"failed", "pending_approval", "running"}]
    if agent_group:
        rows = [r for r in rows if (r.agent_group or (r.agent.group if r.agent else "")) == agent_group]
    if project_id:
        rows = [r for r in rows if (r.project_id or project_for_group(r.agent_group or (r.agent.group if r.agent else ""))) == project_id]

    return [_task_to_out(r) for r in rows]


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_out(row)


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
        project_id=task_metadata_for_agent(agent.group)[0],
        agent_group=task_metadata_for_agent(agent.group)[1],
        skill_name=resolved_skill_name,
        context_files=json.dumps(body.context_files) if body.context_files else None,
    )
    db.add(row)
    db.flush()
    _add_log(db, row.id, "created", body.description)
    db.commit()
    db.refresh(row)
    logger.info("Task #%d created: agent=%s, skill=%s, desc=%s",
                row.id, row.agent_id, row.skill_name, row.description[:60])
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
        raise HTTPException(status_code=404, detail="Task not found")
    if row.status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot run task in '{row.status}' status")

    # Determine skill
    effective_skill = skill or row.skill_name
    if not effective_skill:
        suggestion = suggest_task_execution(
            db=db,
            description=row.description,
            preferred_agent_id=row.agent_id,
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
    persona = _load_full_persona(row.agent_id)

    # Mark as running
    row.status = "running"
    row.skill_name = effective_skill
    row.started_at = utcnow()
    _add_log(db, row.id, "started", f"skill={effective_skill}")
    db.commit()
    db.refresh(row)

    # Dispatch to background thread
    from server.services.task_runner import dispatch
    dispatch(task_id=row.id, agent_persona=persona, skill_name=effective_skill)

    return _task_to_out(row)  # returns status=running immediately


@router.post("/{task_id}/retry", response_model=TaskOut)
def retry_task(
    task_id: int,
    mode: str = Query("run_now", description="Retry mode: run_now | edit_first"),
    db: Session = Depends(get_db),
):
    source = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Task not found")
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
    by_id = {row.id: row for row in rows}
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
        raise HTTPException(status_code=404, detail="Task not found")
    return [_task_to_history_out(item) for item in _retry_history_for_task(task_id, db)]


@router.get("/{task_id}/logs", response_model=list[TaskLogOut])
def get_task_logs(task_id: int, db: Session = Depends(get_db)):
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return db.query(TaskLogRow).filter(TaskLogRow.task_id == task_id).order_by(TaskLogRow.created_at).all()
