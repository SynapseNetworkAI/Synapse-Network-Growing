"""Agent-first requirements API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import (
    AgentFirstRequirementDetailOut,
    AgentFirstRequirementOut,
    RequirementCreate,
    RequirementPatch,
    RequirementRevisionRequest,
    WorkflowReadinessOut,
)
from server.services.requirements.service import (
    build_requirement_detail,
    cancel_requirement,
    create_requirement,
    delete_requirement,
    generate_requirement_workflow_assets,
    list_requirements,
    regenerate_requirement_assets,
    regenerate_requirement_plan,
    requirement_workflow_readiness,
    requirement_attachment_file_path,
    revise_requirement,
    start_requirement_workflow,
    submit_requirement,
    update_requirement,
)


router = APIRouter(prefix="/api/requirements", tags=["requirements"])


class RequirementWorkflowStartRequest(BaseModel):
    workflow_key: str | None = None
    run_immediately: bool = True
    triggered_by: str = "operator"


@router.get("", response_model=list[AgentFirstRequirementOut])
def list_requirements_endpoint(
    status: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
):
    return list_requirements(db, status=status, search=search)


@router.post("", response_model=AgentFirstRequirementDetailOut, status_code=201)
def create_requirement_endpoint(body: RequirementCreate, db: Session = Depends(get_db)):
    if body.priority not in {"low", "normal", "high"}:
        raise HTTPException(status_code=400, detail="priority must be low|normal|high")
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="title is required")
    if not body.description_markdown.strip():
        raise HTTPException(status_code=400, detail="description_markdown is required")
    if body.project_id is None:
        raise HTTPException(status_code=400, detail="project_id is required")
    return create_requirement(db, body)


@router.get("/{requirement_id}", response_model=AgentFirstRequirementDetailOut)
def get_requirement_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return build_requirement_detail(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{requirement_id}/attachments/{attachment_id}")
def get_requirement_attachment_endpoint(requirement_id: int, attachment_id: int, db: Session = Depends(get_db)):
    try:
        row, file_path = requirement_attachment_file_path(db, requirement_id, attachment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    media_type = str(getattr(row, "content_type", "") or "").strip() or "application/octet-stream"
    return FileResponse(path=file_path, media_type=media_type, filename=str(row.file_name or file_path.name))


@router.patch("/{requirement_id}", response_model=AgentFirstRequirementDetailOut)
def patch_requirement_endpoint(requirement_id: int, body: RequirementPatch, db: Session = Depends(get_db)):
    try:
        return update_requirement(db, requirement_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/submit", response_model=AgentFirstRequirementDetailOut)
def submit_requirement_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return submit_requirement(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/revise", response_model=AgentFirstRequirementDetailOut)
def revise_requirement_endpoint(requirement_id: int, body: RequirementRevisionRequest, db: Session = Depends(get_db)):
    try:
        return revise_requirement(db, requirement_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/cancel", response_model=AgentFirstRequirementDetailOut)
def cancel_requirement_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return cancel_requirement(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/delete", response_model=AgentFirstRequirementDetailOut)
def delete_requirement_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return delete_requirement(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/plan", response_model=AgentFirstRequirementDetailOut)
def plan_requirement_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return regenerate_requirement_plan(db=db, requirement_id=requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/regenerate-assets", response_model=AgentFirstRequirementDetailOut)
def regenerate_requirement_assets_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return regenerate_requirement_assets(db=db, requirement_id=requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{requirement_id}/workflow-readiness", response_model=WorkflowReadinessOut)
def get_requirement_workflow_readiness_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return requirement_workflow_readiness(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{requirement_id}/workflow/generate", response_model=AgentFirstRequirementDetailOut)
def generate_requirement_workflow_assets_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return generate_requirement_workflow_assets(db=db, requirement_id=requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/workflow/start", status_code=201)
def start_requirement_workflow_endpoint(
    requirement_id: int,
    body: RequirementWorkflowStartRequest | None = None,
    db: Session = Depends(get_db),
):
    request_body = body or RequirementWorkflowStartRequest()
    try:
        run_detail = start_requirement_workflow(
            db,
            requirement_id,
            workflow_key=request_body.workflow_key,
            triggered_by=request_body.triggered_by,
            run_immediately=request_body.run_immediately,
        )
        db.commit()
        return run_detail
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/start")
def removed_start_endpoint(requirement_id: int):
    raise HTTPException(status_code=410, detail="Legacy start endpoint was removed. Submit the requirement and inspect the declarative run under /api/workflows/runs.")


@router.post("/{requirement_id}/pause")
def removed_pause_endpoint(requirement_id: int):
    raise HTTPException(status_code=410, detail="Legacy pause endpoint was removed. Use workflow human gates or operator decisions instead.")


@router.post("/{requirement_id}/publish")
def removed_publish_endpoint(requirement_id: int):
    raise HTTPException(status_code=410, detail="Legacy publish endpoint was removed. Use /api/releases for release actions.")
