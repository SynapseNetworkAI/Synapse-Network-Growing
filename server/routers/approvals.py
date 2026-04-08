"""Approvals API router."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import Optional

from server.database import get_db, ApprovalRow, TaskRow, TaskLogRow, utcnow
from server.schemas import ApprovalOut, ApprovalDecide

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalOut])
def list_approvals(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(ApprovalRow).options(joinedload(ApprovalRow.task))
    if status:
        q = q.filter(ApprovalRow.status == status)
    return q.order_by(ApprovalRow.created_at.desc()).all()


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
def decide_approval(approval_id: int, body: ApprovalDecide, db: Session = Depends(get_db)):
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    approval = db.query(ApprovalRow).filter(ApprovalRow.id == approval_id).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail=f"Approval already decided: {approval.status}")

    approval.status = "approved" if body.action == "approve" else "rejected"
    approval.reviewer = body.reviewer
    approval.comment = body.comment
    approval.decided_at = utcnow()

    # Update the associated task
    task = db.query(TaskRow).filter(TaskRow.id == approval.task_id).first()
    if body.action == "approve":
        task.status = "completed"
        task.completed_at = utcnow()
        db.add(TaskLogRow(task_id=task.id, event_type="approved", detail=body.comment))
        db.add(TaskLogRow(task_id=task.id, event_type="completed"))
    else:
        task.status = "rejected"
        db.add(TaskLogRow(task_id=task.id, event_type="rejected", detail=body.comment))

    db.commit()
    db.refresh(approval)
    # Eagerly load task for response
    _ = approval.task
    return approval
