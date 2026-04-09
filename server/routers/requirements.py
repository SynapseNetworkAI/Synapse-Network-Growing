"""Requirements and workflow orchestration API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from server.database import RequirementRow, get_db
from server.schemas import (
    RequirementCreate,
    RequirementDependencyUpdate,
    RequirementDetailOut,
    RequirementOut,
    RequirementRevisionRequest,
)
from server.services.workflow_orchestrator import (
    build_requirement_detail,
    create_requirement,
    plan_requirement,
    revise_requirement,
    start_requirement,
    update_requirement_dependencies,
)

router = APIRouter(prefix="/api/requirements", tags=["requirements"])


@router.get("", response_model=list[RequirementOut])
def list_requirements(
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(RequirementRow)
    if status:
        query = query.filter(RequirementRow.status == status)
    rows = query.order_by(RequirementRow.created_at.desc(), RequirementRow.id.desc()).all()
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