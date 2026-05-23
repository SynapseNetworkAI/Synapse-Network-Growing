"""Force-reset helpers for stuck local deployment attempts."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.database import DeploymentRecordRow, ReleaseTaskRow, utcnow
from server.schemas import ReleaseTaskOut, ReleaseTaskPrGateOut
from server.services.releases.deployment_events import append_deployment_event
from server.services.releases.tasks import _clean, _merge_metadata, _release_task_to_out


def reset_release_task_running_deployment(
    db: Session, task_id: int, body: Any
) -> ReleaseTaskOut:
    row = db.get(ReleaseTaskRow, int(task_id))
    if row is None:
        raise ValueError("Release task not found.")
    if _clean(getattr(body, "confirm_phrase", None)) != "RESET_LOCAL_DEPLOY":
        raise ValueError("Reset requires confirm_phrase=RESET_LOCAL_DEPLOY.")
    current_status = _clean(row.status).lower() or "requested"
    if current_status in {"completed", "cancelled"}:
        raise ValueError("Completed or cancelled release task cannot be reset.")
    deployment_id = (
        int(row.deployment_record_id) if row.deployment_record_id is not None else None
    )
    if deployment_id is None:
        raise ValueError("Release task has no deployment record to reset.")
    deployment = db.get(DeploymentRecordRow, deployment_id)
    if deployment is None:
        raise ValueError("Deployment record not found.")
    operator = _clean(getattr(body, "operator", "operator")) or "operator"
    reason = (
        _clean(getattr(body, "reason", None))
        or "Operator force reset local deploy attempt."
    )
    deployment.status = "failed"
    deployment.health_status = "failed"
    deployment.notes = reason
    deployment.finished_at = utcnow()
    _merge_metadata(
        deployment,
        {
            "localDeployForceReset": True,
            "localDeployForceResetAt": utcnow().isoformat(),
            "localDeployForceResetBy": operator,
            "localDeployForceResetReason": reason,
            "resetReleaseTaskId": int(row.id),
        },
    )
    append_deployment_event(
        db,
        deployment_record_id=deployment_id,
        event_type="local_deploy_force_reset",
        step_key="reset",
        message=f"Local deploy force reset by {operator}: {reason}",
    )
    row.status = "requested"
    row.deployment_record_id = None
    row.operator = None
    row.note = reason
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return _release_task_to_out(
        row,
        pr_gate=ReleaseTaskPrGateOut(
            branch_exists=True,
            checks_status="unknown",
            blocked_reason="Local deploy reset; create a new deployment attempt.",
        ),
    )
