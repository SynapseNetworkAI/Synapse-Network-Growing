"""Requirements and workflow orchestration API."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from server.database import RequirementRow, get_db
from server.schemas import (
    RequirementCreate,
    RequirementDependencyUpdate,
    RequirementDetailOut,
    RequirementOut,
    RequirementPatch,
    RequirementRevisionRequest,
)
from server.services.workflow_orchestrator import (
    advance_requirement_queue,
    build_requirement_detail,
    close_requirement,
    create_requirement,
    patch_requirement,
    plan_requirement,
    revise_requirement,
    start_requirement,
    update_requirement_dependencies,
)

router = APIRouter(prefix="/api/requirements", tags=["requirements"])

_PRIORITY_SCORE = {"high": 30, "normal": 10, "low": 0}
_STATUS_PENALTY = {"done": -100, "blocked": -20, "needs_revision": -10}


def _requirement_score(row: RequirementRow) -> float:
    priority = _PRIORITY_SCORE.get(str(row.priority), 10)
    created = row.created_at or datetime.now(timezone.utc)
    age_days = (datetime.now(timezone.utc) - created.replace(tzinfo=timezone.utc if created.tzinfo is None else created.tzinfo)).total_seconds() / 86400
    aging_bonus = min(age_days * 2, 30)
    penalty = _STATUS_PENALTY.get(str(row.status), 0)
    blocker_penalty = int(row.blocked_by_count or 0) * 15
    return priority + aging_bonus + penalty - blocker_penalty


@router.get("", response_model=list[RequirementOut])
def list_requirements(
    status: str | None = Query(None),
    sort: str | None = Query(None, description="Sort mode: 'score' for priority+aging scoring, default is created_at desc"),
    db: Session = Depends(get_db),
):
    query = db.query(RequirementRow)
    if status:
        query = query.filter(RequirementRow.status == status)
    rows = query.all()
    if sort == "score":
        rows.sort(key=_requirement_score, reverse=True)
    else:
        rows.sort(key=lambda r: (r.created_at or datetime.min.replace(tzinfo=timezone.utc), r.id), reverse=True)
    return [RequirementOut.model_validate(row) for row in rows]


@router.post("", response_model=RequirementDetailOut, status_code=201)
def create_requirement_endpoint(body: RequirementCreate, db: Session = Depends(get_db)):
    if body.priority not in {"low", "normal", "high"}:
        raise HTTPException(status_code=400, detail="priority must be low|normal|high")
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="title is required")
    if not body.description_markdown.strip():
        raise HTTPException(status_code=400, detail="description_markdown is required")
    return create_requirement(db, body)


@router.get("/{requirement_id}", response_model=RequirementDetailOut)
def get_requirement(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return build_requirement_detail(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{requirement_id}", response_model=RequirementDetailOut)
def patch_requirement_endpoint(requirement_id: int, body: RequirementPatch, db: Session = Depends(get_db)):
    try:
        return patch_requirement(db, requirement_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/close", response_model=RequirementDetailOut)
def close_requirement_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return close_requirement(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/plan", response_model=RequirementDetailOut)
def plan_requirement_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return plan_requirement(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/start", response_model=RequirementDetailOut)
def start_requirement_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return start_requirement(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/queue/advance")
def queue_advance_endpoint(db: Session = Depends(get_db)):
    """Advance the requirement queue: start the next ready requirement if nothing is in_progress."""
    return advance_requirement_queue(db)


@router.put("/{requirement_id}/dependencies", response_model=RequirementDetailOut)
def update_requirement_dependencies_endpoint(
    requirement_id: int,
    body: RequirementDependencyUpdate,
    db: Session = Depends(get_db),
):
    try:
        return update_requirement_dependencies(db, requirement_id, body.depends_on_requirement_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/revise", response_model=RequirementDetailOut)
def revise_requirement_endpoint(
    requirement_id: int,
    body: RequirementRevisionRequest,
    db: Session = Depends(get_db),
):
    if not body.description_markdown.strip():
        raise HTTPException(status_code=400, detail="description_markdown is required")
    if body.title is not None and not body.title.strip():
        raise HTTPException(status_code=400, detail="title cannot be blank")
    try:
        return revise_requirement(db, requirement_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc