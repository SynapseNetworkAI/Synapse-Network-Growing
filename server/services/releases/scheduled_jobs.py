"""Cloud Run Job release projection for Synapse-Network staging jobs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server import config
from server.database import DeploymentRecordRow, utcnow
from server.services.releases.scheduled_job_catalog import (
    SCHEDULED_JOB_ACTIVE_STATUSES,
    SCHEDULED_JOB_FAMILIES,
    SCHEDULED_JOBS_REPO,
    SCHEDULED_JOBS_TRIGGER_SOURCE,
    SCHEDULED_JOBS_WORKFLOW_FILE,
    scheduled_job_catalog,
)
from server.services.releases.scheduled_job_schemas import (
    ScheduledCloudRunJobOut,
    ScheduledCloudRunJobStatusOut,
    ScheduledCloudRunJobsPublishOut,
    ScheduledCloudRunJobsPublishRequest,
    ScheduledCloudRunJobsStatusOut,
)
from server.services.delivery.deployment_governance import (
    _callback_url,
    _dispatch_github_workflow,
    _json_dump,
)
from server.services.releases.scheduled_job_workflow import (
    ensure_scheduled_job_workflow_accepts_inputs,
)


@dataclass(frozen=True)
class _PublishTarget:
    environment: str
    source_ref_type: str
    family: str
    jobs: list[ScheduledCloudRunJobOut]
    publish_mode: str
    selected_job: ScheduledCloudRunJobOut | None


def _json_load(raw: object) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _run_id_from_url(url: str | None) -> str | None:
    match = re.search(r"/actions/runs/(\d+)", _clean(url))
    return match.group(1) if match else None


def _parse_github_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _merge_metadata(row: DeploymentRecordRow, updates: dict[str, Any]) -> None:
    metadata = _json_load(getattr(row, "metadata_json", None))
    metadata.update({key: value for key, value in updates.items() if value is not None})
    row.metadata_json = _json_dump(metadata)


def _jobs_for_family(family: str) -> list[ScheduledCloudRunJobOut]:
    normalized = _clean(family).lower() or "gateway"
    catalog = scheduled_job_catalog()
    if normalized == "all":
        return catalog
    return [job for job in catalog if job.family == normalized]


def _job_by_name(job_name: str) -> ScheduledCloudRunJobOut | None:
    cleaned = _clean(job_name)
    if not cleaned:
        return None
    return next(
        (job for job in scheduled_job_catalog() if job.job_name == cleaned), None
    )


def _validated_environment(value: object) -> str:
    environment = _clean(value).lower() or "staging"
    if environment != "staging":
        raise ValueError("environment must be staging for scheduled job releases.")
    return environment


def _validated_source_ref_type(value: object) -> str:
    source_ref_type = _clean(value).lower() or "branch"
    if source_ref_type != "branch":
        raise ValueError("source_ref_type must be branch for scheduled job releases.")
    return source_ref_type


def _resolve_single_job_target(
    body: ScheduledCloudRunJobsPublishRequest,
) -> _PublishTarget | None:
    job_name = _clean(body.job_name)
    if not job_name:
        return None
    selected_job = _job_by_name(job_name)
    if selected_job is None:
        raise ValueError("Unknown scheduled job name.")
    if selected_job.migration_execution_required and not body.run_migrations:
        raise ValueError("migration job publish requires run_migrations confirmation.")
    return _PublishTarget(
        environment=_validated_environment(body.environment),
        source_ref_type=_validated_source_ref_type(body.source_ref_type),
        family=selected_job.family,
        jobs=[selected_job],
        publish_mode="single_job",
        selected_job=selected_job,
    )


def _resolve_family_target(body: ScheduledCloudRunJobsPublishRequest) -> _PublishTarget:
    family = _clean(body.family).lower() or "gateway"
    if family not in SCHEDULED_JOB_FAMILIES:
        raise ValueError("family must be gateway, gateway-admin, or all.")
    jobs = _jobs_for_family(family)
    if not jobs:
        raise ValueError("No scheduled jobs are registered for this family.")
    return _PublishTarget(
        environment=_validated_environment(body.environment),
        source_ref_type=_validated_source_ref_type(body.source_ref_type),
        family=family,
        jobs=jobs,
        publish_mode="family",
        selected_job=None,
    )


def _resolve_publish_target(
    body: ScheduledCloudRunJobsPublishRequest,
) -> _PublishTarget:
    return _resolve_single_job_target(body) or _resolve_family_target(body)


def _record_jobs(metadata: dict[str, Any]) -> set[str]:
    explicit = metadata.get("jobs")
    if isinstance(explicit, list):
        return {_clean(item) for item in explicit if _clean(item)}
    return {
        name
        for item in _manifest_entries(metadata)
        for name in [_manifest_job_name(item)]
        if name
    }


def _manifest_entries(metadata: dict[str, Any]) -> list[object]:
    manifest = metadata.get("jobsManifest") or metadata.get("jobs_manifest")
    if not isinstance(manifest, dict):
        return []
    entries = manifest.get("updated") or manifest.get("jobs") or []
    return entries if isinstance(entries, list) else []


def _manifest_job_name(item: object) -> str:
    if isinstance(item, str):
        return _clean(item)
    if not isinstance(item, dict):
        return ""
    return _clean(item.get("job") or item.get("job_name") or item.get("name"))


def _image_from_manifest_item(item: dict[str, Any]) -> tuple[str | None, str | None]:
    image = (
        _clean(
            item.get("effective_image")
            or item.get("effectiveImage")
            or item.get("image")
            or item.get("requested_image")
            or item.get("requestedImage")
        )
        or None
    )
    digest = (
        _clean(
            item.get("image_digest") or item.get("imageDigest") or item.get("digest")
        )
        or None
    )
    return image, digest


def _record_effective_image(
    metadata: dict[str, Any], job_name: str
) -> tuple[str | None, str | None]:
    for item in _manifest_entries(metadata):
        if isinstance(item, dict) and _manifest_job_name(item) == job_name:
            return _image_from_manifest_item(item)
    images = metadata.get("images")
    if isinstance(images, dict):
        family_image = images.get("gateway") or images.get("gateway-admin")
        if isinstance(family_image, str) and family_image.strip():
            return family_image.strip(), None
    return None, None


def _latest_record_for_job(
    db: Session, job: ScheduledCloudRunJobOut
) -> DeploymentRecordRow | None:
    rows = (
        db.query(DeploymentRecordRow)
        .filter(
            DeploymentRecordRow.trigger_source == SCHEDULED_JOBS_TRIGGER_SOURCE,
            DeploymentRecordRow.project_key == "synapse-network",
            DeploymentRecordRow.environment == "staging",
        )
        .order_by(DeploymentRecordRow.id.desc())
        .limit(50)
        .all()
    )
    for row in rows:
        metadata = _json_load(getattr(row, "metadata_json", None))
        family = _clean(metadata.get("jobFamily") or metadata.get("job_family")).lower()
        if family not in {job.family, "all"}:
            continue
        expected_jobs = _record_jobs(metadata)
        if expected_jobs and job.job_name not in expected_jobs:
            continue
        return row
    return None


def scheduled_jobs_status(db: Session) -> ScheduledCloudRunJobsStatusOut:
    diagnostics = [
        "gcp_status_unavailable: Ops Console reads deployment manifests only; Google writes run through GitHub Actions WIF."
    ]
    items = [_status_item_for_job(db, job) for job in scheduled_job_catalog()]
    return ScheduledCloudRunJobsStatusOut(
        items=items, diagnostics=diagnostics, updated_at=utcnow()
    )


def _scheduler_status(job: ScheduledCloudRunJobOut) -> str:
    return "configured_from_docs" if job.scheduler_job else "manual_job"


def _publish_status(status: str) -> str:
    if status == "succeeded":
        return "published"
    return "publishing" if status in SCHEDULED_JOB_ACTIVE_STATUSES else status


def _status_item_for_job(
    db: Session, job: ScheduledCloudRunJobOut
) -> ScheduledCloudRunJobStatusOut:
    record = _latest_record_for_job(db, job)
    if record is None:
        return ScheduledCloudRunJobStatusOut(
            **job.model_dump(),
            publish_status="unknown",
            scheduler_status=_scheduler_status(job),
            health_status="unknown",
            diagnostic="No scheduled-job deployment record yet.",
        )
    metadata = _json_load(getattr(record, "metadata_json", None))
    status = _clean(record.status).lower() or "unknown"
    effective_image, image_digest = _record_effective_image(metadata, job.job_name)
    return ScheduledCloudRunJobStatusOut(
        **job.model_dump(),
        publish_status=_publish_status(status),
        scheduler_status=_scheduler_status(job),
        health_status=_record_health_status(record, status),
        effective_image=effective_image,
        image_digest=image_digest,
        last_published_at=record.finished_at or record.updated_at,
        last_deployment_record_id=int(record.id),
        external_url=_clean(record.external_url) or None,
        failure_summary=_clean(record.notes) if status == "failed" else None,
        diagnostic=_record_diagnostic(status),
        metadata=metadata,
    )


def _record_health_status(record: DeploymentRecordRow, status: str) -> str:
    return _clean(record.health_status).lower() or (
        "passed" if status == "succeeded" else "checking"
    )


def _record_diagnostic(status: str) -> str | None:
    return (
        None
        if status in {"succeeded", "failed"}
        else "GitHub Actions publish is still pending or running."
    )


def publish_scheduled_jobs(
    db: Session, body: ScheduledCloudRunJobsPublishRequest
) -> ScheduledCloudRunJobsPublishOut:
    target = _resolve_publish_target(body)
    actor = _clean(body.actor) or "operator"
    source_ref = _clean(body.source_ref) or "main"
    record = _create_publish_record(
        db,
        body,
        jobs=target.jobs,
        family=target.family,
        environment=target.environment,
        publish_mode=target.publish_mode,
        actor=actor,
        source_ref=source_ref,
    )
    inputs = _workflow_inputs(
        record,
        body,
        family=target.family,
        environment=target.environment,
        actor=actor,
        source_ref=source_ref,
    )
    try:
        _ensure_remote_workflow_accepts_inputs(inputs)
        record.external_url = _dispatch_github_workflow(
            repo_full_name=SCHEDULED_JOBS_REPO,
            workflow_file=SCHEDULED_JOBS_WORKFLOW_FILE,
            ref="main",
            inputs=inputs,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        _mark_dispatch_failed(db, record, exc)
        raise
    return ScheduledCloudRunJobsPublishOut(
        deployment_record_id=int(record.id),
        family=target.family,
        environment=target.environment,
        publish_mode=target.publish_mode,
        job_name=target.selected_job.job_name if target.selected_job else None,
        status=_clean(record.status) or "requested",
        external_url=_clean(record.external_url) or None,
        jobs=[job.job_name for job in target.jobs],
        message=(
            f"Scheduled job publish dispatched for {target.jobs[0].job_name}."
            if target.publish_mode == "single_job"
            else f"Scheduled job publish dispatched for {target.family}."
        ),
    )


def _create_publish_record(
    db: Session,
    body: ScheduledCloudRunJobsPublishRequest,
    *,
    jobs: list[ScheduledCloudRunJobOut],
    family: str,
    environment: str,
    publish_mode: str,
    actor: str,
    source_ref: str,
) -> DeploymentRecordRow:
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment=environment,
        action="publish_cloud_run_jobs",
        status="requested",
        health_status="checking",
        branch_name=source_ref,
        workflow_file=SCHEDULED_JOBS_WORKFLOW_FILE,
        actor=actor,
        trigger_source=SCHEDULED_JOBS_TRIGGER_SOURCE,
        notes=_clean(body.note) or f"Publish {family} Cloud Run Jobs to staging.",
        metadata_json=_json_dump(
            {
                "deploy_repo_full_name": SCHEDULED_JOBS_REPO,
                "deploy_strategy": "github_actions_wif_cloudrun_jobs",
                "publishMode": publish_mode,
                "jobFamily": family,
                "jobName": jobs[0].job_name if publish_mode == "single_job" else None,
                "jobs": [job.job_name for job in jobs],
                "sourceRefType": "branch",
                "sourceRef": source_ref,
                "environment": environment,
                "runSmokeJobs": bool(body.run_smoke_jobs),
                "runMigrations": bool(body.run_migrations),
            }
        ),
        started_at=utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _workflow_inputs(
    record: DeploymentRecordRow,
    body: ScheduledCloudRunJobsPublishRequest,
    *,
    family: str,
    environment: str,
    actor: str,
    source_ref: str,
) -> dict[str, str]:
    inputs = {
        "record_id": str(int(record.id)),
        "job_family": family,
        "source_ref_type": "branch",
        "source_ref": source_ref,
        "actor": actor,
        "trigger_source": SCHEDULED_JOBS_TRIGGER_SOURCE,
        "run_smoke_jobs": "true" if body.run_smoke_jobs else "false",
        "run_migrations": "true" if body.run_migrations else "false",
    }
    job_name = _clean(body.job_name)
    if job_name:
        inputs["job_name"] = job_name
    callback_url = _callback_url(int(record.id))
    if callback_url:
        inputs["callback_url"] = callback_url
    if config.DEPLOY_WEBHOOK_TOKEN:
        inputs["callback_token"] = config.DEPLOY_WEBHOOK_TOKEN
    return inputs


def _ensure_remote_workflow_accepts_inputs(inputs: dict[str, str]) -> None:
    ensure_scheduled_job_workflow_accepts_inputs(inputs)


def _mark_dispatch_failed(
    db: Session, record: DeploymentRecordRow, exc: Exception
) -> None:
    record.status = "failed"
    record.health_status = "failed"
    record.notes = str(exc)[:1000]
    record.finished_at = utcnow()
    db.commit()
