"""Deployment event log and local deploy reset APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import ReleaseTaskOut
from server.services.releases.deployment_event_schemas import (
    DeploymentEventsPageOut,
    ReleaseTaskResetRunningRequest,
)
from server.services.releases.deployment_events import list_deployment_events
from server.services.releases.task_detail import get_release_task
from server.services.releases.release_task_reset import (
    reset_release_task_running_deployment,
)

router = APIRouter(prefix="/api/releases", tags=["release-deployment-events"])


@router.get("/tasks/{task_id}", response_model=ReleaseTaskOut)
def get_release_task_endpoint(task_id: int, db: Session = Depends(get_db)):
    try:
        return get_release_task(db, task_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get(
    "/deployments/{deployment_id}/events", response_model=DeploymentEventsPageOut
)
def list_deployment_events_endpoint(
    deployment_id: int,
    after_sequence: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    try:
        page = list_deployment_events(
            db,
            deployment_record_id=deployment_id,
            after_sequence=after_sequence,
            limit=limit,
        )
        return DeploymentEventsPageOut(
            items=page.items,
            next_sequence=page.next_sequence,
            has_more=page.has_more,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/reset-running", response_model=ReleaseTaskOut)
def reset_release_task_running_endpoint(
    task_id: int,
    body: ReleaseTaskResetRunningRequest,
    db: Session = Depends(get_db),
):
    try:
        return reset_release_task_running_deployment(db, task_id, body)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
