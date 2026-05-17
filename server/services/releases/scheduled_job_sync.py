"""Local-runner reconciliation for scheduled Cloud Run Job releases."""

from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from server.database import DeploymentRecordRow, utcnow
from server.database_scheduled_jobs import ScheduledJobReleaseTaskRow
from server.services.releases.scheduled_job_catalog import SCHEDULED_JOBS_TRIGGER_SOURCE
from server.services.releases.scheduled_job_schemas import ScheduledCloudRunJobsSyncOut
from server.services.releases.scheduled_jobs import _clean, _json_load


def sync_scheduled_job_publish_statuses(
    db: Session, *, max_records: int = 50
) -> ScheduledCloudRunJobsSyncOut:
    bounded_limit = max(1, min(int(max_records or 50), 50))
    rows = (
        db.query(DeploymentRecordRow)
        .filter(
            or_(
                DeploymentRecordRow.trigger_source == SCHEDULED_JOBS_TRIGGER_SOURCE,
                and_(
                    DeploymentRecordRow.trigger_source == "local_deploy_runner",
                    DeploymentRecordRow.action == "publish_cloud_run_jobs",
                ),
            )
        )
        .order_by(DeploymentRecordRow.id.asc())
        .limit(bounded_limit)
        .all()
    )
    result = ScheduledCloudRunJobsSyncOut(processed_count=len(rows))
    for record in rows:
        state = _record_state(record)
        _sync_parent_task(db, record, state)
        if state == "succeeded":
            result.succeeded_ids.append(int(record.id))
        elif state == "failed":
            result.failed_ids.append(int(record.id))
        elif state == "running":
            result.running_ids.append(int(record.id))
        else:
            result.pending_ids.append(int(record.id))
    db.commit()
    return result


def _record_state(record: DeploymentRecordRow) -> str:
    status = _clean(record.status).lower()
    if status == "succeeded":
        return "succeeded"
    if status in {"failed", "blocked", "cancelled"}:
        return "failed"
    if status == "running":
        return "running"
    return "pending"


def _sync_parent_task(db: Session, record: DeploymentRecordRow, state: str) -> None:
    task = _task_for_record(db, record)
    if task is None or _clean(task.status).lower() in {"completed", "cancelled"}:
        return
    if state == "succeeded":
        task.status = "completed"
        task.health_status = "passed"
        task.failure_summary = None
        task.finished_at = record.finished_at or utcnow()
    elif state == "failed":
        task.status = "failed"
        task.health_status = "failed"
        task.failure_summary = _clean(record.notes) or "Local scheduled-job publish failed."
        task.finished_at = record.finished_at or utcnow()
    elif state in {"running", "pending"}:
        task.status = "deploying"
        task.health_status = "checking"
    task.deployment_record_id = int(record.id)
    task.updated_at = utcnow()


def _task_for_record(
    db: Session, record: DeploymentRecordRow
) -> ScheduledJobReleaseTaskRow | None:
    task = (
        db.query(ScheduledJobReleaseTaskRow)
        .filter(ScheduledJobReleaseTaskRow.deployment_record_id == int(record.id))
        .first()
    )
    if task is not None:
        return task
    metadata = _json_load(getattr(record, "metadata_json", None))
    task_id = metadata.get("scheduledJobReleaseTaskId")
    if isinstance(task_id, int):
        return db.get(ScheduledJobReleaseTaskRow, task_id)
    return None
