"""Tasks API router."""
import json
import logging
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

import yaml

from server.database import get_db, TaskRow, AgentRow, TaskLogRow, ApprovalRow, utcnow
from server.schemas import TaskCreate, TaskOut, TaskLogOut
from server.config import PROJECT_ROOT

logger = logging.getLogger("ops-dashboard.tasks")
router = APIRouter(prefix="/api/tasks", tags=["tasks"])

VALID_STATUSES = {"pending", "running", "pending_approval", "approved", "rejected", "completed", "failed"}


def _add_log(db: Session, task_id: int, event_type: str, detail: str = None):
    db.add(TaskLogRow(task_id=task_id, event_type=event_type, detail=detail))


@lru_cache(maxsize=1)
def _group_project_map() -> dict[str, str]:
    """Map agent group -> project repo name using org-structure.yaml."""
    org_path = PROJECT_ROOT / "server" / "org-structure.yaml"
    if not org_path.exists():
        return {}

    cfg = yaml.safe_load(org_path.read_text(encoding="utf-8")) or {}
    mapping: dict[str, str] = {}
    for domain in cfg.get("domains", []):
        project = domain.get("project", "")
        for team in domain.get("teams", []):
            mapping[team.get("id", "")] = project
    return mapping


def _task_to_out(row: TaskRow) -> TaskOut:
    agent_group = row.agent.group if row.agent else ""
    project_id = _group_project_map().get(agent_group, "")
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
    rows = q.order_by(TaskRow.created_at.desc()).all()

    if only_anomalies:
        rows = [r for r in rows if r.status in {"failed", "pending_approval", "running"}]
    if agent_group:
        rows = [r for r in rows if (r.agent.group if r.agent else "") == agent_group]
    if project_id:
        rows = [r for r in rows if _group_project_map().get(r.agent.group if r.agent else "", "") == project_id]

    return [_task_to_out(r) for r in rows]


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_out(row)


@router.post("", response_model=TaskOut, status_code=201)
def create_task(body: TaskCreate, db: Session = Depends(get_db)):
    # Validate agent exists
    agent = db.query(AgentRow).filter(AgentRow.id == body.agent_id).first()
    if not agent:
        raise HTTPException(status_code=400, detail=f"Agent '{body.agent_id}' not found. Sync agents first.")

    if body.priority not in ("low", "normal", "high"):
        raise HTTPException(status_code=400, detail="priority must be low|normal|high")

    row = TaskRow(
        description=body.description,
        agent_id=body.agent_id,
        requires_approval=body.requires_approval,
        priority=body.priority,
        skill_name=body.skill_name,
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
    if source.status not in {"failed", "rejected"}:
        raise HTTPException(status_code=400, detail="Only failed or rejected tasks can be retried")
    if mode not in {"run_now", "edit_first"}:
        raise HTTPException(status_code=400, detail="mode must be run_now|edit_first")

    row = TaskRow(
        description=source.description,
        agent_id=source.agent_id,
        status="pending",
        requires_approval=source.requires_approval,
        priority=source.priority,
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
        if not row.skill_name:
            raise HTTPException(status_code=400, detail="Cannot retry immediately without a skill")
        persona = _load_full_persona(row.agent_id)
        row.status = "running"
        row.started_at = utcnow()
        _add_log(db, row.id, "started", f"skill={row.skill_name}")
        db.commit()
        db.refresh(row)

        from server.services.task_runner import dispatch
        dispatch(task_id=row.id, agent_persona=persona, skill_name=row.skill_name)
        return _task_to_out(row)

    db.commit()
    db.refresh(row)
    return _task_to_out(row)


@router.get("/{task_id}/logs", response_model=list[TaskLogOut])
def get_task_logs(task_id: int, db: Session = Depends(get_db)):
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return db.query(TaskLogRow).filter(TaskLogRow.task_id == task_id).order_by(TaskLogRow.created_at).all()
