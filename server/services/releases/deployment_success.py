"""Helpers for reconciling successful release-task deployments."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from server.database import DeploymentRecordRow, ReleaseTaskRow

DEPLOYMENT_FAILURE_METADATA_KEYS = {
    "deploymentSyncError",
    "deploymentSyncFailureKind",
    "deploymentSyncPendingReason",
    "githubFailureLogError",
    "githubFailureLogExcerpt",
    "githubFailureLogStatus",
    "githubFailureLogSyncedAt",
}


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _json_load(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_dump(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)


def _clear_deployment_failure_metadata(row: DeploymentRecordRow) -> bool:
    metadata = _json_load(getattr(row, "metadata_json", None))
    next_metadata = {
        key: value
        for key, value in metadata.items()
        if key not in DEPLOYMENT_FAILURE_METADATA_KEYS
    }
    if next_metadata == metadata:
        return False
    row.metadata_json = _json_dump(next_metadata)
    return True


def _deployment_has_failure_metadata(row: DeploymentRecordRow) -> bool:
    metadata = _json_load(getattr(row, "metadata_json", None))
    return any(_clean(metadata.get(key)) for key in DEPLOYMENT_FAILURE_METADATA_KEYS)


def _task_note_looks_like_deployment_failure(note: str | None) -> bool:
    lowered = _clean(note).lower()
    if not lowered:
        return False
    return any(
        marker in lowered
        for marker in (
            "github actions",
            "deploy failed",
            "deployment failed",
            "staging deploy failure",
            "unauthorized_client",
            "attribute condition",
            "run id not found",
        )
    )


def _apply_record_success_state(
    record: DeploymentRecordRow,
    *,
    head_sha: str | None,
    now: datetime,
    success_note: str,
) -> bool:
    changed = False
    updates = {
        "status": "succeeded",
        "health_status": "passed",
        "notes": success_note,
    }
    for field, expected in updates.items():
        if _clean(getattr(record, field, None)).lower() != expected.lower():
            setattr(record, field, expected)
            changed = True
    if head_sha and record.commit_sha != head_sha:
        record.commit_sha = head_sha
        changed = True
    if record.finished_at is None:
        record.finished_at = now
        changed = True
    return _clear_deployment_failure_metadata(record) or changed


def _apply_task_completed_state(
    task: ReleaseTaskRow, *, now: datetime, success_note: str
) -> bool:
    changed = False
    if _clean(task.status).lower() != "completed":
        task.status = "completed"
        changed = True
    task.operator = task.operator or "github_actions_sync"
    if _task_note_looks_like_deployment_failure(task.note):
        task.note = success_note
        changed = True
    task.updated_at = now
    return changed


def _apply_deployment_success_state(
    record: DeploymentRecordRow,
    task: ReleaseTaskRow | None,
    *,
    head_sha: str | None,
    now: datetime,
) -> bool:
    environment = _clean(getattr(record, "environment", None)).lower() or "deployment"
    success_note = f"{environment} deploy succeeded; GitHub Actions run passed."
    record_changed = _apply_record_success_state(
        record, head_sha=head_sha, now=now, success_note=success_note
    )
    task_changed = (
        _apply_task_completed_state(task, now=now, success_note=success_note)
        if task is not None
        else False
    )
    return record_changed or task_changed
