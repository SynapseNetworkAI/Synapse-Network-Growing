"""Read-only live release gate projection."""

from __future__ import annotations

from sqlalchemy.orm import Session

from server.database import ReleaseTaskRow
from server.schemas import ReleaseTaskPrGateOut
from server.services.releases.production_tasks import release_task_production_gate
from server.services.releases.tasks import (
    _clean,
    _policy_for_project,
    _release_task_deploy_repo,
    _release_task_pr_gate_for,
)


def release_task_gate_status(db: Session, task_id: int) -> ReleaseTaskPrGateOut:
    """Compute the live gate status without mutating release task rows."""

    row = db.get(ReleaseTaskRow, int(task_id))
    if row is None:
        raise ValueError("Release task not found.")
    environment = _clean(row.environment).lower()
    if environment not in {"staging", "production"}:
        return ReleaseTaskPrGateOut(
            blocked_reason="Gate status is only available for staging or production release tasks."
        )
    try:
        project_key = _clean(row.project_key)
        policy = _policy_for_project(db, project_key)
        repo_full_name = _release_task_deploy_repo(policy, project_key)
        if environment == "production":
            return release_task_production_gate(db, row, repo_full_name)
        return _release_task_pr_gate_for(row, repo_full_name)
    except ValueError as exc:
        return ReleaseTaskPrGateOut(blocked_reason=str(exc))
