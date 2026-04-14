"""Formal project center API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import ProjectCreate, ProjectOut, ProjectPatch, ProjectPolicyOut, ProjectPolicyPatch, ProjectWithPolicyOut
from server.services.projects.policy import project_policy_to_dict
from server.services.projects.project_center import (
    archive_project,
    create_project,
    delete_project,
    get_project,
    get_project_policy_for_project,
    list_projects,
    project_to_dict,
    project_with_policy_to_dict,
    update_project,
    update_project_policy_for_project,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects_endpoint(
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    return [ProjectOut(**project_to_dict(row)) for row in list_projects(db, status=status)]


@router.post("", response_model=ProjectWithPolicyOut, status_code=201)
def create_project_endpoint(body: ProjectCreate, db: Session = Depends(get_db)):
    if body.status not in {"active", "archived"}:
        raise HTTPException(status_code=400, detail="status must be active|archived")
    try:
        row = create_project(
            db,
            project_key=body.project_key,
            display_name=body.display_name,
            root_path=body.root_path,
            repo_full_name=body.repo_full_name,
            default_branch=body.default_branch,
            deploy_repo_full_name=body.deploy_repo_full_name,
            deploy_strategy=body.deploy_strategy,
            deploy_trigger_enabled=body.deploy_trigger_enabled,
            staging_host_label=body.staging_host_label,
            production_host_label=body.production_host_label,
            staging_workflow_file=body.staging_workflow_file,
            production_workflow_file=body.production_workflow_file,
            notes=body.notes,
        )
        if body.status == "archived":
            row = archive_project(db, row)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectWithPolicyOut(**project_with_policy_to_dict(row))


@router.get("/{project_id}", response_model=ProjectWithPolicyOut)
def get_project_endpoint(project_id: int, db: Session = Depends(get_db)):
    row = get_project(db, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return ProjectWithPolicyOut(**project_with_policy_to_dict(row))


@router.patch("/{project_id}", response_model=ProjectWithPolicyOut)
def patch_project_endpoint(project_id: int, body: ProjectPatch, db: Session = Depends(get_db)):
    row = get_project(db, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    if body.status is not None and body.status not in {"active", "archived"}:
        raise HTTPException(status_code=400, detail="status must be active|archived")
    try:
        updated = update_project(
            db,
            row,
            project_key=body.project_key,
            display_name=body.display_name,
            root_path=body.root_path,
            status=body.status,
            repo_full_name=body.repo_full_name,
            default_branch=body.default_branch,
            deploy_repo_full_name=body.deploy_repo_full_name,
            deploy_strategy=body.deploy_strategy,
            deploy_trigger_enabled=body.deploy_trigger_enabled,
            staging_host_label=body.staging_host_label,
            production_host_label=body.production_host_label,
            staging_workflow_file=body.staging_workflow_file,
            production_workflow_file=body.production_workflow_file,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectWithPolicyOut(**project_with_policy_to_dict(updated))


@router.delete("/{project_id}", response_model=ProjectWithPolicyOut)
def delete_project_endpoint(project_id: int, db: Session = Depends(get_db)):
    row = get_project(db, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    try:
        delete_project(db, row)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ProjectWithPolicyOut(**project_with_policy_to_dict(row))


@router.get("/{project_id}/policy", response_model=ProjectPolicyOut)
def get_project_policy_endpoint(project_id: int, db: Session = Depends(get_db)):
    row = get_project_policy_for_project(db, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project policy not found.")
    return ProjectPolicyOut(**project_policy_to_dict(row))


@router.patch("/{project_id}/policy", response_model=ProjectPolicyOut)
def patch_project_policy_endpoint(project_id: int, body: ProjectPolicyPatch, db: Session = Depends(get_db)):
    try:
        row = update_project_policy_for_project(
            db,
            project_id,
            display_name=body.display_name,
            root_path=body.root_path,
            status=body.status,
            allowed_write_globs=body.allowed_write_globs,
            forbidden_globs=body.forbidden_globs,
            required_checks=body.required_checks,
            release_mode=body.release_mode,
            requires_manual_approval=body.requires_manual_approval,
            autonomy_mode=body.autonomy_mode,
            allow_rebalance=body.allow_rebalance,
            allow_preemption=body.allow_preemption,
            capability_matrix=body.capability_matrix.model_dump() if body.capability_matrix is not None else None,
            interrupt_policy=body.interrupt_policy.model_dump() if body.interrupt_policy is not None else None,
            scheduler_weight=body.scheduler_weight,
            max_parallel_requirements=body.max_parallel_requirements,
            portfolio_budget_points=body.portfolio_budget_points,
            deploy_repo_full_name=body.deploy_repo_full_name,
            deploy_strategy=body.deploy_strategy,
            deploy_trigger_enabled=body.deploy_trigger_enabled,
            staging_host_label=body.staging_host_label,
            production_host_label=body.production_host_label,
            staging_workflow_file=body.staging_workflow_file,
            production_workflow_file=body.production_workflow_file,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectPolicyOut(**project_policy_to_dict(row))
