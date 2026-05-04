"""GitHub Actions reconciliation for scheduled Cloud Run Job releases."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from server.database import DeploymentRecordRow, utcnow
from server.database_scheduled_jobs import ScheduledJobReleaseTaskRow
from server.services.releases.github_actions_logs import github_failure_log_result
from server.services.releases.github_cli import run_gh_json, run_gh_text
from server.services.releases.scheduled_job_catalog import (
    SCHEDULED_JOBS_REPO,
    SCHEDULED_JOBS_TRIGGER_SOURCE,
    SCHEDULED_JOBS_WORKFLOW_FILE,
)
from server.services.releases.scheduled_job_schemas import ScheduledCloudRunJobsSyncOut
from server.services.releases.scheduled_jobs import (
    _as_aware_utc,
    _clean,
    _json_load,
    _merge_metadata,
    _parse_github_timestamp,
    _run_id_from_url,
)


def _find_recent_run_id(
    record: DeploymentRecordRow, metadata: dict[str, Any]
) -> str | None:
    status, payload, _error = run_gh_json(
        [
            "run",
            "list",
            "--repo",
            SCHEDULED_JOBS_REPO,
            "--workflow",
            _clean(record.workflow_file) or SCHEDULED_JOBS_WORKFLOW_FILE,
            "--event",
            "workflow_dispatch",
            "--limit",
            "20",
            "--json",
            "databaseId,status,conclusion,createdAt,updatedAt,url,headSha",
        ],
        timeout=30,
    )
    if status != "ok" or not isinstance(payload, list):
        return None
    started_at = _as_aware_utc(record.started_at) or datetime.now(timezone.utc)
    earliest = started_at - timedelta(seconds=30)
    source_ref = _clean(metadata.get("sourceRef") or record.branch_name)
    for item in payload:
        run_id = _recent_run_candidate_id(
            item, earliest=earliest, source_ref=source_ref
        )
        if run_id:
            return run_id
    return None


def _recent_run_candidate_id(
    item: object, *, earliest: datetime, source_ref: str
) -> str | None:
    if not isinstance(item, dict):
        return None
    created_at = _parse_github_timestamp(item.get("createdAt"))
    if created_at is not None and created_at < earliest:
        return None
    run_id = item.get("databaseId")
    if run_id is None:
        return None
    head_branch = _clean(item.get("headBranch"))
    if source_ref and head_branch and source_ref != head_branch:
        return None
    return str(run_id)


def _run_view(run_id: str) -> tuple[dict[str, Any] | None, str | None]:
    status, payload, error = run_gh_json(
        [
            "run",
            "view",
            str(run_id),
            "--repo",
            SCHEDULED_JOBS_REPO,
            "--json",
            "databaseId,status,conclusion,createdAt,updatedAt,url,headSha",
        ],
        timeout=30,
    )
    if status == "ok" and isinstance(payload, dict):
        return payload, None
    return None, error or "Unable to read GitHub Actions run."


def _apply_run_to_record(
    record: DeploymentRecordRow, *, run_payload: dict[str, Any], run_id: str
) -> str:
    now = utcnow()
    status = _clean(run_payload.get("status")).lower()
    conclusion = _clean(run_payload.get("conclusion")).lower()
    run_url = _clean(run_payload.get("url")) or record.external_url
    head_sha = _clean(run_payload.get("headSha")) or None
    _merge_metadata(
        record,
        {
            "githubRunId": str(run_id),
            "githubRunUrl": run_url,
            "githubRunStatus": status,
            "githubRunConclusion": conclusion or None,
            "githubHeadSha": head_sha,
            "lastScheduledJobsSyncedAt": now.isoformat(),
        },
    )
    record.external_run_id = str(run_id)
    record.external_url = run_url
    if status and status != "completed":
        _mark_running(record, status)
        return "running"
    if conclusion == "success":
        _mark_success(record, head_sha=head_sha, now=now)
        return "succeeded"
    if _is_failed_conclusion(conclusion):
        _mark_failed(record, run_id=run_id, conclusion=conclusion, now=now)
        return "failed"
    _mark_pending(record)
    return "pending"


def _mark_running(record: DeploymentRecordRow, status: str) -> None:
    record.status = "running"
    record.health_status = record.health_status or "checking"
    record.notes = f"GitHub Actions scheduled jobs publish {status}."


def _mark_success(
    record: DeploymentRecordRow, *, head_sha: str | None, now: datetime
) -> None:
    record.status = "succeeded"
    record.health_status = "passed"
    record.notes = (
        "staging scheduled jobs publish succeeded; GitHub Actions run passed."
    )
    if head_sha:
        record.commit_sha = head_sha
    record.finished_at = now


def _is_failed_conclusion(conclusion: str) -> bool:
    return conclusion in {
        "failure",
        "cancelled",
        "timed_out",
        "startup_failure",
        "action_required",
    }


def _mark_failed(
    record: DeploymentRecordRow, *, run_id: str, conclusion: str, now: datetime
) -> None:
    failure_log = github_failure_log_result(
        SCHEDULED_JOBS_REPO,
        str(run_id),
        conclusion=conclusion or "failure",
        run_gh_text=lambda args: run_gh_text(args, timeout=45),
    )
    _merge_metadata(
        record,
        {**failure_log.metadata, "githubFailureLogSyncedAt": now.isoformat()},
    )
    record.status = "failed"
    record.health_status = "failed"
    record.notes = (
        failure_log.note or f"GitHub Actions scheduled jobs publish {conclusion}."
    )
    record.finished_at = now


def _mark_pending(record: DeploymentRecordRow) -> None:
    record.status = "pending"
    record.health_status = record.health_status or "checking"
    record.notes = "GitHub Actions scheduled jobs result is not terminal yet."


def sync_scheduled_job_publish_statuses(
    db: Session, *, max_records: int = 50
) -> ScheduledCloudRunJobsSyncOut:
    bounded_limit = max(1, min(int(max_records or 50), 50))
    sync_cutoff = utcnow() - timedelta(days=7)
    rows = (
        db.query(DeploymentRecordRow)
        .filter(
            DeploymentRecordRow.trigger_source == SCHEDULED_JOBS_TRIGGER_SOURCE,
            or_(
                DeploymentRecordRow.status.in_(["requested", "running", "pending"]),
                and_(
                    DeploymentRecordRow.status.in_(["failed", "succeeded"]),
                    DeploymentRecordRow.external_run_id.isnot(None),
                    DeploymentRecordRow.updated_at >= sync_cutoff,
                ),
            ),
        )
        .order_by(DeploymentRecordRow.id.asc())
        .limit(bounded_limit)
        .all()
    )
    result = ScheduledCloudRunJobsSyncOut()
    for record in rows:
        state = _sync_record(record, result)
        _sync_parent_task(db, record, state)
    db.commit()
    return result


def _sync_record(
    record: DeploymentRecordRow, result: ScheduledCloudRunJobsSyncOut
) -> str:
    metadata = _json_load(getattr(record, "metadata_json", None))
    run_id = _clean(record.external_run_id) or _run_id_from_url(record.external_url)
    if not run_id:
        run_id = _find_recent_run_id(record, metadata)
    result.processed_count += 1
    if not run_id:
        if _run_id_missing_timed_out(record):
            _mark_run_id_missing_failed(record)
            result.failed_ids.append(int(record.id))
            return "failed"
        record.status = "pending"
        record.health_status = record.health_status or "checking"
        record.notes = "GitHub Actions scheduled jobs run id not found yet."
        _merge_metadata(
            record,
            {
                "lastScheduledJobsSyncedAt": utcnow().isoformat(),
                "deploymentSyncPendingReason": "GitHub Actions run id not found yet",
            },
        )
        result.pending_ids.append(int(record.id))
        return "pending"
    run_payload, error = _run_view(run_id)
    if run_payload is None:
        record.notes = f"Scheduled jobs sync failed: {error}"
        _merge_metadata(
            record,
            {
                "lastScheduledJobsSyncedAt": utcnow().isoformat(),
                "deploymentSyncError": error,
            },
        )
        result.error_ids.append(int(record.id))
        return "error"
    state = _apply_run_to_record(record, run_payload=run_payload, run_id=run_id)
    if state == "succeeded":
        result.succeeded_ids.append(int(record.id))
    elif state == "failed":
        result.failed_ids.append(int(record.id))
    elif state == "running":
        result.running_ids.append(int(record.id))
    else:
        result.pending_ids.append(int(record.id))
    return state


def _run_id_missing_timed_out(record: DeploymentRecordRow) -> bool:
    started_at = _as_aware_utc(record.started_at)
    if started_at is None:
        return False
    return datetime.now(timezone.utc) - started_at > timedelta(minutes=15)


def _mark_run_id_missing_failed(record: DeploymentRecordRow) -> None:
    now = utcnow()
    record.status = "failed"
    record.health_status = "failed"
    record.notes = "GitHub Actions run id not found after 15m."
    record.finished_at = now
    _merge_metadata(
        record,
        {
            "lastScheduledJobsSyncedAt": now.isoformat(),
            "deploymentSyncFailureKind": "github_actions_run_id_not_found_after_timeout",
        },
    )


def _sync_parent_task(db: Session, record: DeploymentRecordRow, state: str) -> None:
    task = _task_for_record(db, record)
    if task is None or _clean(task.status).lower() in {"completed", "cancelled"}:
        return
    updater = _TASK_STATE_UPDATERS.get(state)
    if updater is not None:
        updater(task, record)
    task.deployment_record_id = int(record.id)
    task.updated_at = utcnow()


def _sync_task_succeeded(
    task: ScheduledJobReleaseTaskRow, record: DeploymentRecordRow
) -> None:
    task.status = "completed"
    task.health_status = "passed"
    task.failure_summary = None
    task.finished_at = record.finished_at or utcnow()


def _sync_task_failed(
    task: ScheduledJobReleaseTaskRow, record: DeploymentRecordRow
) -> None:
    task.status = "failed"
    task.health_status = "failed"
    task.failure_summary = (
        _clean(record.notes) or "GitHub Actions scheduled jobs publish failed."
    )
    task.finished_at = record.finished_at or utcnow()


def _sync_task_running(
    task: ScheduledJobReleaseTaskRow, _record: DeploymentRecordRow
) -> None:
    task.status = "deploying"
    task.health_status = "checking"


def _sync_task_error(
    task: ScheduledJobReleaseTaskRow, record: DeploymentRecordRow
) -> None:
    task.failure_summary = _clean(record.notes) or None


_TASK_STATE_UPDATERS = {
    "succeeded": _sync_task_succeeded,
    "failed": _sync_task_failed,
    "running": _sync_task_running,
    "pending": _sync_task_running,
    "error": _sync_task_error,
}


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
