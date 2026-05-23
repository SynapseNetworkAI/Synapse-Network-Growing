"""Release-task deployment event helpers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from server.database import DeploymentRecordRow, ReleaseTaskRow
from server.services.delivery.deployment_events import record_deployment_event


def record_requested(
    db: Session,
    row: ReleaseTaskRow,
    record: DeploymentRecordRow,
    *,
    actor: str,
    workflow_file: str,
) -> None:
    record_deployment_event(
        db,
        record,
        event_type="deployment_requested",
        actor=actor,
        status_to="requested",
        summary="Release task created a staging DeploymentRecord.",
        payload={"release_task_id": int(row.id), "workflow_file": workflow_file},
    )


def record_dispatched(
    db: Session,
    record: DeploymentRecordRow,
    *,
    actor: str,
    inputs: dict[str, str],
) -> None:
    safe_inputs = {
        key: value for key, value in inputs.items() if key != "callback_token"
    }
    record_deployment_event(
        db,
        record,
        event_type="deployment_dispatched",
        actor=actor,
        status_from="requested",
        status_to=str(record.status or "requested"),
        summary="Staging deployment workflow dispatched.",
        payload={"external_url": record.external_url, "inputs": safe_inputs},
    )


def record_dispatch_failed(
    db: Session,
    row: ReleaseTaskRow,
    record: DeploymentRecordRow,
    *,
    actor: str,
    workflow_file: str,
    exc: Exception,
) -> None:
    record_deployment_event(
        db,
        record,
        event_type="deployment_dispatch_failed",
        actor=actor,
        status_from="requested",
        status_to="failed",
        summary=str(exc)[:1000],
        payload={"release_task_id": int(row.id), "workflow_file": workflow_file},
    )
