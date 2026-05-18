"""Local deploy runner persistence helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from server.database import DeploymentRecordRow, ReleaseTaskRow, utcnow
from server.database_scheduled_jobs import ScheduledJobReleaseTaskRow
from server.services.local_runner.json_utils import json_dump, _json_load_dict
from server.services.releases.deployment_events import append_deployment_event


def _clean(value: Any) -> str:
    return str(value or "").strip()


def merge_metadata(row: DeploymentRecordRow, updates: dict[str, Any]) -> None:
    metadata = _json_load_dict(getattr(row, "metadata_json", None))
    metadata.update({key: value for key, value in updates.items() if value is not None})
    row.metadata_json = json_dump(metadata)


def _load_manifest(row: DeploymentRecordRow) -> dict[str, Any]:
    metadata = _json_load_dict(getattr(row, "metadata_json", None))
    manifest_path = _clean(metadata.get("localManifestPath"))
    if not manifest_path:
        return {}
    path = Path(manifest_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _manifest_image_digest(manifest: dict[str, Any]) -> str:
    return _clean(
        manifest.get("image_digest")
        or manifest.get("imageDigest")
        or manifest.get("effectiveImage")
    )


def _manifest_commit_sha(manifest: dict[str, Any]) -> str:
    return _clean(manifest.get("commit_sha") or manifest.get("commitSha"))


def _manifest_service_url(manifest: dict[str, Any]) -> str:
    return _clean(
        manifest.get("service_url")
        or manifest.get("serviceUrl")
        or manifest.get("cloud_run_url")
    )


def _apply_manifest(row: DeploymentRecordRow, manifest: dict[str, Any]) -> None:
    if not manifest:
        return
    image_digest = _manifest_image_digest(manifest)
    commit_sha = _manifest_commit_sha(manifest)
    service_url = _manifest_service_url(manifest)
    if commit_sha:
        row.commit_sha = commit_sha
    if service_url:
        row.external_url = service_url
    merge_metadata(
        row,
        {
            "manifest": manifest,
            "imageDigest": image_digest or None,
            "commitSha": commit_sha or None,
            "cloudRunService": manifest.get("cloud_run_service"),
            "cloudRunRevision": manifest.get("revision"),
            "smokeStatus": manifest.get("smoke_status"),
        },
    )


def _linked_release_task_id(row: DeploymentRecordRow) -> int:
    return int(_json_load_dict(row.metadata_json).get("release_task_id") or 0)


def _sync_linked_task_status(
    db: Session, row: DeploymentRecordRow, *, status: str, note: str | None = None
) -> None:
    _sync_linked_scheduled_job_task_status(db, row, status=status, note=note)
    release_task_id = _linked_release_task_id(row)
    if not release_task_id:
        return
    task = db.get(ReleaseTaskRow, release_task_id)
    if task is None or _clean(task.status) in {"completed", "cancelled"}:
        return
    task.status = status
    task.deployment_record_id = int(row.id)
    task.operator = task.operator or _clean(row.actor) or "local_deploy_runner"
    if note is not None:
        task.note = note
    task.updated_at = utcnow()


def _linked_scheduled_job_task_id(row: DeploymentRecordRow) -> int:
    return int(_json_load_dict(row.metadata_json).get("scheduledJobReleaseTaskId") or 0)


def _sync_linked_scheduled_job_task_status(
    db: Session, row: DeploymentRecordRow, *, status: str, note: str | None = None
) -> None:
    task_id = _linked_scheduled_job_task_id(row)
    if not task_id:
        return
    task = db.get(ScheduledJobReleaseTaskRow, task_id)
    if task is None or _clean(task.status) in {"completed", "cancelled"}:
        return
    task.status = "completed" if status == "completed" else status
    task.health_status = "passed" if status == "completed" else "checking"
    if status == "failed":
        task.health_status = "failed"
        task.failure_summary = note
        task.finished_at = utcnow()
    elif status == "completed":
        task.failure_summary = None
        task.finished_at = utcnow()
    task.deployment_record_id = int(row.id)
    task.executed_by = task.executed_by or _clean(row.actor) or "local_deploy_runner"
    task.updated_at = utcnow()


def claim_local_deployment(
    db: Session, deployment_record_id: int | None = None
) -> DeploymentRecordRow | None:
    query = db.query(DeploymentRecordRow).filter(
        DeploymentRecordRow.status == "requested",
        DeploymentRecordRow.trigger_source == "local_deploy_runner",
    )
    if deployment_record_id is not None:
        query = query.filter(DeploymentRecordRow.id == int(deployment_record_id))
    row = (
        query.order_by(
            DeploymentRecordRow.created_at.asc(), DeploymentRecordRow.id.asc()
        )
        .with_for_update(skip_locked=True)
        .first()
    )
    if row is None:
        return None
    row.status = "running"
    row.health_status = "checking"
    row.started_at = row.started_at or utcnow()
    row.updated_at = utcnow()
    append_deployment_event(
        db,
        deployment_record_id=int(row.id),
        event_type="runner_status",
        step_key="claim",
        message="Local deploy runner claimed this deployment.\n",
    )
    _sync_linked_task_status(db, row, status="deploying")
    db.commit()
    db.refresh(row)
    return row


def finish_local_deployment(
    db: Session,
    deployment_record_id: int,
    *,
    exit_code: int,
    summary: str | None = None,
) -> DeploymentRecordRow:
    row = db.get(DeploymentRecordRow, int(deployment_record_id))
    if row is None:
        raise ValueError("Deployment record not found.")
    passed = int(exit_code) == 0
    if passed:
        _apply_manifest(row, _load_manifest(row))
    row.status = "succeeded" if passed else "failed"
    row.health_status = "passed" if passed else "failed"
    row.notes = _clean(summary) or (
        "Local deploy succeeded." if passed else "Local deploy failed."
    )
    row.finished_at = utcnow()
    row.updated_at = utcnow()
    merge_metadata(row, {"localDeployExitCode": int(exit_code)})
    append_deployment_event(
        db,
        deployment_record_id=int(row.id),
        event_type="runner_status",
        step_key="finish",
        message=f"{row.notes}\n",
    )
    _sync_linked_task_status(
        db, row, status="completed" if passed else "failed", note=row.notes
    )
    db.commit()
    db.refresh(row)
    return row
