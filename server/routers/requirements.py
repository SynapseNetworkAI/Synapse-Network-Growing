"""Requirements and workflow orchestration API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from server.database import RequirementRow, get_db
from server.schemas import RequirementCreate, RequirementDetailOut, RequirementOut
from server.services.workflow_orchestrator import build_requirement_detail, create_requirement, plan_requirement, start_requirement

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