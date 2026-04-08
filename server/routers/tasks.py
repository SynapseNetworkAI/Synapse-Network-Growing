"""Tasks API router."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from server.database import get_db, TaskRow, AgentRow, TaskLogRow, ApprovalRow, utcnow
from server.schemas import TaskCreate, TaskOut, TaskLogOut

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

VALID_STATUSES = {"pending", "running", "pending_approval", "approved", "rejected", "completed", "failed"}


def _add_log(db: Session, task_id: int, event_type: str, detail: str = None):
    db.add(TaskLogRow(task_id=task_id, event_type=event_type, detail=detail))


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
    )
    db.add(row)
    db.flush()
    _add_log(db, row.id, "created", body.description)
    db.commit()
    db.refresh(row)
    return row


@router.post("/{task_id}/run", response_model=TaskOut)
def run_task(task_id: int, db: Session = Depends(get_db)):
    """Transition task to 'running'. In a real setup this would trigger CrewAI async."""
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    if row.status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot run task in '{row.status}' status")

    row.status = "running"
    row.started_at = utcnow()
    _add_log(db, row.id, "started")

    # Simulate: if requires_approval, move to pending_approval immediately
    # In production this would happen after CrewAI completes
    if row.requires_approval:
        row.status = "pending_approval"
        row.output_content = f"[模拟产出] {row.description}"
        _add_log(db, row.id, "output", row.output_content)
        _add_log(db, row.id, "approval_requested")
        approval = ApprovalRow(task_id=row.id)
        db.add(approval)
    else:
        # Simulate immediate completion for MVP
        row.status = "completed"
        row.output_content = f"[模拟产出] {row.description}"
        row.completed_at = utcnow()
        _add_log(db, row.id, "output", row.output_content)
        _add_log(db, row.id, "completed")

    db.commit()
    db.refresh(row)
    return row


@router.get("/{task_id}/logs", response_model=list[TaskLogOut])
def get_task_logs(task_id: int, db: Session = Depends(get_db)):
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return db.query(TaskLogRow).filter(TaskLogRow.task_id == task_id).order_by(TaskLogRow.created_at).all()
