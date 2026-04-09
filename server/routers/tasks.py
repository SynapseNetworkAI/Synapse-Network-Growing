"""Tasks API router."""
import json
import logging
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
    db: Session = Depends(get_db),
):
    q = db.query(TaskRow)
    if status:
        q = q.filter(TaskRow.status == status)
    if agent_id:
        q = q.filter(TaskRow.agent_id == agent_id)
    return q.order_by(TaskRow.created_at.desc()).all()


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return row


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
    return row


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

    return row  # returns status=running immediately


@router.get("/{task_id}/logs", response_model=list[TaskLogOut])
def get_task_logs(task_id: int, db: Session = Depends(get_db)):
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return db.query(TaskLogRow).filter(TaskLogRow.task_id == task_id).order_by(TaskLogRow.created_at).all()
