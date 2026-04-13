"""Requirement-first workflow orchestration built on top of task runtime compatibility."""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import yaml
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from server.database import (
    SessionLocal,
    AgentRow,
    ApprovalRow,
    ApprovalRequestRow,
    ArtifactRow,
    RequirementDependencyRow,
    RequirementAcceptanceCheckRow,
    RequirementRow,
    StepInputBindingRow,
    TaskLogRow,
    TaskRow,
    WorkflowRunRow,
    WorkflowStepDependencyRow,
    WorkflowStepEventRow,
    WorkflowStepRow,
    utcnow,
)
from server import config
from server.services.agents_memory_sync import (
    push_task_completed as _am_push_task_completed,
    push_task_failed as _am_push_task_failed,
    push_requirement_completed as _am_push_requirement_completed,
)
from server.schemas import (
    ArtifactOut,
    DeliveryStateOut,
    IncidentRecordOut,
    RequirementDependencyOut,
    RequirementAcceptanceCheckOut,
    RequirementCreate,
    RequirementDetailOut,
    RequirementOut,
    RequirementPlanPatch,
    RequirementPatch,
    RequirementPublishRequest,
    RequirementRevisionRequest,
    WorkflowRunOut,
    WorkflowStepPatch,
    WorkflowStepOut,
)
from server.config import PROJECT_ROOT
from server.services.agent_loader import ensure_agents_loaded
from server.services.incidents import classify_artifact_incident, list_requirement_incidents
from server.services.copilot_sdk_state import (
    copilot_runtime_paths,
    load_runtime_state,
    parse_runtime_timestamp,
    save_runtime_state,
    task_output_dir,
)
from server.services.codex_cli import codex_runtime_paths, load_codex_state, save_codex_state, terminate_pid
from server.services.delivery_vcs import execute_requirement_delivery_vcs
from server.services.delivery_pr import sync_requirement_review_pr
from server.services.execution_resolver import suggest_task_execution
from server.services.acceptance import acceptance_contract_for_requirement, list_acceptance_dispatch_candidates, normalize_acceptance_contract
from server.services.requirement_approval import (
    approval_request_reviewer,
    evaluate_requirement_execution_approval,
    normalize_requirement_approval_contract,
    normalize_requirement_approval_status,
    requirement_approval_contract_for_requirement,
)
from server.services.project_policy import project_policy_summary_markdown, project_policy_to_dict, resolve_project_policies_for_target
from server.services.project_intelligence import resolve_requirement_routing, serialize_requirement
from server.services.requirement_family import (
    build_requirement_family_context,
    build_requirement_family_recommendation,
    find_active_requirement_for_family,
)
from server.services.requirement_sources import normalize_requirement_intake_metadata, requirement_intake_metadata_for_requirement
from server.services.task_metadata import task_metadata_for_agent
from server.services.workflow_planner import WorkflowRoleAssignments, build_planner_output


RUNNING_STEP_STATUSES = {"running", "waiting_approval"}
TERMINAL_STEP_STATUSES = {"completed", "failed", "cancelled"}
SCHEDULABLE_STEP_STATUSES = {"pending", "ready", "blocked"}
MUTATING_STEP_TYPES = {"implementation", "bugfix"}
NON_MUTATING_STEP_TYPES = {"research", "plan", "validate", "synthesis", "review", "test"}
DELETED_REQUIREMENT_STATUSES = {"deleted"}
DELETED_WORKFLOW_STATUSES = {"deleted"}
DELETED_STEP_STATUSES = {"deleted"}
DELETED_TASK_STATUSES = {"deleted"}
PRIMARY_GROWING_PROJECT = "/Users/cliff/workspace/agent/Synapse-Network-Growing"
PRIMARY_SYNAPSE_PROJECT = "/Users/cliff/workspace/agent/Synapse-Network"
MAX_BUGFIX_BRANCH_DEPTH = 5
REPEATED_ERROR_CIRCUIT_BREAKER_THRESHOLD = 3
CIRCUIT_BREAKER_REQUIREMENT_SOURCE = "bugfix_circuit_breaker"
_TIER_ORDER = {"mini": 0, "standard": 1, "max": 2}
INFRA_INCIDENT_ERROR_MARKERS = (
    "session not found",
    "session.resume failed",
    "copilot sdk",
    "timeout",
    "timed out",
    "orphaned dispatch",
    "tool_use",
    "tool_result",
    "not authorized",
    "unauthorized",
    "permission",
    "rate limit",
    "connection refused",
    "failed to connect",
)
_AUTO_PLAN_LOCK = threading.Lock()

import logging as _logging
_logger = _logging.getLogger("ops-dashboard.workflow_orchestrator")


def _should_inline_auto_plan(db: Session) -> bool:
    bind = db.get_bind()
    url = getattr(bind, "url", None)
    if url is None:
        return False
    if str(getattr(url, "drivername", "")).split("+", 1)[0] != "sqlite":
        return False
    database = str(getattr(url, "database", "") or "")
    return database in {"", ":memory:"}


def _github_https_remote(remote_url: str | None) -> str | None:
    value = str(remote_url or "").strip()
    if not value:
        return None
    if value.startswith("git@github.com:"):
        path = value.split(":", 1)[1]
        if path.endswith(".git"):
            path = path[:-4]
        return f"https://github.com/{path}"
    match = re.match(r"https?://github\.com/(?P<path>.+?)(?:\.git)?/?$", value)
    if match:
        path = match.group("path")
        return f"https://github.com/{path}"
    return None


def _build_delivery_compare_url(vcs_payload: dict[str, Any], branch_name: str | None, base_branch: str | None) -> str | None:
    if not isinstance(vcs_payload, dict):
        return None
    branch = str(branch_name or "").strip()
    base = str(base_branch or "").strip()
    if not branch or not base:
        return None
    repositories = vcs_payload.get("repositories") or []
    if not isinstance(repositories, list):
        return None
    for item in repositories:
        if not isinstance(item, dict):
            continue
        remote_base = _github_https_remote(item.get("remote_url"))
        if remote_base:
            return f"{remote_base}/compare/{base}...{branch}"
    return None


def _build_delivery_pr_metadata(
    requirement: RequirementRow,
    payload: dict[str, Any],
    compare_url: str | None,
) -> dict[str, Any]:
    branch_name = str(payload.get("branch_name") or "").strip() or None
    base_branch = str(payload.get("base_branch") or "").strip() or None
    vcs_status = str(payload.get("vcs_status") or "").strip() or None
    repositories = payload.get("vcs_repositories") or []
    delivered_repos = 0
    if isinstance(repositories, list):
        delivered_repos = sum(1 for item in repositories if isinstance(item, dict) and str(item.get("status") or "") == "delivered")
    title = f"ops(req-{requirement.id}): {str(requirement.title or '').strip() or 'review-ready bundle'}"
    summary = str(payload.get("review_surface_summary") or "").strip() or f"Requirement #{requirement.id} review-ready bundle."
    return {
        "title": title[:120],
        "head_branch": branch_name,
        "base_branch": base_branch,
        "remote_name": str(payload.get("vcs_remote_name") or "").strip() or None,
        "status": vcs_status,
        "draft": True,
        "compare_url": compare_url,
        "delivered_repository_count": delivered_repos,
        "summary": summary,
    }


def _latest_delivery_sha(vcs_payload: dict[str, Any], key: str) -> str | None:
    repositories = vcs_payload.get("repositories") or []
    if not isinstance(repositories, list):
        return None
    for item in repositories:
        if not isinstance(item, dict):
            continue
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return None


def _latest_delivery_timestamp(vcs_payload: dict[str, Any], key: str) -> str | None:
    repositories = vcs_payload.get("repositories") or []
    if not isinstance(repositories, list):
        return None
    latest: datetime | None = None
    latest_raw: str | None = None
    for item in repositories:
        if not isinstance(item, dict):
            continue
        raw = str(item.get(key) or "").strip()
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if latest is None or parsed > latest:
            latest = parsed
            latest_raw = raw
    return latest_raw


def _build_promotion_checklist(payload: dict[str, Any], compare_url: str | None) -> list[dict[str, Any]]:
    pending_checks = [str(item) for item in (payload.get("pending_checks") or []) if str(item).strip()]
    blockers = [str(item) for item in (payload.get("publish_blockers") or []) if str(item).strip()]
    vcs_status = str(payload.get("vcs_status") or "").strip()
    review_status = str(payload.get("review_status") or "").strip()
    release_mode = str(payload.get("release_mode") or "").strip()
    return [
        {
            "key": "branch_delivery",
            "label": "Branch delivery pushed",
            "status": "completed" if vcs_status == "delivered" else "blocked",
            "detail": "Review branch committed and pushed to remote." if vcs_status == "delivered" else "Delivery branch push is incomplete.",
        },
        {
            "key": "compare_url",
            "label": "Compare URL ready",
            "status": "completed" if compare_url else "pending",
            "detail": compare_url or "No GitHub compare URL could be derived from the configured remote.",
        },
        {
            "key": "required_checks",
            "label": "Required checks confirmed",
            "status": "completed" if not pending_checks else "pending",
            "detail": "All required checks are confirmed." if not pending_checks else f"Pending checks: {', '.join(pending_checks)}",
        },
        {
            "key": "review_bundle",
            "label": "Review bundle prepared",
            "status": "completed" if review_status == "review_ready" else "blocked",
            "detail": "Review-ready bundle is available for promotion." if review_status == "review_ready" else "Review-ready bundle is not yet available.",
        },
        {
            "key": "release_gate",
            "label": "Release mode allows promotion",
            "status": "completed" if release_mode == "manual" and not blockers else ("blocked" if blockers else "pending"),
            "detail": "Manual release mode allows promotion after operator confirmation."
            if release_mode == "manual" and not blockers
            else ("Publish blockers must be cleared before promotion." if blockers else f"Release mode is `{release_mode or 'unknown'}`."),
        },
    ]


def _normalize_runtime_tier(value: str | None) -> str:
    tier = str(value or "").strip().lower()
    if tier in _TIER_ORDER:
        return tier
    return "standard"


def _tier_transition(current_tier: str, requested_tier: str) -> str:
    current = _normalize_runtime_tier(current_tier)
    requested = _normalize_runtime_tier(requested_tier)
    return requested if _TIER_ORDER[requested] >= _TIER_ORDER[current] else current


def _normalize_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _step_execution_profile(step: WorkflowStepRow) -> dict[str, Any]:
    payload = _json_loads(getattr(step, "execution_profile_json", None), {})
    return payload if isinstance(payload, dict) else {}


def _write_step_execution_profile(step: WorkflowStepRow, payload: dict[str, Any]) -> None:
    step.execution_profile_json = _json_dumps(payload or {})


def _default_requirement_approval_status(requirement: RequirementRow) -> str:
    contract = requirement_approval_contract_for_requirement(requirement)
    if str(contract.get("approval_mode") or "") == "waived":
        return "waived"
    return "pending_approval"


def _record_requirement_approval_artifact(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow | None,
    content_summary: str,
    payload: dict[str, Any],
) -> None:
    _create_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
        artifact_type="requirement_approval_state",
        content_summary=content_summary,
        human_readable_body=str(payload.get("reason") or payload.get("approval_status") or "requirement approval updated"),
        machine_readable_payload=payload,
    )


def _sync_requirement_execution_approval(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow | None,
    planner_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = requirement_approval_contract_for_requirement(requirement)
    decision = evaluate_requirement_execution_approval(
        requirement,
        planner_output=planner_output,
        workflow_run=workflow_run,
    )
    reviewer = str(decision.get("reviewer") or approval_request_reviewer(requirement, contract))
    pending_request = db.query(ApprovalRequestRow).filter(
        ApprovalRequestRow.requirement_id == requirement.id,
        ApprovalRequestRow.approval_type == "requirement_execution_approval",
        ApprovalRequestRow.status == "pending",
    ).order_by(ApprovalRequestRow.id.desc()).first()

    target_status = normalize_requirement_approval_status(decision.get("approval_status"))
    if target_status in {"approved", "waived"}:
        requirement.approval_status = target_status
        requirement.approval_requested_at = None
        requirement.approved_at = requirement.approved_at or utcnow()
        if pending_request is not None:
            pending_request.status = "approved"
            pending_request.reviewer = "system"
            pending_request.decided_at = utcnow()
            pending_request.comment = str(decision.get("reason") or "Automatically approved by requirement approval contract")
        _record_requirement_approval_artifact(
            db,
            requirement=requirement,
            workflow_run=workflow_run,
            content_summary=f"Requirement #{requirement.id} {target_status}",
            payload={
                "approval_status": target_status,
                "reason": str(decision.get("reason") or ""),
                "approval_contract": contract,
                "approval_context": dict(decision.get("context") or {}),
                "required_approver_roles": list(decision.get("required_approver_roles") or contract.get("required_approver_roles") or []),
                "approval_source": str(decision.get("approval_source") or "auto"),
                "approval_router": dict(decision.get("approval_router") or {}),
                "approval_recommendation": dict(decision.get("approval_recommendation") or {}),
            },
        )
        return decision

    requirement.approval_status = "pending_approval"
    requirement.approved_at = None
    requirement.approval_requested_at = requirement.approval_requested_at or utcnow()
    if pending_request is None:
        db.add(
            ApprovalRequestRow(
                requirement_id=requirement.id,
                workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
                step_id=None,
                approval_type="requirement_execution_approval",
                status="pending",
                reviewer=reviewer,
                comment=str(
                    (decision.get("approval_recommendation") or {}).get("reason")
                    or decision.get("reason")
                    or "Requirement requires approval before automatic execution"
                ),
            )
        )
    _record_requirement_approval_artifact(
        db,
        requirement=requirement,
        workflow_run=workflow_run,
        content_summary=f"Requirement #{requirement.id} pending approval",
        payload={
            "approval_status": "pending_approval",
            "reason": str(decision.get("reason") or ""),
            "approval_contract": contract,
            "approval_context": dict(decision.get("context") or {}),
            "required_approver_roles": list(decision.get("required_approver_roles") or contract.get("required_approver_roles") or []),
            "reviewer": reviewer,
            "approval_source": str(decision.get("approval_source") or "human"),
            "approval_router": dict(decision.get("approval_router") or {}),
            "approval_recommendation": dict(decision.get("approval_recommendation") or {}),
        },
    )
    return decision


def _workflow_run_has_running_steps(db: Session, workflow_run_id: int) -> bool:
    return (
        db.query(WorkflowStepRow)
        .filter(
            WorkflowStepRow.workflow_run_id == workflow_run_id,
            WorkflowStepRow.status.in_(tuple(RUNNING_STEP_STATUSES)),
        )
        .count()
        > 0
    )


def _select_preferred_workflow_run(db: Session, requirement: RequirementRow) -> WorkflowRunRow | None:
    runs = (
        db.query(WorkflowRunRow)
        .filter(WorkflowRunRow.requirement_id == requirement.id)
        .order_by(WorkflowRunRow.plan_version.desc(), WorkflowRunRow.id.desc())
        .all()
    )
    if not runs:
        return None

    live_runs = [run for run in runs if _workflow_run_has_running_steps(db, _as_int(run.id))]
    if live_runs:
        return live_runs[0]

    if requirement.active_workflow_run_id:
        active = next((run for run in runs if _as_int(run.id) == _as_int(requirement.active_workflow_run_id)), None)
        if active is not None and str(active.status) not in {"completed", "cancelled", "failed", "deleted"}:
            return active

    for status in ("running", "paused", "pending"):
        for run in runs:
            if str(run.status) == status:
                return run

    if str(requirement.status or "") in {"done", "needs_revision"}:
        for status in ("completed", "failed", "cancelled"):
            for run in runs:
                if str(run.status) == status:
                    return run

    return None


def _reconcile_active_workflow_run(db: Session, requirement: RequirementRow) -> WorkflowRunRow | None:
    run = _select_preferred_workflow_run(db, requirement)
    if run is None:
        if requirement.active_workflow_run_id is not None:
            requirement.active_workflow_run_id = None
        return None

    if requirement.active_workflow_run_id != _as_int(run.id):
        requirement.active_workflow_run_id = _as_int(run.id)

    has_running_steps = _workflow_run_has_running_steps(db, _as_int(run.id))
    run_status = str(run.status or "")
    if has_running_steps and requirement.status not in {"in_progress", "paused", "blocked", "deleted"}:
        requirement.status = "in_progress"
        requirement.started_at = requirement.started_at or utcnow()
    elif run_status == "paused" and requirement.status == "in_progress":
        requirement.status = "paused"
        requirement.completed_at = None
    elif run_status == "pending" and not has_running_steps and requirement.status == "in_progress":
        requirement.status = "ready"
        requirement.started_at = None

    return run


def _clear_role_sessions() -> None:
    """Clear runtime role-session caches when a requirement reaches a terminal state."""
    try:
        from server.services.task_runtime import clear_runtime_session_caches
        clear_runtime_session_caches()
    except Exception:
        _logger.debug("Failed to clear role sessions (non-critical)", exc_info=True)


def _task_output_dir_for_snapshot(task: TaskRow) -> Path | None:
    output_path = str(task.output_path or "").strip()
    if output_path:
        return Path(output_path).resolve().parent
    task_id = int(getattr(cast(Any, task), "id", 0) or 0)
    agent_id = str(getattr(cast(Any, task), "agent_id", "unknown") or "unknown")
    if task_id <= 0:
        return None
    return task_output_dir(PROJECT_ROOT, agent_id, task_id)


def _parse_git_diff_files(diff_text: str, *, target_path: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current:
                files.append(current)
            current = {
                "filename": "",
                "additions": 0,
                "deletions": 0,
                "patch": "",
                "target_project_path": target_path,
            }
            continue
        if current is None:
            continue
        if line.startswith("+++ b/"):
            current["filename"] = line[6:].rstrip("\n")
        elif line.startswith("+") and not line.startswith("+++"):
            current["additions"] += 1
            current["patch"] += line
        elif line.startswith("-") and not line.startswith("---"):
            current["deletions"] += 1
            current["patch"] += line
        else:
            current["patch"] += line
    if current:
        files.append(current)
    return [item for item in files if item["filename"]]


def _git_dirty_files(target_dir: Path) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "HEAD", "--name-only"],
        cwd=str(target_dir),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    dirty_files: list[str] = []
    for raw_line in result.stdout.splitlines():
        path = raw_line.strip()
        if not path:
            continue
        dirty_files.append(path)
    return sorted(set(dirty_files))


def _file_content_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dirty_file_hashes(target_dir: Path, dirty_files: list[str]) -> dict[str, str | None]:
    hashes: dict[str, str | None] = {}
    for relative_path in dirty_files:
        candidate = (target_dir / relative_path).resolve()
        hashes[relative_path] = _file_content_sha256(candidate)
    return hashes


def capture_task_file_change_baseline(
    db: Session,
    task: TaskRow,
    requirement: RequirementRow | None = None,
    step: WorkflowStepRow | None = None,
) -> None:
    output_dir = _task_output_dir_for_snapshot(task)
    if output_dir is None:
        return
    baseline_path = output_dir / "file-changes-baseline.json"
    if baseline_path.exists():
        return
    if step is None and task.workflow_steps:
        step = task.workflow_steps[0]
    if requirement is None and step is not None:
        requirement = _require_requirement(db, int(step.requirement_id))
    if requirement is None:
        return
    target_paths = _split_target_project_paths(
        _effective_target_project_path(
            db,
            requirement,
            step_type=str(step.step_type or "") if step is not None else None,
        )
    )
    if not target_paths:
        return
    baselines: list[dict[str, Any]] = []
    for target_path in target_paths:
        target_dir = Path(target_path)
        if not target_dir.is_dir():
            continue
        dirty_files = _git_dirty_files(target_dir)
        baselines.append(
            {
                "target_project_path": target_path,
                "dirty_files": dirty_files,
                "dirty_file_hashes": _dirty_file_hashes(target_dir, dirty_files),
            }
        )
    if not baselines:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(
            {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "task_id": int(task.id),
                "step_id": int(step.id) if step is not None else None,
                "baseline_mode": "content_hash",
                "project_baselines": baselines,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _snapshot_file_changes(db: Session, task: TaskRow, requirement: RequirementRow, step: WorkflowStepRow | None = None) -> None:
    """Capture task-scoped file changes using a dirty-file baseline to avoid worktree pollution."""
    try:
        output_dir = _task_output_dir_for_snapshot(task)
        if output_dir is None:
            return
        target_paths = _split_target_project_paths(
            _effective_target_project_path(
                db,
                requirement,
                step_type=str(step.step_type or "") if step is not None else None,
            )
        )
        if not target_paths:
            return
        baseline_payload: dict[str, Any] = {}
        baseline_path = output_dir / "file-changes-baseline.json"
        if baseline_path.exists():
            try:
                baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
            except Exception:
                baseline_payload = {}
        baseline_by_project: dict[str, dict[str, Any]] = {}
        for item in baseline_payload.get("project_baselines") or []:
            if not isinstance(item, dict):
                continue
            target_project_path = str(item.get("target_project_path") or "").strip()
            if not target_project_path:
                continue
            baseline_by_project[target_project_path] = {
                "dirty_files": {
                    str(path).strip()
                    for path in (item.get("dirty_files") or [])
                    if str(path).strip()
                },
                "dirty_file_hashes": {
                    str(path).strip(): value
                    for path, value in (item.get("dirty_file_hashes") or {}).items()
                    if str(path).strip()
                },
            }
        changed_files: list[dict[str, Any]] = []
        project_snapshots: list[dict[str, Any]] = []
        for target_path in target_paths:
            target_dir = Path(target_path)
            if not target_dir.is_dir():
                continue
            result = subprocess.run(
                ["git", "diff", "HEAD", "--unified=5"],
                cwd=str(target_dir), capture_output=True, text=True, timeout=15,
            )
            diff_text = result.stdout

            repo_changed_files = _parse_git_diff_files(diff_text, target_path=target_path)
            baseline_entry = baseline_by_project.get(target_path, {})
            dirty_before = baseline_entry.get("dirty_files") or set()
            dirty_hashes = baseline_entry.get("dirty_file_hashes") or {}
            filtered_files: list[dict[str, Any]] = []
            for item in repo_changed_files:
                relative_path = str(item.get("filename") or "").strip()
                if not relative_path:
                    continue
                if relative_path not in dirty_before:
                    filtered_files.append(item)
                    continue
                current_hash = _file_content_sha256((target_dir / relative_path).resolve())
                baseline_hash = dirty_hashes.get(relative_path)
                if current_hash != baseline_hash:
                    filtered_files.append(item)
            repo_changed_files = filtered_files
            changed_files.extend(repo_changed_files)
            project_snapshots.append(
                {
                    "target_project_path": target_path,
                    "changed_file_count": len(repo_changed_files),
                    "changed_files": repo_changed_files,
                    "project_policy_summary": project_policy_summary_markdown(db, target_path),
                }
            )

        step_type = str(step.step_type or "") if step is not None else ""
        if not changed_files and step_type in NON_MUTATING_STEP_TYPES:
            snapshot_path = output_dir / "file-changes.json"
            if snapshot_path.exists():
                snapshot_path.unlink()
            return

        snapshot = {
            "changed_files": changed_files,
            "target_project_path": project_snapshots[0]["target_project_path"] if project_snapshots else target_paths[0],
            "changed_target_project_paths": [
                item["target_project_path"]
                for item in project_snapshots
                if int(item.get("changed_file_count") or 0) > 0
            ],
            "project_snapshots": project_snapshots,
            "all_target_project_paths": target_paths,
            "source": "snapshot",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "task_id": int(task.id),
            "step_id": int(step.id) if step is not None else None,
            "baseline_captured_at": baseline_payload.get("captured_at"),
            "baseline_mode": baseline_payload.get("baseline_mode") or "legacy",
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "file-changes.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2)
        )
        _logger.info(
            "Saved file-changes snapshot for task %s: %d files changed across %d target projects",
            task.id, len(changed_files), len(project_snapshots),
        )
    except Exception:
        _logger.debug("Failed to snapshot file changes for task %s (non-critical)", task.id, exc_info=True)


def _record_step_event(db: Session, step_id: int, event_type: str, detail: str | None = None):
    db.add(WorkflowStepEventRow(step_id=step_id, event_type=event_type, detail=detail))


def _normalize_error_text(error_text: str) -> str:
    normalized = re.sub(r"\d{4,}", "<num>", error_text.strip().lower())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized[:1000]


def _error_fingerprint(error_text: str) -> str:
    normalized = _normalize_error_text(error_text)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _root_failure_step_id(db: Session, step: WorkflowStepRow) -> int:
    current = step
    visited: set[int] = set()
    while current.branch_from_step_id:
        current_id = _as_int(current.id)
        if current_id in visited:
            break
        visited.add(current_id)
        parent = db.query(WorkflowStepRow).filter(WorkflowStepRow.id == current.branch_from_step_id).first()
        if parent is None:
            break
        current = parent
    return _as_int(current.id)


def _step_root_failure_step_id(db: Session, step_id: int | None) -> int | None:
    if step_id is None:
        return None
    step = db.query(WorkflowStepRow).filter(WorkflowStepRow.id == step_id).first()
    if step is None:
        return None
    return _root_failure_step_id(db, step)


def _bugfix_branch_depth(db: Session, workflow_run_id: int, failed_step: WorkflowStepRow) -> int:
    root_step_id = _root_failure_step_id(db, failed_step)
    depth = 0
    bugfix_steps = db.query(WorkflowStepRow).filter(
        WorkflowStepRow.workflow_run_id == workflow_run_id,
        WorkflowStepRow.step_type == "bugfix",
    ).all()
    for step in bugfix_steps:
        if _step_root_failure_step_id(db, cast(Any, step).id) == root_step_id:
            depth += 1
    return depth


def _repeated_error_count(
    db: Session,
    requirement_id: int,
    workflow_run_id: int | None,
    root_failure_step_id: int,
    error_fingerprint: str,
) -> int:
    query = db.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == "bug_report",
    )
    if workflow_run_id is not None:
        query = query.filter(ArtifactRow.workflow_run_id == workflow_run_id)
    artifacts = query.order_by(ArtifactRow.id.desc()).limit(20).all()
    count = 0
    for artifact in artifacts:
        payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
        if not isinstance(payload, dict):
            continue
        if payload.get("root_failure_step_id") != root_failure_step_id:
            continue
        if payload.get("error_fingerprint") != error_fingerprint:
            continue
        count += 1
    return count


def _bugfix_circuit_breaker_reason(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    failed_step: WorkflowStepRow,
    error_text: str,
) -> str | None:
    root_step_id = _root_failure_step_id(db, failed_step)
    candidate_depth = _bugfix_branch_depth(db, _as_int(workflow_run.id), failed_step) + 1
    if candidate_depth > MAX_BUGFIX_BRANCH_DEPTH:
        return (
            f"Bugfix loop depth exceeded for root step #{root_step_id}: "
            f"attempted branch depth {candidate_depth} > max {MAX_BUGFIX_BRANCH_DEPTH}."
        )

    fingerprint = _error_fingerprint(error_text)
    repeated_count = _repeated_error_count(
        db,
        _as_int(requirement.id),
        _as_int(workflow_run.id),
        root_step_id,
        fingerprint,
    )
    if repeated_count >= REPEATED_ERROR_CIRCUIT_BREAKER_THRESHOLD:
        return (
            "Repeated identical failure detected for bugfix loop "
            f"(root step #{root_step_id}, count={repeated_count}, fingerprint={fingerprint[:12]})."
        )
    return None


def _populate_handoff_summary(step: WorkflowStepRow, task: TaskRow):
    output = (task.output_content or "").strip()
    if not output:
        return
    summary_lines = output.split("\n")[:10]
    step.handoff_summary_markdown = "\n".join(summary_lines)


def _normalize_target_project_path(raw_path: str | None) -> str | None:
    if raw_path is None:
        return None

    lines: list[str] = []
    seen: set[str] = set()
    for line in raw_path.splitlines():
        candidate = line.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        lines.append(candidate)

    if not lines:
        return None
    return "\n".join(lines)


def _split_target_project_paths(raw_path: str | None) -> list[str]:
    normalized = _normalize_target_project_path(raw_path)
    if not normalized:
        return []
    return [line.strip() for line in normalized.splitlines() if line.strip()]


def _merge_target_project_paths(*raw_paths: str | None) -> str | None:
    merged: list[str] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        normalized = _normalize_target_project_path(raw_path)
        if not normalized:
            continue
        for candidate in normalized.splitlines():
            item = candidate.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            merged.append(item)
    if not merged:
        return None
    return "\n".join(merged)


def _implementation_plan_payload(db: Session, requirement_id: int) -> dict[str, Any]:
    artifact = _latest_artifact(db, requirement_id, "implementation_plan")
    payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
    return payload if isinstance(payload, dict) else {}


def _delivery_expectation_payload(db: Session, requirement_id: int) -> dict[str, Any]:
    payload = _implementation_plan_payload(db, requirement_id)
    expectation = payload.get("delivery_expectation") or {}
    return expectation if isinstance(expectation, dict) else {}


def _effective_target_project_path(
    db: Session,
    requirement: RequirementRow,
    *,
    step_type: str | None = None,
) -> str | None:
    plan_payload = _implementation_plan_payload(db, _as_int(requirement.id))
    preferred = _normalize_target_project_path(str(plan_payload.get("target_project_path") or "") or None)
    if preferred:
        return preferred
    return _normalize_target_project_path(getattr(requirement, "target_project_path", None))


def _primary_target_directory(
    db: Session,
    requirement: RequirementRow,
    *,
    step_type: str | None = None,
) -> str | None:
    target_path = _effective_target_project_path(db, requirement, step_type=step_type)
    paths = _split_target_project_paths(target_path)
    return paths[0] if paths else None


def _is_code_change_file(filename: str) -> bool:
    normalized = str(filename or "").strip().lstrip("./")
    if not normalized:
        return False
    lowered = normalized.lower()
    if lowered.endswith((".md", ".txt", ".rst", ".adoc")):
        return False
    if lowered == "readme" or lowered == "readme.md" or lowered == "changelog.md":
        return False
    if lowered.startswith(("docs/", "roles/", "campaigns/", "demos/")):
        return False
    return True


def _load_task_file_changes(task: TaskRow) -> dict[str, Any]:
    output_path = str(task.output_path or "").strip()
    if not output_path:
        return {}
    cache_file = Path(output_path).parent / "file-changes.json"
    if not cache_file.exists():
        return {}
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_task_file_change_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload or {})
    if not normalized:
        normalized["legacy_snapshot"] = False
        return normalized
    baseline_captured_at = str(normalized.get("baseline_captured_at") or "").strip()
    if baseline_captured_at:
        normalized["legacy_snapshot"] = False
        return normalized
    normalized["legacy_snapshot"] = True
    normalized["changed_files"] = []
    normalized["project_snapshots"] = []
    normalized["changed_target_project_paths"] = []
    normalized["change_warning"] = (
        "This task was captured before task-scoped diff baselines were introduced. "
        "Re-run the step to collect a clean task-only file change snapshot."
    )
    return normalized


def _task_changed_files_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    changed_files_raw = payload.get("changed_files") or []
    return [
        {
            "filename": str(item.get("filename") or "").strip(),
            "additions": int(item.get("additions") or 0),
            "deletions": int(item.get("deletions") or 0),
            "patch": str(item.get("patch") or ""),
            "target_project_path": str(item.get("target_project_path") or "").strip() or None,
        }
        for item in changed_files_raw
        if isinstance(item, dict) and str(item.get("filename") or "").strip()
    ]


def _task_changed_output_files(changed_files: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    output_files: list[str] = []
    for item in changed_files:
        filename = str(item.get("filename") or "").strip()
        if not filename or filename in seen:
            continue
        seen.add(filename)
        output_files.append(filename)
    return output_files


def _task_has_tracked_repo_changes(task: TaskRow) -> bool:
    payload = _normalize_task_file_change_payload(_load_task_file_changes(task))
    changed_files = _task_changed_files_from_payload(payload)
    return bool(changed_files)


def _step_requires_branch_delivery(step: WorkflowStepRow) -> bool:
    return str(step.step_type or "") in MUTATING_STEP_TYPES


def _block_unexpected_non_mutating_repo_changes(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
    task: TaskRow,
) -> None:
    payload = _normalize_task_file_change_payload(_load_task_file_changes(task))
    changed_files = _task_changed_files_from_payload(payload)
    output_files = _task_changed_output_files(changed_files)
    reason = (
        f"{step.step_type} step modified tracked repo files even though this step is non-mutating: "
        + ", ".join(output_files[:5] or ["<unknown>"])
    )
    step.status = "blocked"
    step.completed_at = None
    workflow_run.status = "paused"
    workflow_run.completed_at = None
    requirement.status = "blocked"
    requirement.completed_at = None
    _record_step_event(db, _as_int(step.id), "policy_violation", reason)
    _create_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id),
        step_id=_as_int(step.id),
        producer_step_id=_as_int(step.id),
        artifact_type="policy_violation",
        content_summary=reason[:200],
        human_readable_body="# Policy Violation\n\n" + reason,
        machine_readable_payload={
            "requirement_id": _as_int(requirement.id),
            "workflow_run_id": _as_int(workflow_run.id),
            "step_id": _as_int(step.id),
            "task_id": _as_int(task.id),
            "step_type": str(step.step_type or ""),
            "changed_files": changed_files,
            "recorded_at": utcnow().isoformat(),
        },
    )


def _record_delivery_blocker(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
    *,
    vcs_payload: dict[str, Any],
    pr_payload: dict[str, Any] | None = None,
) -> None:
    blockers = [
        str(item).strip()
        for item in [
            *(vcs_payload.get("blockers") or []),
            *((pr_payload or {}).get("blockers") or []),
        ]
        if str(item).strip()
    ]
    summary = "; ".join(blockers) or "delivery branch or review PR sync failed"
    _create_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id),
        step_id=_as_int(step.id),
        producer_step_id=_as_int(step.id),
        artifact_type="delivery_blocker",
        content_summary=summary[:200],
        human_readable_body=summary,
        machine_readable_payload={
            "requirement_id": _as_int(requirement.id),
            "workflow_run_id": _as_int(workflow_run.id),
            "step_id": _as_int(step.id),
            "vcs_delivery": vcs_payload,
            "review_pr": pr_payload or {},
            "recorded_at": utcnow().isoformat(),
        },
    )


def _sync_step_delivery_branch(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
) -> tuple[bool, dict[str, Any], dict[str, Any]]:
    delivery_contract = _delivery_contract_payload(db, _as_int(requirement.id))
    if not delivery_contract:
        return True, {}, {}
    vcs_payload, _artifact = _execute_requirement_vcs_delivery(db, requirement, workflow_run, step)
    vcs_blockers = [str(item).strip() for item in (vcs_payload.get("blockers") or []) if str(item).strip()]
    pr_payload: dict[str, Any] = {}
    if not vcs_blockers:
        pr_payload, _pr_artifact = _sync_requirement_review_pr(
            db,
            requirement,
            workflow_run,
            step,
            delivery_contract=delivery_contract,
            vcs_payload=vcs_payload,
        )
    pr_blockers = [str(item).strip() for item in (pr_payload.get("blockers") or []) if str(item).strip()]
    if vcs_blockers or pr_blockers:
        step.status = "blocked"
        step.completed_at = None
        workflow_run.status = "paused"
        workflow_run.completed_at = None
        requirement.status = "blocked"
        requirement.completed_at = None
        _record_step_event(db, _as_int(step.id), "delivery_blocked", "; ".join(vcs_blockers + pr_blockers))
        _record_delivery_blocker(
            db,
            requirement,
            workflow_run,
            step,
            vcs_payload=vcs_payload,
            pr_payload=pr_payload,
        )
        _record_delivery_state(
            db,
            requirement,
            workflow_run,
            review_status="blocked",
            publish_status="blocked",
            vcs_payload=vcs_payload,
            pr_payload=pr_payload,
        )
        return False, vcs_payload, pr_payload
    _record_delivery_state(
        db,
        requirement,
        workflow_run,
        review_status="planned",
        publish_status="planned",
        vcs_payload=vcs_payload,
        pr_payload=pr_payload,
    )
    return True, vcs_payload, pr_payload


def _requirement_task_outputs(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if workflow_run is None:
        return [], []
    step_rows = db.query(WorkflowStepRow).filter(
        WorkflowStepRow.workflow_run_id == workflow_run.id
    ).order_by(WorkflowStepRow.sequence_no.asc(), WorkflowStepRow.id.asc()).all()
    task_ids = [
        int(getattr(cast(Any, step), "compatibility_task_id", 0) or 0)
        for step in step_rows
        if int(getattr(cast(Any, step), "compatibility_task_id", 0) or 0) > 0
    ]
    if not task_ids:
        return [], []
    task_rows = db.query(TaskRow).filter(TaskRow.id.in_(task_ids)).all()
    tasks_by_id = {int(task.id): task for task in task_rows}
    task_outputs: list[dict[str, Any]] = []
    merged_index: dict[str, dict[str, Any]] = {}
    for step in step_rows:
        task_id = int(getattr(cast(Any, step), "compatibility_task_id", 0) or 0)
        if task_id <= 0:
            continue
        task = tasks_by_id.get(task_id)
        if task is None:
            continue
        payload = _normalize_task_file_change_payload(_load_task_file_changes(task))
        changed_files = _task_changed_files_from_payload(payload)
        output_files = _task_changed_output_files(changed_files)
        task_outputs.append(
            {
                "task_id": task_id,
                "step_id": int(step.id),
                "step_key": str(step.step_key or ""),
                "step_type": str(step.step_type or ""),
                "step_title": str(step.title or ""),
                "task_status": str(task.status or "pending"),
                "output_files": output_files,
                "changed_files": changed_files,
                "target_project_paths": list(payload.get("changed_target_project_paths") or []),
                "source": str(payload.get("source") or "snapshot"),
                "captured_at": payload.get("captured_at"),
                "legacy_snapshot": bool(payload.get("legacy_snapshot")),
                "change_warning": str(payload.get("change_warning") or "").strip() or None,
            }
        )
        for file_name in output_files:
            merged = merged_index.setdefault(
                file_name,
                {
                    "file_name": file_name,
                    "task_ids": [],
                    "step_keys": [],
                    "step_types": [],
                    "step_titles": [],
                },
            )
            if task_id not in merged["task_ids"]:
                merged["task_ids"].append(task_id)
            step_key = str(step.step_key or "")
            step_type = str(step.step_type or "")
            step_title = str(step.title or "")
            if step_key and step_key not in merged["step_keys"]:
                merged["step_keys"].append(step_key)
            if step_type and step_type not in merged["step_types"]:
                merged["step_types"].append(step_type)
            if step_title and step_title not in merged["step_titles"]:
                merged["step_titles"].append(step_title)
    return task_outputs, list(merged_index.values())


def _record_project_change_summary_artifact(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
    task: TaskRow,
) -> ArtifactRow | None:
    payload = _normalize_task_file_change_payload(_load_task_file_changes(task))
    if not isinstance(payload, dict) or not payload:
        return None
    project_snapshots = payload.get("project_snapshots") or []
    if not isinstance(project_snapshots, list):
        return None
    changed_projects: list[dict[str, Any]] = []
    for item in project_snapshots:
        if not isinstance(item, dict):
            continue
        changed_file_count = int(item.get("changed_file_count") or 0)
        if changed_file_count <= 0:
            continue
        target_project_path = str(item.get("target_project_path") or "").strip()
        changed_projects.append(
            {
                "target_project_path": target_project_path,
                "changed_file_count": changed_file_count,
                "project_policy_summary": str(item.get("project_policy_summary") or "").strip(),
                "changed_files": item.get("changed_files") or [],
            }
        )
    if not changed_projects:
        return None
    lines = [
        "# Project Change Summary",
        "",
        "Validation should focus on the projects actually modified in this run.",
    ]
    for project in changed_projects:
        lines.extend(
            [
                "",
                f"## {project['target_project_path']}",
                f"- Changed files: {project['changed_file_count']}",
            ]
        )
        summary = project.get("project_policy_summary") or ""
        if summary:
            lines.append(summary)
    return _create_or_update_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id),
        step_id=_as_int(step.id),
        producer_step_id=_as_int(step.id),
        artifact_type="project_change_summary",
        path=str(task.output_path or "") or None,
        content_summary=f"Changed projects for step {step.step_key}",
        human_readable_body="\n".join(lines),
        machine_readable_payload={
            "task_id": _as_int(task.id),
            "step_id": _as_int(step.id),
            "changed_projects": changed_projects,
            "changed_target_project_paths": payload.get("changed_target_project_paths") or [],
            "all_target_project_paths": payload.get("all_target_project_paths") or [],
        },
    )


def _project_change_summary_payload(
    db: Session,
    requirement_id: int,
    *,
    workflow_run_id: int | None = None,
) -> dict[str, Any]:
    artifact = _latest_artifact(db, requirement_id, "project_change_summary", workflow_run_id=workflow_run_id)
    payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
    return payload if isinstance(payload, dict) else {}


def _dynamic_validation_scope(
    db: Session,
    requirement_id: int,
    *,
    workflow_run_id: int | None = None,
) -> dict[str, Any]:
    payload = _project_change_summary_payload(db, requirement_id, workflow_run_id=workflow_run_id)
    changed_projects = payload.get("changed_projects") or []
    changed_paths: list[str] = []
    changed_file_counts: dict[str, int] = {}
    changed_files_by_project: dict[str, list[str]] = {}
    if isinstance(changed_projects, list):
        for item in changed_projects:
            if not isinstance(item, dict):
                continue
            path = str(item.get("target_project_path") or "").strip()
            if not path:
                continue
            if path not in changed_paths:
                changed_paths.append(path)
            changed_file_counts[path] = int(item.get("changed_file_count") or 0)
            changed_files_by_project[path] = [
                str(entry.get("filename") or "").strip()
                for entry in item.get("changed_files") or []
                if isinstance(entry, dict) and str(entry.get("filename") or "").strip()
            ]
    for item in payload.get("changed_target_project_paths") or []:
        path = str(item).strip()
        if path and path not in changed_paths:
            changed_paths.append(path)

    policies = [
        project_policy_to_dict(row)
        for row in resolve_project_policies_for_target(db, "\n".join(changed_paths))
    ]
    required_checks: list[str] = []
    affected_projects: list[dict[str, Any]] = []
    for policy in policies:
        root_path = str(policy.get("root_path") or "").strip()
        narrowed_checks = _narrow_required_checks_for_changed_files(
            [str(item) for item in policy.get("required_checks") or [] if str(item).strip()],
            changed_files_by_project.get(root_path) or [],
        )
        for check in narrowed_checks:
            check_text = str(check).strip()
            if check_text and check_text not in required_checks:
                required_checks.append(check_text)
        affected_projects.append(
            {
                "project_key": str(policy.get("project_key") or ""),
                "display_name": str(policy.get("display_name") or ""),
                "root_path": root_path,
                "required_checks": narrowed_checks,
                "changed_file_count": int(changed_file_counts.get(root_path, 0) or 0),
                "changed_files": changed_files_by_project.get(root_path) or [],
            }
        )
    return {
        "changed_target_project_paths": changed_paths,
        "affected_projects": affected_projects,
        "required_checks": required_checks,
    }


def _narrow_required_checks_for_changed_files(required_checks: list[str], changed_files: list[str]) -> list[str]:
    checks = [str(item).strip() for item in required_checks if str(item).strip()]
    files = [str(item).strip().replace("\\", "/") for item in changed_files if str(item).strip()]
    if not checks or not files:
        return checks
    all_dashboard = all(path.startswith("dashboard/") for path in files)
    all_backend = all(path.startswith("server/") or path.startswith("tests/") for path in files)
    if all_dashboard:
        narrowed = [
            check
            for check in checks
            if any(marker in check.lower() for marker in ("dashboard", "npm", "yarn", "vite", "vitest"))
        ]
        return narrowed or checks
    if all_backend:
        narrowed = [
            check
            for check in checks
            if any(marker in check.lower() for marker in ("pytest", "python", "server", "backend"))
        ]
        return narrowed or checks
    return checks


def _project_change_metrics(
    db: Session,
    requirement_id: int,
    *,
    workflow_run_id: int | None = None,
) -> dict[str, Any]:
    payload = _project_change_summary_payload(db, requirement_id, workflow_run_id=workflow_run_id)
    changed_projects = payload.get("changed_projects") or []
    paths: list[str] = []
    total_changed_files = 0
    if isinstance(changed_projects, list):
        for item in changed_projects:
            if not isinstance(item, dict):
                continue
            path = str(item.get("target_project_path") or "").strip()
            if path and path not in paths:
                paths.append(path)
            total_changed_files += int(item.get("changed_file_count") or 0)
    return {
        "changed_project_count": len(paths),
        "changed_target_project_paths": paths,
        "total_changed_files": total_changed_files,
    }


def _is_summary_like_step(step: WorkflowStepRow) -> bool:
    if str(step.step_type or "") in {"closeout", "summary", "report"}:
        return True
    title = str(step.title or "").lower()
    if "summary" in title or "report" in title:
        return True
    profile = _step_execution_profile(step)
    outputs = profile.get("expected_outputs") or []
    if not isinstance(outputs, list) or not outputs:
        return False
    reportish = {"research_report", "plan_brief", "synthesis_report", "validation_report", "validation_manifest", "review_surface"}
    output_types = {
        str(item.get("artifact_type") or "").strip()
        for item in outputs
        if isinstance(item, dict)
    }
    return bool(output_types) and output_types.issubset(reportish)


def _replace_contract_binding(
    db: Session,
    workflow_run_id: int,
    *,
    purpose: str,
    artifact_id: int,
) -> None:
    step_ids = [
        int(step.id)
        for step in db.query(WorkflowStepRow).filter(WorkflowStepRow.workflow_run_id == workflow_run_id).all()
    ]
    if not step_ids:
        return
    db.query(StepInputBindingRow).filter(
        StepInputBindingRow.step_id.in_(step_ids),
        StepInputBindingRow.purpose == purpose,
    ).delete(synchronize_session=False)
    db.flush()
    for step_id in step_ids:
        _bind_artifact(db, step_id, artifact_id, purpose, True)


def _refresh_dynamic_validation_contracts(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
) -> None:
    dynamic_scope = _dynamic_validation_scope(db, _as_int(requirement.id), workflow_run_id=_as_int(workflow_run.id))
    affected_projects = dynamic_scope.get("affected_projects") or []
    if not affected_projects:
        return

    validation_plan = dict(_validation_plan_payload(db, _as_int(requirement.id)) or {})
    delivery_contract = dict(_delivery_contract_payload(db, _as_int(requirement.id)) or {})
    if not validation_plan or not delivery_contract:
        return

    required_checks = [str(item) for item in dynamic_scope.get("required_checks") or [] if str(item).strip()]
    affected_paths = [str(item.get("root_path") or "") for item in affected_projects if str(item.get("root_path") or "").strip()]
    validation_summary = str(validation_plan.get("summary_markdown") or "").strip()
    dynamic_summary = (
        "Dynamic validation scope is now derived from `project_change_summary`; "
        f"current affected projects: {', '.join(item.get('display_name') or item.get('project_key') or '-' for item in affected_projects)}."
    )
    if dynamic_summary not in validation_summary:
        validation_plan["summary_markdown"] = "\n\n".join([part for part in [validation_summary, dynamic_summary] if part])
    validation_plan["validation_mode"] = "dynamic_by_project_change_summary"
    validation_plan["affected_projects"] = affected_projects
    validation_plan["dynamic_required_checks"] = required_checks
    validation_plan["changed_target_project_paths"] = affected_paths

    delivery_summary = str(delivery_contract.get("summary_markdown") or "").strip()
    delivery_dynamic_summary = (
        "Required checks are dynamically narrowed to the projects actually changed in implementation."
    )
    if delivery_dynamic_summary not in delivery_summary:
        delivery_contract["summary_markdown"] = "\n\n".join([part for part in [delivery_summary, delivery_dynamic_summary] if part])
    delivery_contract["required_checks"] = required_checks
    delivery_contract["affected_projects"] = affected_projects
    delivery_contract["changed_target_project_paths"] = affected_paths
    delivery_contract["managed_projects"] = [
        item
        for item in delivery_contract.get("managed_projects") or []
        if str(item.get("root_path") or "").strip() in set(affected_paths)
    ] or list(delivery_contract.get("managed_projects") or [])
    delivery_contract["auto_publish_allowed"] = (
        str(delivery_contract.get("release_mode") or "manual") == "auto"
        and not bool(delivery_contract.get("requires_manual_approval"))
        and not required_checks
        and bool((delivery_contract.get("capability_matrix") or {}).get("git_push"))
        and bool((delivery_contract.get("capability_matrix") or {}).get("publish"))
        and "publish" not in set((delivery_contract.get("interrupt_policy") or {}).get("operator_confirmation_actions") or [])
    )

    validation_artifact = _create_or_update_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id),
        artifact_type="validation_plan",
        content_summary=f"Dynamic validation contract for requirement #{requirement.id}",
        human_readable_body=_validation_plan_markdown(validation_plan),
        machine_readable_payload=validation_plan,
    )
    delivery_artifact = _create_or_update_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id),
        artifact_type="delivery_contract",
        content_summary=f"Dynamic delivery contract for requirement #{requirement.id}",
        human_readable_body=_delivery_contract_markdown(delivery_contract),
        machine_readable_payload=delivery_contract,
    )
    _replace_contract_binding(db, _as_int(workflow_run.id), purpose="validation_contract", artifact_id=_as_int(validation_artifact.id))
    _replace_contract_binding(db, _as_int(workflow_run.id), purpose="delivery_contract", artifact_id=_as_int(delivery_artifact.id))


def _refresh_delivery_contract_for_existing_plan(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    project_policies: list[Any],
) -> None:
    from server.services.project_policy import aggregate_execution_controls, project_policy_to_dict
    from server.services.workflow_planner import _build_delivery_contract

    normalized_policies = [
        project_policy_to_dict(policy) if not isinstance(policy, dict) else dict(policy)
        for policy in project_policies
    ]
    execution_controls = aggregate_execution_controls(normalized_policies)
    refreshed_contract = _build_delivery_contract(
        requirement,
        _normalize_target_project_path(requirement.target_project_path),
        normalized_policies,
        execution_controls,
    )
    existing_contract = dict(_delivery_contract_payload(db, _as_int(requirement.id)) or {})
    if existing_contract == refreshed_contract:
        return
    delivery_artifact = _create_or_update_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id),
        artifact_type="delivery_contract",
        content_summary=f"Delivery contract for requirement #{requirement.id}",
        human_readable_body=_delivery_contract_markdown(refreshed_contract),
        machine_readable_payload=refreshed_contract,
    )
    _replace_contract_binding(db, _as_int(workflow_run.id), purpose="delivery_contract", artifact_id=_as_int(delivery_artifact.id))


def _resolve_repo_file_change_task(
    db: Session,
    *,
    step: WorkflowStepRow,
    task: TaskRow | None,
) -> TaskRow | None:
    if task is not None and _task_has_tracked_repo_changes(task):
        return task
    workflow_run_id = _as_int(getattr(step, "workflow_run_id", 0))
    sequence_no = int(getattr(step, "sequence_no", 0) or 0)
    if workflow_run_id <= 0:
        return task
    candidate_steps = db.query(WorkflowStepRow).filter(
        WorkflowStepRow.workflow_run_id == workflow_run_id,
        WorkflowStepRow.sequence_no <= sequence_no,
        WorkflowStepRow.compatibility_task_id.is_not(None),
    ).order_by(WorkflowStepRow.sequence_no.desc(), WorkflowStepRow.id.desc()).all()
    for candidate_step in candidate_steps:
        candidate_type = str(getattr(candidate_step, "step_type", "") or "")
        if candidate_type not in {"implementation", "bugfix"}:
            continue
        candidate_task_id = _as_int(getattr(candidate_step, "compatibility_task_id", 0))
        if candidate_task_id <= 0:
            continue
        candidate_task = db.query(TaskRow).filter(TaskRow.id == candidate_task_id).first()
        if candidate_task is None:
            continue
        if _task_has_tracked_repo_changes(candidate_task):
            return candidate_task
    return task


def _repo_file_changes_check_error(
    db: Session,
    *,
    step: WorkflowStepRow,
    task: TaskRow | None,
    spec: dict[str, Any],
    artifact: ArtifactRow,
) -> str | None:
    task = _resolve_repo_file_change_task(db, step=step, task=task)
    if task is None:
        return "repo_file_changes check has no task context"
    payload = _load_task_file_changes(task)
    if not payload:
        return "repo_file_changes evidence is missing"
    required_target = str(spec.get("required_target_path") or "").strip()
    required_targets = [
        str(item).strip()
        for item in spec.get("required_target_paths") or []
        if str(item).strip()
    ]
    actual_target = str(payload.get("target_project_path") or "").strip()
    if required_target and actual_target and actual_target != required_target:
        return f"repo_file_changes captured `{actual_target}` but expected `{required_target}`"
    if required_targets:
        changed_targets = {
            str(item).strip()
            for item in payload.get("changed_target_project_paths") or []
            if str(item).strip()
        }
        if changed_targets and not changed_targets.intersection(required_targets):
            expected = ", ".join(f"`{item}`" for item in required_targets)
            actual = ", ".join(f"`{item}`" for item in sorted(changed_targets))
            return f"repo_file_changes captured {actual or '`<none>`'} but expected one of {expected}"
    changed_files = payload.get("changed_files") or []
    if not isinstance(changed_files, list):
        return "repo_file_changes evidence is malformed"
    code_files = [
        str(item.get("filename") or "").strip()
        for item in changed_files
        if isinstance(item, dict) and _is_code_change_file(str(item.get("filename") or ""))
    ]
    if not code_files:
        return "validation found no source-code or test-file changes in the primary target repository"
    return None


def _is_infra_incident_error(error_text: str) -> bool:
    normalized = _normalize_error_text(error_text)
    return any(marker in normalized for marker in INFRA_INCIDENT_ERROR_MARKERS)


def _ensure_requirement_from_followup(
    db: Session,
    *,
    title: str,
    description_markdown: str,
    priority: str,
    source_ref: str,
    target_project_path: str | None,
    template_payload: dict[str, Any],
) -> tuple[int, bool]:
    existing = db.query(RequirementRow).filter(RequirementRow.source_ref == source_ref).first()
    if existing is not None:
        return _as_int(existing.id), False
    detail = create_requirement(
        db,
        RequirementCreate(
            title=title,
            description_markdown=description_markdown,
            priority=priority,
            source=CIRCUIT_BREAKER_REQUIREMENT_SOURCE,
            source_ref=source_ref,
            target_project_path=target_project_path,
            auto_start=False,
            template_payload=template_payload,
        ),
    )
    return _as_int(detail.requirement.id), True


def _create_circuit_breaker_followup_requirements(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    failed_step: WorkflowStepRow,
    error_text: str,
    reason: str,
    linked_bug_report_artifact_id: int,
) -> list[dict[str, Any]]:
    base_ref = f"bugfix-circuit-breaker:{_as_int(requirement.id)}:{_as_int(workflow_run.id)}:{_as_int(failed_step.id)}"
    operator_target = _merge_target_project_paths(requirement.target_project_path, PRIMARY_GROWING_PROJECT)
    shared_payload = {
        "requirement_id": _as_int(requirement.id),
        "workflow_run_id": _as_int(workflow_run.id),
        "failed_step_id": _as_int(failed_step.id),
        "linked_bug_report_artifact_id": linked_bug_report_artifact_id,
        "circuit_breaker_reason": reason,
        "last_error": error_text,
    }

    operator_title = f"Operator Review: Requirement #{requirement.id} circuit breaker"
    operator_description = "\n".join(
        [
            f"# Operator Review For Requirement #{requirement.id}",
            "",
            f"Original requirement: `{requirement.title}`",
            f"Workflow run: `{workflow_run.id}` / failed step: `{failed_step.step_type}` #{failed_step.id}",
            "",
            "## Why this was escalated",
            reason,
            "",
            "## Last observed error",
            f"```text\n{error_text}\n```",
            "",
            "## Operator tasks",
            "1. Confirm whether this is a product requirement issue or a harness/runtime issue.",
            "2. Decide whether the original requirement should be revised, retried, or split.",
            "3. Review any linked infra incident requirement before resuming automation.",
        ]
    )
    operator_id, operator_created = _ensure_requirement_from_followup(
        db,
        title=operator_title,
        description_markdown=operator_description,
        priority="high",
        source_ref=f"{base_ref}:operator-review",
        target_project_path=operator_target,
        template_payload={
            **shared_payload,
            "followup_kind": "operator_review",
            "owner_role": "operator",
        },
    )
    items = [
        {
            "kind": "operator_review",
            "requirement_id": operator_id,
            "source_ref": f"{base_ref}:operator-review",
            "created": operator_created,
        }
    ]

    if _is_infra_incident_error(error_text):
        incident_title = f"Infra Incident: runtime failure behind requirement #{requirement.id}"
        incident_description = "\n".join(
            [
                f"# Infra Incident From Requirement #{requirement.id}",
                "",
                f"Original requirement: `{requirement.title}`",
                f"Failed step: `{failed_step.step_type}` #{failed_step.id}",
                "",
                "This looks like a harness/runtime reliability failure rather than a normal product bugfix.",
                "",
                "## Circuit breaker reason",
                reason,
                "",
                "## Last observed error",
                f"```text\n{error_text}\n```",
                "",
                "## Expected outcome",
                "1. Restore runtime/session health.",
                "2. Add or improve recovery / cache invalidation / observability so the same failure does not recur.",
                "3. Only then decide whether the original requirement can be resumed.",
            ]
        )
        incident_id, incident_created = _ensure_requirement_from_followup(
            db,
            title=incident_title,
            description_markdown=incident_description,
            priority="high",
            source_ref=f"{base_ref}:infra-incident",
            target_project_path=PRIMARY_GROWING_PROJECT,
            template_payload={
                **shared_payload,
                "followup_kind": "infra_incident",
                "owner_role": "platform",
            },
        )
        items.append(
            {
                "kind": "infra_incident",
                "requirement_id": incident_id,
                "source_ref": f"{base_ref}:infra-incident",
                "created": incident_created,
            }
        )

    return items


def create_requirement(db: Session, body: RequirementCreate) -> RequirementDetailOut:
    requested_target = _normalize_target_project_path(body.target_project_path)
    routing_context = resolve_requirement_routing(
        db,
        title=body.title,
        description_markdown=body.description_markdown,
        target_project_path=requested_target,
    )
    intake_metadata = normalize_requirement_intake_metadata(body.source, body.source_ref, body.intake_metadata)
    resolved_target = _normalize_target_project_path(
        str(routing_context.get("target_project_path") or "") or requested_target
    )
    family_context = build_requirement_family_context(
        title=body.title,
        source=body.source,
        source_ref=body.source_ref,
        target_project_path=resolved_target,
        description_markdown=body.description_markdown,
        intake_metadata=intake_metadata,
    )
    existing_family_requirement = find_active_requirement_for_family(
        db,
        family_key=str(family_context.get("family_key") or ""),
    )
    family_recommendation = build_requirement_family_recommendation(
        title=body.title,
        source=body.source,
        source_ref=body.source_ref,
        target_project_path=resolved_target,
        description_markdown=body.description_markdown,
        intake_metadata=intake_metadata,
        existing_requirement=existing_family_requirement,
    )
    intake_metadata.update(
        {
            "family_key": family_context.get("family_key"),
            "family_category": family_context.get("family_category"),
            "family_target_root": family_context.get("family_target_root"),
            "family_key_suffix": family_context.get("family_key_suffix"),
            "is_validation_experiment": bool(family_context.get("is_validation_experiment")),
            "family_recommendation": family_recommendation,
        }
    )
    if existing_family_requirement is not None and str(family_recommendation.get("action") or "") in {"reuse_existing", "archive_experiment"}:
        existing_intake = requirement_intake_metadata_for_requirement(existing_family_requirement)
        existing_intake.update(
            {
                "family_key": family_context.get("family_key"),
                "family_category": family_context.get("family_category"),
                "family_target_root": family_context.get("family_target_root"),
                "family_key_suffix": family_context.get("family_key_suffix"),
                "is_validation_experiment": bool(family_context.get("is_validation_experiment")),
                "family_recommendation": family_recommendation,
                "family_primary_requirement_id": int(existing_family_requirement.id),
                "family_reuse_count": int(existing_intake.get("family_reuse_count") or 0) + 1,
                "family_last_source_ref": str(body.source_ref or "").strip() or None,
                "family_last_title": str(body.title or ""),
            }
        )
        existing_family_requirement.intake_metadata_json = json.dumps(existing_intake, ensure_ascii=False)
        priority_rank = {"low": 0, "normal": 1, "high": 2}
        if priority_rank.get(str(body.priority), 1) > priority_rank.get(str(existing_family_requirement.priority), 1):
            existing_family_requirement.priority = body.priority
        _create_artifact(
            db,
            requirement_id=int(existing_family_requirement.id),
            artifact_type="family_intake_decision",
            content_summary=f"Family intake reused requirement #{existing_family_requirement.id}",
            human_readable_body=(
                f"Incoming requirement `{body.title}` was merged into active family requirement #{existing_family_requirement.id}.\n"
                f"Family key: `{family_context.get('family_key')}`\n"
                f"Decision: `{family_recommendation.get('action')}`\n"
                f"Reason: {family_recommendation.get('reason')}"
            ),
            machine_readable_payload={
                "incoming_title": str(body.title),
                "incoming_source": str(body.source),
                "incoming_source_ref": str(body.source_ref or "") or None,
                "family_context": family_context,
                "family_recommendation": family_recommendation,
                "primary_requirement_id": int(existing_family_requirement.id),
            },
        )
        db.commit()
        return build_requirement_detail(db, int(existing_family_requirement.id))
    requirement = RequirementRow(
        title=body.title,
        description_markdown=body.description_markdown,
        status="ready",
        priority=body.priority,
        source=body.source,
        source_ref=body.source_ref,
        intake_metadata_json=json.dumps(
            intake_metadata,
            ensure_ascii=False,
        ),
        target_project_path=resolved_target,
        acceptance_contract_json=json.dumps(normalize_acceptance_contract(body.acceptance_contract), ensure_ascii=False),
        approval_contract_json=json.dumps(normalize_requirement_approval_contract(body.approval_contract), ensure_ascii=False),
    )
    requirement.approval_status = _default_requirement_approval_status(requirement)
    if requirement.approval_status == "waived":
        requirement.approved_at = utcnow()
    db.add(requirement)
    db.flush()
    _create_artifact(
        db,
        requirement_id=requirement.id,
        artifact_type="intake_record",
        content_summary=f"Intake record for requirement #{requirement.id}",
        human_readable_body=str(
            (
                intake_metadata.get("intake_reason")
                or "Requirement entered the pool."
            )
        ),
        machine_readable_payload=intake_metadata,
    )
    _create_artifact(
        db,
        requirement_id=requirement.id,
        artifact_type="family_intake_decision",
        content_summary=f"Family intake decision for requirement #{requirement.id}",
        human_readable_body=(
            f"Family key: `{family_context.get('family_key')}`\n"
            f"Decision: `{family_recommendation.get('action')}`\n"
            f"Reason: {family_recommendation.get('reason')}"
        ),
        machine_readable_payload={
            "family_context": family_context,
            "family_recommendation": family_recommendation,
        },
    )
    _create_artifact(
        db,
        requirement_id=requirement.id,
        artifact_type="routing_decision",
        content_summary=f"Routing for requirement #{requirement.id}",
        human_readable_body=str(routing_context.get("summary") or "Requirement routing was assessed during intake."),
        machine_readable_payload=routing_context,
    )
    acceptance_contract = acceptance_contract_for_requirement(requirement)
    _create_artifact(
        db,
        requirement_id=requirement.id,
        artifact_type="acceptance_contract",
        content_summary=f"Acceptance contract for requirement #{requirement.id}",
        human_readable_body=(
            f"Acceptance owner: {acceptance_contract.get('acceptance_owner_role')}\n"
            f"Review owner: {acceptance_contract.get('review_owner_role')}\n"
            f"Mode: {acceptance_contract.get('acceptance_mode')}\n"
            f"Trigger: {acceptance_contract.get('acceptance_trigger')}"
        ),
        machine_readable_payload=acceptance_contract,
    )
    _create_artifact(
        db,
        requirement_id=requirement.id,
        artifact_type="requirement_approval_contract",
        content_summary=f"Requirement approval contract for requirement #{requirement.id}",
        human_readable_body=(
            f"Approval status: {requirement.approval_status}\n"
            f"Mode: {requirement_approval_contract_for_requirement(requirement).get('approval_mode')}\n"
            f"Fallback reviewer: {requirement_approval_contract_for_requirement(requirement).get('fallback_reviewer')}"
        ),
        machine_readable_payload=requirement_approval_contract_for_requirement(requirement),
    )
    if body.template_key or body.template_payload or body.template_acceptance_checks:
        template_payload = dict(body.template_payload or {})
        if body.template_key and "template_key" not in template_payload:
            template_payload["template_key"] = body.template_key
        if body.template_acceptance_checks:
            template_payload["acceptance_checks"] = body.template_acceptance_checks
        _create_artifact(
            db,
            requirement_id=requirement.id,
            artifact_type="requirement_template",
            content_summary=f"Template for requirement #{requirement.id}",
            human_readable_body=str(template_payload.get("description") or body.description_markdown[:500]),
            machine_readable_payload=template_payload,
        )
    _replace_dependencies(db, requirement.id, body.depends_on_requirement_ids)
    _refresh_requirement_dependency_state(db, requirement)
    db.commit()

    detail = build_requirement_detail(db, requirement.id)
    target_policies = resolve_project_policies_for_target(
        db,
        requirement.target_project_path,
        require_active=False,
    )
    inferred_auto_start = bool(target_policies) and all(
        str(project_policy_to_dict(policy).get("autonomy_mode") or "recommend") == "execute_autonomously"
        for policy in target_policies
    )
    requested_auto_start = bool(body.auto_start)
    effective_auto_start = bool(requested_auto_start or inferred_auto_start)
    inline_auto_plan = _should_inline_auto_plan(db) and bool(
        requested_auto_start or inferred_auto_start or body.target_project_path
    )
    _logger.info(
        "event=requirement_created requirement_id=%s source=%s priority=%s routing_mode=%s target_paths=%s auto_start=%s",
        requirement.id,
        requirement.source,
        requirement.priority,
        routing_context.get("routing_mode") or "unknown",
        len(str(requirement.target_project_path or "").splitlines()) if requirement.target_project_path else 0,
        effective_auto_start,
    )
    approved_for_execution = (
        requirement.blocked_by_count == 0
        and normalize_requirement_approval_status(requirement.approval_status) in {"approved", "waived"}
    )
    if requested_auto_start and approved_for_execution:
        req_id = _as_int(requirement.id)
        if req_id is not None and inline_auto_plan:
            with _AUTO_PLAN_LOCK:
                _plan_requirement_after_approval(db, requirement_id=req_id, trigger="auto_start", raise_on_failure=True)
            return start_requirement(db, req_id)

        def _bg_plan_and_start(req_id: int) -> None:
            bg_db = SessionLocal()
            try:
                with _AUTO_PLAN_LOCK:
                    _plan_requirement_after_approval(bg_db, requirement_id=req_id, trigger="auto_start", raise_on_failure=True)
                start_requirement(bg_db, req_id)
            except Exception as exc:  # noqa: BLE001
                import logging
                logging.getLogger("ops-dashboard.orchestrator").warning(
                    "Background plan/start failed for req %s: %s", req_id, exc
                )
            finally:
                bg_db.close()

        threading.Thread(target=_bg_plan_and_start, args=(req_id,), daemon=True).start()
    elif approved_for_execution:
        req_id = _as_int(requirement.id)
        if req_id is not None and inline_auto_plan:
            with _AUTO_PLAN_LOCK:
                _plan_requirement_after_approval(
                    db,
                    requirement_id=req_id,
                    trigger="requirement_create",
                    raise_on_failure=True,
                )
            return build_requirement_detail(db, requirement.id)
        if _should_inline_auto_plan(db):
            return detail

        def _bg_plan_only(req_id: int) -> None:
            bg_db = SessionLocal()
            try:
                with _AUTO_PLAN_LOCK:
                    _plan_requirement_after_approval(
                        bg_db,
                        requirement_id=req_id,
                        trigger="requirement_create",
                        raise_on_failure=True,
                    )
            except Exception as exc:  # noqa: BLE001
                import logging
                logging.getLogger("ops-dashboard.orchestrator").warning(
                    "Background auto-plan failed for req %s: %s", req_id, exc
                )
            finally:
                bg_db.close()

        threading.Thread(target=_bg_plan_only, args=(req_id,), daemon=True).start()

    return detail


def plan_requirement(db: Session, requirement_id: int) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    _reconcile_active_workflow_run(db, requirement)
    project_policies = resolve_project_policies_for_target(
        db,
        _normalize_target_project_path(requirement.target_project_path),
        require_active=bool(requirement.target_project_path),
    )
    _refresh_requirement_dependency_state(db, requirement)
    if requirement.blocked_by_count > 0:
        raise ValueError("Requirement is blocked by unfinished dependencies.")
    if requirement.current_plan_version > 0 and requirement.active_workflow_run_id:
        workflow_run = _active_workflow_run(db, requirement)
        if workflow_run is not None and str(workflow_run.status or "").strip().lower() in {"pending", "ready", "paused"}:
            _refresh_delivery_contract_for_existing_plan(
                db,
                requirement=requirement,
                workflow_run=workflow_run,
                project_policies=project_policies,
            )
        if requirement.status in {"planning", "plan_failed", "draft"}:
            requirement.status = "ready"
        db.commit()
        return build_requirement_detail(db, requirement.id)

    requirement.status = "planning"
    db.flush()

    planner_output, assignments = build_planner_output(db, requirement)
    db.refresh(requirement)
    _reconcile_active_workflow_run(db, requirement)
    if requirement.current_plan_version > 0 and requirement.active_workflow_run_id:
        db.rollback()
        requirement = _require_requirement(db, requirement_id)
        return build_requirement_detail(db, requirement.id)
    snapshot_artifact = _create_artifact(
        db,
        requirement_id=requirement.id,
        artifact_type="requirement_snapshot",
        content_summary=requirement.title,
        human_readable_body=requirement.description_markdown,
        machine_readable_payload={
            "title": requirement.title,
            "description_markdown": requirement.description_markdown,
            "priority": requirement.priority,
            "source": requirement.source,
            "source_ref": requirement.source_ref,
            "target_project_path": requirement.target_project_path,
            "project_policies": [
                {
                    "project_key": str(row.project_key),
                    "display_name": str(row.display_name),
                    "root_path": str(row.root_path),
                    "status": str(row.status),
                }
                for row in project_policies
            ],
        },
    )
    requirement_brief_artifact = _create_artifact(
        db,
        requirement_id=requirement.id,
        artifact_type="requirement_brief",
        content_summary=f"Bootstrap brief for requirement #{requirement.id}",
        human_readable_body="\n".join(
            [
                "# Requirement Brief",
                "",
                f"## Goal\n{requirement.title}",
                "",
                f"## Context\n{requirement.description_markdown}",
                "",
                "## Constraints",
                f"- Target project: `{requirement.target_project_path or '-'}`",
                f"- Branch strategy: `{((planner_output.get('delivery_contract') or {}).get('branch_strategy') or 'requirement_branch')}`",
                f"- Release mode: `{((planner_output.get('delivery_contract') or {}).get('release_mode') or 'manual')}`",
                f"- Required checks: {', '.join(((planner_output.get('delivery_contract') or {}).get('required_checks') or [])) or 'none'}",
            ]
        ),
        machine_readable_payload={
            "goal": requirement.title,
            "target_project_path": requirement.target_project_path,
            "delivery_contract": planner_output.get("delivery_contract") or {},
            "validation_plan": planner_output.get("validation_plan") or {},
            "step_model_version": planner_output.get("step_model_version") or "2.0",
        },
    )

    workflow_run = WorkflowRunRow(
        requirement_id=requirement.id,
        plan_version=requirement.current_plan_version + 1,
        status="pending",
        triggered_by="user",
    )
    db.add(workflow_run)
    db.flush()

    plan_artifact = _create_artifact(
        db,
        requirement_id=requirement.id,
        workflow_run_id=workflow_run.id,
        artifact_type="implementation_plan",
        content_summary=f"Plan v{workflow_run.plan_version}",
        human_readable_body=_planner_markdown(planner_output, assignments),
        machine_readable_payload=planner_output,
    )
    workflow_run.planner_artifact_id = _as_int(plan_artifact.id)

    delivery_contract_artifact = _create_artifact(
        db,
        requirement_id=requirement.id,
        workflow_run_id=workflow_run.id,
        artifact_type="delivery_contract",
        content_summary=f"Delivery contract v{workflow_run.plan_version}",
        human_readable_body=_delivery_contract_markdown(planner_output.get("delivery_contract") or {}),
        machine_readable_payload=planner_output.get("delivery_contract") or {},
    )

    validation_plan_artifact = _create_artifact(
        db,
        requirement_id=requirement.id,
        workflow_run_id=workflow_run.id,
        artifact_type="validation_plan",
        content_summary=f"Validation contract v{workflow_run.plan_version}",
        human_readable_body=_validation_plan_markdown(planner_output.get("validation_plan") or {}),
        machine_readable_payload=planner_output.get("validation_plan") or {},
    )

    _create_acceptance_checks(db, requirement.id, planner_output)
    steps_by_key = _create_workflow_steps(db, requirement, workflow_run, planner_output, assignments)
    _create_step_dependencies(db, steps_by_key, planner_output)
    for step in steps_by_key.values():
        _bind_artifact(db, step.id, snapshot_artifact.id, "primary_spec", True)
        _bind_artifact(db, step.id, requirement_brief_artifact.id, "bootstrap_context", False)
        _bind_artifact(db, step.id, plan_artifact.id, "implementation_context", True)
        _bind_artifact(db, step.id, delivery_contract_artifact.id, "delivery_contract", True)
        _bind_artifact(db, step.id, validation_plan_artifact.id, "validation_contract", True)

    requirement.current_plan_version = workflow_run.plan_version
    requirement.planned_roles_json = json.dumps(planner_output.get("required_roles", []))
    requirement.active_workflow_run_id = _as_int(workflow_run.id)
    requirement.status = "ready"
    if normalize_requirement_approval_status(requirement.approval_status) not in {"approved", "waived"}:
        _sync_requirement_execution_approval(
            db,
            requirement=requirement,
            workflow_run=workflow_run,
            planner_output=planner_output,
        )
    db.commit()
    _logger.info(
        "event=requirement_planned requirement_id=%s plan_version=%s steps=%s acceptance_checks=%s",
        requirement.id,
        workflow_run.plan_version,
        len(planner_output.get("workflow_steps") or []),
        len(planner_output.get("acceptance_checks") or []),
    )
    if normalize_requirement_approval_status(requirement.approval_status) in {"approved", "waived"}:
        preferred_project_key, preferred_root_path = _queue_preference_for_requirement(db, requirement)
        _schedule_advance_queue_compat(
            preferred_project_key=preferred_project_key,
            preferred_root_path=preferred_root_path,
        )
    return build_requirement_detail(db, requirement.id)


def _record_planning_failure(
    db: Session,
    *,
    requirement: RequirementRow,
    reason: str,
    trigger: str,
) -> None:
    requirement.status = "plan_failed"
    _create_artifact(
        db,
        requirement_id=requirement.id,
        artifact_type="planning_failure",
        content_summary=f"Planning failed for requirement #{requirement.id}",
        human_readable_body=reason,
        machine_readable_payload={
            "requirement_id": _as_int(requirement.id),
            "trigger": trigger,
            "reason": reason,
            "failed_at": utcnow().isoformat(),
        },
    )


def _plan_requirement_after_approval(
    db: Session,
    *,
    requirement_id: int,
    trigger: str,
    raise_on_failure: bool,
) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    if int(requirement.current_plan_version or 0) > 0 and requirement.active_workflow_run_id is not None:
        if requirement.status in {"draft", "planning", "plan_failed", "blocked"} and normalize_requirement_approval_status(requirement.approval_status) in {"approved", "waived"}:
            requirement.status = "ready"
            db.commit()
        return build_requirement_detail(db, requirement.id)

    requirement.status = "planning"
    db.commit()
    try:
        attempts = 0
        while True:
            attempts += 1
            try:
                return plan_requirement(db, requirement_id)
            except OperationalError as exc:
                if "database is locked" not in str(exc).lower() or attempts >= 4:
                    raise
                db.rollback()
                time.sleep(0.25 * attempts)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        requirement = _require_requirement(db, requirement_id)
        _record_planning_failure(
            db,
            requirement=requirement,
            reason=str(exc),
            trigger=trigger,
        )
        db.commit()
        if raise_on_failure:
            raise ValueError(f"Workflow planning failed: {exc}") from exc
        return build_requirement_detail(db, requirement.id)


def update_requirement_dependencies(db: Session, requirement_id: int, dependency_ids: list[int]) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    if requirement.active_workflow_run_id and requirement.status == "in_progress":
        raise ValueError("Cannot edit dependencies while a workflow run is in progress.")
    _replace_dependencies(db, requirement.id, dependency_ids)
    _refresh_requirement_dependency_state(db, requirement)
    _refresh_dependents_for_requirement(db, requirement.id)
    db.commit()
    return build_requirement_detail(db, requirement.id)


def patch_requirement(db: Session, requirement_id: int, body: RequirementPatch) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    if requirement.status == "in_progress":
        raise ValueError("Cannot edit a requirement that is currently in progress.")
    reset_approval = False
    if body.title is not None:
        if not body.title.strip():
            raise ValueError("title cannot be blank")
        requirement.title = body.title.strip()
        reset_approval = True
    if body.description_markdown is not None:
        if not body.description_markdown.strip():
            raise ValueError("description_markdown cannot be blank")
        requirement.description_markdown = body.description_markdown.strip()
        reset_approval = True
    if body.priority is not None:
        if body.priority not in {"low", "normal", "high"}:
            raise ValueError("priority must be low|normal|high")
        requirement.priority = body.priority
        reset_approval = True
    if body.source_ref is not None:
        requirement.source_ref = body.source_ref
        reset_approval = True
    if body.intake_metadata is not None or body.source_ref is not None:
        requirement.intake_metadata_json = json.dumps(
            normalize_requirement_intake_metadata(
                requirement.source,
                body.source_ref if body.source_ref is not None else requirement.source_ref,
                body.intake_metadata,
            ),
            ensure_ascii=False,
        )
        reset_approval = True
    if body.target_project_path is not None:
        requirement.target_project_path = _normalize_target_project_path(body.target_project_path)
        reset_approval = True
    if body.acceptance_contract is not None:
        requirement.acceptance_contract_json = json.dumps(
            normalize_acceptance_contract(body.acceptance_contract),
            ensure_ascii=False,
        )
    if body.approval_contract is not None:
        requirement.approval_contract_json = json.dumps(
            normalize_requirement_approval_contract(body.approval_contract),
            ensure_ascii=False,
        )
        reset_approval = True
    if reset_approval:
        requirement.approval_status = _default_requirement_approval_status(requirement)
        requirement.approval_requested_at = None
        requirement.approved_at = utcnow() if requirement.approval_status == "waived" else None
    db.commit()
    return build_requirement_detail(db, requirement.id)


def _latest_plan_artifact_for_run(db: Session, requirement_id: int, workflow_run_id: int) -> ArtifactRow | None:
    return _latest_artifact(db, requirement_id, "implementation_plan", workflow_run_id=workflow_run_id)


def _update_plan_payload_step(plan_payload: dict[str, Any], step: WorkflowStepRow) -> dict[str, Any]:
    payload = dict(plan_payload or {})
    workflow_steps = list(payload.get("workflow_steps") or [])
    for item in workflow_steps:
        if not isinstance(item, dict):
            continue
        if str(item.get("step_key") or "") != str(step.step_key or ""):
            continue
        item["title"] = str(step.title or "")
        item["done_when_markdown"] = str(step.done_when_markdown or "")
        if step.handoff_summary_markdown is not None:
            item["handoff_summary_markdown"] = str(step.handoff_summary_markdown or "")
    payload["workflow_steps"] = workflow_steps
    payload["edited_at"] = utcnow().isoformat()
    return payload


def _sync_plan_artifact_for_step_edit(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
) -> None:
    artifact = _latest_plan_artifact_for_run(db, _as_int(requirement.id), _as_int(workflow_run.id))
    if artifact is None:
        return
    payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
    if not isinstance(payload, dict):
        payload = {}
    updated_payload = _update_plan_payload_step(payload, step)
    body = str(artifact.human_readable_body or "").strip() or _plan_artifact_to_markdown(artifact)
    new_artifact = _create_or_update_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id),
        artifact_type="implementation_plan",
        content_summary=artifact.content_summary,
        human_readable_body=body,
        machine_readable_payload=updated_payload,
    )
    if _as_int(new_artifact.id) != _as_int(artifact.id):
        _replace_contract_binding(
            db,
            _as_int(workflow_run.id),
            purpose="implementation_context",
            artifact_id=_as_int(new_artifact.id),
        )
        workflow_run.planner_artifact_id = _as_int(new_artifact.id)


def _sync_pending_task_description_for_step(db: Session, step: WorkflowStepRow) -> None:
    raw_task_id = getattr(step, "compatibility_task_id", None)
    if raw_task_id in (None, ""):
        return
    task_id = _as_int(raw_task_id)
    if task_id is None:
        return
    task = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if task is None:
        return
    task_status = str(task.status or "").strip().lower()
    if task_status not in {"pending", "paused"}:
        return
    snapshot = _step_context_snapshot(db, step)
    description = _compact_task_description_from_snapshot(step, snapshot)
    if description == str(task.description or ""):
        return
    task.description = description
    db.add(TaskLogRow(task_id=task.id, event_type="edited_from_step", detail=f"workflow_step={step.id}"))


def patch_requirement_plan(db: Session, requirement_id: int, body: RequirementPlanPatch) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    workflow_run = _active_workflow_run(db, requirement)
    if workflow_run is None:
        raise ValueError("Requirement has no active workflow plan.")
    if requirement.status == "in_progress" or str(workflow_run.status or "") == "running":
        raise ValueError("Cannot edit plan while workflow is running.")
    markdown = str(body.human_readable_body or "").strip()
    if not markdown:
        raise ValueError("human_readable_body cannot be blank")
    artifact = _latest_plan_artifact_for_run(db, _as_int(requirement.id), _as_int(workflow_run.id))
    if artifact is None:
        raise ValueError("Implementation plan artifact is missing.")
    payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
    if not isinstance(payload, dict):
        payload = {}
    payload["edited_markdown"] = markdown
    payload["edited_at"] = utcnow().isoformat()
    new_artifact = _create_or_update_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id),
        artifact_type="implementation_plan",
        content_summary=artifact.content_summary,
        human_readable_body=markdown,
        machine_readable_payload=payload,
    )
    if _as_int(new_artifact.id) != _as_int(artifact.id):
        _replace_contract_binding(
            db,
            _as_int(workflow_run.id),
            purpose="implementation_context",
            artifact_id=_as_int(new_artifact.id),
        )
        workflow_run.planner_artifact_id = _as_int(new_artifact.id)
    db.commit()
    return build_requirement_detail(db, requirement.id)


def patch_workflow_step(
    db: Session,
    requirement_id: int,
    step_id: int,
    body: WorkflowStepPatch,
) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    workflow_run = _active_workflow_run(db, requirement)
    if workflow_run is None:
        raise ValueError("Requirement has no active workflow plan.")
    step = db.query(WorkflowStepRow).filter(
        WorkflowStepRow.id == step_id,
        WorkflowStepRow.requirement_id == requirement.id,
        WorkflowStepRow.workflow_run_id == workflow_run.id,
    ).first()
    if step is None:
        raise ValueError("Workflow step not found.")
    if str(step.status or "") in {"running", "waiting_approval", "completed", "deleted"}:
        raise ValueError("Completed or running workflow steps cannot be edited.")
    if all(value is None for value in (body.title, body.done_when_markdown, body.handoff_summary_markdown)):
        raise ValueError("At least one workflow step field must be provided.")
    if body.title is not None:
        title = str(body.title or "").strip()
        if not title:
            raise ValueError("step title cannot be blank")
        step.title = title
    if body.done_when_markdown is not None:
        done_when = str(body.done_when_markdown or "").strip()
        if not done_when:
            raise ValueError("done_when_markdown cannot be blank")
        step.done_when_markdown = done_when
    if body.handoff_summary_markdown is not None:
        step.handoff_summary_markdown = str(body.handoff_summary_markdown or "").strip() or None
    _sync_plan_artifact_for_step_edit(
        db,
        requirement=requirement,
        workflow_run=workflow_run,
        step=step,
    )
    _sync_pending_task_description_for_step(db, step)
    _record_step_event(db, _as_int(step.id), "edited", "workflow step updated")
    db.commit()
    return build_requirement_detail(db, requirement.id)


def dispatch_acceptance_sweep(db: Session, *, limit: int = 20, auto_dispatch: bool = False) -> dict[str, Any]:
    candidates = list_acceptance_dispatch_candidates(db, limit=limit)
    dispatched_requirement_ids: list[int] = []
    if auto_dispatch:
        for candidate in candidates:
            requirement = _require_requirement(db, int(candidate["requirement_id"]))
            if str(requirement.status or "") in {"deleted", "done", "blocked"}:
                continue
            _dispatch_next_step_for_requirement(int(requirement.id))
            dispatched_requirement_ids.append(int(requirement.id))
    return {
        "scanned": len(candidates),
        "dispatched_requirement_ids": dispatched_requirement_ids,
        "candidates": candidates,
    }


def decide_requirement_approval(
    db: Session,
    requirement_id: int,
    *,
    action: str,
    reviewer: str,
    comment: str = "",
) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    workflow_run = _active_workflow_run(db, requirement)
    if action not in {"approve", "reject", "waive"}:
        raise ValueError("action must be approve|reject|waive")

    pending = db.query(ApprovalRequestRow).filter(
        ApprovalRequestRow.requirement_id == requirement.id,
        ApprovalRequestRow.approval_type == "requirement_execution_approval",
        ApprovalRequestRow.status == "pending",
    ).all()
    current_decision = evaluate_requirement_execution_approval(requirement, workflow_run=workflow_run)
    for approval in pending:
        approval.status = "approved" if action in {"approve", "waive"} else "rejected"
        approval.reviewer = reviewer
        approval.comment = comment or approval.comment
        approval.decided_at = utcnow()

    if action == "approve":
        requirement.approval_status = "approved"
        requirement.approved_at = utcnow()
        if requirement.status == "blocked" and requirement.blocked_by_count == 0:
            requirement.status = "draft" if int(requirement.current_plan_version or 0) == 0 else "ready"
    elif action == "waive":
        requirement.approval_status = "waived"
        requirement.approved_at = utcnow()
        if requirement.status == "blocked" and requirement.blocked_by_count == 0:
            requirement.status = "draft" if int(requirement.current_plan_version or 0) == 0 else "ready"
    else:
        requirement.approval_status = "rejected"
        requirement.approved_at = None
        requirement.status = "blocked"
    requirement.approval_requested_at = None
    _record_requirement_approval_artifact(
        db,
        requirement=requirement,
        workflow_run=workflow_run,
        content_summary=f"Requirement #{requirement.id} approval {action}",
        payload={
            "approval_status": requirement.approval_status,
            "action": action,
            "reviewer": reviewer,
            "comment": comment,
            "approval_contract": requirement_approval_contract_for_requirement(requirement),
            "approval_source": str(current_decision.get("approval_source") or "human"),
            "approval_router": dict(current_decision.get("approval_router") or {}),
            "approval_recommendation": dict(current_decision.get("approval_recommendation") or {}),
        },
    )
    db.commit()
    if action in {"approve", "waive"}:
        return _plan_requirement_after_approval(
            db,
            requirement_id=requirement.id,
            trigger="approval_decision",
            raise_on_failure=False,
        )
    return build_requirement_detail(db, requirement.id)


def close_requirement(db: Session, requirement_id: int) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    if requirement.status == "done":
        return build_requirement_detail(db, requirement.id)
    workflow_run = _active_workflow_run(db, requirement)
    validation_errors = _validation_gate_errors(db, requirement.id)
    if validation_errors:
        raise ValueError(
            "Requirement cannot close before validation passes: " + "; ".join(validation_errors)
        )
    if workflow_run is not None and workflow_run.status not in {"completed", "cancelled", "failed"}:
        raise ValueError("Requirement cannot close while workflow execution is still active.")
    if workflow_run is not None and _latest_artifact(
        db,
        requirement.id,
        "validation_manifest",
        workflow_run_id=workflow_run.id,
    ) is None:
        _create_artifact(
            db,
            requirement_id=requirement.id,
            workflow_run_id=workflow_run.id,
            artifact_type="validation_manifest",
            content_summary=f"Manual closeout for requirement #{requirement.id}",
            human_readable_body=_manual_closeout_markdown(requirement, db),
            machine_readable_payload=_manual_closeout_payload(db, requirement, workflow_run),
        )
        workflow_run.status = "completed"
        workflow_run.completed_at = workflow_run.completed_at or utcnow()
    if workflow_run is not None and _latest_artifact(
        db,
        requirement.id,
        "delivery_state",
        workflow_run_id=workflow_run.id,
    ) is None:
        vcs_payload, _artifact = _execute_requirement_vcs_delivery(db, requirement, workflow_run, None)
        pr_payload: dict[str, Any] = {}
        if not ((vcs_payload.get("blockers") or []) and str(vcs_payload.get("status") or "") != "delivered"):
            pr_payload, _pr_artifact = _sync_requirement_review_pr(
                db,
                requirement,
                workflow_run,
                None,
                vcs_payload=vcs_payload,
            )
        if ((vcs_payload.get("blockers") or []) and str(vcs_payload.get("status") or "") != "delivered") or (pr_payload.get("blockers") or []):
            requirement.status = "blocked"
            requirement.completed_at = None
            if workflow_run is not None:
                workflow_run.status = "paused"
                workflow_run.completed_at = None
            _record_delivery_state(
                db,
                requirement,
                workflow_run,
                review_status="blocked",
                publish_status="blocked",
                vcs_payload=vcs_payload,
                pr_payload=pr_payload,
            )
            db.commit()
            raise ValueError("Requirement cannot close before delivery branch/PR sync succeeds.")
        delivery_contract = _delivery_contract_payload(db, requirement.id)
        _record_delivery_state(
            db,
            requirement,
            workflow_run,
            review_status="review_ready",
            publish_status="blocked" if str(delivery_contract.get("release_mode") or "manual") == "disabled" else "review_ready",
            vcs_payload=vcs_payload,
            pr_payload=pr_payload,
        )
    requirement.status = "done"
    requirement.completed_at = requirement.completed_at or utcnow()
    _refresh_dependents_for_requirement(db, requirement.id)
    db.commit()
    _logger.info("event=requirement_closed requirement_id=%s manual=true", requirement.id)
    return build_requirement_detail(db, requirement.id)


def publish_requirement(
    db: Session,
    requirement_id: int,
    body: RequirementPublishRequest | None = None,
) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)

    workflow_run = _active_workflow_run(db, requirement)
    delivery_contract = _delivery_contract_payload(db, requirement.id)
    if not delivery_contract:
        raise ValueError("Requirement has no delivery contract. Plan it first.")
    if requirement.status != "done":
        raise ValueError("Requirement must be done before publish can be promoted.")

    validation_errors = _validation_gate_errors(db, requirement.id)
    if validation_errors:
        raise ValueError(
            "Requirement cannot publish before validation passes: " + "; ".join(validation_errors)
        )

    release_mode = str(delivery_contract.get("release_mode") or "manual")
    if release_mode == "disabled":
        raise ValueError("Publish is disabled by project policy.")

    completed_checks = []
    for check in (body.completed_checks if body is not None else []):
        value = str(check).strip()
        if value and value not in completed_checks:
            completed_checks.append(value)
    required_checks = [str(item) for item in delivery_contract.get("required_checks") or [] if str(item).strip()]
    missing_checks = [check for check in required_checks if check not in completed_checks]
    if missing_checks:
        raise ValueError(
            "Publish blocked until required checks are confirmed: " + ", ".join(missing_checks)
        )

    latest_state = _latest_artifact(
        db,
        requirement.id,
        "delivery_state",
        workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
    )
    latest_state_payload = _json_loads(getattr(latest_state, "machine_readable_payload", None), {})
    if isinstance(latest_state_payload, dict) and latest_state_payload.get("publish_status") == "published":
        return build_requirement_detail(db, requirement.id)
    pr_status = str(latest_state_payload.get("pr_status") or "").strip()
    if pr_status in {"", "missing"}:
        vcs_payload = _latest_vcs_delivery_payload(
            db,
            _as_int(requirement.id),
            workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
        )
        pr_payload, _pr_artifact = _sync_requirement_review_pr(
            db,
            requirement,
            workflow_run,
            None,
            vcs_payload=vcs_payload,
        )
        if pr_payload:
            latest_state_payload = _delivery_state_payload(
                db,
                requirement,
                workflow_run,
                review_status=str(latest_state_payload.get("review_status") or "review_ready"),
                publish_status=str(latest_state_payload.get("publish_status") or "review_ready"),
                confirmed_checks=list(latest_state_payload.get("confirmed_checks") or []),
                publish_note=str(latest_state_payload.get("publish_note") or "") or None,
                vcs_payload=vcs_payload,
                pr_payload=pr_payload,
            )
    pr_status = str(latest_state_payload.get("pr_status") or "").strip()
    if pr_status in {"", "missing"}:
        raise ValueError("Publish blocked until a review PR is created or synced.")
    if pr_status in {"closed"}:
        raise ValueError("Publish blocked because the review PR is closed.")

    note = (body.note if body is not None else None) or ""
    _create_artifact(
        db,
        requirement_id=requirement.id,
        workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
        artifact_type="publish_record",
        content_summary=f"Published requirement #{requirement.id}",
        human_readable_body=_publish_record_markdown(requirement, delivery_contract, completed_checks, note),
        machine_readable_payload={
            "requirement_id": _as_int(requirement.id),
            "workflow_run_id": _as_int(workflow_run.id) if workflow_run is not None else None,
            "branch_name": delivery_contract.get("branch_name"),
            "base_branch": delivery_contract.get("base_branch"),
            "release_mode": release_mode,
            "completed_checks": completed_checks,
            "publish_note": note or None,
            "published_at": utcnow().isoformat(),
            "promoted_commit_sha": str(latest_state_payload.get("latest_remote_sha") or latest_state_payload.get("latest_commit_sha") or "") or None,
            "pr_number": latest_state_payload.get("pr_number"),
            "pr_url": latest_state_payload.get("pr_url"),
        },
    )
    _record_delivery_state(
        db,
        requirement,
        workflow_run,
        publish_status="published",
        confirmed_checks=completed_checks,
        publish_note=note or None,
        vcs_payload=_latest_vcs_delivery_payload(
            db,
            _as_int(requirement.id),
            workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
        ),
        pr_payload=_latest_review_pr_payload(
            db,
            _as_int(requirement.id),
            workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
        ),
    )
    db.commit()
    _logger.info(
        "event=requirement_published requirement_id=%s release_mode=%s confirmed_checks=%s",
        requirement.id,
        release_mode,
        len(completed_checks),
    )
    return build_requirement_detail(db, requirement.id)


def sync_requirement_review_pr_surface(db: Session, requirement_id: int) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    workflow_run = _active_workflow_run(db, requirement)
    delivery_contract = _delivery_contract_payload(db, requirement.id)
    if not delivery_contract:
        raise ValueError("Requirement has no delivery contract. Plan it first.")
    vcs_payload = _latest_vcs_delivery_payload(
        db,
        _as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
    )
    if not vcs_payload:
        vcs_payload, _artifact = _execute_requirement_vcs_delivery(db, requirement, workflow_run, None)
    pr_payload, _pr_artifact = _sync_requirement_review_pr(
        db,
        requirement,
        workflow_run,
        None,
        delivery_contract=delivery_contract,
        vcs_payload=vcs_payload,
    )
    review_status = "review_ready" if requirement.status == "done" and not (pr_payload.get("blockers") or []) else "planned"
    publish_status = "published" if requirement.status == "done" and _latest_artifact(
        db,
        requirement.id,
        "publish_record",
        workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
    ) is not None else ("review_ready" if review_status == "review_ready" else "planned")
    _record_delivery_state(
        db,
        requirement,
        workflow_run,
        review_status=review_status if not (pr_payload.get("blockers") or []) else "blocked",
        publish_status=publish_status if not (pr_payload.get("blockers") or []) else "blocked",
        vcs_payload=vcs_payload,
        pr_payload=pr_payload,
    )
    db.commit()
    return build_requirement_detail(db, requirement.id)


def delete_requirement(db: Session, requirement_id: int) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    if requirement.status == "deleted":
        return build_requirement_detail(db, requirement.id)
    _soft_delete_requirement_tree(db, requirement, visited=set())
    db.commit()
    _logger.info("event=requirement_deleted requirement_id=%s", requirement.id)
    return build_requirement_detail(db, requirement.id)


def revise_requirement(db: Session, requirement_id: int, body: RequirementRevisionRequest) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    active_run = _active_workflow_run(db, requirement)
    previous_title = requirement.title
    previous_description = requirement.description_markdown

    if active_run is not None:
        active_run.status = "cancelled"
        for step in db.query(WorkflowStepRow).filter(WorkflowStepRow.workflow_run_id == active_run.id).all():
            if step.status in TERMINAL_STEP_STATUSES:
                continue
            task = None
            if step.compatibility_task_id:
                task = db.query(TaskRow).filter(TaskRow.id == step.compatibility_task_id).first()
            if task is not None and str(getattr(cast(Any, task), "status", "") or "") not in {
                "completed",
                "failed",
                "cancelled",
                "deleted",
            }:
                _terminate_task_runtime(task)
                cast(Any, task).status = "cancelled"
                cast(Any, task).last_error_message = body.revision_note or "Requirement revised"
                cast(Any, task).completed_at = task.completed_at or utcnow()
                db.add(
                    TaskLogRow(
                        task_id=task.id,
                        event_type="cancelled",
                        detail=body.revision_note or "Requirement revised",
                    )
                )
            step.status = "cancelled"
            step.completed_at = step.completed_at or utcnow()
            step.runtime_session_id = None
            step.runtime_backend = ""
            step.compatibility_task_id = None
            _record_step_event(db, step.id, "status_change", "cancelled (revision)")

    db.query(RequirementAcceptanceCheckRow).filter(
        RequirementAcceptanceCheckRow.requirement_id == requirement.id
    ).delete(synchronize_session=False)

    for approval in db.query(ApprovalRequestRow).filter(
        ApprovalRequestRow.requirement_id == requirement.id,
        ApprovalRequestRow.status == "pending",
    ).all():
        approval.status = "approved"
        approval.reviewer = "system"
        approval.decided_at = utcnow()
        approval.comment = body.revision_note or "Requirement revision submitted"

    if body.depends_on_requirement_ids is not None:
        _replace_dependencies(db, requirement.id, body.depends_on_requirement_ids)

    requirement.title = (body.title or requirement.title).strip()
    requirement.description_markdown = body.description_markdown.strip()
    if body.source_ref is not None:
        requirement.source_ref = body.source_ref
    requirement.active_workflow_run_id = None
    requirement.current_plan_version = 0
    requirement.planned_roles_json = "[]"
    requirement.started_at = None
    requirement.completed_at = None
    requirement.status = "draft"
    requirement.approval_status = _default_requirement_approval_status(requirement)
    requirement.approval_requested_at = None
    requirement.approved_at = utcnow() if requirement.approval_status == "waived" else None
    requirement.intake_metadata_json = json.dumps(
        normalize_requirement_intake_metadata(
            requirement.source,
            requirement.source_ref,
            _json_loads(requirement.intake_metadata_json, {}),
        ),
        ensure_ascii=False,
    )

    _create_artifact(
        db,
        requirement_id=requirement.id,
        artifact_type="requirement_revision",
        content_summary=f"Revision for requirement #{requirement.id}",
        human_readable_body=body.revision_note or requirement.description_markdown,
        machine_readable_payload={
            "previous_title": previous_title,
            "previous_description_markdown": previous_description,
            "title": requirement.title,
            "description_markdown": requirement.description_markdown,
            "revision_note": body.revision_note,
        },
    )

    _refresh_requirement_dependency_state(db, requirement)
    _refresh_dependents_for_requirement(db, requirement.id)
    db.commit()
    _logger.info(
        "event=requirement_revised requirement_id=%s had_active_run=%s dependency_count=%s",
        requirement.id,
        active_run is not None,
        len(body.depends_on_requirement_ids or []),
    )
    return build_requirement_detail(db, requirement.id)


def start_requirement(db: Session, requirement_id: int) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    _reconcile_active_workflow_run(db, requirement)
    resolve_project_policies_for_target(
        db,
        _normalize_target_project_path(requirement.target_project_path),
        require_active=bool(requirement.target_project_path),
    )
    if requirement.status == "in_progress":
        return build_requirement_detail(db, requirement.id)
    if requirement.status == "planning":
        raise ValueError("Requirement is currently generating workflow plan.")
    _refresh_requirement_dependency_state(db, requirement)
    if requirement.blocked_by_count > 0:
        raise ValueError("Requirement is blocked by unfinished dependencies.")

    active_workflow_run = None
    if requirement.active_workflow_run_id is not None:
        active_workflow_run = (
            db.query(WorkflowRunRow)
            .filter(WorkflowRunRow.id == requirement.active_workflow_run_id)
            .first()
        )
        if active_workflow_run is None or str(active_workflow_run.status or "") in {
            "completed",
            "cancelled",
            "failed",
            "deleted",
        }:
            requirement.active_workflow_run_id = None
            active_workflow_run = None
            if requirement.status in {"in_progress", "paused", "needs_revision"}:
                requirement.status = "ready"
            db.flush()

    current_approval_status = normalize_requirement_approval_status(requirement.approval_status)
    if current_approval_status in {"approved", "waived"}:
        approval_decision = {
            "approval_status": current_approval_status,
            "reason": "requirement already approved",
        }
    else:
            approval_decision = _sync_requirement_execution_approval(
                db,
                requirement=requirement,
                workflow_run=active_workflow_run,
            )
    if normalize_requirement_approval_status(requirement.approval_status) in {"pending_approval", "rejected"}:
        db.commit()
        raise ValueError(
            "Requirement must be approved before automatic execution: "
            + str(approval_decision.get("reason") or "pending approval")
        )

    if int(requirement.current_plan_version or 0) == 0 or active_workflow_run is None:
        _plan_requirement_after_approval(
            db,
            requirement_id=requirement_id,
            trigger="start_requirement",
            raise_on_failure=True,
        )
        requirement = _require_requirement(db, requirement_id)

    workflow_run = _active_workflow_run(db, requirement)
    if workflow_run is None:
        raise ValueError("Requirement has no active workflow run. Plan it first.")

    if workflow_run.status == "completed":
        return build_requirement_detail(db, requirement.id)

    from server.services.portfolio_scheduler import validate_requirement_start_capacity

    capacity_error = validate_requirement_start_capacity(db, requirement)
    if capacity_error:
        raise ValueError(capacity_error)

    workflow_run.completed_at = None
    if workflow_run.status == "paused":
        workflow_run.status = "pending"
    if requirement.status == "paused":
        requirement.status = "ready"
    requirement.completed_at = None
    db.commit()

    _dispatch_next_step_for_requirement(requirement.id)
    db.expire_all()
    _logger.info(
        "event=requirement_started requirement_id=%s workflow_run_id=%s plan_version=%s",
        requirement.id,
        workflow_run.id,
        workflow_run.plan_version,
    )

    fresh_db = SessionLocal()
    try:
        return build_requirement_detail(fresh_db, requirement.id)
    finally:
        fresh_db.close()


def pause_requirement(db: Session, requirement_id: int) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    workflow_run = _active_workflow_run(db, requirement)
    if workflow_run is None:
        raise ValueError("Requirement is not currently running.")

    running_steps = db.query(WorkflowStepRow).filter(
        WorkflowStepRow.workflow_run_id == workflow_run.id,
        WorkflowStepRow.status.in_(tuple(RUNNING_STEP_STATUSES)),
    ).all()
    if not running_steps and requirement.status != "in_progress" and workflow_run.status != "running":
        raise ValueError("Requirement has no running workflow step to pause.")

    for step in running_steps:
        _pause_workflow_step(db, step)

    workflow_run.status = "paused"
    workflow_run.started_at = None
    workflow_run.completed_at = None
    requirement.status = "paused"
    requirement.started_at = None
    requirement.completed_at = None
    _clear_role_sessions()
    db.commit()
    _logger.info("event=requirement_paused requirement_id=%s running_steps=%s", requirement.id, len(running_steps))
    return build_requirement_detail(db, requirement.id)


def pause_task(
    db: Session,
    task_id: int,
    *,
    reason: str = "Paused by user",
    event_detail: str | None = None,
) -> TaskRow:
    """Pause a running task and cascade the pause to its parent requirement.

    Sets the task status to 'paused', terminates the runtime, resets the linked
    workflow step back to 'ready', and pauses the parent requirement if it is
    currently in_progress.
    """
    task = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if task is None:
        raise ValueError(f"Task #{task_id} not found")
    task_status = str(getattr(cast(Any, task), "status", "") or "")
    if task_status != "running":
        raise ValueError(f"Task #{task_id} is not running (status={task_status})")

    _terminate_task_runtime(task)
    cast(Any, task).status = "cancelled"
    cast(Any, task).last_error_message = reason
    db.add(TaskLogRow(task_id=task_id, event_type="paused", detail=event_detail or reason))

    # Reset the linked workflow step back to ready
    step = db.query(WorkflowStepRow).filter(
        WorkflowStepRow.compatibility_task_id == task_id
    ).first()
    if step is not None:
        step.status = "ready"
        step.runtime_session_id = None
        step.runtime_backend = ""
        step.compatibility_task_id = None
        step.started_at = None
        step.completed_at = None
        _record_step_event(db, step.id, "status_change", event_detail or "ready (task paused)")

        # Cascade to parent requirement
        parent_req = db.query(RequirementRow).filter(
            RequirementRow.id == step.requirement_id
        ).first()
        if parent_req is not None and str(getattr(cast(Any, parent_req), "status", "") or "") == "in_progress":
            workflow_run = _active_workflow_run(db, parent_req)
            if workflow_run is not None:
                workflow_run.status = "paused"
                workflow_run.started_at = None
                workflow_run.completed_at = None
            cast(Any, parent_req).status = "paused"
            cast(Any, parent_req).started_at = None
            cast(Any, parent_req).completed_at = None
            _clear_role_sessions()

    db.commit()
    db.refresh(task)
    return task


def build_requirement_detail(db: Session, requirement_id: int) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    workflow_run = _active_workflow_run(db, requirement)
    steps = []
    task_outputs: list[dict[str, Any]] = []
    merged_output_files: list[dict[str, Any]] = []
    if workflow_run is not None:
        rows = db.query(WorkflowStepRow).filter(WorkflowStepRow.workflow_run_id == workflow_run.id).order_by(
            WorkflowStepRow.sequence_no.asc(), WorkflowStepRow.id.asc()
        ).all()
        steps = [WorkflowStepOut.model_validate(row) for row in rows]
        task_outputs, merged_output_files = _requirement_task_outputs(db, requirement, workflow_run)

    checks = db.query(RequirementAcceptanceCheckRow).filter(
        RequirementAcceptanceCheckRow.requirement_id == requirement.id
    ).order_by(RequirementAcceptanceCheckRow.id.asc()).all()
    dependency_rows = db.query(RequirementDependencyRow).filter(
        RequirementDependencyRow.requirement_id == requirement.id
    ).order_by(RequirementDependencyRow.id.asc()).all()
    dependency_requirements = {
        row.id: row
        for row in db.query(RequirementRow).filter(
            RequirementRow.id.in_([dep.depends_on_requirement_id for dep in dependency_rows] or [-1])
        ).all()
    }
    artifacts = db.query(ArtifactRow).filter(ArtifactRow.requirement_id == requirement.id).order_by(ArtifactRow.id.asc()).all()
    run_out = None
    if workflow_run is not None:
        run_out = WorkflowRunOut.model_validate(workflow_run)
        run_out.steps = steps
        validation_payload = _validation_plan_payload(db, _as_int(requirement.id))
        run_out.step_model_version = str(validation_payload.get("step_model_version") or "1.0")

    return RequirementDetailOut(
        requirement=RequirementOut(**serialize_requirement(db, requirement)),
        workflow_run=run_out,
        dependencies=[
            RequirementDependencyOut(
                id=dep.id,
                requirement_id=dep.requirement_id,
                depends_on_requirement_id=dep.depends_on_requirement_id,
                depends_on_title=dependency_requirements.get(dep.depends_on_requirement_id).title,
                depends_on_status=dependency_requirements.get(dep.depends_on_requirement_id).status,
                dependency_type=dep.dependency_type,
            )
            for dep in dependency_rows
            if dependency_requirements.get(dep.depends_on_requirement_id) is not None
        ],
        acceptance_checks=[RequirementAcceptanceCheckOut.model_validate(check) for check in checks],
        artifacts=[ArtifactOut.model_validate(artifact) for artifact in artifacts],
        delivery_state=_build_delivery_state(db, requirement),
        incidents=[IncidentRecordOut(**incident) for incident in list_requirement_incidents(db, requirement_id)],
        task_outputs=task_outputs,
        merged_output_files=merged_output_files,
    )


def sync_workflow_for_task(task_id: int):
    db = SessionLocal()
    try:
        _sync_workflow_for_task_db(db, task_id)
    finally:
        db.close()


def _sync_workflow_for_task_db(db: Session, task_id: int):
    step = db.query(WorkflowStepRow).filter(WorkflowStepRow.compatibility_task_id == task_id).first()
    if not step:
        return

    task = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not task:
        return

    run = db.query(WorkflowRunRow).filter(WorkflowRunRow.id == step.workflow_run_id).first()
    requirement = _require_requirement(db, step.requirement_id)
    if (
        step.status in DELETED_STEP_STATUSES
        or requirement.status in DELETED_REQUIREMENT_STATUSES
        or (run is not None and run.status in DELETED_WORKFLOW_STATUSES)
    ):
        return
    should_dispatch_next = False

    if task.status == "running":
        step.status = "running"
        step.runtime_session_id = task.runtime_session_id
        step.runtime_backend = task.runtime_backend or ""
        step.started_at = step.started_at or task.started_at or utcnow()
        _record_runtime_lifecycle_artifacts(db, step, task, phase="running")
        _record_step_event(db, step.id, "status_change", "running")
        db.commit()
        return

    if task.status == "pending_approval":
        step.status = "waiting_approval"
        step.runtime_session_id = task.runtime_session_id
        step.runtime_backend = task.runtime_backend or ""
        step.started_at = step.started_at or task.started_at or utcnow()
        run.status = "running"
        _record_runtime_lifecycle_artifacts(db, step, task, phase="waiting_approval")
        _record_step_event(db, step.id, "status_change", "waiting_approval")
        db.commit()
        return

    if task.status == "completed":
        step.status = "completed"
        step.runtime_session_id = task.runtime_session_id
        step.runtime_backend = task.runtime_backend or ""
        step.started_at = step.started_at or task.started_at or utcnow()
        step.completed_at = task.completed_at or utcnow()
        _populate_handoff_summary(step, task)
        _record_runtime_lifecycle_artifacts(db, step, task, phase="completed")
        _record_step_event(db, step.id, "status_change", "completed")
        artifact = _create_step_completion_artifact(db, step, task)
        # Snapshot git diff now, before the next step is dispatched
        _snapshot_file_changes(db, task, requirement, step)
        project_change_artifact = _record_project_change_summary_artifact(
            db,
            requirement=requirement,
            workflow_run=run,
            step=step,
            task=task,
        )
        _record_budget_usage_artifact(db, requirement=requirement, workflow_run=run)
        if project_change_artifact is not None and step.step_type in {"implementation", "bugfix"}:
            _refresh_dynamic_validation_contracts(
                db,
                requirement=requirement,
                workflow_run=run,
            )
        if _task_has_tracked_repo_changes(task):
            if str(step.step_type or "") in NON_MUTATING_STEP_TYPES:
                _block_unexpected_non_mutating_repo_changes(
                    db,
                    requirement,
                    run,
                    step,
                    task,
                )
                should_dispatch_next = False
                _refresh_run_status(db, requirement, run)
                db.commit()
                return
        if _task_has_tracked_repo_changes(task) and _step_requires_branch_delivery(step):
            delivery_ok, _step_vcs_payload, _step_pr_payload = _sync_step_delivery_branch(
                db,
                requirement,
                run,
                step,
            )
            if not delivery_ok:
                should_dispatch_next = False
                _refresh_run_status(db, requirement, run)
                db.commit()
                return
        target_failures = _mark_step_targets_passed(db, requirement, step, artifact, task=task)
        if target_failures:
            step.status = "failed"
            failure_count = _failure_count_for_step(step)
            step.retry_count = failure_count
            _record_step_event(db, step.id, "validation_failed", "; ".join(target_failures))
            error_text = "; ".join(target_failures)
            bug_report_payload = _build_bug_report_payload(db, requirement, run, step, task, error_text)
            error_artifact = _create_artifact(
                db,
                requirement_id=step.requirement_id,
                workflow_run_id=step.workflow_run_id,
                step_id=step.id,
                producer_step_id=step.id,
                artifact_type="bug_report",
                content_summary=error_text[:200],
                human_readable_body=error_text,
                machine_readable_payload=bug_report_payload,
            )
            _am_push_task_failed(task, step, requirement)
            if step.step_type in {"implementation", "validate", "review", "test", "bugfix"}:
                project_metrics = _project_change_metrics(db, _as_int(requirement.id), workflow_run_id=_as_int(run.id))
                bugfix_profile = _build_followup_execution_profile(
                    step,
                    step_type="bugfix",
                    failure_count=failure_count,
                    error_text=error_text,
                    project_change_metrics=project_metrics,
                )
                validate_profile = _build_followup_execution_profile(
                    step,
                    step_type="validate",
                    failure_count=failure_count,
                    error_text=error_text,
                    project_change_metrics=project_metrics,
                )
                circuit_breaker_reason = _bugfix_circuit_breaker_reason(db, requirement, run, step, error_text)
                if circuit_breaker_reason:
                    _trip_bugfix_circuit_breaker(
                        db,
                        requirement,
                        run,
                        step,
                        error_artifact,
                        error_text,
                        circuit_breaker_reason,
                    )
                else:
                    _create_bugfix_branch(
                        db,
                        requirement,
                        run,
                        step,
                        error_artifact,
                        bugfix_execution_profile=bugfix_profile,
                        validate_execution_profile=validate_profile,
                    )
                    should_dispatch_next = True
            else:
                run.status = "failed"
                requirement.status = "needs_revision"
        else:
            _bind_output_to_followup_steps(db, step, artifact)
            if project_change_artifact is not None:
                _bind_output_to_followup_steps(db, step, project_change_artifact)
            _am_push_task_completed(task, step, requirement)
            if step.step_type == "closeout":
                _finalize_requirement(db, requirement, run, step, artifact)
            else:
                should_dispatch_next = True
        if _budget_guardrail_after_task(db, requirement=requirement, workflow_run=run, step=step, task=task):
            should_dispatch_next = False

    elif task.status in {"failed", "rejected"}:
        step.status = "failed"
        failure_count = _failure_count_for_step(step)
        step.retry_count = failure_count
        step.started_at = step.started_at or task.started_at or utcnow()
        step.completed_at = task.completed_at or utcnow()
        _record_runtime_lifecycle_artifacts(db, step, task, phase="failed")
        _record_step_event(db, step.id, "status_change", f"failed ({task.status})")
        error_text = task.last_error_message or task.output_content or "Workflow step failed"
        bug_report_payload = _build_bug_report_payload(db, requirement, run, step, task, error_text)
        error_artifact = _create_artifact(
            db,
            requirement_id=step.requirement_id,
            workflow_run_id=step.workflow_run_id,
            step_id=step.id,
            producer_step_id=step.id,
            artifact_type="bug_report",
            content_summary=error_text[:200],
            human_readable_body=error_text,
            machine_readable_payload=bug_report_payload,
        )
        _mark_step_targets_failed(db, step, error_artifact)
        _am_push_task_failed(task, step, requirement)
        _record_budget_usage_artifact(db, requirement=requirement, workflow_run=run)
        failure_route = _resolve_failure_route(step, error_text)
        if failure_route == "requirement_revision":
            _create_requirement_revision_request(db, requirement, run, step, error_artifact, error_text)
        elif step.step_type in {"implementation", "validate", "review", "test", "bugfix"}:
            project_metrics = _project_change_metrics(db, _as_int(requirement.id), workflow_run_id=_as_int(run.id))
            bugfix_profile = _build_followup_execution_profile(
                step,
                step_type="bugfix",
                failure_count=failure_count,
                error_text=error_text,
                project_change_metrics=project_metrics,
            )
            validate_profile = _build_followup_execution_profile(
                step,
                step_type="validate",
                failure_count=failure_count,
                error_text=error_text,
                project_change_metrics=project_metrics,
            )
            circuit_breaker_reason = _bugfix_circuit_breaker_reason(db, requirement, run, step, error_text)
            if circuit_breaker_reason:
                _trip_bugfix_circuit_breaker(
                    db,
                    requirement,
                    run,
                    step,
                    error_artifact,
                    error_text,
                    circuit_breaker_reason,
                )
            else:
                _create_bugfix_branch(
                    db,
                    requirement,
                    run,
                    step,
                    error_artifact,
                    bugfix_execution_profile=bugfix_profile,
                    validate_execution_profile=validate_profile,
                )
                should_dispatch_next = True
        else:
            run.status = "failed"
            requirement.status = "needs_revision"
        if _budget_guardrail_after_task(db, requirement=requirement, workflow_run=run, step=step, task=task):
            should_dispatch_next = False

    _refresh_run_status(db, requirement, run)
    db.commit()

    if should_dispatch_next:
        _dispatch_next_step_for_requirement(requirement.id)


def _interrupt_step_for_policy(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
) -> bool:
    policy = _json_loads(getattr(step, "approval_policy_json", None), {})
    if not isinstance(policy, dict) or not policy:
        return False

    approval_type: str | None = None
    event_type: str | None = None
    reason = ""

    if bool(policy.get("deny_execution")):
        approval_type = "capability_policy_review"
        event_type = "capability_denied"
        reason = "; ".join(str(item) for item in policy.get("deny_reasons") or [] if str(item).strip()) or "step denied by capability matrix"
    elif bool(policy.get("requires_operator_confirmation")):
        approval_type = "step_operator_confirmation"
        event_type = "operator_confirmation_required"
        actions = ", ".join(str(item) for item in policy.get("operator_confirmation_actions") or [] if str(item).strip())
        reason = f"operator confirmation required before step may use: {actions}" if actions else "operator confirmation required"
    else:
        return False

    interrupt_policy = policy.get("interrupt_policy") or {}
    auto_abort_events = set(str(item) for item in interrupt_policy.get("auto_abort_on_events") or [] if str(item).strip())
    auto_pause_events = set(str(item) for item in interrupt_policy.get("auto_pause_on_events") or [] if str(item).strip())

    existing = db.query(ApprovalRequestRow).filter(
        ApprovalRequestRow.requirement_id == requirement.id,
        ApprovalRequestRow.step_id == step.id,
        ApprovalRequestRow.approval_type == approval_type,
        ApprovalRequestRow.status == "pending",
    ).first()
    if existing is None:
        db.add(
            ApprovalRequestRow(
                requirement_id=requirement.id,
                workflow_run_id=workflow_run.id,
                step_id=step.id,
                approval_type=approval_type,
                status="pending",
                reviewer="operator",
                comment=reason,
            )
        )
    _create_artifact(
        db,
        requirement_id=step.requirement_id,
        workflow_run_id=step.workflow_run_id,
        step_id=step.id,
        producer_step_id=step.id,
        artifact_type="capability_interrupt",
        content_summary=reason[:200],
        human_readable_body=reason,
        machine_readable_payload={
            "step_id": _as_int(step.id),
            "step_key": str(step.step_key),
            "step_type": str(step.step_type),
            "event_type": event_type,
            "approval_type": approval_type,
            "approval_policy": policy,
            "triggered_at": utcnow().isoformat(),
        },
    )
    step.status = "blocked"
    step.completed_at = None
    if event_type in auto_abort_events:
        workflow_run.status = "failed"
        workflow_run.completed_at = utcnow()
        requirement.status = "needs_revision"
    elif event_type in auto_pause_events or approval_type == "step_operator_confirmation":
        workflow_run.status = "paused"
        requirement.status = "blocked"
    else:
        workflow_run.status = "paused"
        requirement.status = "blocked"
    _record_step_event(db, step.id, event_type or "policy_interrupt", reason)
    _logger.warning(
        "event=step_policy_interrupt requirement_id=%s workflow_run_id=%s step_id=%s event=%s reason=%s",
        requirement.id,
        workflow_run.id,
        step.id,
        event_type,
        reason,
    )
    return True


def _interrupt_step_for_stale_context(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
    context_snapshot: dict[str, Any],
) -> bool:
    context_policy = dict(context_snapshot.get("context_policy") or {})
    if not bool(context_policy.get("block_on_stale_memory", True)):
        return False
    if str(context_snapshot.get("verification_status") or "fresh") == "fresh":
        return False

    reason = "; ".join(str(item) for item in context_snapshot.get("stale_findings") or [] if str(item).strip()) or "stale memory verification failed"
    existing = db.query(ApprovalRequestRow).filter(
        ApprovalRequestRow.requirement_id == requirement.id,
        ApprovalRequestRow.step_id == step.id,
        ApprovalRequestRow.approval_type == "stale_memory_review",
        ApprovalRequestRow.status == "pending",
    ).first()
    if existing is None:
        db.add(
            ApprovalRequestRow(
                requirement_id=requirement.id,
                workflow_run_id=workflow_run.id,
                step_id=step.id,
                approval_type="stale_memory_review",
                status="pending",
                reviewer="operator",
                comment=reason,
            )
        )
    step.status = "blocked"
    workflow_run.status = "paused"
    requirement.status = "blocked"
    _record_step_event(db, step.id, "stale_memory_blocked", reason)
    _logger.warning(
        "event=stale_memory_blocked requirement_id=%s workflow_run_id=%s step_id=%s reason=%s",
        requirement.id,
        workflow_run.id,
        step.id,
        reason,
    )
    return True


def _dispatch_next_step_for_requirement(requirement_id: int):
    db = SessionLocal()
    try:
        requirement = _require_requirement(db, requirement_id)
        if requirement.status in DELETED_REQUIREMENT_STATUSES:
            return
        workflow_run = _active_workflow_run(db, requirement)
        if workflow_run is None:
            return
        if workflow_run.status in DELETED_WORKFLOW_STATUSES:
            return
        if db.query(WorkflowStepRow).filter(
            WorkflowStepRow.workflow_run_id == workflow_run.id,
            WorkflowStepRow.status.in_(tuple(RUNNING_STEP_STATUSES)),
        ).count():
            return

        steps = db.query(WorkflowStepRow).filter(WorkflowStepRow.workflow_run_id == workflow_run.id).order_by(
            WorkflowStepRow.sequence_no.asc(), WorkflowStepRow.id.asc()
        ).all()

        # Refresh ready/blocked state for schedulable steps
        for step in steps:
            if step.status not in SCHEDULABLE_STEP_STATUSES:
                continue
            if _dependencies_satisfied(db, step.id):
                if step.status != "ready":
                    step.status = "ready"
                    _record_step_event(db, step.id, "status_change", "ready")
            else:
                if step.status != "blocked":
                    step.status = "blocked"
                    _record_step_event(db, step.id, "status_change", "blocked (deps pending)")

        for step in steps:
            if step.status != "ready":
                continue
            context_snapshot = _materialize_step_context(db, step)
            profile = _step_execution_profile(step)
            budget_cap = profile.get("budget_cap") or {}
            if isinstance(budget_cap, dict):
                max_attempts = int(budget_cap.get("max_attempts") or 0)
                failure_count = max(int(step.retry_count or 0), int(profile.get("failure_count") or 0))
                if max_attempts > 0 and failure_count >= max_attempts:
                    _pause_for_budget_guardrail(
                        db,
                        requirement=requirement,
                        workflow_run=workflow_run,
                        step=step,
                        reason=f"Step exceeded max_attempts budget ({failure_count}/{max_attempts})",
                        payload={
                            "requirement_id": _as_int(requirement.id),
                            "workflow_run_id": _as_int(workflow_run.id),
                            "step_id": _as_int(step.id),
                            "budget_cap": budget_cap,
                            "failure_count": failure_count,
                            "reasons": [f"step exceeded max_attempts budget ({failure_count}/{max_attempts})"],
                        },
                    )
                    db.commit()
                    return
            if _interrupt_step_for_stale_context(db, requirement, workflow_run, step, context_snapshot):
                db.commit()
                return
            if _interrupt_step_for_policy(db, requirement, workflow_run, step):
                db.commit()
                return
            _maybe_escalate_ready_step(db, requirement=requirement, workflow_run=workflow_run, step=step)
            _maybe_downgrade_ready_step(db, requirement=requirement, workflow_run=workflow_run, step=step)
            if step.step_type == "closeout":
                _auto_complete_closeout(db, requirement, workflow_run, step)
                if step.status == "completed":
                    _record_step_event(db, step.id, "status_change", "completed (auto-closeout)")
                db.commit()
                return

            task, persona, skill_name = _prepare_step_task(
                db,
                step,
                prepared_description=str(context_snapshot.get("task_description") or context_snapshot.get("prompt") or ""),
            )
            step.status = "running"
            step.started_at = step.started_at or utcnow()
            step.compatibility_task_id = _as_int(task.id)
            workflow_run.status = "running"
            workflow_run.started_at = workflow_run.started_at or utcnow()
            requirement.status = "in_progress"
            requirement.started_at = requirement.started_at or utcnow()
            _record_runtime_lifecycle_artifacts(db, step, task, phase="dispatch_requested")
            _record_step_event(db, step.id, "status_change", f"running (task={task.id})")
            db.commit()

            from server.services.task_runner import dispatch

            try:
                dispatch(task_id=_as_int(task.id), agent_persona=persona, skill_name=skill_name)
            except Exception:
                logger.exception("dispatch() failed for task #%d, resetting step to ready", task.id)
                db2 = SessionLocal()
                try:
                    s = db2.query(WorkflowStepRow).filter(WorkflowStepRow.id == step.id).first()
                    t = db2.query(TaskRow).filter(TaskRow.id == task.id).first()
                    req2 = db2.query(RequirementRow).filter(RequirementRow.id == requirement.id).first()
                    run2 = db2.query(WorkflowRunRow).filter(WorkflowRunRow.id == workflow_run.id).first()
                    if s:
                        s.status = "ready"
                    if t:
                        cast(Any, t).status = "failed"
                        cast(Any, t).last_error_message = "dispatch failed"
                        cast(Any, t).completed_at = utcnow()
                    if req2 is not None and run2 is not None:
                        _refresh_run_status(db2, req2, run2)
                    db2.commit()
                finally:
                    db2.close()
            return

        _refresh_run_status(db, requirement, workflow_run)
        db.commit()
    finally:
        db.close()


def _pause_workflow_step(db: Session, step: WorkflowStepRow) -> None:
    task = None
    if step.compatibility_task_id:
        task = db.query(TaskRow).filter(TaskRow.id == step.compatibility_task_id).first()

    if task is not None:
        _terminate_task_runtime(task)
        cast(Any, task).status = "cancelled"
        cast(Any, task).last_error_message = "Paused by user"
        cast(Any, task).completed_at = utcnow()
        db.add(TaskLogRow(task_id=task.id, event_type="paused", detail="Requirement paused by user"))
        _record_runtime_lifecycle_artifacts(db, step, task, phase="paused", note="Requirement paused by user")

    step.status = "ready"
    step.runtime_session_id = None
    step.runtime_backend = ""
    step.compatibility_task_id = None
    step.started_at = None
    step.completed_at = None
    _record_step_event(db, step.id, "status_change", "ready (manual pause)")


def _terminate_task_runtime(task: TaskRow) -> None:
    runtime_backend = str(task.runtime_backend or "")
    if runtime_backend == "openai_responses":
        response_id = str(task.runtime_session_id or "")
        if not response_id:
            return
        try:
            from server.services.llm_adapter import OpenAIProvider

            OpenAIProvider().cancel_response(response_id, timeout=config.LLM_TIMEOUT)
        except Exception as exc:
            message = str(exc)
            if "cannot cancel a failed response" in message.lower() or "cannot cancel a completed response" in message.lower():
                _logger.info(
                    "OpenAI response %s for task #%s was already terminal before cancel attempt: %s",
                    response_id,
                    task.id,
                    message,
                )
            else:
                _logger.warning("Failed to cancel OpenAI response %s for task #%s: %s", response_id, task.id, exc)
        return

    if runtime_backend == "codex_cli":
        output_dir = task_output_dir(PROJECT_ROOT, str(task.agent_id), int(task.id))
        paths = codex_runtime_paths(output_dir)
        state = load_codex_state(paths["state"]) or {}
        pid = int(state.get("pid") or 0)
        if pid > 0:
            terminate_pid(pid)
        save_codex_state(
            paths["state"],
            {
                **state,
                "status": "cancelled",
                "updated_at": utcnow().isoformat(),
                "cancelled_at": utcnow().isoformat(),
            },
        )
        return

    if runtime_backend != "copilot_sdk":
        return

    output_dir = task_output_dir(PROJECT_ROOT, str(task.agent_id), int(task.id))
    paths = copilot_runtime_paths(output_dir)
    state = load_runtime_state(paths["state"]) or {}
    worker_pid = int(state.get("workerPid") or 0)

    if worker_pid > 0:
        try:
            os.killpg(worker_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            _logger.warning("Permission denied while pausing worker pid=%s for task #%s", worker_pid, task.id)
        except OSError as exc:
            _logger.warning("Failed to pause worker pid=%s for task #%s: %s", worker_pid, task.id, exc)

    state["status"] = "paused"
    state["updatedAt"] = utcnow().isoformat()
    state["pausedAt"] = utcnow().isoformat()
    state["cleanupRequestedAt"] = utcnow().isoformat()
    state["abortPropagation"] = "manual_pause"
    save_runtime_state(paths["state"], state)


def _create_acceptance_checks(db: Session, requirement_id: int, planner_output: dict):
    for check in planner_output.get("acceptance_checks", []):
        db.add(
            RequirementAcceptanceCheckRow(
                requirement_id=requirement_id,
                check_key=str(check.get("check_key", "")),
                description=str(check.get("description", "")),
                check_type=str(check.get("check_type", "content_assertion")),
                owner_role=str(check.get("owner_role", "tester")),
                success_criteria_markdown=str(check.get("success_criteria_markdown") or ""),
            )
        )
    db.flush()


def _create_workflow_steps(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    planner_output: dict,
    assignments: WorkflowRoleAssignments,
) -> dict[str, WorkflowStepRow]:
    role_agent_map = {
        "researcher": assignments.researcher_agent_id,
        "planner": assignments.synthesizer_agent_id,
        "synthesizer": assignments.synthesizer_agent_id,
        "implementer": assignments.implementer_agent_id,
        "validator": assignments.tester_agent_id,
        "reviewer": assignments.reviewer_agent_id,
        "tester": assignments.tester_agent_id,
    }
    steps_by_key: dict[str, WorkflowStepRow] = {}
    for index, step_packet in enumerate(planner_output.get("workflow_steps", []), start=1):
        assigned_role = str(step_packet.get("assigned_role") or "implementer")
        step = WorkflowStepRow(
            workflow_run_id=workflow_run.id,
            requirement_id=requirement.id,
            step_key=str(step_packet.get("step_key")),
            step_type=str(step_packet.get("step_type")),
            title=str(step_packet.get("title")),
            sequence_no=index * 10,
            assigned_agent_id=role_agent_map.get(assigned_role),
            assigned_workflow_role=assigned_role,
            context_scope="verification" if str(step_packet.get("step_type")) in {"validate", "review", "test", "closeout"} else "step_private",
            done_when_markdown=str(step_packet.get("done_when_markdown") or ""),
            context_policy_json=json.dumps(step_packet.get("context_policy") or {}),
            execution_profile_json=json.dumps(step_packet.get("execution_profile") or {}),
            file_scope_json=json.dumps(step_packet.get("file_scope") or {}),
            validation_targets_json=json.dumps(step_packet.get("validation_targets") or []),
            failure_policy_json=json.dumps(step_packet.get("failure_policy") or {}),
            approval_policy_json=json.dumps(step_packet.get("approval_policy") or {}),
        )
        db.add(step)
        db.flush()
        steps_by_key[step.step_key] = step
    return steps_by_key


def _create_step_dependencies(db: Session, steps_by_key: dict[str, WorkflowStepRow], planner_output: dict):
    for step_packet in planner_output.get("workflow_steps", []):
        step = steps_by_key[str(step_packet.get("step_key"))]
        for depends_on_key in step_packet.get("depends_on", []):
            depends_on_step = steps_by_key[str(depends_on_key)]
            db.add(
                WorkflowStepDependencyRow(
                    step_id=step.id,
                    depends_on_step_id=depends_on_step.id,
                    dependency_kind="output_required",
                    required_artifact_types_json=json.dumps([]),
                    is_blocking=True,
                )
            )
    db.flush()


def _prepare_step_task(db: Session, step: WorkflowStepRow, *, prepared_description: str | None = None) -> tuple[TaskRow, dict, str]:
    if step.compatibility_task_id:
        task = db.query(TaskRow).filter(TaskRow.id == step.compatibility_task_id).first()
        if task is not None:
            skill_name = _resolve_step_skill(db, step)
            persona = _execution_persona_for_step(db, step)
            return task, persona, skill_name

    agent = _task_agent_for_step(db, step)
    if agent is None:
        raise ValueError(f"Assigned agent '{step.assigned_agent_id}' not found for step {step.step_key}")
    if str(step.assigned_agent_id or "") != str(agent.id):
        step.assigned_agent_id = str(agent.id)

    project_id, agent_group = task_metadata_for_agent(str(agent.group))
    description = prepared_description or _step_task_description(db, step)
    suggestion = suggest_task_execution(db, description=description, preferred_agent_id=str(agent.id))
    skill_name = _resolve_step_skill(db, step, prepared_description=description) or suggestion.skill_name or "content-strategy"
    from server.services.task_runtime import resolve_runtime_selection

    selection = resolve_runtime_selection(
        _json_loads(getattr(step, "execution_profile_json", None), {}),
        step_type=str(step.step_type or ""),
    )
    task = TaskRow(
        description=description,
        agent_id=str(agent.id),
        status="running",
        requires_approval=False,
        priority="high" if step.step_type in {"validate", "test", "bugfix"} else "normal",
        project_id=project_id,
        agent_group=agent_group,
        skill_name=skill_name,
        runtime_backend=selection.backend,
        runtime_provider=selection.provider,
        runtime_model=selection.model,
        started_at=utcnow(),
    )
    db.add(task)
    db.flush()
    db.add(TaskLogRow(task_id=task.id, event_type="created", detail=description))
    db.add(TaskLogRow(task_id=task.id, event_type="started", detail=f"workflow_step={step.id} skill={skill_name}"))
    persona = _execution_persona_for_step(db, step)
    return task, persona, skill_name


def _truncate_text(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    head = max(0, limit - 80)
    return text[:head].rstrip() + f"\n\n[truncated {len(text) - head} chars]"


def _format_artifact_for_context(artifact: ArtifactRow) -> tuple[str, str]:
    if artifact.artifact_type == "implementation_plan":
        return "Implementation Plan", _plan_artifact_to_markdown(artifact)
    if artifact.artifact_type == "delivery_contract":
        return "Delivery Contract", _delivery_contract_artifact_to_markdown(artifact)
    if artifact.artifact_type == "validation_plan":
        return "Validation Contract", _validation_plan_artifact_to_markdown(artifact)
    title = f"{artifact.artifact_type}: {artifact.content_summary or ''}".strip(": ").strip()
    body = str(artifact.human_readable_body or artifact.content_summary or "").strip()
    return title or artifact.artifact_type, body


def _prompt_cacheable_binding(binding: dict[str, Any]) -> bool:
    artifact_type = str(binding.get("artifact_type") or "").strip()
    return artifact_type in {
        "implementation_plan",
        "delivery_contract",
        "validation_plan",
        "routing_decision",
        "requirement_snapshot",
        "project_change_summary",
    }


def _prompt_cache_payload(sections: list[dict[str, Any]], binding_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    reusable_sections: list[dict[str, Any]] = []
    seen_reusable_keys: set[str] = set()
    reused_chars = 0
    reusable_artifact_count = 0
    reusable_section_count = 0
    for section in sections:
        kind = str(section.get("kind") or "")
        if kind not in {"project", "capability", "done_when"}:
            continue
        body = str(section.get("body") or "").strip()
        if not body:
            continue
        title = str(section.get("title") or "")
        summary = _truncate_text(body, 240)
        reusable_key = hashlib.sha1(f"{kind}\n{title}\n{summary}".encode("utf-8")).hexdigest()
        if reusable_key in seen_reusable_keys:
            continue
        seen_reusable_keys.add(reusable_key)
        reusable_section_count += 1
        reused_chars += max(0, len(body) - len(summary))
        reusable_sections.append(
            {
                "kind": kind,
                "title": title,
                "summary": summary,
                "raw_chars": len(body),
                "summary_chars": len(summary),
            }
        )
    for binding in binding_summaries:
        if not _prompt_cacheable_binding(binding):
            continue
        body = str(binding.get("body") or "").strip()
        if not body:
            continue
        artifact_type = str(binding.get("artifact_type") or "")
        title = str(binding.get("title") or "")
        summary = _truncate_text(body, 240)
        reusable_key = hashlib.sha1(f"{artifact_type}\n{title}\n{summary}".encode("utf-8")).hexdigest()
        if reusable_key in seen_reusable_keys:
            continue
        seen_reusable_keys.add(reusable_key)
        reusable_artifact_count += 1
        reused_chars += max(0, len(body) - len(summary))
        reusable_sections.append(
            {
                "kind": "artifact",
                "artifact_type": artifact_type,
                "title": title,
                "summary": summary,
                "raw_chars": len(body),
                "summary_chars": len(summary),
            }
        )
    digest_source = "\n".join(
        f"{item.get('kind')}::{item.get('title')}::{item.get('summary')}"
        for item in reusable_sections
    )
    return {
        "cache_key": hashlib.sha1(digest_source.encode("utf-8")).hexdigest() if digest_source else "",
        "reusable_sections": reusable_sections,
        "reusable_section_count": reusable_section_count,
        "reusable_artifact_count": reusable_artifact_count,
        "reused_chars": reused_chars,
        "cache_applied": bool(reusable_sections),
    }


def _prompt_cache_profile_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Prompt Cache Profile",
        "",
        f"- cache key: `{payload.get('cache_key') or '-'}`",
        f"- cache applied: `{payload.get('cache_applied')}`",
        f"- reusable sections: `{payload.get('reusable_section_count') or 0}`",
        f"- reusable artifacts: `{payload.get('reusable_artifact_count') or 0}`",
        f"- deduped bindings: `{payload.get('deduped_binding_count') or 0}`",
        f"- raw chars: `{payload.get('raw_chars') or 0}`",
        f"- final chars: `{payload.get('final_chars') or 0}`",
        f"- saved chars before compaction: `{payload.get('cached_chars_saved') or 0}`",
    ]
    reusable_sections = payload.get("reusable_sections") or []
    if isinstance(reusable_sections, list) and reusable_sections:
        lines.extend(["", "## Reusable Context"])
        for item in reusable_sections:
            if not isinstance(item, dict):
                continue
            label = str(item.get("title") or item.get("artifact_type") or item.get("kind") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if not label or not summary:
                continue
            lines.append(f"- {label}: {summary}")
    return "\n".join(lines)


def _binding_relevant_for_step(step: WorkflowStepRow, binding: StepInputBindingRow, artifact: ArtifactRow) -> bool:
    step_type = str(step.step_type or "").strip().lower()
    purpose = str(getattr(binding, "purpose", "") or "").strip().lower()
    artifact_type = str(artifact.artifact_type or "").strip().lower()

    if step_type == "research":
        if purpose in {"delivery_contract", "validation_contract", "review_context", "test_context"}:
            return False
        if artifact_type in {"implementation_plan", "delivery_contract", "validation_plan", "review_report", "test_report"}:
            return False
    elif step_type == "plan":
        if purpose in {"delivery_contract", "validation_contract", "review_context", "test_context"}:
            return False
        if artifact_type in {"implementation_plan", "delivery_contract", "validation_plan", "validation_report"}:
            return False
    elif step_type in {"implementation", "bugfix"}:
        if purpose in {"delivery_contract", "validation_contract", "review_context", "test_context"}:
            return False
        if artifact_type in {"delivery_contract", "validation_plan", "validation_report"}:
            return False
    if step_type == "plan" and artifact_type == "research_report":
        return False
    if step_type in {"implementation", "bugfix"} and artifact_type == "plan_brief":
        return False

    return True


def _is_requirement_centric_delivery_requirement(requirement: RequirementRow | None) -> bool:
    if requirement is None:
        return False
    title = str(getattr(requirement, "title", "") or "").strip().lower()
    description = str(getattr(requirement, "description_markdown", "") or "").strip().lower()
    text = f"{title}\n{description}"
    strong_markers = (
        "commit",
        "push",
        "draft pr",
        "pull request",
        "review-ready",
        "compare url",
        "requirement branch",
        "same branch",
        "branch delivery",
        "review surface",
        "validation clone",
    )
    return any(marker in text for marker in strong_markers)


def _step_execution_guidance(db: Session, step: WorkflowStepRow) -> str:
    step_type = str(step.step_type or "").strip().lower()
    requirement = _require_requirement(db, step.requirement_id)
    delivery_requirement = _is_requirement_centric_delivery_requirement(requirement)
    if step_type == "research":
        if delivery_requirement:
            return "\n".join(
                [
                    "- Treat this as a branch-delivery preflight, not a general repository investigation.",
                    "- Limit commands to high-signal checks such as `git status --short --branch`, `git branch --show-current`, `git remote -v`, `ls docs`, and targeted reads of `README.md` or the requested output path parent.",
                    "- Do not scan unrelated source trees, test suites, or service internals in this step.",
                    "- Stop once you know the current branch, remote, required target path, and any blockers to creating exactly the requested tracked file.",
                    "- Do not edit production code in this step.",
                ]
            )
        return "\n".join(
            [
                "- Limit exploration to the highest-signal files only; avoid broad repo surveys.",
                "- Stop once you have a plausible root cause, 3-6 relevant files, and concrete implementation options.",
                "- Do not edit production code in this step.",
            ]
        )
    if step_type == "plan":
        if delivery_requirement:
            return "\n".join(
                [
                    "- Build the execution plan from the delivery contract, git preflight, and requested output path only.",
                    "- Do not re-scan broad parts of the repository; synthesize from the known branch/remote state and the requested tracked file scope.",
                    "- Keep the plan anchored to one branch, one tracked file, commit/push, and draft PR sync.",
                    "- Do not edit production code in this step.",
                ]
            )
        return "\n".join(
            [
                "- Build the execution plan from the research findings; do not re-scan large unrelated parts of the repo.",
                "- Only inspect extra files when they are strictly needed to finalize sequencing or validation.",
                "- Do not edit production code in this step.",
            ]
        )
    if step_type in {"implementation", "bugfix"}:
        return "\n".join(
            [
                "- Keep changes tightly scoped to the target project and files already identified by research/plan unless new evidence requires expansion.",
                "- Prefer minimal diffs that directly satisfy the stated goal and validation contract.",
                "- Do not run dependency installation/bootstrap commands such as `npm install`, `pnpm install`, or `yarn install` unless the requirement explicitly asks for dependency changes.",
                "- Reuse the repository's existing lockfile and scripts; if a required check cannot run without new installs, fail fast and report the blocker instead of broad environment setup.",
            ]
        )
    if step_type == "validate":
        return "\n".join(
            [
                "- Treat validate as the single final quality gate for this requirement.",
                "- Reuse plan and implementation evidence instead of repeating the whole requirement.",
                "- Make the result binary: either validated and ready for closeout, or specific enough to trigger bugfix.",
                "- Do not make new source edits in this step unless a policy artifact explicitly allows it.",
            ]
        )
    return ""


def _step_includes_predecessor_handoff(step: WorkflowStepRow) -> bool:
    step_type = str(step.step_type or "").strip().lower()
    if step_type in {"implementation", "bugfix"}:
        return False
    return True


def _normalize_file_hint(path_hint: str) -> str | None:
    value = str(path_hint or "").strip().strip("`").strip()
    if not value:
        return None
    value = value.split("#L", 1)[0]
    if ":" in value:
        prefix, suffix = value.rsplit(":", 1)
        if suffix.isdigit() or ("-" in suffix and suffix.replace("-", "").isdigit()):
            value = prefix
    value = value.strip()
    if "/" not in value:
        return None
    return value or None


def _extract_file_hints_from_text(markdown: str, *, limit: int = 6) -> list[str]:
    text = str(markdown or "")
    hints: list[str] = []
    seen: set[str] = set()
    for match in re.findall(r"`([^`]+)`", text):
        normalized = _normalize_file_hint(match)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        hints.append(normalized)
        if len(hints) >= limit:
            return hints
    for match in re.findall(r"\b[\w./-]+\.[A-Za-z0-9_]+\b", text):
        normalized = _normalize_file_hint(match)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        hints.append(normalized)
        if len(hints) >= limit:
            return hints
    return hints


def _step_relevant_file_hints(db: Session, step: WorkflowStepRow, *, limit: int = 6) -> list[str]:
    step_type = str(step.step_type or "").strip().lower()
    requirement = _require_requirement(db, step.requirement_id)
    delivery_requirement = _is_requirement_centric_delivery_requirement(requirement)
    if step_type not in {"implementation", "bugfix", "validate", "review", "test"} and not (
        delivery_requirement and step_type in {"research", "plan"}
    ):
        return []
    if delivery_requirement and step_type in {"research", "plan"}:
        hints: list[str] = []
        seen: set[str] = set()
        description = str(getattr(requirement, "description_markdown", "") or "")
        for candidate in _extract_file_hints_from_text(description, limit=limit):
            if candidate in seen:
                continue
            seen.add(candidate)
            hints.append(candidate)
            if len(hints) >= limit:
                return hints
        for candidate in ("README.md", "docs/", "docs/auto-validation/"):
            if candidate in seen:
                continue
            seen.add(candidate)
            hints.append(candidate)
            if len(hints) >= limit:
                return hints
        return hints
    requirement_id = _as_int(step.requirement_id)
    artifact_types = ["research_report", "plan_brief", "implementation_plan"]
    hints: list[str] = []
    seen: set[str] = set()
    for artifact_type in artifact_types:
        artifact = _latest_artifact(db, requirement_id, artifact_type)
        if not artifact:
            continue
        bodies = [
            str(getattr(artifact, "human_readable_body", "") or ""),
            str(getattr(artifact, "content_summary", "") or ""),
        ]
        for body in bodies:
            for hint in _extract_file_hints_from_text(body, limit=limit):
                if hint in seen:
                    continue
                seen.add(hint)
                hints.append(hint)
                if len(hints) >= limit:
                    return hints
    return hints


def _effective_done_when_markdown(step: WorkflowStepRow, requirement: RequirementRow, target_path: str | None) -> str:
    done_when = str(step.done_when_markdown or "").strip()
    step_type = str(step.step_type or "").strip().lower()
    title = str(step.title or "").strip().lower()
    step_key = str(step.step_key or "").strip().lower()
    if (
        _requirement_prefers_engineering_contract(requirement)
        and step_type in {"implementation", "bugfix"}
        and "do not write implementation code" in done_when.lower()
    ):
        if any(marker in f"{title} {step_key}" for marker in {"verify", "validation", "regression", "test"}):
            done_when = (
                "SCOPE: Implement automated validation for the incident recovery path. "
                "You may add or modify tests and supporting harness code that proves the failure path is now closed.\n\n"
                "Add or update regression validation that reproduces the incident conditions and proves the new guard holds."
            )
        else:
            done_when = (
                "SCOPE: Implement a minimal engineering fix in code or supporting runtime/test harness files. "
                "Do NOT stop at documentation-only output.\n\n"
                "Apply the smallest safe change that closes the runtime failure path, and record root cause/recovery notes in task output or handoff."
            )
        if target_path:
            done_when += f"\nTarget project: {target_path}"
    return done_when


def _step_context_snapshot(db: Session, step: WorkflowStepRow) -> dict[str, Any]:
    requirement = _require_requirement(db, step.requirement_id)
    target_path = _effective_target_project_path(db, requirement, step_type=str(step.step_type or ""))
    effective_done_when = _effective_done_when_markdown(step, requirement, target_path)
    context_policy = _json_loads(getattr(step, "context_policy_json", None), {})
    max_artifact_body_chars = int(context_policy.get("max_artifact_body_chars") or 2200)
    max_handoff_chars = int(context_policy.get("max_handoff_chars") or 1200)
    requirement_summary = _truncate_text(str(requirement.description_markdown or "").strip(), 900)

    sections: list[dict[str, Any]] = [
        {
            "kind": "base",
            "title": "Step",
            "body": "\n".join([
                f"[workflow_step:{step.step_type}] {step.title}",
                f"Requirement #{requirement.id}: {requirement.title}",
                requirement_summary,
            ]).strip(),
        }
    ]
    if target_path:
        project_lines = [f"Target project path: {target_path}"]
        project_lines.append("IMPORTANT: Write actual source code files in the target project, not just documentation.")
        project_policy_summary = project_policy_summary_markdown(db, target_path)
        if project_policy_summary:
            project_lines.append(project_policy_summary)
        sections.append({"kind": "project", "title": "Project Context", "body": "\n".join(project_lines)})

    approval_policy = _json_loads(getattr(step, "approval_policy_json", None), {})
    capability_lines = _approval_policy_markdown_lines(approval_policy)
    if capability_lines:
        sections.append({"kind": "capability", "title": "Capability Contract", "body": "\n".join(capability_lines)})

    sections.append({"kind": "done_when", "title": "Done When", "body": effective_done_when})
    execution_guidance = _step_execution_guidance(db, step)
    if execution_guidance:
        sections.append({"kind": "guidance", "title": "Execution Guidance", "body": execution_guidance})
    relevant_files = _step_relevant_file_hints(db, step)
    if relevant_files:
        sections.append(
            {
                "kind": "file_hints",
                "title": "Suggested File Scope",
                "body": "\n".join(f"- {path}" for path in relevant_files),
            }
        )

    if _step_includes_predecessor_handoff(step):
        deps = db.query(WorkflowStepDependencyRow).filter(WorkflowStepDependencyRow.step_id == step.id).all()
        for dep in deps:
            pred = db.query(WorkflowStepRow).filter(WorkflowStepRow.id == dep.depends_on_step_id).first()
            if pred and pred.handoff_summary_markdown:
                sections.append(
                    {
                        "kind": "handoff",
                        "title": f"Prior Step: {pred.title}",
                        "body": _truncate_text(str(pred.handoff_summary_markdown), max_handoff_chars),
                    }
                )

    binding_summaries: list[dict[str, Any]] = []
    seen_binding_keys: set[str] = set()
    deduped_binding_count = 0
    bindings = db.query(StepInputBindingRow).filter(StepInputBindingRow.step_id == step.id).all()
    total_binding_count = len(bindings)
    for binding in bindings:
        artifact = db.query(ArtifactRow).filter(ArtifactRow.id == binding.artifact_id).first()
        if not artifact:
            continue
        if not _binding_relevant_for_step(step, binding, artifact):
            continue
        title, body = _format_artifact_for_context(artifact)
        truncated_body = _truncate_text(body, max_artifact_body_chars)
        dedupe_key = hashlib.sha1(f"{title}\n{truncated_body}".encode("utf-8")).hexdigest()
        if dedupe_key in seen_binding_keys:
            deduped_binding_count += 1
            continue
        seen_binding_keys.add(dedupe_key)
        binding_summaries.append(
            {
                "artifact_id": _as_int(artifact.id),
                "artifact_type": str(artifact.artifact_type),
                "title": title,
                "body": truncated_body,
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
                "workflow_run_id": int(artifact.workflow_run_id) if artifact.workflow_run_id is not None else None,
            }
        )
        sections.append({"kind": "artifact", "title": title, "body": truncated_body})

    prompt_cache = _prompt_cache_payload(sections, binding_summaries)
    cache_key = str(prompt_cache.get("cache_key") or "")
    reusable_sections = list(prompt_cache.get("reusable_sections") or [])
    cache_applied = bool(prompt_cache.get("cache_applied"))
    raw_prompt_before_cache = "\n\n".join(
        f"## {section['title']}\n{section['body']}".strip()
        for section in sections
        if str(section.get("body") or "").strip()
    ).strip()
    raw_chars_before_cache = len(raw_prompt_before_cache)
    if cache_applied:
        compact_lines = [
            f"Cache key: `{cache_key}`",
            "Reusable context summary:",
        ]
        for item in reusable_sections:
            compact_lines.append(
                f"- {item.get('title') or item.get('artifact_type') or item.get('kind')}: {item.get('summary') or ''}"
            )
        sections = [
            section
            for section in sections
            if not (
                str(section.get("kind") or "") in {"project", "capability"}
                or (
                    str(section.get("kind") or "") == "artifact"
                    and any(
                        str(item.get("title") or "") == str(section.get("title") or "")
                        and str(item.get("summary") or "") == _truncate_text(str(section.get("body") or ""), 240)
                        for item in reusable_sections
                    )
                )
            )
        ]
        sections.insert(1, {"kind": "prompt_cache", "title": "Cached Context Profile", "body": "\n".join(compact_lines)})

    raw_prompt = "\n\n".join(
        f"## {section['title']}\n{section['body']}".strip()
        for section in sections
        if str(section.get("body") or "").strip()
    ).strip()

    max_prompt_chars = int(context_policy.get("max_prompt_chars") or 12000)
    compact_after_chars = int(context_policy.get("compact_after_chars") or max_prompt_chars)
    compacted = len(raw_prompt) > compact_after_chars
    final_prompt = raw_prompt
    if compacted:
        compact_header = [
            "## Context Compact Summary",
            f"- Raw prompt chars: {len(raw_prompt)}",
            f"- Compacted to stay under budget `{max_prompt_chars}`.",
        ]
        compact_sections: list[str] = []
        for section in sections:
            body = str(section.get("body") or "").strip()
            if not body:
                continue
            compact_sections.append(f"### {section['title']}\n{_truncate_text(body, max(400, max_prompt_chars // max(1, len(sections) + 2)))}")
        final_prompt = "\n\n".join(compact_header + compact_sections)
        if len(final_prompt) > max_prompt_chars:
            final_prompt = _truncate_text(final_prompt, max_prompt_chars)

    stale_after_minutes = max(1, int(context_policy.get("stale_after_minutes") or 30))
    cutoff = _normalize_utc_datetime(utcnow() - timedelta(minutes=stale_after_minutes))
    stale_sensitive_types = {
        str(item).strip()
        for item in context_policy.get("stale_sensitive_artifact_types") or []
        if str(item).strip()
    }
    lineage_only_types = {
        "requirement_snapshot",
        "implementation_plan",
    }
    stale_findings: list[str] = []
    for binding in binding_summaries:
        artifact_type = str(binding.get("artifact_type") or "")
        created_at = _normalize_utc_datetime(parse_runtime_timestamp(str(binding.get("created_at") or "")))
        workflow_run_id = int(binding.get("workflow_run_id") or 0)
        if workflow_run_id and workflow_run_id != int(step.workflow_run_id):
            stale_findings.append(f"{artifact_type} comes from workflow run #{workflow_run_id}, not the active run #{step.workflow_run_id}")
            continue
        if artifact_type in lineage_only_types:
            continue
        if artifact_type in stale_sensitive_types and created_at is not None and cutoff is not None and created_at < cutoff:
            stale_findings.append(
                f"{artifact_type} is older than stale-memory threshold ({stale_after_minutes} min)"
            )
    # Requirement.updated_at also moves during operational state transitions
    # like start/pause/block. Treating that field as a content freshness anchor
    # causes false stale-memory blocks on otherwise fresh plans. The reliable
    # freshness guards are:
    # 1. artifact bound to a different workflow run
    # 2. artifact older than the explicit stale threshold

    verification_status = "fresh" if not stale_findings else "stale"
    return {
        "requirement": requirement,
        "context_policy": context_policy,
        "raw_chars_before_cache": raw_chars_before_cache,
        "raw_prompt": raw_prompt,
        "prompt": final_prompt,
        "raw_chars": len(raw_prompt),
        "final_chars": len(final_prompt),
        "compacted": compacted,
        "sections": sections,
        "binding_summaries": binding_summaries,
        "prompt_cache": prompt_cache,
        "cache_applied": cache_applied,
        "total_binding_count": total_binding_count,
        "unique_binding_count": len(binding_summaries),
        "deduped_binding_count": deduped_binding_count,
        "cached_chars_saved": max(0, raw_chars_before_cache - len(raw_prompt)),
        "verification_status": verification_status,
        "stale_findings": list(dict.fromkeys(stale_findings)),
    }


def _compact_task_description_from_snapshot(step: WorkflowStepRow, snapshot: dict[str, Any]) -> str:
    sections = list(snapshot.get("sections") or [])
    binding_summaries = list(snapshot.get("binding_summaries") or [])
    context_parts: list[str] = []
    constraint_parts: list[str] = []
    delta_parts: list[str] = []
    done_when = ""
    step_goal = ""

    for section in sections:
        kind = str(section.get("kind") or "").strip()
        title = str(section.get("title") or "").strip()
        body = str(section.get("body") or "").strip()
        if not body:
            continue
        if kind == "base" and not step_goal:
            lines = [line.strip() for line in body.splitlines() if line.strip()]
            headline = lines[:5]
            goal_text = "\n".join(headline).strip()
            if len(lines) > 5:
                remaining = " ".join(lines[5:]).strip()
                if remaining:
                    goal_text = f"{goal_text}\n{remaining}".strip()
            step_goal = _truncate_text(goal_text, 520)
            continue
        if kind == "done_when" and not done_when:
            done_when = _truncate_text(body, 280)
            continue
        if kind in {"project", "file_hints"}:
            context_parts.append(f"### {title}\n{_truncate_text(body, 220)}")
            continue
        if kind in {"capability", "guidance"}:
            constraint_parts.append(f"### {title}\n{_truncate_text(body, 180)}")
            continue
        if kind == "handoff":
            delta_parts.append(f"### {title}\n{_truncate_text(body, 160)}")

    if binding_summaries:
        bound_inputs = []
        for item in binding_summaries[:3]:
            if str(item.get("artifact_type") or "").strip() == "requirement_snapshot":
                continue
            title = str(item.get("title") or item.get("artifact_type") or "artifact").strip()
            artifact_type = str(item.get("artifact_type") or "").strip()
            bound_inputs.append(f"- {title} ({artifact_type})")
        if bound_inputs:
            delta_parts.append("### Bound Inputs\n" + "\n".join(bound_inputs))

    parts = [
        "## Step",
        step_goal or f"[workflow_step:{step.step_type}] {step.title}",
    ]
    if done_when:
        parts.extend(["", "## Done When", done_when])
    if context_parts:
        parts.extend(["", "## Context", "\n\n".join(context_parts[:2])])
    if constraint_parts:
        parts.extend(["", "## Constraints", "\n\n".join(constraint_parts[:2])])
    if delta_parts:
        parts.extend(["", "## Delta", "\n\n".join(delta_parts[:2])])
    return _truncate_text("\n".join(parts).strip(), 1400)


def _materialize_step_context(db: Session, step: WorkflowStepRow) -> dict[str, Any]:
    snapshot = _step_context_snapshot(db, step)
    snapshot["task_description"] = _compact_task_description_from_snapshot(step, snapshot)
    prompt_cache_payload = {
        **snapshot["prompt_cache"],
        "cache_applied": snapshot["cache_applied"],
        "raw_chars_before_cache": snapshot["raw_chars_before_cache"],
        "raw_chars": snapshot["raw_chars"],
        "final_chars": snapshot["final_chars"],
        "cached_chars_saved": snapshot["cached_chars_saved"],
        "total_binding_count": snapshot["total_binding_count"],
        "unique_binding_count": snapshot["unique_binding_count"],
        "deduped_binding_count": snapshot["deduped_binding_count"],
        "section_count": len(snapshot["sections"]),
    }
    payload = {
        "step_id": _as_int(step.id),
        "step_key": str(step.step_key),
        "step_type": str(step.step_type),
        "context_policy": snapshot["context_policy"],
        "raw_chars_before_cache": snapshot["raw_chars_before_cache"],
        "raw_chars": snapshot["raw_chars"],
        "final_chars": snapshot["final_chars"],
        "compacted": snapshot["compacted"],
        "section_count": len(snapshot["sections"]),
        "binding_summaries": snapshot["binding_summaries"],
        "prompt_cache": prompt_cache_payload,
        "total_binding_count": snapshot["total_binding_count"],
        "unique_binding_count": snapshot["unique_binding_count"],
        "deduped_binding_count": snapshot["deduped_binding_count"],
        "cached_chars_saved": snapshot["cached_chars_saved"],
    }
    _create_or_update_artifact(
        db,
        requirement_id=step.requirement_id,
        workflow_run_id=step.workflow_run_id,
        step_id=step.id,
        producer_step_id=step.id,
        artifact_type="prompt_cache_profile",
        content_summary=f"prompt cache profile for step {step.step_key}",
        human_readable_body=_prompt_cache_profile_markdown(prompt_cache_payload),
        machine_readable_payload=prompt_cache_payload,
    )
    if snapshot["compacted"]:
        _create_artifact(
            db,
            requirement_id=step.requirement_id,
            workflow_run_id=step.workflow_run_id,
            step_id=step.id,
            producer_step_id=step.id,
            artifact_type="context_compaction",
            content_summary=f"context compacted for step {step.step_key}",
            human_readable_body=snapshot["prompt"],
            machine_readable_payload=payload,
        )
    _create_artifact(
        db,
        requirement_id=step.requirement_id,
        workflow_run_id=step.workflow_run_id,
        step_id=step.id,
        producer_step_id=step.id,
        artifact_type="stale_memory_verification",
        content_summary=f"{snapshot['verification_status']} context verification for step {step.step_key}",
        human_readable_body="\n".join(
            [
                f"Verification status: {snapshot['verification_status']}",
                *(f"- {item}" for item in snapshot["stale_findings"]),
            ]
        ).strip(),
        machine_readable_payload={
            **payload,
            "verification_status": snapshot["verification_status"],
            "stale_findings": snapshot["stale_findings"],
        },
    )
    return snapshot


def _step_task_description(db: Session, step: WorkflowStepRow) -> str:
    snapshot = _step_context_snapshot(db, step)
    compact_task_description = _compact_task_description_from_snapshot(step, snapshot)
    lines = [compact_task_description or snapshot["prompt"]]
    if snapshot["verification_status"] != "fresh":
        lines.extend([
            "",
            "## Stale Memory Verification",
            *(f"- {item}" for item in snapshot["stale_findings"]),
        ])
    return "\n".join(lines)


def _approval_policy_markdown_lines(policy: dict[str, Any]) -> list[str]:
    if not isinstance(policy, dict) or not policy:
        return []
    lines: list[str] = []
    required = [str(item) for item in policy.get("required_capabilities") or [] if str(item).strip()]
    if required:
        lines.append(f"- Required capabilities: {', '.join(required)}")
    approval_scope = str(policy.get("approval_scope") or "").strip()
    if approval_scope:
        lines.append(f"- Human gate scope: {approval_scope}")
    matrix = policy.get("capability_matrix") or {}
    if isinstance(matrix, dict) and matrix:
        summary = ", ".join(
            f"{key}={'yes' if bool(matrix.get(key)) else 'no'}"
            for key in ("shell_access", "git_read", "git_write", "git_push", "network_access", "publish")
        )
        lines.append(f"- Effective matrix: {summary}")
    confirmation = [str(item) for item in policy.get("operator_confirmation_actions") or [] if str(item).strip()]
    if confirmation:
        lines.append(f"- Operator confirmation actions: {', '.join(confirmation)}")
    deny_reasons = [str(item) for item in policy.get("deny_reasons") or [] if str(item).strip()]
    if deny_reasons:
        lines.append(f"- Denied actions: {'; '.join(deny_reasons)}")
    interrupt_policy = policy.get("interrupt_policy") or {}
    if isinstance(interrupt_policy, dict):
        pause_events = ", ".join(str(item) for item in interrupt_policy.get("auto_pause_on_events") or [] if str(item).strip()) or "none"
        abort_events = ", ".join(str(item) for item in interrupt_policy.get("auto_abort_on_events") or [] if str(item).strip()) or "none"
        lines.append(f"- Interrupt policy: pause on {pause_events}; abort on {abort_events}")
    return lines


def _step_required_capabilities_for_type(step_type: str) -> list[str]:
    required = ["git_read"]
    if step_type in {"research", "plan", "validate", "synthesis", "review", "test", "implementation", "bugfix"}:
        required.append("shell_access")
    if step_type in {"implementation", "bugfix"}:
        required.append("git_write")
    ordered: list[str] = []
    for key in ("shell_access", "git_read", "git_write", "git_push", "network_access", "publish"):
        if key in required and key not in ordered:
            ordered.append(key)
    return ordered


def _derived_approval_policy(
    step_type: str,
    base_policy: dict[str, Any],
    *,
    execution_profile: dict[str, Any] | None = None,
    requirement: RequirementRow | None = None,
) -> dict[str, Any]:
    if not isinstance(base_policy, dict):
        base_policy = {}
    capability_matrix = dict(base_policy.get("capability_matrix") or {})
    interrupt_policy = dict(base_policy.get("interrupt_policy") or {})
    required_capabilities = _step_required_capabilities_for_type(step_type)
    denied = [name for name in required_capabilities if capability_matrix and not bool(capability_matrix.get(name))]
    from server.services.workflow_planner import _operator_confirmation_actions_for_step

    confirmation, approval_scope = _operator_confirmation_actions_for_step(
        step_type=step_type,
        required_capabilities=required_capabilities,
        interrupt_policy=interrupt_policy,
        execution_profile=execution_profile,
        requirement=requirement,
    )
    return {
        "required_capabilities": required_capabilities,
        "capability_matrix": capability_matrix,
        "interrupt_policy": interrupt_policy,
        "approval_scope": approval_scope,
        "requires_operator_confirmation": bool(confirmation),
        "operator_confirmation_actions": confirmation,
        "deny_execution": bool(denied),
        "deny_reasons": [f"{name} disabled by project capability matrix" for name in denied],
    }


def _plan_artifact_to_markdown(artifact: ArtifactRow) -> str:
    """Convert an implementation_plan artifact into concise Markdown for the executing agent."""
    payload = artifact.machine_readable_payload
    if not payload:
        return artifact.human_readable_body[:2000] if artifact.human_readable_body else ""
    try:
        plan = json.loads(payload) if isinstance(payload, str) else payload
    except (json.JSONDecodeError, TypeError):
        return artifact.human_readable_body[:2000] if artifact.human_readable_body else ""

    edited_markdown = str(plan.get("edited_markdown") or "").strip()
    if edited_markdown:
        return edited_markdown[:4000]

    lines = []
    goal = plan.get("goal_summary_markdown") or plan.get("goal_summary", "")
    if goal:
        lines.append(goal)

    target = plan.get("target_project_path")
    if target:
        lines.append(f"**Target project:** `{target}`")

    phases = plan.get("detected_phases", {})
    active = [k for k, v in phases.items() if v]
    if active:
        lines.append(f"**Phases:** {', '.join(active)}")

    steps = plan.get("workflow_steps", [])
    if steps:
        lines.append("\n### Workflow Steps")
        for i, s in enumerate(steps, 1):
            role = s.get("assigned_role", "")
            done = s.get("done_when_markdown", "")
            tier = str(s.get("complexity_tier") or (s.get("execution_profile") or {}).get("complexity_tier") or "").strip()
            budget = (s.get("budget_cap") or (s.get("execution_profile") or {}).get("budget_cap") or {})
            budget_note = ""
            if tier:
                budget_note = f" [{tier}]"
            if isinstance(budget, dict) and budget:
                budget_note += f" input≤{budget.get('max_input_tokens', '-')} output≤{budget.get('max_output_tokens', '-')}"
            lines.append(f"{i}. **{s.get('title', s.get('step_key', ''))}** ({role}){budget_note}: {done}")

    risks = plan.get("known_risks_markdown", "")
    if risks:
        lines.append(f"\n### Risks\n{risks}")

    return "\n".join(lines)


def _validation_plan_artifact_to_markdown(artifact: ArtifactRow) -> str:
    payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
    if not isinstance(payload, dict):
        return artifact.human_readable_body[:2000] if artifact.human_readable_body else ""
    return _validation_plan_markdown(payload)


def _delivery_contract_artifact_to_markdown(artifact: ArtifactRow) -> str:
    payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
    if not isinstance(payload, dict):
        return artifact.human_readable_body[:2000] if artifact.human_readable_body else ""
    return _delivery_contract_markdown(payload)


def _resolve_step_skill(db: Session, step: WorkflowStepRow, *, prepared_description: str | None = None) -> str:
    if _step_prefers_engineering_contract(db, step):
        return "__direct_execution__"
    description = prepared_description or _step_task_description(db, step)
    suggestion = suggest_task_execution(db, description=description, preferred_agent_id=step.assigned_agent_id)
    return suggestion.skill_name or "content-strategy"


def _requirement_prefers_engineering_contract(requirement: RequirementRow) -> bool:
    title = str(requirement.title or "").strip().lower()
    source = str(requirement.source or "").strip().lower()
    source_ref = str(requirement.source_ref or "").strip().lower()
    description = str(requirement.description_markdown or "").strip().lower()
    intake_metadata = str(getattr(requirement, "intake_metadata_json", "") or "").strip().lower()
    if title.startswith(("bug fix:", "incident recovery:", "infra incident:", "workflow incident:")):
        return True
    if source in {"bug_intake", "bugfix_circuit_breaker", "workflow_incident"}:
        return True
    markers = (
        "runtime_failure",
        "workflow_incident",
        "incident recovery",
        "bugfix_regression",
        "bug report",
        "approval automation",
        "manual approval",
        "expensive_branches_only",
        "stale_memory",
        "stale-memory",
        "context_refresh_automation",
        "gate config",
        "gate state",
        "draft pr",
        "pull request",
        "review-ready",
        "compare url",
        "requirement branch",
        "same branch",
        "branch delivery",
        "review surface",
        "validation clone",
    )
    haystack = " ".join([title, source, source_ref, description, intake_metadata])
    if source == "automation_candidate" and "approval_automation" in haystack:
        return True
    return any(marker in haystack for marker in markers)


def _step_prefers_engineering_contract(db: Session, step: WorkflowStepRow) -> bool:
    requirement = _require_requirement(db, step.requirement_id)
    step_type = str(step.step_type or "").strip().lower()
    if step_type in {"implementation", "bugfix", "validate", "review", "test", "closeout"}:
        return True
    if _requirement_prefers_engineering_contract(requirement):
        return step_type in {"research", "plan"}
    return False


def _task_agent_for_step(db: Session, step: WorkflowStepRow) -> AgentRow | None:
    preferred_id = str(step.assigned_agent_id or "").strip()
    if _step_prefers_engineering_contract(db, step):
        engineering = db.query(AgentRow).filter(AgentRow.id == "dev_rel").first()
        if engineering is not None:
            return engineering
    if preferred_id:
        return db.query(AgentRow).filter(AgentRow.id == preferred_id).first()
    return None


def _engineering_execution_persona(step: WorkflowStepRow) -> dict[str, Any]:
    role_id = str(step.assigned_agent_id or "engineering_executor")
    step_type = str(step.step_type or "").strip().lower()
    goal = {
        "research": "Investigate the codebase like a senior software engineer and isolate the likely root cause quickly.",
        "plan": "Turn the current research into a compact implementation and validation brief for engineers.",
        "synthesis": "Turn the current research into a concrete implementation and verification plan for engineers.",
        "implementation": "Implement the smallest safe code change that fixes the issue and keeps verification in view.",
        "bugfix": "Apply a focused fix for the failed validation path and preserve the delivery contract.",
        "validate": "Run the single final validation gate and confirm the outcome is ready for closeout or bugfix.",
        "review": "Review the code and verification evidence like a pragmatic engineering reviewer.",
        "test": "Run targeted technical validation and confirm the failure path is closed.",
        "closeout": "Summarize the engineering outcome, changed files, and validation evidence succinctly.",
    }.get(step_type, "Execute this software delivery step like a pragmatic senior engineer.")
    body = "\n".join(
        [
            "You are operating in engineering execution mode.",
            "Ignore any growth, SEO, launch, or marketing framing that may come from the stored role assignment.",
            "Prioritize repository evidence, minimal diffs, concrete verification, and closing the stated software issue.",
            "When the step allows edits, make real source-code or test changes in the target project instead of only producing documentation.",
            "When the step is research or plan, avoid broad repo tours and stop once you have enough evidence to move the workflow forward.",
        ]
    )
    return {
        "role": role_id,
        "id": role_id,
        "display_name": "Engineering Executor",
        "goal": goal,
        "skills": [],
        "body": body,
    }


def _execution_persona_for_step(db: Session, step: WorkflowStepRow) -> dict[str, Any]:
    if _step_prefers_engineering_contract(db, step):
        return _engineering_execution_persona(step)
    return _load_full_persona(step.assigned_agent_id or "")


def _dependencies_satisfied(db: Session, step_id: int) -> bool:
    deps = db.query(WorkflowStepDependencyRow).filter(WorkflowStepDependencyRow.step_id == step_id).all()
    for dep in deps:
        if not dep.is_blocking:
            continue
        source = db.query(WorkflowStepRow).filter(WorkflowStepRow.id == dep.depends_on_step_id).first()
        if source is None or source.status != "completed":
            return False
    return True


def _create_step_completion_artifact(db: Session, step: WorkflowStepRow, task: TaskRow) -> ArtifactRow:
    artifact_type = {
        "research": "research_report",
        "plan": "plan_brief",
        "synthesis": "synthesis_report",
        "implementation": "step_output",
        "bugfix": "step_output",
        "validate": "validation_report",
        "review": "review_report",
        "test": "test_report",
        "closeout": "validation_manifest",
        "requirement_revision": "requirement_revision",
    }.get(step.step_type, "step_output")
    body = task.output_content or ""
    payload = {
        "task_id": task.id,
        "step_id": step.id,
        "step_type": step.step_type,
        "status": task.status,
        "runtime_backend": task.runtime_backend,
        "runtime_provider": getattr(cast(Any, task), "runtime_provider", ""),
        "runtime_model": getattr(cast(Any, task), "runtime_model", ""),
        "runtime_session_id": task.runtime_session_id,
        "output_path": task.output_path,
        "output_content": body,
        "execution_time_ms": task.execution_time_ms,
        "tokens_used": int(getattr(cast(Any, task), "tokens_used", 0) or 0),
        "budget_cost_points": int(getattr(cast(Any, task), "budget_cost_points", 0) or 0),
    }
    return _create_artifact(
        db,
        requirement_id=step.requirement_id,
        workflow_run_id=step.workflow_run_id,
        step_id=step.id,
        producer_step_id=step.id,
        artifact_type=artifact_type,
        path=task.output_path,
        content_summary=(body or task.last_error_message or step.title)[:200],
        human_readable_body=body,
        machine_readable_payload=payload,
    )


def _runtime_lifecycle_phase_for_task(task: TaskRow) -> str:
    status = str(task.status or "")
    return {
        "running": "running",
        "pending_approval": "waiting_approval",
        "completed": "completed",
        "failed": "failed",
        "rejected": "failed",
        "cancelled": "paused",
    }.get(status, status or "unknown")


def _runtime_output_dir(task: TaskRow) -> Path:
    return task_output_dir(PROJECT_ROOT, str(task.agent_id), int(task.id))


def _runtime_state_snapshot(task: TaskRow) -> dict[str, Any]:
    if str(task.runtime_backend or "") != "copilot_sdk":
        return {}
    paths = copilot_runtime_paths(_runtime_output_dir(task))
    state = load_runtime_state(paths["state"]) or {}
    return {
        "status": str(state.get("status") or ""),
        "session_id": str(state.get("sessionId") or task.runtime_session_id or ""),
        "selected_agent": str(state.get("selectedAgent") or task.runtime_selected_agent or ""),
        "heartbeat_at": str(state.get("heartbeatAt") or ""),
        "updated_at": str(state.get("updatedAt") or ""),
        "resume_requested_at": str(state.get("resumeRequestedAt") or ""),
        "last_event_type": str(state.get("lastEventType") or ""),
        "worker_pid": int(state.get("workerPid") or 0),
    }


def _runtime_telemetry_logs(db: Session, task_id: int) -> list[TaskLogRow]:
    logs = db.query(TaskLogRow).filter(TaskLogRow.task_id == task_id).order_by(TaskLogRow.id.asc()).all()
    return [
        log
        for log in logs
        if (
            str(log.event_type).startswith("runtime_")
            or str(log.event_type).startswith("subagent_")
            or str(log.event_type).startswith("assistant_")
            or str(log.event_type).startswith("tool_")
            or str(log.event_type).startswith("permission_")
            or str(log.event_type).startswith("user_input_")
            or str(log.event_type).startswith("elicitation_")
            or str(log.event_type) in {"crew_started", "approval_requested", "completed", "failed", "paused", "started", "created"}
        )
    ]


def _runtime_telemetry_payload(db: Session, step: WorkflowStepRow, task: TaskRow, *, phase: str) -> dict[str, Any]:
    logs = _runtime_telemetry_logs(db, int(task.id))
    event_counts: dict[str, int] = {}
    subagent_counts = {"selected": 0, "started": 0, "completed": 0, "failed": 0}
    recent_events: list[dict[str, Any]] = []
    recent_subagents: list[dict[str, Any]] = []
    for log in logs:
        event_type = str(log.event_type or "")
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        detail = str(log.detail or "")
        if event_type.startswith("subagent_"):
            name = event_type.split("_", 1)[1]
            if name in subagent_counts:
                subagent_counts[name] += 1
            recent_subagents.append(
                {
                    "event_type": event_type,
                    "detail": detail or None,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
            )
        recent_events.append(
            {
                "event_type": event_type,
                "detail": detail or None,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
        )

    runtime_state = _runtime_state_snapshot(task)
    return {
        "requirement_id": _as_int(step.requirement_id),
        "workflow_run_id": _as_int(step.workflow_run_id),
        "step_id": _as_int(step.id),
        "step_key": str(step.step_key),
        "step_type": str(step.step_type),
        "task_id": _as_int(task.id),
        "phase": phase,
        "runtime_backend": str(task.runtime_backend or ""),
        "runtime_provider": str(getattr(cast(Any, task), "runtime_provider", "") or ""),
        "runtime_model": str(getattr(cast(Any, task), "runtime_model", "") or ""),
        "runtime_session_id": str(task.runtime_session_id or ""),
        "runtime_selected_agent": str(task.runtime_selected_agent or ""),
        "runtime_event_cursor": int(getattr(task, "runtime_event_cursor", 0) or 0),
        "tokens_used": int(getattr(cast(Any, task), "tokens_used", 0) or 0),
        "budget_cost_points": int(getattr(cast(Any, task), "budget_cost_points", 0) or 0),
        "event_counts": event_counts,
        "subagent_counts": subagent_counts,
        "recent_events": recent_events[-12:],
        "recent_subagents": recent_subagents[-6:],
        "runtime_state": runtime_state,
        "transcript_available": bool(task.output_content or task.output_path),
    }


def _runtime_lifecycle_payload(step: WorkflowStepRow, task: TaskRow, *, phase: str, note: str | None = None) -> dict[str, Any]:
    return {
        "requirement_id": _as_int(step.requirement_id),
        "workflow_run_id": _as_int(step.workflow_run_id),
        "step_id": _as_int(step.id),
        "step_key": str(step.step_key),
        "step_type": str(step.step_type),
        "task_id": _as_int(task.id),
        "phase": phase,
        "task_status": str(task.status or ""),
        "step_status": str(step.status or ""),
        "runtime_backend": str(task.runtime_backend or ""),
        "runtime_provider": str(getattr(cast(Any, task), "runtime_provider", "") or ""),
        "runtime_model": str(getattr(cast(Any, task), "runtime_model", "") or ""),
        "runtime_session_id": str(task.runtime_session_id or ""),
        "runtime_selected_agent": str(task.runtime_selected_agent or ""),
        "agent_id": str(task.agent_id or ""),
        "skill_name": str(task.skill_name or ""),
        "requires_approval": bool(task.requires_approval),
        "output_path": str(task.output_path or "") or None,
        "last_error_message": str(task.last_error_message or "") or None,
        "note": note,
        "tokens_used": int(getattr(cast(Any, task), "tokens_used", 0) or 0),
        "budget_cost_points": int(getattr(cast(Any, task), "budget_cost_points", 0) or 0),
        "task_created_at": task.created_at.isoformat() if task.created_at else None,
        "task_started_at": task.started_at.isoformat() if task.started_at else None,
        "task_completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "step_started_at": step.started_at.isoformat() if step.started_at else None,
        "step_completed_at": step.completed_at.isoformat() if step.completed_at else None,
        "execution_time_ms": int(task.execution_time_ms or 0) or None,
    }


def _runtime_lifecycle_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Runtime Lifecycle",
        "",
        f"- Phase: `{payload.get('phase') or '-'}`",
        f"- Task status: `{payload.get('task_status') or '-'}`",
        f"- Step status: `{payload.get('step_status') or '-'}`",
        f"- Backend: `{payload.get('runtime_backend') or '-'}`",
        f"- Provider: `{payload.get('runtime_provider') or '-'}`",
        f"- Model: `{payload.get('runtime_model') or '-'}`",
        f"- Tokens used: `{payload.get('tokens_used') or 0}`",
        f"- Budget cost points: `{payload.get('budget_cost_points') or 0}`",
        f"- Session: `{payload.get('runtime_session_id') or '-'}`",
        f"- Selected agent: `{payload.get('runtime_selected_agent') or '-'}`",
        f"- Skill: `{payload.get('skill_name') or '-'}`",
    ]
    if payload.get("last_error_message"):
        lines.append(f"- Last error: {payload.get('last_error_message')}")
    if payload.get("note"):
        lines.append(f"- Note: {payload.get('note')}")
    return "\n".join(lines)


def _runtime_telemetry_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Runtime Telemetry",
        "",
        f"- Backend: `{payload.get('runtime_backend') or '-'}`",
        f"- Provider: `{payload.get('runtime_provider') or '-'}`",
        f"- Model: `{payload.get('runtime_model') or '-'}`",
        f"- Tokens used: `{payload.get('tokens_used') or 0}`",
        f"- Budget cost points: `{payload.get('budget_cost_points') or 0}`",
        f"- Session: `{payload.get('runtime_session_id') or '-'}`",
        f"- Transcript available: {'yes' if payload.get('transcript_available') else 'no'}",
    ]
    subagent_counts = payload.get("subagent_counts") or {}
    if isinstance(subagent_counts, dict):
        lines.append(
            "- Subagents: "
            + ", ".join(
                f"{key}={int(subagent_counts.get(key) or 0)}"
                for key in ("selected", "started", "completed", "failed")
            )
        )
    recent_events = payload.get("recent_events") or []
    if isinstance(recent_events, list) and recent_events:
        lines.extend(["", "## Recent Runtime Events"])
        for item in recent_events[-5:]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- `{item.get('event_type', '-')}`"
                + (f": {item.get('detail')}" if item.get("detail") else "")
            )
    return "\n".join(lines)


def _create_or_update_artifact(
    db: Session,
    *,
    requirement_id: int,
    artifact_type: str,
    workflow_run_id: int | None = None,
    step_id: int | None = None,
    producer_step_id: int | None = None,
    path: str | None = None,
    content_summary: str | None = None,
    human_readable_body: str | None = None,
    machine_readable_payload: dict | list | str | None = None,
) -> ArtifactRow:
    payload_text = _json_dumps(machine_readable_payload) if machine_readable_payload is not None else None
    checksum = hashlib.sha1((payload_text or human_readable_body or content_summary or "").encode("utf-8")).hexdigest()
    latest = db.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == artifact_type,
        ArtifactRow.workflow_run_id == workflow_run_id,
        ArtifactRow.step_id == step_id,
    ).order_by(ArtifactRow.id.desc()).first()
    if latest is not None and str(latest.checksum or "") == checksum:
        return latest
    return _create_artifact(
        db,
        requirement_id=requirement_id,
        artifact_type=artifact_type,
        workflow_run_id=workflow_run_id,
        step_id=step_id,
        producer_step_id=producer_step_id,
        path=path,
        content_summary=content_summary,
        human_readable_body=human_readable_body,
        machine_readable_payload=machine_readable_payload,
    )


def _record_runtime_lifecycle_artifacts(
    db: Session,
    step: WorkflowStepRow,
    task: TaskRow,
    *,
    phase: str | None = None,
    note: str | None = None,
) -> None:
    resolved_phase = phase or _runtime_lifecycle_phase_for_task(task)
    lifecycle_payload = _runtime_lifecycle_payload(step, task, phase=resolved_phase, note=note)
    telemetry_payload = _runtime_telemetry_payload(db, step, task, phase=resolved_phase)
    lifecycle_artifact = _create_or_update_artifact(
        db,
        requirement_id=step.requirement_id,
        workflow_run_id=step.workflow_run_id,
        step_id=step.id,
        producer_step_id=step.id,
        artifact_type="runtime_lifecycle",
        path=str(task.output_path or "") or None,
        content_summary=f"{resolved_phase} runtime lifecycle for step {step.step_key}",
        human_readable_body=_runtime_lifecycle_markdown(lifecycle_payload),
        machine_readable_payload=lifecycle_payload,
    )
    _create_or_update_artifact(
        db,
        requirement_id=step.requirement_id,
        workflow_run_id=step.workflow_run_id,
        step_id=step.id,
        producer_step_id=step.id,
        artifact_type="runtime_telemetry",
        path=str(task.output_path or "") or None,
        content_summary=f"{resolved_phase} runtime telemetry for step {step.step_key}",
        human_readable_body=_runtime_telemetry_markdown(telemetry_payload),
        machine_readable_payload=telemetry_payload,
    )
    _maybe_record_runtime_incident_artifact(db, step, lifecycle_artifact, phase=resolved_phase, note=note)


def _maybe_record_runtime_incident_artifact(
    db: Session,
    step: WorkflowStepRow,
    lifecycle_artifact: ArtifactRow | None,
    *,
    phase: str,
    note: str | None = None,
) -> None:
    if lifecycle_artifact is None:
        return
    resolved_phase = str(phase or "").strip()
    if resolved_phase not in {"failed", "paused"}:
        return
    requirement = _require_requirement(db, _as_int(step.requirement_id))
    incident = classify_artifact_incident(requirement, lifecycle_artifact)
    if not incident:
        return
    summary = str(incident.get("summary") or "").strip()
    title = str(incident.get("title") or "Incident Record").strip()
    project_display = str(incident.get("project_display_name") or incident.get("project_root_path") or "Org Ops").strip()
    lines = [
        f"# {title}",
        "",
        f"- Project: {project_display}",
        f"- Phase: {resolved_phase or '-'}",
        f"- Incident family: {incident.get('incident_family') or '-'}",
        f"- Incident code: {incident.get('incident_code') or '-'}",
        f"- Severity: {incident.get('severity') or '-'}",
        f"- Recovery status: {incident.get('recovery_status') or '-'}",
    ]
    if note:
        lines.extend(["", "## Note", str(note).strip()])
    if summary:
        lines.extend(["", "## Summary", summary])
    recommended_action = str(incident.get("recommended_action") or "").strip()
    if recommended_action:
        lines.extend(["", "## Recommended action", recommended_action])
    evidence = incident.get("evidence") or []
    if evidence:
        lines.extend(["", "## Evidence"])
        for item in evidence:
            lines.append(f"- {json.dumps(item, ensure_ascii=False, sort_keys=True)}")
    _create_or_update_artifact(
        db,
        requirement_id=_as_int(step.requirement_id),
        workflow_run_id=_as_int(step.workflow_run_id),
        step_id=step.id,
        producer_step_id=step.id,
        artifact_type="incident_record",
        content_summary=_truncate_text(summary or recommended_action or title, 200),
        human_readable_body="\n".join(lines).strip(),
        machine_readable_payload=incident,
    )

def _runtime_adaptation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Runtime {str(payload.get('adaptation_type') or 'adaptation').capitalize()}",
        "",
        f"- Step: `{payload.get('step_key') or '-'}` ({payload.get('step_type') or '-'})",
        f"- Tier: `{payload.get('from_tier') or '-'}` -> `{payload.get('to_tier') or '-'}`",
        f"- Trigger: `{payload.get('trigger') or '-'}`",
    ]
    reasons = [str(item).strip() for item in payload.get("reasons") or [] if str(item).strip()]
    if reasons:
        lines.extend(["", "## Reasons"])
        lines.extend([f"- {item}" for item in reasons])
    metrics = payload.get("project_change_metrics") or {}
    if isinstance(metrics, dict) and metrics:
        lines.extend(
            [
                "",
                "## Project Change Metrics",
                f"- Changed projects: `{metrics.get('changed_project_count', 0)}`",
                f"- Changed files: `{metrics.get('total_changed_files', 0)}`",
            ]
        )
    return "\n".join(lines)


def _record_runtime_adaptation(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
    payload: dict[str, Any],
) -> ArtifactRow:
    return _create_or_update_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id),
        step_id=_as_int(step.id),
        producer_step_id=_as_int(step.id),
        artifact_type="runtime_adaptation",
        content_summary=(
            f"{payload.get('adaptation_type', 'adaptation')} {payload.get('from_tier', '-')}"
            f" -> {payload.get('to_tier', '-')}"
        ),
        human_readable_body=_runtime_adaptation_markdown(payload),
        machine_readable_payload=payload,
    )


def _apply_step_runtime_tier(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
    target_tier: str,
    adaptation_type: str,
    trigger: str,
    reasons: list[str],
    project_change_metrics: dict[str, Any] | None = None,
    persist_failure_count: int | None = None,
) -> bool:
    profile = _step_execution_profile(step)
    from_tier = _normalize_runtime_tier(profile.get("complexity_tier"))
    to_tier = _normalize_runtime_tier(target_tier)
    if from_tier == to_tier:
        return False

    from server.services.workflow_planner import _default_budget_cap, _default_escalation_rule

    allow_escalation = bool(profile.get("allow_escalation", True))
    if to_tier == "max":
        allow_escalation = False
    profile["complexity_tier"] = to_tier
    profile["budget_cap"] = dict(_default_budget_cap(to_tier))
    profile["allow_escalation"] = allow_escalation
    profile["escalation_rule"] = dict(
        profile.get("escalation_rule") or _default_escalation_rule(to_tier, allow_escalation=allow_escalation)
    )
    if persist_failure_count is not None:
        profile["failure_count"] = int(persist_failure_count)
    profile["last_runtime_adaptation"] = {
        "adaptation_type": adaptation_type,
        "trigger": trigger,
        "from_tier": from_tier,
        "to_tier": to_tier,
        "reasons": reasons,
        "adapted_at": utcnow().isoformat(),
    }
    _write_step_execution_profile(step, profile)
    _record_runtime_adaptation(
        db,
        requirement=requirement,
        workflow_run=workflow_run,
        step=step,
        payload={
            "requirement_id": _as_int(requirement.id),
            "workflow_run_id": _as_int(workflow_run.id),
            "step_id": _as_int(step.id),
            "step_key": str(step.step_key or ""),
            "step_type": str(step.step_type or ""),
            "adaptation_type": adaptation_type,
            "trigger": trigger,
            "from_tier": from_tier,
            "to_tier": to_tier,
            "reasons": reasons,
            "project_change_metrics": project_change_metrics or {},
        },
    )
    _record_step_event(db, _as_int(step.id), f"runtime_{adaptation_type}", "; ".join(reasons) or trigger)
    return True


def _workflow_run_task_rows(db: Session, workflow_run_id: int) -> list[TaskRow]:
    task_ids = [
        int(step.compatibility_task_id)
        for step in db.query(WorkflowStepRow).filter(WorkflowStepRow.workflow_run_id == workflow_run_id).all()
        if int(step.compatibility_task_id or 0) > 0
    ]
    if not task_ids:
        return []
    return db.query(TaskRow).filter(TaskRow.id.in_(task_ids)).all()


def _budget_cap_points_for_step(step: WorkflowStepRow) -> int:
    from server.services.task_runtime import budget_points_for_tier

    profile = _step_execution_profile(step)
    tier = _normalize_runtime_tier(profile.get("complexity_tier"))
    attempts = max(1, int((profile.get("budget_cap") or {}).get("max_attempts") or 1))
    return budget_points_for_tier(tier) * attempts


def _budget_usage_summary(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
) -> dict[str, Any]:
    tasks = _workflow_run_task_rows(db, _as_int(workflow_run.id))
    spent_points = sum(int(getattr(cast(Any, task), "budget_cost_points", 0) or 0) for task in tasks)
    tokens_used = sum(int(getattr(cast(Any, task), "tokens_used", 0) or 0) for task in tasks)
    runtime_ms = sum(int(task.execution_time_ms or 0) for task in tasks)
    step_cap_points = sum(_budget_cap_points_for_step(step) for step in workflow_run.steps)
    project_scope = _dynamic_validation_scope(db, _as_int(requirement.id), workflow_run_id=_as_int(workflow_run.id))
    affected_projects = project_scope.get("affected_projects") or []
    return {
        "requirement_id": _as_int(requirement.id),
        "workflow_run_id": _as_int(workflow_run.id),
        "spent_points": spent_points,
        "tokens_used": tokens_used,
        "execution_time_ms": runtime_ms,
        "task_count": len(tasks),
        "step_budget_cap_points": step_cap_points,
        "affected_projects": affected_projects,
    }


def _budget_usage_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Budget Usage Summary",
        "",
        f"- Spent points: `{payload.get('spent_points') or 0}` / `{payload.get('step_budget_cap_points') or 0}`",
        f"- Tokens used: `{payload.get('tokens_used') or 0}`",
        f"- Execution time ms: `{payload.get('execution_time_ms') or 0}`",
        f"- Task count: `{payload.get('task_count') or 0}`",
    ]
    projects = payload.get("affected_projects") or []
    if isinstance(projects, list) and projects:
        lines.extend(["", "## Affected Projects"])
        for item in projects:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- `{item.get('display_name') or item.get('project_key') or '-'}`"
                f" changed_files={int(item.get('changed_file_count') or 0)}"
            )
    return "\n".join(lines)


def _record_budget_usage_artifact(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
) -> ArtifactRow:
    payload = _budget_usage_summary(db, requirement, workflow_run)
    return _create_or_update_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id),
        artifact_type="budget_usage_summary",
        content_summary=f"Budget usage for requirement #{requirement.id}",
        human_readable_body=_budget_usage_markdown(payload),
        machine_readable_payload=payload,
    )


def _pause_for_budget_guardrail(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
    reason: str,
    payload: dict[str, Any],
) -> None:
    existing = db.query(ApprovalRequestRow).filter(
        ApprovalRequestRow.requirement_id == requirement.id,
        ApprovalRequestRow.workflow_run_id == workflow_run.id,
        ApprovalRequestRow.step_id == step.id,
        ApprovalRequestRow.approval_type == "budget_review",
        ApprovalRequestRow.status == "pending",
    ).first()
    if existing is None:
        db.add(
            ApprovalRequestRow(
                requirement_id=requirement.id,
                workflow_run_id=workflow_run.id,
                step_id=step.id,
                approval_type="budget_review",
                status="pending",
                reviewer="operator",
                comment=reason,
            )
        )
    _create_or_update_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id),
        step_id=_as_int(step.id),
        producer_step_id=_as_int(step.id),
        artifact_type="budget_guardrail",
        content_summary=f"Budget review required for step {step.step_key}",
        human_readable_body=reason,
        machine_readable_payload=payload,
    )
    workflow_run.status = "paused"
    workflow_run.completed_at = None
    requirement.status = "paused"
    requirement.completed_at = None
    _record_step_event(db, _as_int(step.id), "budget_guardrail", reason)


def _budget_guardrail_after_task(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
    task: TaskRow,
) -> bool:
    profile = _step_execution_profile(step)
    budget_cap = profile.get("budget_cap") or {}
    if not isinstance(budget_cap, dict):
        budget_cap = {}
    reasons: list[str] = []
    max_runtime_seconds = int(budget_cap.get("max_runtime_seconds") or 0)
    max_tokens = int(budget_cap.get("max_input_tokens") or 0) + int(budget_cap.get("max_output_tokens") or 0)
    execution_time_ms = int(task.execution_time_ms or 0)
    tokens_used = int(getattr(cast(Any, task), "tokens_used", 0) or 0)
    if max_runtime_seconds > 0 and execution_time_ms > max_runtime_seconds * 1000:
        reasons.append(f"task runtime exceeded max_runtime_seconds ({execution_time_ms}ms > {max_runtime_seconds * 1000}ms)")
    if max_tokens > 0 and tokens_used > max_tokens:
        reasons.append(f"task token usage exceeded prompt budget ({tokens_used} > {max_tokens})")

    failure_count = max(int(step.retry_count or 0), int(profile.get("failure_count") or 0))
    max_attempts = int(budget_cap.get("max_attempts") or 0)
    if max_attempts > 0 and failure_count >= max_attempts and str(task.status or "") in {"failed", "rejected"}:
        reasons.append(f"failure count exhausted step budget ({failure_count}/{max_attempts})")

    budget_summary = _budget_usage_summary(db, requirement, workflow_run)
    step_budget_cap_points = int(budget_summary.get("step_budget_cap_points") or 0)
    spent_points = int(budget_summary.get("spent_points") or 0)
    if step_budget_cap_points > 0 and spent_points > step_budget_cap_points:
        reasons.append(f"requirement budget exhausted ({spent_points}/{step_budget_cap_points})")

    project_scope = budget_summary.get("affected_projects") or []
    project_root = ""
    if isinstance(project_scope, list) and project_scope:
        project_root = str(project_scope[0].get("root_path") or "")
    if project_root:
        policies = resolve_project_policies_for_target(db, project_root, require_active=False)
        if policies:
            policy = policies[0]
            project_budget = max(20, int(getattr(policy, "portfolio_budget_points", 100) or 100))
            if spent_points > project_budget:
                reasons.append(f"project budget exhausted ({spent_points}/{project_budget})")

    if not reasons:
        return False

    payload = {
        "requirement_id": _as_int(requirement.id),
        "workflow_run_id": _as_int(workflow_run.id),
        "step_id": _as_int(step.id),
        "task_id": _as_int(task.id),
        "task_status": str(task.status or ""),
        "budget_cap": budget_cap,
        "spent_points": spent_points,
        "step_budget_cap_points": step_budget_cap_points,
        "tokens_used": tokens_used,
        "execution_time_ms": execution_time_ms,
        "reasons": reasons,
    }
    _pause_for_budget_guardrail(
        db,
        requirement=requirement,
        workflow_run=workflow_run,
        step=step,
        reason="; ".join(reasons),
        payload=payload,
    )
    return True


def _maybe_escalate_ready_step(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
) -> bool:
    if str(step.step_type or "") not in {"implementation", "bugfix", "validate", "review", "test"}:
        return False
    profile = _step_execution_profile(step)
    if not bool(profile.get("allow_escalation", True)):
        return False
    current_tier = _normalize_runtime_tier(profile.get("complexity_tier"))
    if current_tier == "max":
        return False
    rule = profile.get("escalation_rule") or {}
    if not isinstance(rule, dict):
        return False
    when = {str(item).strip() for item in rule.get("when") or [] if str(item).strip()}
    metrics = _project_change_metrics(db, _as_int(requirement.id), workflow_run_id=_as_int(workflow_run.id))
    reasons: list[str] = []
    threshold = int(rule.get("changed_files_threshold") or 8)
    if "multi_project_change_detected" in when and int(metrics.get("changed_project_count") or 0) > 1:
        reasons.append("multi-project change detected")
    if "changed_files_over_threshold" in when and int(metrics.get("total_changed_files") or 0) >= threshold:
        reasons.append(f"changed files exceeded threshold ({threshold})")
    next_tier = _tier_transition(current_tier, str(rule.get("next_tier") or current_tier))
    if next_tier == current_tier or not reasons:
        return False
    return _apply_step_runtime_tier(
        db,
        requirement=requirement,
        workflow_run=workflow_run,
        step=step,
        target_tier=next_tier,
        adaptation_type="escalation",
        trigger="dispatch_guard",
        reasons=reasons,
        project_change_metrics=metrics,
    )


def _maybe_downgrade_ready_step(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
) -> bool:
    profile = _step_execution_profile(step)
    current_tier = _normalize_runtime_tier(profile.get("complexity_tier"))
    if current_tier == "mini":
        return False
    metrics = _project_change_metrics(db, _as_int(requirement.id), workflow_run_id=_as_int(workflow_run.id))
    if _is_summary_like_step(step):
        return _apply_step_runtime_tier(
            db,
            requirement=requirement,
            workflow_run=workflow_run,
            step=step,
            target_tier="mini",
            adaptation_type="downgrade",
            trigger="dispatch_guard",
            reasons=["summary/report step downgraded to mini tier"],
            project_change_metrics=metrics,
        )
    if str(step.step_type or "") in {"validate", "review", "test"} and current_tier == "max":
        threshold = 8
        if int(metrics.get("changed_project_count") or 0) <= 1 and int(metrics.get("total_changed_files") or 0) < threshold:
            return _apply_step_runtime_tier(
                db,
                requirement=requirement,
                workflow_run=workflow_run,
                step=step,
                target_tier="standard",
                adaptation_type="downgrade",
                trigger="dispatch_guard",
                reasons=["verification scope is small enough to return from max to standard"],
                project_change_metrics=metrics,
            )
    return False


def _failure_count_for_step(step: WorkflowStepRow) -> int:
    profile = _step_execution_profile(step)
    tracked = int(profile.get("failure_count") or 0)
    return max(int(step.retry_count or 0), tracked) + 1


def _build_followup_execution_profile(
    failed_step: WorkflowStepRow,
    *,
    step_type: str,
    failure_count: int,
    error_text: str,
    project_change_metrics: dict[str, Any],
) -> dict[str, Any]:
    from server.services.workflow_planner import _default_budget_cap, _default_escalation_rule

    profile = dict(_step_execution_profile(failed_step))
    current_tier = _normalize_runtime_tier(profile.get("complexity_tier"))
    allow_escalation = bool(profile.get("allow_escalation", True))
    rule = profile.get("escalation_rule") if isinstance(profile.get("escalation_rule"), dict) else {}
    when = {str(item).strip() for item in rule.get("when") or [] if str(item).strip()}
    threshold = int(rule.get("changed_files_threshold") or 8)
    reasons: list[str] = []
    if allow_escalation and "step_failed_twice" in when and failure_count >= 2:
        reasons.append("step failed twice")
    if allow_escalation and ("review_or_test_blocker" in when or "validation_blocker" in when) and str(failed_step.step_type or "") in {"validate", "review", "test"}:
        reasons.append(f"{failed_step.step_type} blocker detected")
    if allow_escalation and "multi_project_change_detected" in when and int(project_change_metrics.get("changed_project_count") or 0) > 1:
        reasons.append("multi-project change detected")
    if allow_escalation and "changed_files_over_threshold" in when and int(project_change_metrics.get("total_changed_files") or 0) >= threshold:
        reasons.append(f"changed files exceeded threshold ({threshold})")
    target_tier = current_tier
    if reasons:
        target_tier = _tier_transition(current_tier, str(rule.get("next_tier") or current_tier))
    profile["complexity_tier"] = target_tier
    profile["budget_cap"] = dict(_default_budget_cap(target_tier))
    profile["allow_escalation"] = False if target_tier == "max" else allow_escalation
    profile["escalation_rule"] = dict(rule or _default_escalation_rule(target_tier, allow_escalation=bool(profile["allow_escalation"])))
    profile["failure_count"] = int(failure_count)
    profile["followup_from_step_type"] = str(failed_step.step_type or "")
    profile["followup_error_summary"] = str(error_text or "")[:500]
    if reasons:
        profile["last_runtime_adaptation"] = {
            "adaptation_type": "escalation",
            "trigger": "failure_loop",
            "from_tier": current_tier,
            "to_tier": target_tier,
            "reasons": reasons,
            "adapted_at": utcnow().isoformat(),
        }
    if step_type in {"validate", "review", "test"} and target_tier == "max" and int(project_change_metrics.get("changed_project_count") or 0) <= 1:
        profile["complexity_tier"] = "standard"
        profile["budget_cap"] = dict(_default_budget_cap("standard"))
    if step_type == "closeout":
        profile["complexity_tier"] = "mini"
        profile["budget_cap"] = dict(_default_budget_cap("mini"))
    return profile


def _bind_output_to_followup_steps(db: Session, step: WorkflowStepRow, artifact: ArtifactRow):
    dependents = db.query(WorkflowStepDependencyRow).filter(
        WorkflowStepDependencyRow.depends_on_step_id == step.id
    ).all()
    purpose = {
        "research": "research_context",
        "plan": "plan_context",
        "synthesis": "implementation_context",
        "implementation": "implementation_context",
        "bugfix": "bugfix_context",
        "validate": "validation_context",
        "review": "review_context",
        "test": "test_context",
        "closeout": "validation_context",
    }.get(step.step_type, "implementation_context")
    for dep in dependents:
        _bind_artifact(db, dep.step_id, artifact.id, purpose, True)


def _mark_step_targets_passed(
    db: Session,
    requirement: RequirementRow,
    step: WorkflowStepRow,
    artifact: ArtifactRow,
    *,
    task: TaskRow | None = None,
) -> list[str]:
    targets = _json_loads(step.validation_targets_json, [])
    if not isinstance(targets, list):
        return []
    failures: list[str] = []
    for target in targets:
        check_key = str((target or {}).get("check_key") or "")
        if not check_key:
            continue
        check = db.query(RequirementAcceptanceCheckRow).filter(
            RequirementAcceptanceCheckRow.requirement_id == step.requirement_id,
            RequirementAcceptanceCheckRow.check_key == check_key,
        ).first()
        if check is None:
            continue
        failure_reason: str | None = None
        if str(getattr(check, "check_type", "") or "") == "repo_file_changes":
            failure_reason = _repo_file_changes_check_error(
                db,
                step=step,
                task=task,
                spec=target if isinstance(target, dict) else {},
                artifact=artifact,
            )
        if failure_reason:
            check.status = "failed"
            check.verified_by_step_id = step.id
            check.evidence_artifact_id = artifact.id
            failures.append(f"check `{check_key}` failed: {failure_reason}")
            continue
        check.status = "passed"
        check.verified_by_step_id = step.id
        check.evidence_artifact_id = artifact.id
    return failures


def _mark_step_targets_failed(db: Session, step: WorkflowStepRow, artifact: ArtifactRow):
    targets = _json_loads(step.validation_targets_json, [])
    if not isinstance(targets, list):
        return
    for target in targets:
        check_key = str((target or {}).get("check_key") or "")
        if not check_key:
            continue
        check = db.query(RequirementAcceptanceCheckRow).filter(
            RequirementAcceptanceCheckRow.requirement_id == step.requirement_id,
            RequirementAcceptanceCheckRow.check_key == check_key,
        ).first()
        if check is None:
            continue
        check.status = "failed"
        check.verified_by_step_id = step.id
        check.evidence_artifact_id = artifact.id


def _create_bugfix_branch(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    failed_step: WorkflowStepRow,
    bug_report_artifact: ArtifactRow,
    *,
    bugfix_execution_profile: dict[str, Any] | None = None,
    validate_execution_profile: dict[str, Any] | None = None,
):
    existing = db.query(WorkflowStepRow).filter(
        WorkflowStepRow.workflow_run_id == workflow_run.id,
        WorkflowStepRow.step_type == "bugfix",
        WorkflowStepRow.branch_from_step_id == failed_step.id,
    ).first()
    if existing:
        return

    max_sequence = db.query(WorkflowStepRow).filter(WorkflowStepRow.workflow_run_id == workflow_run.id).order_by(
        WorkflowStepRow.sequence_no.desc()
    ).first()
    next_sequence = (max_sequence.sequence_no if max_sequence else 0) + 10
    bugfix_agent_id = failed_step.assigned_agent_id or _fallback_agent_id(db)
    tester_agent_id = _secondary_agent_id(db, exclude={bugfix_agent_id})
    inherited_targets = _json_loads(failed_step.validation_targets_json, [])
    validate_targets = [{"check_key": "validation_passed", "method": "agent_validation"}]
    if failed_step.step_type in {"validate", "review", "test"} and isinstance(inherited_targets, list) and inherited_targets:
        validate_targets = inherited_targets
    base_approval_policy = _json_loads(getattr(failed_step, "approval_policy_json", None), {})

    bugfix_step = WorkflowStepRow(
        workflow_run_id=workflow_run.id,
        requirement_id=requirement.id,
        step_key=f"bugfix-{failed_step.id}",
        step_type="bugfix",
        title=f"Bugfix after {failed_step.step_type} failure",
        status="pending",
        sequence_no=next_sequence,
        assigned_agent_id=bugfix_agent_id,
        assigned_workflow_role="bugfixer",
        branch_from_step_id=failed_step.id,
        context_scope="step_private",
        done_when_markdown="Bugfix output resolves the recorded failure and is ready for re-review.",
        file_scope_json=failed_step.file_scope_json,
        validation_targets_json=json.dumps([]),
        failure_policy_json=json.dumps({"on_failure": "bugfix", "max_retries": 0}),
        approval_policy_json=json.dumps(_derived_approval_policy(
            "bugfix",
            base_approval_policy,
            execution_profile=bugfix_execution_profile or _step_execution_profile(failed_step),
            requirement=requirement,
        )),
        execution_profile_json=json.dumps(bugfix_execution_profile or _step_execution_profile(failed_step)),
    )
    db.add(bugfix_step)
    db.flush()
    _bind_artifact(db, bugfix_step.id, bug_report_artifact.id, "bugfix_context", True)

    validate_step = WorkflowStepRow(
        workflow_run_id=workflow_run.id,
        requirement_id=requirement.id,
        step_key=f"validate-{bugfix_step.id}",
        step_type="validate",
        title=f"Validate bugfix for {requirement.title}",
        status="pending",
        sequence_no=next_sequence + 10,
        assigned_agent_id=tester_agent_id,
        assigned_workflow_role="validator",
        branch_from_step_id=failed_step.id,
        context_scope="verification",
        done_when_markdown="Validation reruns and confirms the bugfix is ready for closeout.",
        file_scope_json=failed_step.file_scope_json,
        validation_targets_json=json.dumps(validate_targets),
        failure_policy_json=json.dumps({"on_failure": "bugfix", "max_retries": 0}),
        approval_policy_json=json.dumps(_derived_approval_policy(
            "validate",
            base_approval_policy,
            execution_profile=validate_execution_profile or _step_execution_profile(failed_step),
            requirement=requirement,
        )),
        execution_profile_json=json.dumps(validate_execution_profile or _step_execution_profile(failed_step)),
    )
    db.add(validate_step)
    db.flush()

    db.add(
        WorkflowStepDependencyRow(
            step_id=validate_step.id,
            depends_on_step_id=bugfix_step.id,
            dependency_kind="output_required",
            required_artifact_types_json=json.dumps(["step_output"]),
            is_blocking=True,
        )
    )

    closeout_step = db.query(WorkflowStepRow).filter(
        WorkflowStepRow.workflow_run_id == workflow_run.id,
        WorkflowStepRow.step_type == "closeout",
    ).first()
    if closeout_step is not None:
        closeout_step.sequence_no = next_sequence + 20
        existing_deps = db.query(WorkflowStepDependencyRow).filter(WorkflowStepDependencyRow.step_id == closeout_step.id).all()
        for dep in existing_deps:
            db.delete(dep)
        db.flush()
        db.add(
            WorkflowStepDependencyRow(
                step_id=closeout_step.id,
                depends_on_step_id=validate_step.id,
                dependency_kind="validation_required",
                required_artifact_types_json=json.dumps(["validation_report"]),
                is_blocking=True,
            )
        )
    workflow_run.status = "running"
    requirement.status = "in_progress"


def _trip_bugfix_circuit_breaker(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    failed_step: WorkflowStepRow,
    error_artifact: ArtifactRow,
    error_text: str,
    reason: str,
) -> None:
    root_step_id = _root_failure_step_id(db, failed_step)
    fingerprint = _error_fingerprint(error_text)
    followup_items = _create_circuit_breaker_followup_requirements(
        db,
        requirement=requirement,
        workflow_run=workflow_run,
        failed_step=failed_step,
        error_text=error_text,
        reason=reason,
        linked_bug_report_artifact_id=_as_int(error_artifact.id),
    )
    payload = {
        "requirement_id": _as_int(requirement.id),
        "workflow_run_id": _as_int(workflow_run.id),
        "failed_step_id": _as_int(failed_step.id),
        "root_failure_step_id": root_step_id,
        "error_fingerprint": fingerprint,
        "reason": reason,
        "triggered_at": utcnow().isoformat(),
        "linked_bug_report_artifact_id": _as_int(error_artifact.id),
        "followup_requirements": followup_items,
    }
    _create_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id),
        step_id=_as_int(failed_step.id),
        producer_step_id=_as_int(failed_step.id),
        artifact_type="bugfix_circuit_breaker",
        content_summary=reason[:200],
        human_readable_body="\n".join(
            [
                "# Bugfix Loop Circuit Breaker",
                "",
                reason,
                "",
                f"Last error: {error_text}",
            ]
        ),
        machine_readable_payload=payload,
    )
    _record_step_event(db, _as_int(failed_step.id), "circuit_breaker", reason)
    workflow_run.status = "failed"
    workflow_run.completed_at = utcnow()
    requirement.status = "needs_revision"
    requirement.completed_at = None
    _clear_role_sessions()
    _logger.warning(
        "event=bugfix_loop_circuit_breaker requirement_id=%s workflow_run_id=%s step_id=%s reason=%s",
        requirement.id,
        workflow_run.id,
        failed_step.id,
        reason,
    )


def _refresh_run_status(db: Session, requirement: RequirementRow, workflow_run: WorkflowRunRow):
    if requirement.status == "needs_revision":
        workflow_run.status = "cancelled"
        return
    if requirement.status == "paused" or str(workflow_run.status or "") == "paused":
        workflow_run.status = "paused"
        workflow_run.completed_at = None
        requirement.status = "paused"
        requirement.completed_at = None
        return
    steps = db.query(WorkflowStepRow).filter(WorkflowStepRow.workflow_run_id == workflow_run.id).all()
    if not steps:
        workflow_run.status = "pending"
        return
    if any(step.status in RUNNING_STEP_STATUSES for step in steps):
        workflow_run.status = "running"
        requirement.status = "in_progress"
        workflow_run.started_at = workflow_run.started_at or utcnow()
        requirement.started_at = requirement.started_at or utcnow()
        return
    non_cancelled = [s for s in steps if s.status != "cancelled"]
    if non_cancelled and all(step.status == "completed" for step in non_cancelled) and _all_checks_passed(db, requirement.id):
        workflow_run.status = "completed"
        workflow_run.completed_at = workflow_run.completed_at or utcnow()
        requirement.status = "done"
        requirement.completed_at = requirement.completed_at or utcnow()
        _clear_role_sessions()
        return
    if any(step.status == "failed" for step in steps):
        workflow_run.status = "running"
        requirement.status = "in_progress"
        return
    workflow_run.status = "pending"
    workflow_run.completed_at = None
    if requirement.status not in {"blocked", "paused", "needs_revision", "done"}:
        requirement.status = "ready" if int(requirement.current_plan_version or 0) > 0 else "draft"
        requirement.started_at = None
        requirement.completed_at = None


def _auto_complete_closeout(db: Session, requirement: RequirementRow, workflow_run: WorkflowRunRow, step: WorkflowStepRow):
    validation_errors = _validation_gate_errors(db, _as_int(requirement.id))
    if validation_errors:
        step.status = "blocked"
        step.started_at = step.started_at or utcnow()
        step.completed_at = None
        workflow_run.status = "paused"
        requirement.status = "blocked"
        requirement.completed_at = None
        reason = "; ".join(validation_errors)
        _record_step_event(db, _as_int(step.id), "closeout_blocked", reason)
        _create_or_update_artifact(
            db,
            requirement_id=_as_int(requirement.id),
            workflow_run_id=_as_int(workflow_run.id),
            step_id=_as_int(step.id),
            producer_step_id=_as_int(step.id),
            artifact_type="validation_manifest",
            content_summary=f"Closeout blocked for requirement #{requirement.id}",
            human_readable_body="# Closeout Blocked\n\n" + reason,
            machine_readable_payload={
                **_manual_closeout_payload(db, requirement, workflow_run),
                "status": "blocked",
                "validation_errors": validation_errors,
            },
        )
        return
    artifact = _create_artifact(
        db,
        requirement_id=requirement.id,
        workflow_run_id=workflow_run.id,
        step_id=step.id,
        producer_step_id=step.id,
        artifact_type="validation_manifest",
        content_summary=f"Closeout for requirement #{requirement.id}",
        human_readable_body=_manual_closeout_markdown(requirement, db),
        machine_readable_payload=_manual_closeout_payload(db, requirement, workflow_run),
    )
    step.started_at = step.started_at or utcnow()
    step.completed_at = None
    _finalize_requirement(db, requirement, workflow_run, step, artifact)


def _finalize_requirement(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
    artifact: ArtifactRow,
):
    _mark_step_targets_passed(db, requirement, step, artifact)
    delivery_contract = _delivery_contract_payload(db, requirement.id)
    vcs_payload, _vcs_artifact = _execute_requirement_vcs_delivery(db, requirement, workflow_run, step)
    vcs_blockers = [str(item).strip() for item in (vcs_payload.get("blockers") or []) if str(item).strip()]
    pr_payload: dict[str, Any] = {}
    pr_blockers: list[str] = []
    if not vcs_blockers:
        pr_payload, _pr_artifact = _sync_requirement_review_pr(
            db,
            requirement,
            workflow_run,
            step,
            delivery_contract=delivery_contract,
            vcs_payload=vcs_payload,
        )
        pr_blockers = [str(item).strip() for item in (pr_payload.get("blockers") or []) if str(item).strip()]
    if vcs_blockers or pr_blockers:
        step.status = "blocked"
        step.completed_at = None
        workflow_run.status = "paused"
        workflow_run.completed_at = None
        requirement.status = "blocked"
        requirement.completed_at = None
        _record_step_event(db, _as_int(step.id), "closeout_blocked", "; ".join(vcs_blockers + pr_blockers))
        _record_delivery_blocker(
            db,
            requirement,
            workflow_run,
            step,
            vcs_payload=vcs_payload,
            pr_payload=pr_payload,
        )
        _record_delivery_state(
            db,
            requirement,
            workflow_run,
            review_status="blocked",
            publish_status="blocked",
            vcs_payload=vcs_payload,
            pr_payload=pr_payload,
        )
        return

    step.status = "completed"
    step.completed_at = utcnow()
    workflow_run.status = "completed"
    workflow_run.completed_at = utcnow()
    requirement.status = "done"
    requirement.completed_at = utcnow()
    auto_publish_allowed = bool(delivery_contract.get("auto_publish_allowed"))
    required_checks = [str(item) for item in delivery_contract.get("required_checks") or [] if str(item).strip()]
    publish_status = "published" if auto_publish_allowed and not required_checks else (
        "blocked" if str(delivery_contract.get("release_mode") or "manual") == "disabled" else "review_ready"
    )
    compare_url = _build_delivery_compare_url(
        vcs_payload,
        str(delivery_contract.get("branch_name") or "") or None,
        str(delivery_contract.get("base_branch") or "") or None,
    )
    review_surface_payload = {
        "requirement_id": _as_int(requirement.id),
        "workflow_run_id": _as_int(workflow_run.id),
        "branch_name": delivery_contract.get("branch_name"),
        "validation_checks": _validation_check_statuses(db, _as_int(requirement.id)),
        "vcs_delivery": vcs_payload,
        "compare_url": compare_url,
        "pr_metadata": _build_delivery_pr_metadata(
            requirement,
            {
                "branch_name": delivery_contract.get("branch_name"),
                "base_branch": delivery_contract.get("base_branch"),
                "review_surface_summary": _delivery_review_surface_summary(requirement, db),
                "vcs_status": vcs_payload.get("status"),
                "vcs_remote_name": vcs_payload.get("remote_name"),
                "vcs_repositories": vcs_payload.get("repositories") or [],
            },
            compare_url,
        ),
        "review_pr": pr_payload,
        "promotion_checklist": _build_promotion_checklist(
            {
                "review_status": "review_ready",
                "release_mode": delivery_contract.get("release_mode"),
                "pending_checks": required_checks if publish_status != "published" else [],
                "publish_blockers": [],
                "vcs_status": vcs_payload.get("status"),
            },
            compare_url,
        ),
        "generated_at": utcnow().isoformat(),
    }
    review_surface = _create_artifact(
        db,
        requirement_id=requirement.id,
        workflow_run_id=workflow_run.id,
        artifact_type="review_surface",
        content_summary=f"Review-ready bundle for requirement #{requirement.id}",
        human_readable_body=_delivery_review_surface_summary(requirement, db),
        machine_readable_payload=review_surface_payload,
    )
    _record_delivery_state(
        db,
        requirement,
        workflow_run,
        review_status="review_ready",
        publish_status=publish_status,
        confirmed_checks=required_checks if publish_status == "published" else [],
        publish_note="auto-published by release gate" if publish_status == "published" else None,
        vcs_payload=vcs_payload,
        pr_payload=pr_payload,
    )
    if publish_status == "published":
        _create_artifact(
            db,
            requirement_id=requirement.id,
            workflow_run_id=workflow_run.id,
            artifact_type="publish_record",
            content_summary=f"Auto-published requirement #{requirement.id}",
            human_readable_body=_publish_record_markdown(
                requirement,
                delivery_contract,
                required_checks,
                "auto-published by release gate",
            ),
            machine_readable_payload={
                "requirement_id": _as_int(requirement.id),
                "workflow_run_id": _as_int(workflow_run.id),
                "branch_name": delivery_contract.get("branch_name"),
                "base_branch": delivery_contract.get("base_branch"),
                "release_mode": delivery_contract.get("release_mode"),
                "completed_checks": required_checks,
                "publish_note": "auto-published by release gate",
                "published_at": utcnow().isoformat(),
                "review_surface_artifact_id": _as_int(review_surface.id),
                "promoted_commit_sha": str(pr_payload.get("latest_remote_sha") or vcs_payload.get("latest_remote_sha") or "") or None,
            },
        )
    _refresh_dependents_for_requirement(db, requirement.id)
    _clear_role_sessions()
    # Async push full requirement summary to Agents-Memory
    steps = db.query(WorkflowStepRow).filter(
        WorkflowStepRow.workflow_run_id == workflow_run.id
    ).order_by(WorkflowStepRow.sequence_no.asc(), WorkflowStepRow.id.asc()).all()
    steps_summary = [
        {
            "title": s.title,
            "role": s.assigned_workflow_role or "",
            "status": s.status,
            "execution_time_ms": None,
        }
        for s in steps
    ]
    output_summary = artifact.human_readable_body if artifact else ""
    changed_files_json = _json_loads(getattr(artifact, "machine_readable_payload", None) or "{}", {})
    changed_files = list(changed_files_json.get("changed_files", []))
    _am_push_requirement_completed(requirement, steps_summary, output_summary or "", changed_files)
    # After completing, advance the queue so the next ready requirement starts automatically
    preferred_project_key, preferred_root_path = _queue_preference_for_requirement(db, requirement)
    _schedule_advance_queue_compat(
        preferred_project_key=preferred_project_key,
        preferred_root_path=preferred_root_path,
    )


def _schedule_advance_queue(
    *,
    preferred_project_key: str | None = None,
    preferred_root_path: str | None = None,
) -> None:
    """Fire-and-forget: pick the next queued ready requirement and start it."""
    def _run() -> None:
        db = SessionLocal()
        try:
            advance_requirement_queue(
                db,
                preferred_project_key=preferred_project_key,
                preferred_root_path=preferred_root_path,
            )
        except Exception:
            _logger.debug("Queue advance failed (non-critical)", exc_info=True)
        finally:
            db.close()
    threading.Thread(target=_run, daemon=True).start()


def _schedule_advance_queue_compat(
    *,
    preferred_project_key: str | None = None,
    preferred_root_path: str | None = None,
) -> None:
    try:
        _schedule_advance_queue(
            preferred_project_key=preferred_project_key,
            preferred_root_path=preferred_root_path,
        )
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        _schedule_advance_queue()


def _queue_preference_for_requirement(db: Session, requirement: RequirementRow) -> tuple[str | None, str | None]:
    target_paths = [
        item.strip()
        for item in str(_normalize_target_project_path(requirement.target_project_path) or "").splitlines()
        if item.strip()
    ]
    preferred_root_path = target_paths[0] if target_paths else None
    preferred_project_key = None
    if preferred_root_path:
        policies = resolve_project_policies_for_target(db, preferred_root_path, require_active=False)
        if policies:
            preferred_project_key = str(project_policy_to_dict(policies[0]).get("project_key") or "").strip() or None
    return preferred_project_key, preferred_root_path


def advance_requirement_queue(
    db: Session,
    *,
    preferred_project_key: str | None = None,
    preferred_root_path: str | None = None,
) -> dict:
    """Run the portfolio scheduler and start every candidate that fits the current window."""
    from server.services.portfolio_scheduler import execute_portfolio_schedule

    result = execute_portfolio_schedule(
        db,
        allow_intake=False,
        preferred_project_key=preferred_project_key,
        preferred_root_path=preferred_root_path,
    )
    started_ids = list(result.get("started_ids") or [])
    skip_reasons = list(result.get("skipped") or [])

    if started_ids:
        result["started"] = started_ids[0]
        result["skipped_reasons"] = skip_reasons
        _logger.info(
            "event=requirement_queue_advanced started=%s created_requirements=%s rebalanced=%s preempted=%s skipped=%s",
            len(started_ids),
            len(result.get("created_requirement_ids") or []),
            len(result.get("rebalanced_ids") or []),
            len(result.get("preempted_ids") or []),
            len(skip_reasons),
        )
        return result

    delay_decision = next(
        (
            decision
            for decision in result.get("decisions") or []
            if str(decision.get("action") or "") in {"delay", "preempt_candidate"}
        ),
        None,
    )
    if skip_reasons:
        result["skipped"] = skip_reasons[0]
    elif delay_decision:
        result["skipped"] = str(delay_decision.get("reason") or "no schedulable work")
    else:
        result["skipped"] = "no ready requirements"
    result["skipped_reasons"] = skip_reasons
    _logger.info(
        "event=requirement_queue_idle started=0 created_requirements=%s rebalanced=%s preempted=%s skipped=%s reason=%s",
        len(result.get("created_requirement_ids") or []),
        len(result.get("rebalanced_ids") or []),
        len(result.get("preempted_ids") or []),
        len(skip_reasons),
        result.get("skipped"),
    )
    return result


def _create_requirement_revision_request(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    failed_step: WorkflowStepRow,
    revision_artifact: ArtifactRow,
    error_text: str,
):
    db.add(
        ApprovalRequestRow(
            requirement_id=requirement.id,
            workflow_run_id=workflow_run.id,
            step_id=failed_step.id,
            approval_type="requirement_revision_approval",
            status="pending",
            reviewer="requirement_editor",
            comment=error_text,
        )
    )
    for step in db.query(WorkflowStepRow).filter(WorkflowStepRow.workflow_run_id == workflow_run.id).all():
        if step.id == failed_step.id or step.status in TERMINAL_STEP_STATUSES:
            continue
        step.status = "cancelled"
        step.completed_at = step.completed_at or utcnow()
    workflow_run.status = "cancelled"
    workflow_run.completed_at = utcnow()
    requirement.active_workflow_run_id = None
    requirement.status = "needs_revision"
    revision_artifact.artifact_type = "requirement_revision"
    _clear_role_sessions()


def _resolve_failure_route(step: WorkflowStepRow, error_text: str) -> str:
    lowered = error_text.lower()
    if any(marker in lowered for marker in [
        "requirement_revision",
        "needs revision",
        "ambiguous requirement",
        "ambiguous spec",
        "unclear acceptance",
        "requirement issue",
    ]):
        return "requirement_revision"
    policy = _json_loads(step.failure_policy_json, {})
    return str((policy or {}).get("on_failure") or "bugfix")


def _replace_dependencies(db: Session, requirement_id: int, dependency_ids: list[int]):
    normalized = []
    seen: set[int] = set()
    for dep_id in dependency_ids:
        dep_int = int(dep_id)
        if dep_int == requirement_id:
            raise ValueError("Requirement cannot depend on itself.")
        if dep_int in seen:
            continue
        dependency = db.query(RequirementRow).filter(RequirementRow.id == dep_int).first()
        if dependency is None:
            raise ValueError(f"Dependency requirement #{dep_int} not found.")
        if dependency.status == "deleted":
            raise ValueError(f"Dependency requirement #{dep_int} has been deleted.")
        if _dependency_creates_cycle(db, requirement_id, dep_int):
            raise ValueError(f"Dependency on requirement #{dep_int} would create a cycle.")
        seen.add(dep_int)
        normalized.append(dep_int)

    existing = db.query(RequirementDependencyRow).filter(
        RequirementDependencyRow.requirement_id == requirement_id
    ).all()
    existing_ids = {row.depends_on_requirement_id for row in existing}
    for row in existing:
        if row.depends_on_requirement_id not in seen:
            db.delete(row)
    for dep_id in normalized:
        if dep_id in existing_ids:
            continue
        db.add(
            RequirementDependencyRow(
                requirement_id=requirement_id,
                depends_on_requirement_id=dep_id,
                dependency_type="hard_block",
            )
        )
    db.flush()


def _dependency_creates_cycle(db: Session, requirement_id: int, dependency_id: int) -> bool:
    pending = [dependency_id]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if current == requirement_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        children = db.query(RequirementDependencyRow).filter(
            RequirementDependencyRow.requirement_id == current
        ).all()
        pending.extend(dep.depends_on_requirement_id for dep in children)
    return False


def _refresh_requirement_dependency_state(db: Session, requirement: RequirementRow):
    if requirement.status == "deleted":
        return
    dependency_rows = db.query(RequirementDependencyRow).filter(
        RequirementDependencyRow.requirement_id == requirement.id
    ).all()
    if not dependency_rows:
        requirement.blocked_by_count = 0
        if requirement.active_workflow_run_id is None and requirement.status in {"draft", "blocked", "ready"}:
            requirement.status = "ready"
        return

    dependency_ids = [row.depends_on_requirement_id for row in dependency_rows]
    finished = {
        row.id
        for row in db.query(RequirementRow).filter(RequirementRow.id.in_(dependency_ids)).all()
        if row.status == "done"
    }
    requirement.blocked_by_count = sum(1 for dep_id in dependency_ids if dep_id not in finished)
    if requirement.active_workflow_run_id is None:
        requirement.status = "blocked" if requirement.blocked_by_count > 0 else "ready"


def _refresh_dependents_for_requirement(db: Session, requirement_id: int):
    dependent_rows = db.query(RequirementDependencyRow).filter(
        RequirementDependencyRow.depends_on_requirement_id == requirement_id
    ).all()
    for dep in dependent_rows:
        dependent = db.query(RequirementRow).filter(RequirementRow.id == dep.requirement_id).first()
        if dependent is None or dependent.status in {"done", "deleted"}:
            continue
        _refresh_requirement_dependency_state(db, dependent)


def _soft_delete_requirement_tree(db: Session, requirement: RequirementRow, visited: set[int]) -> None:
    requirement_id = _as_int(requirement.id)
    if requirement_id in visited:
        return
    visited.add(requirement_id)

    deleted_at = utcnow()

    workflow_runs = db.query(WorkflowRunRow).filter(
        WorkflowRunRow.requirement_id == requirement_id
    ).all()
    for workflow_run in workflow_runs:
        steps = db.query(WorkflowStepRow).filter(
            WorkflowStepRow.workflow_run_id == workflow_run.id
        ).all()
        for step in steps:
            task = None
            if step.compatibility_task_id:
                task = db.query(TaskRow).filter(TaskRow.id == step.compatibility_task_id).first()
            if task is not None and str(task.status) not in DELETED_TASK_STATUSES:
                if str(task.status) == "running":
                    _terminate_task_runtime(task)
                cast(Any, task).status = "deleted"
                cast(Any, task).last_error_message = "Requirement deleted"
                cast(Any, task).completed_at = cast(Any, task).completed_at or deleted_at
                db.add(TaskLogRow(task_id=task.id, event_type="deleted", detail=f"Requirement #{requirement_id} deleted"))
            if step.status not in DELETED_STEP_STATUSES:
                step.status = "deleted"
                step.completed_at = step.completed_at or deleted_at
                _record_step_event(db, step.id, "status_change", "deleted (requirement removed)")
        workflow_run.status = "deleted"
        workflow_run.completed_at = workflow_run.completed_at or deleted_at

    for approval in db.query(ApprovalRequestRow).filter(
        ApprovalRequestRow.requirement_id == requirement_id
    ).all():
        if approval.status == "deleted":
            continue
        approval.status = "deleted"
        approval.reviewer = approval.reviewer or "system"
        approval.decided_at = approval.decided_at or deleted_at
        approval.comment = approval.comment or "Requirement deleted"

    for check in db.query(RequirementAcceptanceCheckRow).filter(
        RequirementAcceptanceCheckRow.requirement_id == requirement_id
    ).all():
        check.status = "deleted"
        check.updated_at = deleted_at

    requirement.status = "deleted"
    requirement.completed_at = requirement.completed_at or deleted_at
    requirement.started_at = None
    requirement.blocked_by_count = 0

    dependent_rows = db.query(RequirementDependencyRow).filter(
        RequirementDependencyRow.depends_on_requirement_id == requirement_id
    ).all()
    for dep in dependent_rows:
        dependent = db.query(RequirementRow).filter(RequirementRow.id == dep.requirement_id).first()
        if dependent is None:
            continue
        _soft_delete_requirement_tree(db, dependent, visited)

    _clear_role_sessions()


def _create_artifact(
    db: Session,
    *,
    requirement_id: int,
    artifact_type: str,
    workflow_run_id: int | None = None,
    step_id: int | None = None,
    producer_step_id: int | None = None,
    path: str | None = None,
    content_summary: str | None = None,
    human_readable_body: str | None = None,
    machine_readable_payload: dict | list | str | None = None,
) -> ArtifactRow:
    payload_text = _json_dumps(machine_readable_payload) if machine_readable_payload is not None else None
    checksum = hashlib.sha1((payload_text or human_readable_body or content_summary or "").encode("utf-8")).hexdigest()
    artifact = ArtifactRow(
        requirement_id=requirement_id,
        workflow_run_id=workflow_run_id,
        step_id=step_id,
        producer_step_id=producer_step_id,
        artifact_type=artifact_type,
        path=path,
        content_summary=content_summary,
        human_readable_body=human_readable_body,
        machine_readable_payload=payload_text,
        checksum=checksum,
    )
    db.add(artifact)
    db.flush()
    return artifact


def _latest_artifact(
    db: Session,
    requirement_id: int,
    artifact_type: str,
    *,
    workflow_run_id: int | None = None,
) -> ArtifactRow | None:
    query = db.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == artifact_type,
    )
    if workflow_run_id is not None:
        query = query.filter(ArtifactRow.workflow_run_id == workflow_run_id)
    return query.order_by(ArtifactRow.id.desc()).first()


def _validation_plan_payload(db: Session, requirement_id: int) -> dict[str, Any]:
    artifact = _latest_artifact(db, requirement_id, "validation_plan")
    payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
    return payload if isinstance(payload, dict) else {}


def _validation_plan_check_specs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    combined = payload.get("validation_checks") or []
    if isinstance(combined, list) and combined:
        return [entry for entry in combined if isinstance(entry, dict)]
    checks: list[dict[str, Any]] = []
    for group_name in ("manual_checks", "automated_checks"):
        entries = payload.get(group_name) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict):
                checks.append(entry)
    return checks


def _validation_plan_markdown(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""

    lines = ["# Validation Contract"]
    summary = str(payload.get("summary_markdown") or "").strip()
    if summary:
        lines.extend(["", summary])

    gates = [str(item) for item in payload.get("gates") or [] if str(item).strip()]
    if gates:
        lines.extend(["", "## Close Gate", *[f"- `{gate}` must pass before closeout." for gate in gates]])

    validation_checks = _validation_plan_check_specs(payload)
    if validation_checks:
        lines.extend(["", "## Validation Checks"])
        for check in validation_checks:
            lines.append(
                f"- `{check.get('check_key', '')}` via `{check.get('method', 'agent_validation')}` "
                f"owned by `{check.get('owner_role', 'tester')}`."
            )

    affected_projects = payload.get("affected_projects") or []
    if isinstance(affected_projects, list) and affected_projects:
        lines.extend(["", "## Affected Projects"])
        for item in affected_projects:
            if not isinstance(item, dict):
                continue
            display = str(item.get("display_name") or item.get("project_key") or item.get("root_path") or "").strip()
            if not display:
                continue
            checks = [str(check) for check in item.get("required_checks") or [] if str(check).strip()]
            changed_file_count = int(item.get("changed_file_count") or 0)
            lines.append(f"- `{display}` changed files: `{changed_file_count}`")
            if checks:
                lines.append(f"  Required checks: {', '.join(f'`{check}`' for check in checks)}")

    dynamic_required_checks = [str(item) for item in payload.get("dynamic_required_checks") or [] if str(item).strip()]
    if dynamic_required_checks:
        lines.extend(["", "## Dynamic Required Checks", *[f"- `{item}`" for item in dynamic_required_checks]])

    bugfix_owner = str(payload.get("bugfix_owner_role") or "").strip()
    closeout_owner = str(payload.get("closeout_owner_role") or "").strip()
    if bugfix_owner or closeout_owner:
        lines.extend(["", "## Ownership"])
        if bugfix_owner:
            lines.append(f"- Bugfix owner: `{bugfix_owner}`")
        if closeout_owner:
            lines.append(f"- Closeout owner: `{closeout_owner}`")

    bugfix_loop = payload.get("bugfix_loop") or {}
    if isinstance(bugfix_loop, dict):
        loop_summary = str(bugfix_loop.get("summary_markdown") or "").strip()
        if loop_summary:
            lines.extend(["", "## Bugfix Loop", loop_summary])

    return "\n".join(lines)


def _validation_check_statuses(db: Session, requirement_id: int) -> list[dict[str, Any]]:
    checks = db.query(RequirementAcceptanceCheckRow).filter(
        RequirementAcceptanceCheckRow.requirement_id == requirement_id
    ).order_by(RequirementAcceptanceCheckRow.id.asc()).all()
    return [
        {
            "check_key": str(check.check_key),
            "description": str(check.description),
            "check_type": str(check.check_type),
            "owner_role": str(check.owner_role),
            "status": str(check.status),
            "verified_by_step_id": cast(Any, check).verified_by_step_id,
            "evidence_artifact_id": cast(Any, check).evidence_artifact_id,
        }
        for check in checks
    ]


def _validation_gate_errors(db: Session, requirement_id: int) -> list[str]:
    payload = _validation_plan_payload(db, requirement_id)
    if not payload:
        return ["validation_plan artifact is missing"]

    contract_checks = _validation_plan_check_specs(payload)
    if not contract_checks:
        return ["validation contract declares no blocking checks"]

    checks_by_key = {
        str(check.check_key): check
        for check in db.query(RequirementAcceptanceCheckRow).filter(
            RequirementAcceptanceCheckRow.requirement_id == requirement_id
        ).all()
    }
    errors: list[str] = []
    for spec in contract_checks:
        check_key = str(spec.get("check_key") or "").strip()
        if not check_key:
            continue
        check = checks_by_key.get(check_key)
        if check is None:
            errors.append(f"missing acceptance check `{check_key}`")
            continue
        if check.status != "passed":
            errors.append(f"check `{check_key}` is {check.status}")
    return errors


def _manual_closeout_markdown(requirement: RequirementRow, db: Session) -> str:
    lines = [
        "# Closeout",
        "",
        f"Requirement {requirement.title} has satisfied the validation contract and is ready to close.",
    ]
    for check in _validation_check_statuses(db, _as_int(requirement.id)):
        lines.append(f"- `{check['check_key']}` ({check['owner_role']}) -> `{check['status']}`")
    return "\n".join(lines)


def _manual_closeout_payload(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow | None,
) -> dict[str, Any]:
    return {
        "requirement_id": _as_int(requirement.id),
        "workflow_run_id": _as_int(workflow_run.id) if workflow_run is not None else None,
        "status": "completed",
        "validation_contract": _validation_plan_payload(db, _as_int(requirement.id)),
        "check_statuses": _validation_check_statuses(db, _as_int(requirement.id)),
        "closed_at": utcnow().isoformat(),
    }


def _build_bug_report_payload(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow | None,
    step: WorkflowStepRow,
    task: TaskRow,
    error_text: str,
) -> dict[str, Any]:
    validation_plan = _validation_plan_payload(db, _as_int(requirement.id))
    root_failure_step_id = _root_failure_step_id(db, step)
    error_fingerprint = _error_fingerprint(error_text)
    validation_targets = [
        item
        for item in _json_loads(step.validation_targets_json, [])
        if isinstance(item, dict)
    ]
    checks_by_key = {
        str(check.check_key): check
        for check in db.query(RequirementAcceptanceCheckRow).filter(
            RequirementAcceptanceCheckRow.requirement_id == requirement.id
        ).all()
    }
    failed_checks: list[dict[str, Any]] = []
    for target in validation_targets:
        check_key = str(target.get("check_key") or "").strip()
        if not check_key:
            continue
        check = checks_by_key.get(check_key)
        failed_checks.append(
            {
                "check_key": check_key,
                "method": str(target.get("method") or ""),
                "step_type": str(step.step_type),
                "owner_role": str(getattr(check, "owner_role", "") or ""),
                "check_type": str(getattr(check, "check_type", "") or ""),
                "status": str(getattr(check, "status", "pending") or "pending"),
            }
        )

    verification_type = "automated"
    if str(step.step_type or "") == "review":
        verification_type = "manual"
    elif str(step.step_type or "") == "validate":
        methods = {str(item.get("method") or "").strip() for item in validation_targets}
        automated_methods = {"agent_validation", "content_assertion", "repo_file_changes", "closeout_gate"}
        verification_type = "automated" if methods & automated_methods else "manual"

    return {
        "requirement_id": _as_int(requirement.id),
        "requirement_title": str(requirement.title),
        "workflow_run_id": _as_int(workflow_run.id) if workflow_run is not None else None,
        "task_id": _as_int(task.id),
        "step_id": _as_int(step.id),
        "step_key": str(step.step_key),
        "step_type": str(step.step_type),
        "verification_type": verification_type,
        "bugfix_owner_role": str(validation_plan.get("bugfix_owner_role") or "implementer"),
        "root_failure_step_id": root_failure_step_id,
        "bugfix_depth": _bugfix_branch_depth(db, _as_int(workflow_run.id), step) if workflow_run is not None else 0,
        "error_fingerprint": error_fingerprint,
        "target_project_path": _effective_target_project_path(db, requirement, step_type=str(step.step_type or "")),
        "validation_targets": validation_targets,
        "failed_checks": failed_checks,
        "error": error_text,
        "status": str(task.status),
        "recorded_at": utcnow().isoformat(),
    }


def _delivery_contract_payload(db: Session, requirement_id: int) -> dict[str, Any]:
    artifact = _latest_artifact(db, requirement_id, "delivery_contract")
    payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
    return payload if isinstance(payload, dict) else {}


def _delivery_contract_markdown(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""
    lines = ["# Delivery Contract"]
    summary = str(payload.get("summary_markdown") or "").strip()
    if summary:
        lines.extend(["", summary])
    branch_name = str(payload.get("branch_name") or "").strip()
    base_branch = str(payload.get("base_branch") or "").strip()
    branch_strategy = str(payload.get("branch_strategy") or "").strip()
    if branch_name or base_branch or branch_strategy:
        lines.extend(["", "## Branch"])
        if branch_name:
            lines.append(f"- Branch: `{branch_name}`")
        if base_branch:
            lines.append(f"- Base branch: `{base_branch}`")
        if branch_strategy:
            lines.append(f"- Strategy: `{branch_strategy}`")
    release_mode = str(payload.get("release_mode") or "").strip()
    if release_mode:
        lines.extend(["", "## Promotion"])
        lines.append(f"- Release mode: `{release_mode}`")
        lines.append(
            f"- Manual approval: {'yes' if payload.get('requires_manual_approval') else 'no'}"
        )
    capability_matrix = payload.get("capability_matrix") or {}
    if isinstance(capability_matrix, dict) and capability_matrix:
        lines.extend(["", "## Capability Matrix"])
        for key, value in capability_matrix.items():
            lines.append(f"- {key}: {'enabled' if value else 'disabled'}")
    interrupt_policy = payload.get("interrupt_policy") or {}
    if isinstance(interrupt_policy, dict) and interrupt_policy:
        lines.extend(["", "## Interrupt Policy"])
        lines.append(
            "- Operator confirmation actions: "
            + (", ".join(str(item) for item in interrupt_policy.get("operator_confirmation_actions") or [] if str(item).strip()) or "none")
        )
        lines.append(
            "- Auto-pause on: "
            + (", ".join(str(item) for item in interrupt_policy.get("auto_pause_on_events") or [] if str(item).strip()) or "none")
        )
        lines.append(
            "- Auto-abort on: "
            + (", ".join(str(item) for item in interrupt_policy.get("auto_abort_on_events") or [] if str(item).strip()) or "none")
        )
    required_checks = [str(item) for item in payload.get("required_checks") or [] if str(item).strip()]
    if required_checks:
        lines.extend(["", "## Required Checks", *[f"- `{item}`" for item in required_checks]])
    affected_projects = payload.get("affected_projects") or []
    if isinstance(affected_projects, list) and affected_projects:
        lines.extend(["", "## Validation Scope"])
        for item in affected_projects:
            if not isinstance(item, dict):
                continue
            display = str(item.get("display_name") or item.get("project_key") or item.get("root_path") or "").strip()
            if not display:
                continue
            changed_file_count = int(item.get("changed_file_count") or 0)
            checks = [str(check) for check in item.get("required_checks") or [] if str(check).strip()]
            lines.append(f"- `{display}` changed files: `{changed_file_count}`")
            if checks:
                lines.append(f"  Checks: {', '.join(f'`{check}`' for check in checks)}")
    rollback_hint = str(payload.get("rollback_hint_markdown") or "").strip()
    if rollback_hint:
        lines.extend(["", "## Rollback", rollback_hint])
    return "\n".join(lines)


def _latest_vcs_delivery_payload(
    db: Session,
    requirement_id: int,
    *,
    workflow_run_id: int | None = None,
) -> dict[str, Any]:
    artifact = _latest_artifact(db, requirement_id, "vcs_delivery", workflow_run_id=workflow_run_id)
    payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
    return payload if isinstance(payload, dict) else {}


def _latest_review_pr_payload(
    db: Session,
    requirement_id: int,
    *,
    workflow_run_id: int | None = None,
) -> dict[str, Any]:
    artifact = _latest_artifact(db, requirement_id, "review_pr_sync", workflow_run_id=workflow_run_id)
    payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
    return payload if isinstance(payload, dict) else {}


def _vcs_delivery_markdown(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""
    lines = ["# VCS Delivery", ""]
    lines.append(f"- Status: `{payload.get('status', 'unknown')}`")
    if payload.get("branch_name"):
        lines.append(f"- Branch: `{payload.get('branch_name')}`")
    if payload.get("base_branch"):
        lines.append(f"- Base branch: `{payload.get('base_branch')}`")
    if payload.get("remote_name"):
        lines.append(f"- Remote: `{payload.get('remote_name')}`")
    blockers = payload.get("blockers") or []
    if isinstance(blockers, list) and blockers:
        lines.extend(["", "## Delivery Blockers", *[f"- {item}" for item in blockers]])
    repositories = payload.get("repositories") or []
    if isinstance(repositories, list) and repositories:
        lines.extend(["", "## Repository Results"])
        for item in repositories:
            if not isinstance(item, dict):
                continue
            repo_path = str(item.get("repo_path") or "").strip() or "-"
            status = str(item.get("status") or "unknown")
            lines.append(f"- `{repo_path}` -> `{status}`")
            commit_sha = str(item.get("commit_sha") or "").strip()
            remote_sha = str(item.get("remote_sha") or "").strip()
            if commit_sha:
                lines.append(f"  Commit: `{commit_sha[:12]}`")
            if remote_sha:
                lines.append(f"  Remote: `{remote_sha[:12]}`")
            repo_blockers = item.get("blockers") or []
            if isinstance(repo_blockers, list):
                for blocker in repo_blockers:
                    lines.append(f"  Blocker: {blocker}")
    return "\n".join(lines)


def _record_vcs_delivery_artifact(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow | None,
    step: WorkflowStepRow | None,
    payload: dict[str, Any],
) -> ArtifactRow:
    status = str(payload.get("status") or "unknown")
    return _create_or_update_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
        step_id=_as_int(step.id) if step is not None else None,
        producer_step_id=_as_int(step.id) if step is not None else None,
        artifact_type="vcs_delivery",
        content_summary=f"VCS delivery {status} for requirement #{requirement.id}",
        human_readable_body=_vcs_delivery_markdown(payload),
        machine_readable_payload=payload,
    )


def _review_pr_sync_markdown(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""
    lines = ["# Review PR Sync", ""]
    lines.append(f"- Status: `{payload.get('pr_status') or payload.get('status') or 'missing'}`")
    pr_url = str(payload.get("pr_url") or "").strip()
    if pr_url:
        lines.append(f"- PR: {pr_url}")
    branch_name = str(payload.get("head_branch") or payload.get("branch_name") or "").strip()
    if branch_name:
        lines.append(f"- Head branch: `{branch_name}`")
    base_branch = str(payload.get("base_branch") or "").strip()
    if base_branch:
        lines.append(f"- Base branch: `{base_branch}`")
    latest_remote_sha = str(payload.get("latest_remote_sha") or "").strip()
    if latest_remote_sha:
        lines.append(f"- Latest remote SHA: `{latest_remote_sha[:12]}`")
    compare_url = str(payload.get("compare_url") or "").strip()
    if compare_url:
        lines.append(f"- Compare URL: {compare_url}")
    blockers = payload.get("blockers") or []
    if isinstance(blockers, list) and blockers:
        lines.extend(["", "## PR Sync Blockers", *[f"- {item}" for item in blockers]])
    return "\n".join(lines)


def _record_review_pr_sync_artifact(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow | None,
    step: WorkflowStepRow | None,
    payload: dict[str, Any],
) -> ArtifactRow:
    status = str(payload.get("pr_status") or payload.get("status") or "missing")
    return _create_or_update_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
        step_id=_as_int(step.id) if step is not None else None,
        producer_step_id=_as_int(step.id) if step is not None else None,
        artifact_type="review_pr_sync",
        content_summary=f"Review PR {status} for requirement #{requirement.id}",
        human_readable_body=_review_pr_sync_markdown(payload),
        machine_readable_payload=payload,
    )


def _sync_requirement_review_pr(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow | None,
    step: WorkflowStepRow | None,
    *,
    delivery_contract: dict[str, Any] | None = None,
    vcs_payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ArtifactRow | None]:
    contract = delivery_contract if isinstance(delivery_contract, dict) else _delivery_contract_payload(db, _as_int(requirement.id))
    effective_vcs = vcs_payload if isinstance(vcs_payload, dict) else _latest_vcs_delivery_payload(
        db,
        _as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
    )
    branch_name = str(contract.get("branch_name") or "").strip()
    base_branch = str(contract.get("base_branch") or "main").strip() or "main"
    compare_url = _build_delivery_compare_url(effective_vcs, branch_name or None, base_branch or None)
    payload = sync_requirement_review_pr(
        requirement_id=_as_int(requirement.id),
        requirement_title=str(requirement.title or ""),
        branch_name=branch_name,
        base_branch=base_branch,
        compare_url=compare_url,
        latest_commit_sha=_latest_delivery_sha(effective_vcs, "commit_sha") or str(effective_vcs.get("latest_commit_sha") or "").strip() or None,
        latest_remote_sha=_latest_delivery_sha(effective_vcs, "remote_sha") or str(effective_vcs.get("latest_remote_sha") or "").strip() or None,
        last_pushed_at=_latest_delivery_timestamp(effective_vcs, "last_pushed_at") or str(effective_vcs.get("last_pushed_at") or "").strip() or None,
        review_surface_summary=_delivery_review_surface_summary(
            requirement,
            db,
            workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
        ),
        promotion_checklist=_build_promotion_checklist(
            {
                "review_status": "review_ready" if requirement.status == "done" else "planned",
                "release_mode": contract.get("release_mode"),
                "pending_checks": [str(item) for item in contract.get("required_checks") or [] if str(item).strip()],
                "publish_blockers": [],
                "vcs_status": effective_vcs.get("status"),
            },
            compare_url,
        ),
        vcs_payload=effective_vcs,
    )
    artifact = _record_review_pr_sync_artifact(db, requirement, workflow_run, step, payload)
    return payload, artifact


def _execute_requirement_vcs_delivery(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow | None,
    step: WorkflowStepRow | None,
) -> tuple[dict[str, Any], ArtifactRow | None]:
    contract = _delivery_contract_payload(db, _as_int(requirement.id))
    if not contract:
        return {}, None
    payload = execute_requirement_delivery_vcs(
        requirement_id=_as_int(requirement.id),
        requirement_title=str(requirement.title),
        delivery_contract=contract,
        fallback_target_path=_effective_target_project_path(
            db,
            requirement,
            step_type=str(getattr(step, "step_type", "") or "closeout"),
        ),
    )
    artifact = _record_vcs_delivery_artifact(db, requirement, workflow_run, step, payload)
    return payload, artifact


def _delivery_review_surface_summary(requirement: RequirementRow, db: Session, *, workflow_run_id: int | None = None) -> str:
    check_lines = [
        f"`{check['check_key']}`={check['status']}"
        for check in _validation_check_statuses(db, _as_int(requirement.id))
    ]
    summary = (
        f"Requirement #{requirement.id} is review-ready for `{requirement.title}`. "
        f"Validation: {', '.join(check_lines) if check_lines else 'no checks recorded'}."
    )
    vcs_payload = _latest_vcs_delivery_payload(db, _as_int(requirement.id), workflow_run_id=workflow_run_id)
    repositories = vcs_payload.get("repositories") or []
    delivered = [item for item in repositories if isinstance(item, dict) and str(item.get("status") or "") == "delivered"]
    if delivered:
        repos = ", ".join(str(item.get("repo_path") or "").strip() for item in delivered if str(item.get("repo_path") or "").strip())
        if repos:
            summary += f" Delivered branches pushed for: {repos}."
    return summary


def _delivery_state_payload(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow | None,
    *,
    review_status: str = "review_ready",
    publish_status: str,
    confirmed_checks: list[str] | None = None,
    publish_note: str | None = None,
    vcs_payload: dict[str, Any] | None = None,
    pr_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = _delivery_contract_payload(db, _as_int(requirement.id))
    effective_vcs_payload = vcs_payload if isinstance(vcs_payload, dict) else _latest_vcs_delivery_payload(
        db,
        _as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
    )
    effective_pr_payload = pr_payload if isinstance(pr_payload, dict) else _latest_review_pr_payload(
        db,
        _as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
    )
    required_checks = [str(item) for item in contract.get("required_checks") or [] if str(item).strip()]
    confirmed = [str(item) for item in (confirmed_checks or []) if str(item).strip()]
    pending = [check for check in required_checks if check not in confirmed]
    blockers: list[str] = []
    if str(contract.get("release_mode") or "manual") == "disabled":
        blockers.append("publish disabled by project policy")
    capability_matrix = contract.get("capability_matrix") or {}
    if bool(contract.get("commit_required")) and not bool(capability_matrix.get("git_write", True)):
        blockers.append("branch commit required but git_write is disabled by project policy")
    if bool(contract.get("push_required")) and not bool(capability_matrix.get("git_push")):
        blockers.append("branch push required but git_push is disabled by project policy")
    vcs_blockers = [
        str(item).strip()
        for item in (effective_vcs_payload.get("blockers") or [])
        if str(item).strip()
    ]
    blockers.extend(vcs_blockers)
    pr_blockers = [
        str(item).strip()
        for item in (effective_pr_payload.get("blockers") or [])
        if str(item).strip()
    ]
    blockers.extend(pr_blockers)
    pr_status = str(effective_pr_payload.get("pr_status") or "").strip()
    if str(effective_vcs_payload.get("status") or "").strip() == "delivered":
        if pr_status in {"", "missing"}:
            blockers.append("review PR missing")
        elif pr_status == "closed":
            blockers.append("review PR is closed")
    blockers.extend([f"required check pending: {check}" for check in pending])
    compare_url = _build_delivery_compare_url(
        effective_vcs_payload,
        str(contract.get("branch_name") or "") or None,
        str(contract.get("base_branch") or "") or None,
    )
    payload = {
        "branch_name": contract.get("branch_name"),
        "branch_strategy": contract.get("branch_strategy"),
        "base_branch": contract.get("base_branch"),
        "review_status": review_status,
        "publish_status": publish_status,
        "release_mode": contract.get("release_mode"),
        "requires_manual_approval": bool(contract.get("requires_manual_approval")),
        "required_checks": required_checks,
        "confirmed_checks": confirmed,
        "pending_checks": pending,
        "publish_blockers": blockers,
        "review_surface_summary": _delivery_review_surface_summary(
            requirement,
            db,
            workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
        ),
        "rollback_hint_markdown": contract.get("rollback_hint_markdown"),
        "review_ready_at": utcnow().isoformat() if review_status == "review_ready" else None,
        "published_at": utcnow().isoformat() if publish_status == "published" else None,
        "publish_note": publish_note,
        "workflow_run_id": _as_int(workflow_run.id) if workflow_run is not None else None,
        "vcs_status": str(effective_vcs_payload.get("status") or "") or None,
        "vcs_remote_name": str(effective_vcs_payload.get("remote_name") or "") or None,
        "vcs_repositories": effective_vcs_payload.get("repositories") or [],
        "compare_url": compare_url,
        "pr_status": str(effective_pr_payload.get("pr_status") or "") or None,
        "pr_number": int(effective_pr_payload.get("pr_number") or 0) or None,
        "pr_url": str(effective_pr_payload.get("pr_url") or "").strip() or None,
        "head_branch": str(effective_pr_payload.get("head_branch") or contract.get("branch_name") or "").strip() or None,
        "latest_commit_sha": str(effective_pr_payload.get("latest_commit_sha") or effective_vcs_payload.get("latest_commit_sha") or "").strip() or None,
        "latest_remote_sha": str(effective_pr_payload.get("latest_remote_sha") or effective_vcs_payload.get("latest_remote_sha") or "").strip() or None,
        "review_bundle_generated_at": str(effective_pr_payload.get("review_bundle_generated_at") or "").strip() or None,
        "last_pushed_at": str(effective_pr_payload.get("last_pushed_at") or effective_vcs_payload.get("last_pushed_at") or "").strip() or None,
    }
    payload["pr_metadata"] = (
        {
            **_build_delivery_pr_metadata(requirement, payload, compare_url),
            **(effective_pr_payload if isinstance(effective_pr_payload, dict) else {}),
        }
        if effective_pr_payload
        else _build_delivery_pr_metadata(requirement, payload, compare_url)
    )
    payload["promotion_checklist"] = _build_promotion_checklist(payload, compare_url)
    return payload


def _delivery_state_markdown(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""
    lines = ["# Delivery State", ""]
    summary = str(payload.get("review_surface_summary") or "").strip()
    if summary:
        lines.append(summary)
    lines.extend(
        [
            "",
            f"- Review status: `{payload.get('review_status', 'unplanned')}`",
            f"- Publish status: `{payload.get('publish_status', 'unplanned')}`",
            f"- Release mode: `{payload.get('release_mode', '-')}`",
        ]
    )
    vcs_status = str(payload.get("vcs_status") or "").strip()
    if vcs_status:
        lines.append(f"- VCS status: `{vcs_status}`")
    compare_url = str(payload.get("compare_url") or "").strip()
    if compare_url:
        lines.append(f"- Compare URL: {compare_url}")
    required_checks = payload.get("required_checks") or []
    if isinstance(required_checks, list) and required_checks:
        lines.extend(["", "## Required Checks", *[f"- `{item}`" for item in required_checks]])
    checklist = payload.get("promotion_checklist") or []
    if isinstance(checklist, list) and checklist:
        lines.extend(["", "## Promotion Checklist"])
        for item in checklist:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip() or "check"
            status = str(item.get("status") or "pending").strip()
            detail = str(item.get("detail") or "").strip()
            lines.append(f"- `{label}`: `{status}`" + (f" — {detail}" if detail else ""))
    blockers = payload.get("publish_blockers") or []
    if isinstance(blockers, list) and blockers:
        lines.extend(["", "## Publish Blockers", *[f"- {item}" for item in blockers]])
    rollback_hint = str(payload.get("rollback_hint_markdown") or "").strip()
    if rollback_hint:
        lines.extend(["", "## Rollback", rollback_hint])
    return "\n".join(lines)


def _record_delivery_state(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow | None,
    *,
    review_status: str = "review_ready",
    publish_status: str,
    confirmed_checks: list[str] | None = None,
    publish_note: str | None = None,
    vcs_payload: dict[str, Any] | None = None,
    pr_payload: dict[str, Any] | None = None,
) -> ArtifactRow:
    payload = _delivery_state_payload(
        db,
        requirement,
        workflow_run,
        review_status=review_status,
        publish_status=publish_status,
        confirmed_checks=confirmed_checks,
        publish_note=publish_note,
        vcs_payload=vcs_payload,
        pr_payload=pr_payload,
    )
    if review_status == "blocked":
        summary_label = "Delivery blocked"
    else:
        summary_label = "Published" if publish_status == "published" else "Review-ready"
    return _create_artifact(
        db,
        requirement_id=_as_int(requirement.id),
        workflow_run_id=_as_int(workflow_run.id) if workflow_run is not None else None,
        artifact_type="delivery_state",
        content_summary=f"{summary_label} delivery state for requirement #{requirement.id}",
        human_readable_body=_delivery_state_markdown(payload),
        machine_readable_payload=payload,
    )


def _publish_record_markdown(
    requirement: RequirementRow,
    contract: dict[str, Any],
    completed_checks: list[str],
    note: str,
) -> str:
    lines = [
        "# Publish Record",
        "",
        f"Requirement #{requirement.id} `{requirement.title}` was promoted for publish.",
        f"- Branch: `{contract.get('branch_name') or '-'}`",
        f"- Base branch: `{contract.get('base_branch') or '-'}`",
        f"- Release mode: `{contract.get('release_mode') or '-'}`",
    ]
    if completed_checks:
        lines.extend(["", "## Confirmed Checks", *[f"- `{item}`" for item in completed_checks]])
    if note.strip():
        lines.extend(["", "## Note", note.strip()])
    return "\n".join(lines)


def _build_delivery_state(db: Session, requirement: RequirementRow) -> DeliveryStateOut | None:
    contract = _delivery_contract_payload(db, _as_int(requirement.id))
    if not contract:
        return None
    latest_state = _latest_artifact(db, _as_int(requirement.id), "delivery_state")
    payload = _json_loads(getattr(latest_state, "machine_readable_payload", None), {})
    if not isinstance(payload, dict):
        payload = _delivery_state_payload(
            db,
            requirement,
            _active_workflow_run(db, requirement),
            publish_status="unplanned",
        )
        payload["review_status"] = "planned"
        payload["publish_status"] = "planned"
        payload["review_ready_at"] = None
    return DeliveryStateOut(
        branch_name=str(payload.get("branch_name") or contract.get("branch_name") or "") or None,
        branch_strategy=str(payload.get("branch_strategy") or contract.get("branch_strategy") or "") or None,
        base_branch=str(payload.get("base_branch") or contract.get("base_branch") or "") or None,
        review_status=str(payload.get("review_status") or "planned"),
        publish_status=str(payload.get("publish_status") or "planned"),
        release_mode=str(payload.get("release_mode") or contract.get("release_mode") or "manual"),
        requires_manual_approval=bool(payload.get("requires_manual_approval", contract.get("requires_manual_approval"))),
        required_checks=[str(item) for item in payload.get("required_checks") or contract.get("required_checks") or [] if str(item).strip()],
        confirmed_checks=[str(item) for item in payload.get("confirmed_checks") or [] if str(item).strip()],
        pending_checks=[str(item) for item in payload.get("pending_checks") or [] if str(item).strip()],
        publish_blockers=[str(item) for item in payload.get("publish_blockers") or [] if str(item).strip()],
        review_surface_summary=str(payload.get("review_surface_summary") or "") or None,
        rollback_hint_markdown=str(payload.get("rollback_hint_markdown") or contract.get("rollback_hint_markdown") or "") or None,
        review_ready_at=str(payload.get("review_ready_at") or "") or None,
        published_at=str(payload.get("published_at") or "") or None,
        publish_note=str(payload.get("publish_note") or "") or None,
        vcs_status=str(payload.get("vcs_status") or "") or None,
        vcs_remote_name=str(payload.get("vcs_remote_name") or "") or None,
        vcs_repositories=payload.get("vcs_repositories") or [],
        compare_url=str(payload.get("compare_url") or "") or None,
        pr_status=str(payload.get("pr_status") or "") or None,
        pr_number=int(payload.get("pr_number") or 0) or None,
        pr_url=str(payload.get("pr_url") or "") or None,
        head_branch=str(payload.get("head_branch") or "") or None,
        latest_commit_sha=str(payload.get("latest_commit_sha") or "") or None,
        latest_remote_sha=str(payload.get("latest_remote_sha") or "") or None,
        review_bundle_generated_at=str(payload.get("review_bundle_generated_at") or "") or None,
        last_pushed_at=str(payload.get("last_pushed_at") or "") or None,
        pr_metadata=payload.get("pr_metadata") if isinstance(payload.get("pr_metadata"), dict) else None,
        promotion_checklist=payload.get("promotion_checklist") if isinstance(payload.get("promotion_checklist"), list) else [],
    )


def _bind_artifact(db: Session, step_id: int, artifact_id: int, purpose: str, is_required: bool):
    existing = db.query(StepInputBindingRow).filter(
        StepInputBindingRow.step_id == step_id,
        StepInputBindingRow.artifact_id == artifact_id,
        StepInputBindingRow.purpose == purpose,
    ).first()
    if existing:
        return existing
    binding = StepInputBindingRow(step_id=step_id, artifact_id=artifact_id, purpose=purpose, is_required=is_required)
    db.add(binding)
    db.flush()
    return binding


def _load_full_persona(agent_id: str) -> dict:
    if not agent_id:
        return {"role": "unknown", "display_name": "Unknown", "goal": "", "body": ""}

    from server.config import PROJECT_ROOT

    persona_path = PROJECT_ROOT / "roles" / agent_id / "prompts" / "persona.md"
    if not persona_path.exists():
        return {"role": agent_id, "display_name": agent_id, "goal": "", "body": ""}

    text = persona_path.read_text(encoding="utf-8")
    metadata: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            metadata = yaml.safe_load(text[3:end]) or {}
            body = text[end + 3 :].strip()
    return {
        "role": metadata.get("role", agent_id),
        "id": metadata.get("role", agent_id),
        "display_name": metadata.get("display_name", agent_id),
        "goal": metadata.get("goal", ""),
        "skills": metadata.get("skills", []),
        "body": body,
    }


def _planner_markdown(planner_output: dict, assignments: WorkflowRoleAssignments) -> str:
    validation_summary_lines = [
        f"- {line}"
        for line in str((planner_output.get("validation_plan") or {}).get("summary_markdown") or "").splitlines()
        if line.strip()
    ]
    delivery_summary_lines = [
        f"- {line}"
        for line in str((planner_output.get("delivery_contract") or {}).get("summary_markdown") or "").splitlines()
        if line.strip()
    ]
    intelligence = planner_output.get("project_intelligence") or {}
    intelligence_summary = str(intelligence.get("summary_markdown") or "").strip()
    execution_controls = planner_output.get("execution_controls") or {}
    capability_matrix = execution_controls.get("capability_matrix") or {}
    capability_summary = ", ".join(
        f"{key}={'yes' if bool(capability_matrix.get(key)) else 'no'}"
        for key in ("shell_access", "git_read", "git_write", "git_push", "network_access", "publish")
        if key in capability_matrix
    )
    context_governance = planner_output.get("context_governance") or {}
    context_summary = str(context_governance.get("summary_markdown") or "").strip()
    model_routing = planner_output.get("model_routing") or {}
    routing_summary = str(model_routing.get("summary_markdown") or "").strip()
    return "\n".join(
        [
            f"# Plan\n",
            f"## Goal\n\n{planner_output.get('goal_summary', '')}",
            "## Role Assignments",
            f"- Researcher: {assignments.researcher_agent_id}",
            f"- Synthesizer: {assignments.synthesizer_agent_id}",
            f"- Implementer: {assignments.implementer_agent_id}",
            f"- Reviewer: {assignments.reviewer_agent_id}",
            f"- Tester: {assignments.tester_agent_id}",
            "## Project Intelligence",
            *( [f"- {line}" for line in intelligence_summary.splitlines() if line.strip()] or ["- No project routing intelligence was attached."] ),
            "## Capability Matrix",
            *( [f"- {capability_summary}"] if capability_summary else ["- No explicit capability matrix attached."] ),
            "## Context Governance",
            *( [f"- {line}" for line in context_summary.splitlines() if line.strip()] or ["- No explicit context governance attached."] ),
            "## Model Routing",
            *( [f"- {line}" for line in routing_summary.splitlines() if line.strip()] or ["- No model routing annotations attached."] ),
            "## Delivery Contract",
            *(delivery_summary_lines or ["- Delivery contract will be generated for branch/review-ready/publish/rollback."]),
            "## Validation Contract",
            *(validation_summary_lines or ["- Validation contract will be generated for review/test/closeout."]),
            "## Steps",
            *[
                (
                    f"- {step.get('step_key')}: {step.get('title')}"
                    f" [{step.get('complexity_tier') or (step.get('execution_profile') or {}).get('complexity_tier') or 'standard'}]"
                )
                for step in planner_output.get("workflow_steps", [])
            ],
        ]
    )


def _require_requirement(db: Session, requirement_id: int) -> RequirementRow:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found")
    normalized_target = _normalize_target_project_path(requirement.target_project_path)
    if normalized_target != requirement.target_project_path:
        requirement.target_project_path = normalized_target
    return requirement


def _ensure_requirement_not_deleted(requirement: RequirementRow) -> None:
    if requirement.status == "deleted":
        raise ValueError("Requirement has been deleted.")


def _active_workflow_run(db: Session, requirement: RequirementRow) -> WorkflowRunRow | None:
    return _reconcile_active_workflow_run(db, requirement)


def _all_checks_passed(db: Session, requirement_id: int) -> bool:
    return not _validation_gate_errors(db, requirement_id)


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _as_int(value: Any) -> int:
    return int(value)


def _fallback_agent_id(db: Session) -> str:
    rows = ensure_agents_loaded(db)
    agent = rows[0] if rows else None
    if agent is None:
        raise ValueError("No agents available")
    return str(agent.id)


def _secondary_agent_id(db: Session, exclude: set[str]) -> str:
    ensure_agents_loaded(db)
    for preferred_id in ["dev_rel", "cro_optimizer", "seo_strategist", "growth_lead", "content_writer", "launch_strategist"]:
        if preferred_id in exclude:
            continue
        agent = db.query(AgentRow).filter(AgentRow.id == preferred_id).first()
        if agent is not None:
            return str(agent.id)
    return _fallback_agent_id(db)
