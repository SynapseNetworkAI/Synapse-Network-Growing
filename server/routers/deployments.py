"""Deployment governance API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from server import config
from server.database import DeploymentRecordRow, get_db
from server.schemas import DeploymentOverviewOut, DeploymentRecordOut, DeploymentReportRequest, EnvironmentStatusOut
from server.schemas_deployment_events import DeploymentEventOut
from server.services.delivery.deployment_events import list_deployment_events, record_deployment_event
from server.services.delivery.deployment_governance import (
    build_deployment_overview,
    build_project_environment_statuses,
    report_deployment_result,
)
from server.services.projects.policy import get_project_policy

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


@router.get("/{record_id}/events", response_model=list[DeploymentEventOut])
def list_deployment_events_endpoint(record_id: int, db: Session = Depends(get_db)):
    return list_deployment_events(db, record_id)


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
        row = db.get(DeploymentRecordRow, int(record_id))
        previous_status = str(getattr(row, "status", "") or "requested") if row else None
        result = report_deployment_result(
            db,
            record_id,
            status=body.status,
            external_run_id=body.external_run_id,
            external_url=body.external_url,
            health_status=body.health_status,
            branch_name=body.branch_name,
            commit_sha=body.commit_sha,
            notes=body.notes,
            metadata=body.metadata,
        )
        row = db.get(DeploymentRecordRow, int(record_id))
        if row is not None:
            record_deployment_event(
                db,
                row,
                event_type="deployment_reported",
                actor="staging_deploy_runner",
                status_from=previous_status,
                status_to=str(row.status or ""),
                summary=row.notes or f"Deployment reported {row.status}.",
                payload={
                    "external_run_id": row.external_run_id,
                    "external_url": row.external_url,
                    "health_status": row.health_status,
                },
            )
            if row.environment == "production":
                record_deployment_event(
                    db,
                    row,
                    event_type="production_reported",
                    actor="production_deploy_runner",
                    status_from=previous_status,
                    status_to=str(row.status or ""),
                    summary=row.notes or f"Production deployment reported {row.status}.",
                    payload={
                        "external_run_id": row.external_run_id,
                        "external_url": row.external_url,
                        "health_status": row.health_status,
                    },
                )
            db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
