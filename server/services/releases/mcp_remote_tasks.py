"""Release Task bridge for prod-only Remote MCP GCloud deploys."""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from server import config
from server.database import ReleaseTaskRow, utcnow
from server.schemas import ReleaseTaskPrGateOut
from server.services.releases.mcp_server_catalog import (
    MCP_REMOTE_CLOUD_RUN_REGION,
    MCP_REMOTE_CLOUD_RUN_SERVICE,
    MCP_REMOTE_ENDPOINT_URL,
    MCP_REMOTE_GCP_PROJECT_ID,
    MCP_REMOTE_PROD_CONFIRM_PHRASE,
)
from server.services.releases.mcp_server_helpers import clean, json_dump, record_event
from server.services.releases.mcp_server_models import McpServerReleaseRow

MCP_REMOTE_SOURCE_TYPE = "mcp_remote_gcloud"
MCP_PROJECT_KEY = "synapse-network-mcp-server"
MCP_SERVICE_KEY = "remote-mcp"
MCP_REPO_PATH = Path("/Users/cliff/workspace/agent/Synapse-Network-MCP-Server")
READY_STATUSES = {"ready_to_publish", "remote_prod_ready"}
RETRYABLE_FAILED_STATUS = "failed"
VERIFIED_STATUSES = {"remote_prod_verified", "completed"}
RESUME_STATUSES = {
    "remote_prod_deploying",
    "remote_prod_deployed",
    "openai_smoke_running",
}
GATE_ALLOWED_STATUSES = READY_STATUSES | {
    "remote_prod_deploying",
    "remote_prod_deployed",
    "openai_smoke_running",
    "remote_prod_verified",
    "completed",
}


class McpRemoteTaskMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    mcpServerId: int | None = None
    mcpServerReleaseId: int | None = None
    remoteEndpointUrl: str | None = None
    gcpProjectId: str | None = None
    cloudRunService: str | None = None
    cloudRunRegion: str | None = None
    targetCommitSha: str | None = None
    noStagingEnvironment: bool | None = None
    releaseTaskBridge: str | None = None
    mcpReleaseStatus: str | None = None
    resumeRunnerState: str | None = None


class McpRemoteTaskMetadataResult(BaseModel):
    task_metadata: McpRemoteTaskMetadata
    target_commit_sha: str


def is_mcp_remote_task(row: ReleaseTaskRow) -> bool:
    return clean(row.source_type) == MCP_REMOTE_SOURCE_TYPE or (
        clean(row.project_key) == MCP_PROJECT_KEY
        and clean(getattr(row, "service_key", None)) == MCP_SERVICE_KEY
    )


def task_metadata(row: ReleaseTaskRow) -> McpRemoteTaskMetadata:
    try:
        payload = json.loads(getattr(row, "metadata_json", None) or "{}")
    except json.JSONDecodeError:
        payload = {}
    return McpRemoteTaskMetadata.model_validate(
        payload if isinstance(payload, dict) else {}
    )


def create_metadata_for_task(db: Session, body: Any) -> McpRemoteTaskMetadataResult:
    release = _release_for_create(db, body)
    release_status = clean(release.status)
    target_commit_sha = _target_commit_sha(body)
    resume_runner_state = _prepare_release_for_task(db, release, body, release_status)
    return _metadata_result(release, target_commit_sha, resume_runner_state)


def _release_for_create(db: Session, body: Any) -> McpServerReleaseRow:
    if clean(getattr(body, "project_key", "")) != MCP_PROJECT_KEY:
        raise ValueError(
            "MCP remote release tasks must use project_key=synapse-network-mcp-server."
        )
    if clean(getattr(body, "service_key", "")) != MCP_SERVICE_KEY:
        raise ValueError("MCP remote release tasks must use service_key=remote-mcp.")
    if clean(getattr(body, "environment", "")).lower() != "production":
        raise ValueError(
            "MCP remote release task is production-only; staging does not exist."
        )
    if clean(getattr(body, "branch_name", "")) != "main":
        raise ValueError("MCP remote production deploy only allows branch main.")
    release_id = int(getattr(body, "mcp_server_release_id", 0) or 0)
    if not release_id:
        raise ValueError(
            "mcp_server_release_id is required for MCP remote release tasks."
        )
    release = db.get(McpServerReleaseRow, release_id)
    if release is None:
        raise ValueError("MCP server release not found.")
    if clean(release.status) not in READY_STATUSES | {RETRYABLE_FAILED_STATUS}:
        raise ValueError(
            "MCP server release must pass readiness before remote production deploy."
        )
    return release


def _target_commit_sha(body: Any) -> str:
    target_commit_sha = (
        clean(getattr(body, "target_commit_sha", None)) or _mcp_main_commit_sha()
    )
    if not target_commit_sha:
        raise ValueError("Unable to resolve MCP main commit sha.")
    return target_commit_sha


def _prepare_release_for_task(
    db: Session, release: McpServerReleaseRow, body: Any, release_status: str
) -> str | None:
    if release_status == "ready_to_publish":
        release.status = "remote_prod_ready"
        record_event(
            db,
            release,
            action="remote_prod_task_created",
            from_status="ready_to_publish",
            to_status="remote_prod_ready",
            actor=clean(getattr(body, "actor", "operator")) or "operator",
        )
        return None
    resume_runner_state = _retry_runner_state(release)
    release.status = "remote_prod_ready"
    record_event(
        db,
        release,
        action="remote_prod_retry_task_created",
        from_status="failed",
        to_status="remote_prod_ready",
        actor=clean(getattr(body, "actor", "operator")) or "operator",
        note="Retry Remote MCP production deploy after failed runner attempt.",
        metadata={"resume_runner_state": resume_runner_state}
        if resume_runner_state
        else {},
    )
    return resume_runner_state


def _metadata_result(
    release: McpServerReleaseRow,
    target_commit_sha: str,
    resume_runner_state: str | None,
) -> McpRemoteTaskMetadataResult:
    task_metadata_payload = {
        "mcpServerId": int(release.mcp_server_id) if release.mcp_server_id else None,
        "mcpServerReleaseId": int(release.id),
        "remoteEndpointUrl": MCP_REMOTE_ENDPOINT_URL,
        "gcpProjectId": MCP_REMOTE_GCP_PROJECT_ID,
        "cloudRunService": MCP_REMOTE_CLOUD_RUN_SERVICE,
        "cloudRunRegion": MCP_REMOTE_CLOUD_RUN_REGION,
        "targetCommitSha": target_commit_sha,
        "noStagingEnvironment": True,
        "releaseTaskBridge": MCP_REMOTE_SOURCE_TYPE,
    }
    if resume_runner_state:
        task_metadata_payload["resumeRunnerState"] = resume_runner_state
    return McpRemoteTaskMetadataResult(
        task_metadata=McpRemoteTaskMetadata.model_validate(task_metadata_payload),
        target_commit_sha=target_commit_sha,
    )


def gate_status(db: Session, row: ReleaseTaskRow) -> ReleaseTaskPrGateOut:
    gate = _base_gate(row)
    if _apply_static_gate_blocker(gate, row):
        return gate
    data = task_metadata(row)
    release = _release_for_gate(db, data, gate)
    if release is None:
        return gate
    return _finalize_gate(gate, row, release, data)


def _base_gate(row: ReleaseTaskRow) -> ReleaseTaskPrGateOut:
    return ReleaseTaskPrGateOut(
        branch_exists=clean(row.branch_name) == "main",
        pr_state="mcp_remote_prod",
        checks_status="unknown",
        environment_gate_summary=(
            "No staging version; prod-only MCP release requires Human Gate + "
            "readiness + secret preflight + prod smoke."
        ),
        blocked_reason="MCP remote production gate pending.",
    )


def _apply_static_gate_blocker(gate: ReleaseTaskPrGateOut, row: ReleaseTaskRow) -> bool:
    if clean(row.environment).lower() != "production":
        gate.blocked_reason = "MCP Remote GCloud release tasks are production-only."
        return True
    if clean(row.branch_name) == "main":
        return False
    gate.blocked_reason = "MCP Remote GCloud production deploy only allows branch main."
    return True


def _release_for_gate(
    db: Session, data: McpRemoteTaskMetadata, gate: ReleaseTaskPrGateOut
) -> McpServerReleaseRow | None:
    release_id = int(data.mcpServerReleaseId or 0)
    if not release_id:
        gate.blocked_reason = (
            "mcp_server_release_id is missing from release task metadata."
        )
        return None
    release = db.get(McpServerReleaseRow, release_id)
    if release is None:
        gate.blocked_reason = "MCP server release not found."
        return None
    if clean(release.status) not in GATE_ALLOWED_STATUSES:
        gate.blocked_reason = (
            "MCP server release must pass readiness before remote production deploy."
        )
        return None
    return release


def _finalize_gate(
    gate: ReleaseTaskPrGateOut,
    row: ReleaseTaskRow,
    release: McpServerReleaseRow,
    data: McpRemoteTaskMetadata,
) -> ReleaseTaskPrGateOut:
    target_commit = clean(getattr(row, "target_commit_sha", None)) or clean(
        data.targetCommitSha
    )
    current_commit = _mcp_main_commit_sha()
    gate.resolved_commit_sha = target_commit or current_commit
    if not current_commit:
        gate.blocked_reason = "Unable to resolve current MCP main commit sha."
        return gate
    if target_commit and target_commit != current_commit:
        gate.blocked_reason = "MCP production target commit is no longer current main."
        return gate
    gate.checks_status = "success"
    gate.checks_summary = f"MCP readiness passed for main {current_commit[:12]}."
    release_status = clean(release.status)
    gate.can_deploy_production = release_status in READY_STATUSES
    gate.blocked_reason = (
        None
        if gate.can_deploy_production
        else f"MCP release is already {release_status}."
    )
    return gate


def deploy_task(db: Session, row: ReleaseTaskRow, body: Any) -> ReleaseTaskPrGateOut:
    _validate_deploy_request(row, body)
    gate = gate_status(db, row)
    if not gate.can_deploy_production:
        raise ValueError(
            gate.blocked_reason or "MCP remote production gate is not ready."
        )
    release = _release_for_task(db, row)
    next_runner_status = _next_runner_status_for_task(row)
    _mark_deploying(db, row, release, body, next_runner_status)
    return gate


def _validate_deploy_request(row: ReleaseTaskRow, body: Any) -> None:
    if clean(getattr(body, "confirm_phrase", None)) != MCP_REMOTE_PROD_CONFIRM_PHRASE:
        raise ValueError(
            f"Remote MCP production deploy requires confirm_phrase={MCP_REMOTE_PROD_CONFIRM_PHRASE}."
        )
    if clean(row.status).lower() not in {"requested", "failed"}:
        raise ValueError(
            "Only requested or failed MCP remote release tasks can deploy."
        )


def _release_for_task(db: Session, row: ReleaseTaskRow) -> McpServerReleaseRow:
    release_id = int(task_metadata(row).mcpServerReleaseId or 0)
    release = db.get(McpServerReleaseRow, release_id)
    if release is None:
        raise ValueError("MCP server release not found.")
    return release


def _next_runner_status_for_task(row: ReleaseTaskRow) -> str:
    data = task_metadata(row)
    resume_runner_state = clean(data.resumeRunnerState)
    return (
        resume_runner_state
        if resume_runner_state in RESUME_STATUSES
        else "remote_prod_deploying"
    )


def _mark_deploying(
    db: Session,
    row: ReleaseTaskRow,
    release: McpServerReleaseRow,
    body: Any,
    next_runner_status: str,
) -> None:
    from_status = clean(release.status)
    resume_runner_state = clean(task_metadata(row).resumeRunnerState)
    release.status = next_runner_status
    release.failure_summary = None
    release.workflow_run_url = f"local-mcp-run:{next_runner_status}:{int(release.id)}"
    record_event(
        db,
        release,
        action="deploy_remote_prod",
        from_status=from_status,
        to_status=next_runner_status,
        actor=clean(getattr(body, "actor", "operator")) or "operator",
        note=clean(getattr(body, "note", None)) or None,
        metadata={
            "release_task_id": int(row.id),
            "remote_endpoint_url": MCP_REMOTE_ENDPOINT_URL,
            "cloud_run_service": MCP_REMOTE_CLOUD_RUN_SERVICE,
            "resume_runner_state": resume_runner_state or None,
        },
    )
    row.status = "deploying"
    row.operator = clean(getattr(body, "actor", "operator")) or "operator"
    row.updated_at = utcnow()
    row.metadata_json = json_dump(
        {
            **task_metadata(row).model_dump(exclude_none=True),
            "mcpReleaseStatus": next_runner_status,
        }
    )
    db.commit()
    db.refresh(row)


def update_terminal_status(
    db: Session, row: ReleaseTaskRow, next_status: str, operator: str, note: str | None
) -> ReleaseTaskPrGateOut:
    release_id = int(task_metadata(row).mcpServerReleaseId or 0)
    release = db.get(McpServerReleaseRow, release_id) if release_id else None
    if (
        next_status == "completed"
        and clean(getattr(release, "status", None)) not in VERIFIED_STATUSES
    ):
        raise ValueError(
            "MCP remote release task can complete only after remote prod smoke is verified."
        )
    row.status = next_status
    row.operator = operator
    if note is not None:
        row.note = clean(note) or None
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return gate_status(db, row)


def sync_linked_task_for_release(db: Session, release: McpServerReleaseRow) -> None:
    if clean(release.status) != "remote_prod_verified":
        return
    rows = (
        db.query(ReleaseTaskRow)
        .filter(
            ReleaseTaskRow.source_type == MCP_REMOTE_SOURCE_TYPE,
            ReleaseTaskRow.status == "deploying",
        )
        .all()
    )
    for row in rows:
        if int(task_metadata(row).mcpServerReleaseId or 0) != int(release.id):
            continue
        row.status = "completed"
        row.operator = row.operator or "mcp_remote_gcloud_runner"
        row.metadata_json = json_dump(
            {
                **task_metadata(row).model_dump(exclude_none=True),
                "mcpReleaseStatus": clean(release.status),
            }
        )
        row.updated_at = utcnow()


def _mcp_main_commit_sha() -> str | None:
    if config.E2E_MODE:
        return "e2e-mcp-main"
    git_bin = shutil.which("git")
    if not git_bin:
        return None
    try:
        result = subprocess.run(  # nosec B603
            [git_bin, "-C", str(MCP_REPO_PATH), "rev-parse", "main^{commit}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return clean(result.stdout) or None


def _retry_runner_state(release: McpServerReleaseRow) -> str | None:
    try:
        release_metadata = json.loads(release.metadata_json or "{}")
    except json.JSONDecodeError:
        release_metadata = {}
    last_failed = clean(release_metadata.get("last_failed_runner_state"))
    if last_failed in RESUME_STATUSES:
        return last_failed
    try:
        smoke_evidence = json.loads(release.smoke_evidence_json or "{}")
    except json.JSONDecodeError:
        smoke_evidence = {}
    remote_deploy = release_metadata.get("remote_prod_deploy") or {}
    if clean(smoke_evidence.get("status")) == "public_probe_passed":
        return "openai_smoke_running"
    if (
        isinstance(remote_deploy, dict)
        and clean(remote_deploy.get("status")) == "passed"
    ):
        return "remote_prod_deployed"
    return None
