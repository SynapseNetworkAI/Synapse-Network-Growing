"""Durable production release task dispatch sweep."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.database import DeploymentRecordRow, ReleaseTaskRow, utcnow
from server.services.delivery.deployment_governance import (
    _dispatch_github_workflow,
    _json_dump,
)
from server.services.result_objects import ServiceObjectResult
from server.services.releases.production_tasks import (
    _assert_production_deploy_secrets,
    _production_deployment_metadata,
    _production_dispatch_inputs,
    _production_staging_evidence,
    _production_workflow_file,
    release_task_production_gate,
)
from server.services.releases.tasks import (
    _clean,
    _json_load,
    _merge_metadata,
    _policy_for_project,
    _release_task_deploy_repo,
)


def _fail_pending_dispatch(
    db: Session,
    *,
    record: DeploymentRecordRow,
    row: ReleaseTaskRow | None,
    error: Exception,
) -> None:
    message = str(error)[:1000]
    record.status = "failed"
    record.health_status = "failed"
    record.notes = message
    record.finished_at = utcnow()
    _merge_metadata(
        record,
        {
            "dispatchPending": False,
            "dispatchStatus": "failed",
            "dispatchFailureSummary": message,
            "githubDispatchFailedAt": utcnow().isoformat(),
        },
    )
    if row is not None:
        row.status = "failed"
        row.note = message
        row.updated_at = utcnow()
    db.commit()


def _dispatch_context(
    db: Session, record: DeploymentRecordRow, row: ReleaseTaskRow
) -> tuple[Any, str, Any, DeploymentRecordRow, str]:
    project_key = _clean(row.project_key)
    policy = _policy_for_project(db, project_key)
    repo_full_name = _release_task_deploy_repo(policy, project_key)
    gate = release_task_production_gate(db, row, repo_full_name)
    staging_record = _production_staging_evidence(db, gate)
    _assert_production_deploy_secrets(repo_full_name)
    actor = _clean(getattr(record, "actor", None)) or _clean(row.operator) or "operator"
    return policy, repo_full_name, gate, staging_record, actor


def _pending_dispatch_records(db: Session, *, limit: int) -> list[DeploymentRecordRow]:
    return (
        db.query(DeploymentRecordRow)
        .filter(
            DeploymentRecordRow.trigger_source == "release_task",
            DeploymentRecordRow.environment == "production",
            DeploymentRecordRow.status == "requested",
        )
        .order_by(DeploymentRecordRow.created_at.asc(), DeploymentRecordRow.id.asc())
        .limit(limit)
        .all()
    )


def _is_pending_production_dispatch(record: DeploymentRecordRow) -> bool:
    metadata = _json_load(record.metadata_json, {})
    return (
        metadata.get("dispatchPending") is True
        and _clean(metadata.get("dispatchStatus")) == "pending"
    )


def _release_task_for_record(
    db: Session, record: DeploymentRecordRow
) -> ReleaseTaskRow | None:
    return (
        db.query(ReleaseTaskRow)
        .filter(ReleaseTaskRow.deployment_record_id == int(record.id))
        .one_or_none()
    )


def _mark_dispatched(
    db: Session,
    *,
    record: DeploymentRecordRow,
    row: ReleaseTaskRow,
    repo_full_name: str,
    gate: Any,
    staging_record: DeploymentRecordRow,
    actor: str,
    service_key: str,
) -> None:
    next_metadata = _production_deployment_metadata(
        row=row,
        repo_full_name=repo_full_name,
        service_key=service_key,
        commit_sha=gate.resolved_commit_sha or "",
        staging_record=staging_record,
    )
    next_metadata.update(
        {
            "dispatchPending": False,
            "dispatchStatus": "dispatched",
            "githubWorkflowFile": record.workflow_file,
            "githubDispatchAt": utcnow().isoformat(),
        }
    )
    record.metadata_json = _json_dump(next_metadata)
    record.notes = "Production workflow dispatched; waiting for GitHub Actions."
    row.status = "deploying"
    row.operator = actor
    row.target_commit_sha = gate.resolved_commit_sha
    row.updated_at = utcnow()
    db.commit()


def _dispatch_one_pending_record(
    db: Session, record: DeploymentRecordRow, row: ReleaseTaskRow
) -> None:
    policy, repo_full_name, gate, staging_record, actor = _dispatch_context(
        db, record, row
    )
    service_key = _clean(getattr(row, "service_key", None)).lower()
    workflow_file = _production_workflow_file(
        policy, project_key=_clean(row.project_key), service_key=service_key
    )
    record.workflow_file = workflow_file
    record.commit_sha = gate.resolved_commit_sha
    record.branch_name = "main"
    inputs = _production_dispatch_inputs(
        row=row,
        record=record,
        commit_sha=gate.resolved_commit_sha or "",
        service_key=service_key,
        actor=actor,
    )
    record.external_url = _dispatch_github_workflow(
        repo_full_name=repo_full_name,
        workflow_file=workflow_file,
        ref="main",
        inputs=inputs,
    )
    _mark_dispatched(
        db,
        record=record,
        row=row,
        repo_full_name=repo_full_name,
        gate=gate,
        staging_record=staging_record,
        actor=actor,
        service_key=service_key,
    )


def dispatch_pending_production_deployments(
    db: Session, *, max_records: int = 5
) -> ServiceObjectResult:
    bounded_limit = max(1, min(int(max_records or 5), 10))
    result: dict[str, Any] = {
        "processed_count": 0,
        "dispatched_ids": [],
        "failed_ids": [],
        "skipped_ids": [],
    }
    for record in _pending_dispatch_records(db, limit=bounded_limit * 3):
        if not _is_pending_production_dispatch(record):
            continue
        if result["processed_count"] >= bounded_limit:
            break
        result["processed_count"] += 1
        row = _release_task_for_record(db, record)
        if row is None:
            _fail_pending_dispatch(
                db,
                record=record,
                row=None,
                error=ValueError("Production dispatch failed: release task not found."),
            )
            result["failed_ids"].append(int(record.id))
            continue
        if _clean(row.status).lower() in {"completed", "cancelled"}:
            result["skipped_ids"].append(int(record.id))
            continue
        try:
            _dispatch_one_pending_record(db, record, row)
            result["dispatched_ids"].append(int(record.id))
        except Exception as exc:  # noqa: BLE001
            _fail_pending_dispatch(db, record=record, row=row, error=exc)
            result["failed_ids"].append(int(record.id))
    return ServiceObjectResult(result)


def append_pending_production_dispatches(
    db: Session, result: dict[str, Any], *, max_records: int
) -> None:
    try:
        production_dispatch = dispatch_pending_production_deployments(
            db, max_records=max_records
        )
    except Exception as exc:  # noqa: BLE001
        result["production_dispatch_error"] = str(exc)[:1000]
        return
    result["production_dispatch"] = production_dispatch
    result["processed_count"] += int(production_dispatch.get("processed_count") or 0)
    result["failed_ids"].extend(production_dispatch.get("failed_ids") or [])
    result["pending_ids"].extend(production_dispatch.get("dispatched_ids") or [])
