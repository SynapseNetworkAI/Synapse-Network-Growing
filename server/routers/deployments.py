"""Deployment governance API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from server import config
from server.database import get_db
from server.schemas import DeploymentOverviewOut, DeploymentRecordOut, DeploymentReportRequest, EnvironmentStatusOut
from server.services.deployment_governance import (
    build_deployment_overview,
    build_project_environment_statuses,
    report_deployment_result,
)
from server.services.project_policy import get_project_policy

router = APIRouter(prefix="/api/deployments", tags=["deployments"])


@router.get("/overview", response_model=DeploymentOverviewOut)
def get_deployment_overview_endpoint(db: Session = Depends(get_db)):
    return build_deployment_overview(db)


@router.get("/project-policies/{policy_id}/environment-status", response_model=list[EnvironmentStatusOut])
def get_project_environment_status_endpoint(policy_id: int, db: Session = Depends(get_db)):
    policy = get_project_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Project policy not found.")
    return build_project_environment_statuses(db, policy)


@router.post("/{record_id}/report", response_model=DeploymentRecordOut)
def report_deployment_status_endpoint(
    record_id: int,
    body: DeploymentReportRequest,
    db: Session = Depends(get_db),
    x_deploy_token: str | None = Header(default=None),
):
    required = config.DEPLOY_WEBHOOK_TOKEN.strip()
    if required and x_deploy_token != required:
        raise HTTPException(status_code=401, detail="Invalid deploy webhook token.")
    try:
        return report_deployment_result(
            db,
            record_id,
            status=body.status,
            external_run_id=body.external_run_id,
            external_url=body.external_url,
            health_status=body.health_status,
            branch_name=body.branch_name,
            commit_sha=body.commit_sha,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
