"""Project policy registry API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import ProjectPolicyCreate, ProjectPolicyOut, ProjectPolicyPatch
from server.services.project_policy import (
    create_project_policy,
    delete_project_policy,
    get_project_policy,
    list_project_policies,
    project_policy_to_dict,
    update_project_policy,
)

router = APIRouter(prefix="/api/project-policies", tags=["project-policies"])


@router.get("", response_model=list[ProjectPolicyOut])
def list_project_policies_endpoint(db: Session = Depends(get_db)):
    return [ProjectPolicyOut(**project_policy_to_dict(row)) for row in list_project_policies(db)]


@router.get("/{policy_id}", response_model=ProjectPolicyOut)
def get_project_policy_endpoint(policy_id: int, db: Session = Depends(get_db)):
    row = get_project_policy(db, policy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project policy not found.")
    return ProjectPolicyOut(**project_policy_to_dict(row))


@router.post("", response_model=ProjectPolicyOut, status_code=201)
def create_project_policy_endpoint(body: ProjectPolicyCreate, db: Session = Depends(get_db)):
    if body.status not in {"active", "disabled"}:
        raise HTTPException(status_code=400, detail="status must be active|disabled")
    if body.release_mode not in {"disabled", "manual", "auto"}:
        raise HTTPException(status_code=400, detail="release_mode must be disabled|manual|auto")
    if body.autonomy_mode not in {"observe", "recommend", "execute_with_approval", "execute_autonomously"}:
        raise HTTPException(status_code=400, detail="autonomy_mode must be observe|recommend|execute_with_approval|execute_autonomously")
    if not body.project_key.strip() or not body.display_name.strip() or not body.root_path.strip():
        raise HTTPException(status_code=400, detail="project_key, display_name, and root_path are required")
    try:
        row = create_project_policy(
            db,
            project_key=body.project_key,
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
            capability_matrix=body.capability_matrix.model_dump(),
            interrupt_policy=body.interrupt_policy.model_dump(),
            scheduler_weight=body.scheduler_weight,
            max_parallel_requirements=body.max_parallel_requirements,
            portfolio_budget_points=body.portfolio_budget_points,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectPolicyOut(**project_policy_to_dict(row))


@router.patch("/{policy_id}", response_model=ProjectPolicyOut)
def update_project_policy_endpoint(policy_id: int, body: ProjectPolicyPatch, db: Session = Depends(get_db)):
    row = get_project_policy(db, policy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project policy not found.")
    if body.status is not None and body.status not in {"active", "disabled"}:
        raise HTTPException(status_code=400, detail="status must be active|disabled")
    if body.release_mode is not None and body.release_mode not in {"disabled", "manual", "auto"}:
        raise HTTPException(status_code=400, detail="release_mode must be disabled|manual|auto")
    if body.autonomy_mode is not None and body.autonomy_mode not in {"observe", "recommend", "execute_with_approval", "execute_autonomously"}:
        raise HTTPException(status_code=400, detail="autonomy_mode must be observe|recommend|execute_with_approval|execute_autonomously")
    try:
        updated = update_project_policy(
            db,
            row,
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
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectPolicyOut(**project_policy_to_dict(updated))


@router.delete("/{policy_id}", status_code=204)
def delete_project_policy_endpoint(policy_id: int, db: Session = Depends(get_db)):
    row = get_project_policy(db, policy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project policy not found.")
    try:
        delete_project_policy(db, row)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
