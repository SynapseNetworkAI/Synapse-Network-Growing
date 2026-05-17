"""Two-step task lifecycle for scheduled Cloud Run Job releases."""

from __future__ import annotations

from typing import Any

from sqlalchemy import case
from sqlalchemy.orm import Session

from server.database import DeploymentRecordRow, utcnow
from server.database_scheduled_jobs import ScheduledJobReleaseTaskRow
from server.services.releases.scheduled_job_catalog import (
    SCHEDULED_JOBS_TRIGGER_SOURCE,
)
from server.services.releases.scheduled_job_schemas import (
    ScheduledCloudRunJobRecordOut,
    ScheduledCloudRunJobRecordsOut,
    ScheduledCloudRunJobTaskCreateRequest,
    ScheduledCloudRunJobTaskPublishRequest,
    ScheduledCloudRunJobsPublishOut,
    ScheduledCloudRunJobsPublishRequest,
)
from server.services.releases.scheduled_jobs import (
    _clean,
    _create_publish_record,
    _json_load,
    _record_jobs,
    _resolve_single_job_target,
)
from server.services.delivery.deployment_governance import _json_dump


def create_scheduled_job_release_task(
    db: Session, body: ScheduledCloudRunJobTaskCreateRequest
) -> ScheduledCloudRunJobRecordOut:
    target = _validated_single_job_body(body)
    actor = _clean(body.actor) or "operator"
    source_ref = _clean(body.source_ref) or "main"
    selected = target.selected_job
    if selected is None:
        raise ValueError("job_name is required for scheduled job release tasks.")
    row = ScheduledJobReleaseTaskRow(
        project_key="synapse-network",
        job_name=selected.job_name,
        job_family=selected.family,
        job_type=selected.job_type,
        environment=target.environment,
        source_ref_type=target.source_ref_type,
        source_ref=source_ref,
        status="requested",
        health_status="pending",
        run_smoke_jobs=bool(body.run_smoke_jobs),
        run_migrations=bool(body.run_migrations),
        created_by=actor,
        note=_clean(body.note)
        or f"Create scheduled job release for {selected.job_name}.",
        metadata_json=_json_dump(
            {
                "publishMode": "single_job",
                "jobName": selected.job_name,
                "jobs": [selected.job_name],
                "jobFamily": selected.family,
                "jobType": selected.job_type,
                "sourceRefType": target.source_ref_type,
                "sourceRef": source_ref,
                "environment": target.environment,
                "runSmokeJobs": bool(body.run_smoke_jobs),
                "runMigrations": bool(body.run_migrations),
                "createdWithoutDispatch": True,
            }
        ),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _task_out(row)


def list_scheduled_job_release_tasks(
    db: Session,
    *,
    environment: str | None = None,
    job_name: str | None = None,
    family: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> ScheduledCloudRunJobRecordsOut:
    _backfill_legacy_deployment_records(db)
    bounded_limit = max(1, min(int(limit or 10), 100))
    bounded_offset = max(0, int(offset or 0))
    query = db.query(ScheduledJobReleaseTaskRow)
    if _clean(environment):
        query = query.filter(
            ScheduledJobReleaseTaskRow.environment == _clean(environment).lower()
        )
    if _clean(job_name):
        query = query.filter(ScheduledJobReleaseTaskRow.job_name == _clean(job_name))
    if _clean(family):
        query = query.filter(
            ScheduledJobReleaseTaskRow.job_family == _clean(family).lower()
        )
    if _clean(status):
        query = query.filter(
            ScheduledJobReleaseTaskRow.status == _clean(status).lower()
        )
    total = query.count()
    status_priority = case(
        (
            ScheduledJobReleaseTaskRow.status.in_(
                ["requested", "deploying", "running", "pending", "publishing"]
            ),
            0,
        ),
        (ScheduledJobReleaseTaskRow.status.in_(["completed", "succeeded"]), 1),
        (ScheduledJobReleaseTaskRow.status.in_(["failed", "blocked"]), 2),
        (ScheduledJobReleaseTaskRow.status.in_(["cancelled", "canceled"]), 3),
        else_=0,
    )
    rows = (
        query.order_by(
            status_priority.asc(),
            ScheduledJobReleaseTaskRow.updated_at.desc(),
            ScheduledJobReleaseTaskRow.id.desc(),
        )
        .offset(bounded_offset)
        .limit(bounded_limit)
        .all()
    )
    return ScheduledCloudRunJobRecordsOut(
        items=[_task_out(row) for row in rows],
        total=total,
        limit=bounded_limit,
        offset=bounded_offset,
    )


def get_scheduled_job_release_task(
    db: Session, task_id: int
) -> ScheduledCloudRunJobRecordOut:
    row = _task_row(db, task_id)
    return _task_out(row)


def publish_scheduled_job_release_task(
    db: Session, task_id: int, body: ScheduledCloudRunJobTaskPublishRequest
) -> ScheduledCloudRunJobsPublishOut:
    row = _task_row(db, task_id)
    _ensure_publishable(row)
    request = _publish_request_from_task(row, actor=_clean(body.actor) or "operator")
    target = _resolve_single_job_target(request)
    if target is None or target.selected_job is None:
        raise ValueError("scheduled job release task must target exactly one job.")
    actor = _clean(body.actor) or "operator"
    source_ref = _clean(row.source_ref) or "main"
    record = _create_task_deployment_record(db, request, target, actor, source_ref)
    _mark_task_deploying(row, record, actor)
    db.commit()
    return ScheduledCloudRunJobsPublishOut(
        deployment_record_id=int(record.id),
        task_id=int(row.id),
        family=target.family,
        environment=target.environment,
        publish_mode="single_job",
        job_name=target.selected_job.job_name,
        status=_clean(row.status) or "deploying",
        external_url=_clean(record.external_url) or None,
        jobs=[job.job_name for job in target.jobs],
        message=f"Scheduled job release task #{row.id} queued for local runner.",
    )


def _ensure_publishable(row: ScheduledJobReleaseTaskRow) -> None:
    if _clean(row.status).lower() not in {"requested", "failed"}:
        raise ValueError(
            "Only requested or failed scheduled job release tasks can be published."
        )


def _create_task_deployment_record(
    db: Session,
    request: ScheduledCloudRunJobsPublishRequest,
    target: Any,
    actor: str,
    source_ref: str,
) -> DeploymentRecordRow:
    record = _create_publish_record(
        db,
        request,
        jobs=target.jobs,
        family=target.family,
        environment=target.environment,
        publish_mode="single_job",
        actor=actor,
        source_ref=source_ref,
    )
    return record


def _mark_task_deploying(
    row: ScheduledJobReleaseTaskRow, record: DeploymentRecordRow, actor: str
) -> None:
    _attach_task_to_record(record, row)
    row.status = "deploying"
    row.health_status = "checking"
    row.deployment_record_id = int(record.id)
    row.executed_by = actor
    row.failure_summary = None
    row.started_at = utcnow()
    row.finished_at = None
    row.updated_at = utcnow()


def _task_workflow_inputs(
    record: DeploymentRecordRow,
    request: ScheduledCloudRunJobsPublishRequest,
    target: Any,
    actor: str,
    source_ref: str,
) -> dict[str, str]:
    return {
        "record_id": str(int(record.id)),
        "actor": actor,
        "source_ref": source_ref,
    }


def _dispatch_task_workflow(
    record: DeploymentRecordRow, inputs: dict[str, str]
) -> None:
    raise ValueError("github_workflows_removed: scheduled jobs use local runner.")


def _mark_task_dispatch_failed(
    db: Session,
    row: ScheduledJobReleaseTaskRow,
    record: DeploymentRecordRow,
    exc: Exception,
) -> None:
    record.status = "failed"
    record.health_status = "failed"
    record.notes = str(exc)[:1000]
    record.finished_at = utcnow()
    row.status = "failed"
    row.health_status = "failed"
    row.failure_summary = str(exc)[:1000]
    row.finished_at = utcnow()
    row.updated_at = utcnow()
    db.commit()


def cancel_scheduled_job_release_task(
    db: Session, task_id: int
) -> ScheduledCloudRunJobRecordOut:
    row = _task_row(db, task_id)
    if _clean(row.status).lower() not in {"requested", "failed"}:
        raise ValueError(
            "Only requested or failed scheduled job release tasks can be cancelled."
        )
    row.status = "cancelled"
    row.health_status = "failed"
    row.finished_at = utcnow()
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return _task_out(row)


def _validated_single_job_body(
    body: ScheduledCloudRunJobTaskCreateRequest,
):
    request = ScheduledCloudRunJobsPublishRequest(
        job_name=body.job_name,
        environment=body.environment,
        source_ref_type=body.source_ref_type,
        source_ref=body.source_ref,
        actor=body.actor,
        note=body.note,
        run_smoke_jobs=body.run_smoke_jobs,
        run_migrations=body.run_migrations,
    )
    target = _resolve_single_job_target(request)
    if target is None:
        raise ValueError("job_name is required for scheduled job release tasks.")
    return target


def _publish_request_from_task(
    row: ScheduledJobReleaseTaskRow, *, actor: str
) -> ScheduledCloudRunJobsPublishRequest:
    return ScheduledCloudRunJobsPublishRequest(
        job_name=row.job_name,
        environment=row.environment,
        source_ref_type=row.source_ref_type,
        source_ref=row.source_ref,
        actor=actor,
        note=row.note,
        run_smoke_jobs=bool(row.run_smoke_jobs),
        run_migrations=bool(row.run_migrations),
    )


def _task_row(db: Session, task_id: int) -> ScheduledJobReleaseTaskRow:
    row = db.get(ScheduledJobReleaseTaskRow, int(task_id))
    if row is None:
        raise ValueError("Scheduled job release task not found.")
    return row


def _task_out(row: ScheduledJobReleaseTaskRow) -> ScheduledCloudRunJobRecordOut:
    record = row.deployment_record
    metadata = _merged_task_metadata(row, record)
    return ScheduledCloudRunJobRecordOut(
        id=int(row.id),
        deployment_record_id=int(row.deployment_record_id)
        if row.deployment_record_id
        else None,
        job_name=row.job_name,
        jobs=[row.job_name],
        family=row.job_family,
        job_type=row.job_type,
        environment=row.environment,
        publish_mode="single_job",
        source_ref_type=row.source_ref_type,
        source_ref=row.source_ref,
        status=_task_status(row, record),
        health_status=_task_health(row, record),
        actor=row.executed_by or row.created_by,
        created_by=row.created_by,
        executed_by=row.executed_by,
        workflow_file=_clean(getattr(record, "workflow_file", None)) or None,
        external_run_id=_clean(getattr(record, "external_run_id", None)) or None,
        external_url=_clean(getattr(record, "external_url", None)) or None,
        failure_summary=_task_failure(row, record),
        notes=_clean(row.note) or _clean(getattr(record, "notes", None)) or None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.started_at or getattr(record, "started_at", None),
        finished_at=row.finished_at or getattr(record, "finished_at", None),
        metadata=metadata,
    )


def _task_status(
    row: ScheduledJobReleaseTaskRow, record: DeploymentRecordRow | None
) -> str:
    if _clean(row.status):
        return _clean(row.status)
    return _record_status_to_task(_clean(getattr(record, "status", None)))


def _task_health(
    row: ScheduledJobReleaseTaskRow, record: DeploymentRecordRow | None
) -> str:
    if _clean(row.health_status):
        return _clean(row.health_status)
    return _clean(getattr(record, "health_status", None)) or "pending"


def _task_failure(
    row: ScheduledJobReleaseTaskRow, record: DeploymentRecordRow | None
) -> str | None:
    if _clean(row.failure_summary):
        return _clean(row.failure_summary)
    if _clean(getattr(record, "status", None)) == "failed":
        return _clean(getattr(record, "notes", None)) or None
    return None


def _merged_task_metadata(
    row: ScheduledJobReleaseTaskRow, record: DeploymentRecordRow | None
) -> dict[str, object]:
    metadata = _json_load(row.metadata_json)
    if record is not None:
        metadata["deploymentRecord"] = _json_load(
            getattr(record, "metadata_json", None)
        )
    return metadata


def _attach_task_to_record(
    record: DeploymentRecordRow, row: ScheduledJobReleaseTaskRow
) -> None:
    metadata = _json_load(record.metadata_json)
    metadata.update(
        {
            "scheduledJobReleaseTaskId": int(row.id),
            "jobName": row.job_name,
            "jobs": [row.job_name],
            "jobFamily": row.job_family,
            "publishMode": "single_job",
        }
    )
    record.metadata_json = _json_dump(metadata)


def _backfill_legacy_deployment_records(db: Session) -> None:
    records = (
        db.query(DeploymentRecordRow)
        .filter(DeploymentRecordRow.trigger_source == SCHEDULED_JOBS_TRIGGER_SOURCE)
        .order_by(DeploymentRecordRow.id.asc())
        .all()
    )
    changed = False
    for record in records:
        if (
            db.query(ScheduledJobReleaseTaskRow)
            .filter(ScheduledJobReleaseTaskRow.deployment_record_id == int(record.id))
            .first()
            is not None
        ):
            continue
        metadata = _json_load(record.metadata_json)
        task_id = metadata.get("scheduledJobReleaseTaskId")
        if isinstance(task_id, int) and db.get(ScheduledJobReleaseTaskRow, task_id):
            continue
        jobs = sorted(_record_jobs(metadata))
        if not jobs:
            continue
        row = _legacy_task_row(record, metadata, jobs[0])
        db.add(row)
        changed = True
    if changed:
        db.commit()


def _legacy_task_row(
    record: DeploymentRecordRow, metadata: dict[str, Any], job_name: str
) -> ScheduledJobReleaseTaskRow:
    return ScheduledJobReleaseTaskRow(
        project_key="synapse-network",
        job_name=job_name,
        job_family=_legacy_metadata_value(
            metadata, "jobFamily", "job_family", "gateway"
        ),
        job_type=_legacy_metadata_value(metadata, "jobType", "job_type", "periodic"),
        environment=_clean(record.environment) or "staging",
        source_ref_type=_clean(metadata.get("sourceRefType")) or "branch",
        source_ref=_legacy_source_ref(metadata, record),
        status=_record_status_to_task(_clean(record.status)),
        health_status=_clean(record.health_status) or "checking",
        deployment_record_id=int(record.id),
        created_by=_legacy_actor(record),
        executed_by=_legacy_actor(record),
        note=_clean(record.notes) or None,
        failure_summary=_legacy_failure_summary(record),
        metadata_json=_json_dump({**metadata, "legacyBackfilled": True}),
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


def _legacy_failure_summary(record: DeploymentRecordRow) -> str | None:
    return _clean(record.notes) if _clean(record.status) == "failed" else None


def _legacy_metadata_value(
    metadata: dict[str, Any], primary_key: str, fallback_key: str, default: str
) -> str:
    return _clean(metadata.get(primary_key) or metadata.get(fallback_key)) or default


def _legacy_source_ref(metadata: dict[str, Any], record: DeploymentRecordRow) -> str:
    return _clean(metadata.get("sourceRef") or record.branch_name) or "main"


def _legacy_actor(record: DeploymentRecordRow) -> str:
    return _clean(record.actor) or "operator"


def _record_status_to_task(status: str) -> str:
    if status == "succeeded":
        return "completed"
    if status == "failed":
        return "failed"
    if status in {"requested", "running", "pending"}:
        return "deploying"
    if status in {"cancelled", "canceled"}:
        return "cancelled"
    return "requested"
