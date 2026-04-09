"""Approvals API router."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import Optional

from server.database import get_db, ApprovalRow, TaskRow, TaskLogRow, utcnow
from server.schemas import ApprovalOut, ApprovalDecide, ApprovalBulkDecide

logger = logging.getLogger("ops-dashboard.approvals")
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


def _validate_approval_action(action: str):
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")


def _apply_approval_decision(approval: ApprovalRow, action: str, comment: str, reviewer: str, db: Session):
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail=f"Approval already decided: {approval.status}")

    approval.status = "approved" if action == "approve" else "rejected"
    approval.reviewer = reviewer
    approval.comment = comment
    approval.decided_at = utcnow()

    task = db.query(TaskRow).filter(TaskRow.id == approval.task_id).first()
    if action == "approve":
        task.status = "completed"
        task.completed_at = utcnow()
        db.add(TaskLogRow(task_id=task.id, event_type="approved", detail=comment))
        db.add(TaskLogRow(task_id=task.id, event_type="completed"))
    else:
        task.status = "rejected"
        db.add(TaskLogRow(task_id=task.id, event_type="rejected", detail=comment))


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
def decide_approval(approval_id: int, body: ApprovalDecide, db: Session = Depends(get_db)):
    _validate_approval_action(body.action)

    approval = db.query(ApprovalRow).filter(ApprovalRow.id == approval_id).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    _apply_approval_decision(approval, body.action, body.comment, body.reviewer, db)

    db.commit()
    db.refresh(approval)
    from server.services.workflow_orchestrator import sync_workflow_for_task

    sync_workflow_for_task(approval.task_id)
    logger.info("Approval #%d %s by %s (task #%d)", approval.id, approval.status, approval.reviewer, approval.task_id)
    # Eagerly load task for response
    _ = approval.task
    return approval


@router.post("/bulk-decide", response_model=list[ApprovalOut])
def bulk_decide_approvals(body: ApprovalBulkDecide, db: Session = Depends(get_db)):
    _validate_approval_action(body.action)
    if not body.approval_ids:
        raise HTTPException(status_code=400, detail="approval_ids is required")

    unique_ids = list(dict.fromkeys(body.approval_ids))
    approvals = db.query(ApprovalRow).options(joinedload(ApprovalRow.task)).filter(ApprovalRow.id.in_(unique_ids)).all()
    by_id = {approval.id: approval for approval in approvals}
    missing_ids = [approval_id for approval_id in unique_ids if approval_id not in by_id]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"Approvals not found: {missing_ids}")

    ordered_approvals = [by_id[approval_id] for approval_id in unique_ids]
    for approval in ordered_approvals:
        _apply_approval_decision(approval, body.action, body.comment, body.reviewer, db)

    db.commit()
    for approval in ordered_approvals:
        db.refresh(approval)
        _ = approval.task

    from server.services.workflow_orchestrator import sync_workflow_for_task

    for approval in ordered_approvals:
        sync_workflow_for_task(approval.task_id)

    logger.info("Bulk approval decision: action=%s reviewer=%s count=%d", body.action, body.reviewer, len(ordered_approvals))
    return ordered_approvals
