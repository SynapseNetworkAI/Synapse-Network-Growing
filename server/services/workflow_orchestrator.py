"""Requirement-first workflow orchestration built on top of task runtime compatibility."""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import yaml
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
    RequirementPatch,
    RequirementPublishRequest,
    RequirementRevisionRequest,
    WorkflowRunOut,
    WorkflowStepOut,
)
from server.config import PROJECT_ROOT
from server.services.incidents import list_requirement_incidents
from server.services.copilot_sdk_state import (
    copilot_runtime_paths,
    load_runtime_state,
    parse_runtime_timestamp,
    save_runtime_state,
    task_output_dir,
)
from server.services.execution_resolver import suggest_task_execution
from server.services.project_policy import project_policy_summary_markdown, project_policy_to_dict, resolve_project_policies_for_target
from server.services.project_intelligence import resolve_requirement_routing, serialize_requirement
from server.services.task_metadata import task_metadata_for_agent
from server.services.workflow_planner import WorkflowRoleAssignments, build_planner_output


RUNNING_STEP_STATUSES = {"running", "waiting_approval"}
TERMINAL_STEP_STATUSES = {"completed", "failed", "cancelled"}
SCHEDULABLE_STEP_STATUSES = {"pending", "ready", "blocked"}
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

import logging as _logging
_logger = _logging.getLogger("ops-dashboard.workflow_orchestrator")


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


def _snapshot_file_changes(db: Session, task: TaskRow, requirement: RequirementRow, step: WorkflowStepRow | None = None) -> None:
    """Capture `git diff HEAD` across configured target projects and save to the task output dir."""
    try:
        target_paths = _split_target_project_paths(
            _effective_target_project_path(
                db,
                requirement,
                step_type=str(step.step_type or "") if step is not None else None,
            )
        )
        output_path = str(task.output_path) if task.output_path else None
        if not target_paths or not output_path:
            return
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

            repo_changed_files: list[dict[str, Any]] = []
            current: dict[str, Any] | None = None
            for line in diff_text.splitlines(keepends=True):
                if line.startswith("diff --git "):
                    if current:
                        repo_changed_files.append(current)
                    current = {
                        "filename": "",
                        "additions": 0,
                        "deletions": 0,
                        "patch": "",
                        "target_project_path": target_path,
                    }
                elif current is not None:
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
                repo_changed_files.append(current)
            repo_changed_files = [f for f in repo_changed_files if f["filename"]]
            changed_files.extend(repo_changed_files)
            project_snapshots.append(
                {
                    "target_project_path": target_path,
                    "changed_file_count": len(repo_changed_files),
                    "changed_files": repo_changed_files,
                    "project_policy_summary": project_policy_summary_markdown(db, target_path),
                }
            )

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
        }
        output_dir = Path(output_path).parent
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


def _record_project_change_summary_artifact(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
    task: TaskRow,
) -> ArtifactRow | None:
    payload = _load_task_file_changes(task)
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
        for check in policy.get("required_checks") or []:
            check_text = str(check).strip()
            if check_text and check_text not in required_checks:
                required_checks.append(check_text)
        affected_projects.append(
            {
                "project_key": str(policy.get("project_key") or ""),
                "display_name": str(policy.get("display_name") or ""),
                "root_path": root_path,
                "required_checks": [str(item) for item in policy.get("required_checks") or [] if str(item).strip()],
                "changed_file_count": int(changed_file_counts.get(root_path, 0) or 0),
            }
        )
    return {
        "changed_target_project_paths": changed_paths,
        "affected_projects": affected_projects,
        "required_checks": required_checks,
    }


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
    reportish = {"research_report", "synthesis_report", "validation_manifest", "review_surface"}
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


def _repo_file_changes_check_error(
    *,
    step: WorkflowStepRow,
    task: TaskRow | None,
    spec: dict[str, Any],
    artifact: ArtifactRow,
) -> str | None:
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
    requirement = RequirementRow(
        title=body.title,
        description_markdown=body.description_markdown,
        status="ready",
        priority=body.priority,
        source=body.source,
        source_ref=body.source_ref,
        target_project_path=_normalize_target_project_path(
            str(routing_context.get("target_project_path") or "") or requested_target
        ),
    )
    db.add(requirement)
    db.flush()
    _create_artifact(
        db,
        requirement_id=requirement.id,
        artifact_type="routing_decision",
        content_summary=f"Routing for requirement #{requirement.id}",
        human_readable_body=str(routing_context.get("summary") or "Requirement routing was assessed during intake."),
        machine_readable_payload=routing_context,
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
    _logger.info(
        "event=requirement_created requirement_id=%s source=%s priority=%s routing_mode=%s target_paths=%s auto_start=%s",
        requirement.id,
        requirement.source,
        requirement.priority,
        routing_context.get("routing_mode") or "unknown",
        len(str(requirement.target_project_path or "").splitlines()) if requirement.target_project_path else 0,
        body.auto_start,
    )
    if body.auto_start and requirement.blocked_by_count == 0:
        req_id = _as_int(requirement.id)

        def _bg_plan_and_start(req_id: int) -> None:
            bg_db = SessionLocal()
            try:
                plan_requirement(bg_db, req_id)
                start_requirement(bg_db, req_id)
            except Exception as exc:  # noqa: BLE001
                import logging
                logging.getLogger("ops-dashboard.orchestrator").warning(
                    "Background plan/start failed for req %s: %s", req_id, exc
                )
            finally:
                bg_db.close()

        threading.Thread(target=_bg_plan_and_start, args=(req_id,), daemon=True).start()

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
        return build_requirement_detail(db, requirement.id)

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
        _bind_artifact(db, step.id, plan_artifact.id, "implementation_context", True)
        _bind_artifact(db, step.id, delivery_contract_artifact.id, "delivery_contract", True)
        _bind_artifact(db, step.id, validation_plan_artifact.id, "validation_contract", True)

    requirement.current_plan_version = workflow_run.plan_version
    requirement.planned_roles_json = json.dumps(planner_output.get("required_roles", []))
    requirement.active_workflow_run_id = _as_int(workflow_run.id)
    requirement.status = "ready"
    db.commit()
    _logger.info(
        "event=requirement_planned requirement_id=%s plan_version=%s steps=%s acceptance_checks=%s",
        requirement.id,
        workflow_run.plan_version,
        len(planner_output.get("workflow_steps") or []),
        len(planner_output.get("acceptance_checks") or []),
    )
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
    if body.title is not None:
        if not body.title.strip():
            raise ValueError("title cannot be blank")
        requirement.title = body.title.strip()
    if body.description_markdown is not None:
        if not body.description_markdown.strip():
            raise ValueError("description_markdown cannot be blank")
        requirement.description_markdown = body.description_markdown.strip()
    if body.priority is not None:
        if body.priority not in {"low", "normal", "high"}:
            raise ValueError("priority must be low|normal|high")
        requirement.priority = body.priority
    if body.source_ref is not None:
        requirement.source_ref = body.source_ref
    db.commit()
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
        delivery_contract = _delivery_contract_payload(db, requirement.id)
        _record_delivery_state(
            db,
            requirement,
            workflow_run,
            publish_status="blocked" if str(delivery_contract.get("release_mode") or "manual") == "disabled" else "review_ready",
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
        },
    )
    _record_delivery_state(
        db,
        requirement,
        workflow_run,
        publish_status="published",
        confirmed_checks=completed_checks,
        publish_note=note or None,
    )
    db.commit()
    _logger.info(
        "event=requirement_published requirement_id=%s release_mode=%s confirmed_checks=%s",
        requirement.id,
        release_mode,
        len(completed_checks),
    )
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
            step.status = "cancelled"
            step.completed_at = step.completed_at or utcnow()
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
    requirement.source_ref = body.source_ref
    requirement.active_workflow_run_id = None
    requirement.current_plan_version = 0
    requirement.planned_roles_json = None
    requirement.started_at = None
    requirement.completed_at = None
    requirement.status = "ready"

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

    if int(requirement.current_plan_version or 0) == 0 or active_workflow_run is None:
        plan_requirement(db, requirement_id)
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
    if workflow_run is not None:
        rows = db.query(WorkflowStepRow).filter(WorkflowStepRow.workflow_run_id == workflow_run.id).order_by(
            WorkflowStepRow.sequence_no.asc(), WorkflowStepRow.id.asc()
        ).all()
        steps = [WorkflowStepOut.model_validate(row) for row in rows]

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
            if step.step_type in {"implementation", "review", "test", "bugfix"}:
                project_metrics = _project_change_metrics(db, _as_int(requirement.id), workflow_run_id=_as_int(run.id))
                bugfix_profile = _build_followup_execution_profile(
                    step,
                    step_type="bugfix",
                    failure_count=failure_count,
                    error_text=error_text,
                    project_change_metrics=project_metrics,
                )
                review_profile = _build_followup_execution_profile(
                    step,
                    step_type="review",
                    failure_count=failure_count,
                    error_text=error_text,
                    project_change_metrics=project_metrics,
                )
                test_profile = _build_followup_execution_profile(
                    step,
                    step_type="test",
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
                        review_execution_profile=review_profile,
                        test_execution_profile=test_profile,
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
        elif step.step_type in {"implementation", "review", "test", "bugfix"}:
            project_metrics = _project_change_metrics(db, _as_int(requirement.id), workflow_run_id=_as_int(run.id))
            bugfix_profile = _build_followup_execution_profile(
                step,
                step_type="bugfix",
                failure_count=failure_count,
                error_text=error_text,
                project_change_metrics=project_metrics,
            )
            review_profile = _build_followup_execution_profile(
                step,
                step_type="review",
                failure_count=failure_count,
                error_text=error_text,
                project_change_metrics=project_metrics,
            )
            test_profile = _build_followup_execution_profile(
                step,
                step_type="test",
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
                    review_execution_profile=review_profile,
                    test_execution_profile=test_profile,
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
                _record_step_event(db, step.id, "status_change", "completed (auto-closeout)")
                db.commit()
                return

            task, persona, skill_name = _prepare_step_task(db, step, prepared_description=str(context_snapshot.get("prompt") or ""))
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
        "synthesizer": assignments.synthesizer_agent_id,
        "implementer": assignments.implementer_agent_id,
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
            context_scope="verification" if str(step_packet.get("step_type")) in {"review", "test", "closeout"} else "step_private",
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
            persona = _load_full_persona(step.assigned_agent_id or "")
            return task, persona, skill_name

    agent = db.query(AgentRow).filter(AgentRow.id == step.assigned_agent_id).first()
    if agent is None:
        raise ValueError(f"Assigned agent '{step.assigned_agent_id}' not found for step {step.step_key}")

    project_id, agent_group = task_metadata_for_agent(str(agent.group))
    description = prepared_description or _step_task_description(db, step)
    suggestion = suggest_task_execution(db, description=description, preferred_agent_id=str(agent.id))
    skill_name = suggestion.skill_name or "content-strategy"
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
        priority="high" if step.step_type in {"test", "bugfix"} else "normal",
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
    persona = _load_full_persona(str(agent.id))
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


def _step_context_snapshot(db: Session, step: WorkflowStepRow) -> dict[str, Any]:
    requirement = _require_requirement(db, step.requirement_id)
    target_path = _effective_target_project_path(db, requirement, step_type=str(step.step_type or ""))
    context_policy = _json_loads(getattr(step, "context_policy_json", None), {})
    max_artifact_body_chars = int(context_policy.get("max_artifact_body_chars") or 2200)
    max_handoff_chars = int(context_policy.get("max_handoff_chars") or 1200)

    sections: list[dict[str, Any]] = [
        {
            "kind": "base",
            "title": "Step",
            "body": "\n".join([
                f"[workflow_step:{step.step_type}] {step.title}",
                f"Requirement #{requirement.id}: {requirement.title}",
                str(requirement.description_markdown or "").strip(),
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

    sections.append({"kind": "done_when", "title": "Done When", "body": str(step.done_when_markdown or "").strip()})

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
                str(section.get("kind") or "") in {"project", "capability", "done_when"}
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
    stale_findings: list[str] = []
    for binding in binding_summaries:
        artifact_type = str(binding.get("artifact_type") or "")
        created_at = _normalize_utc_datetime(parse_runtime_timestamp(str(binding.get("created_at") or "")))
        workflow_run_id = int(binding.get("workflow_run_id") or 0)
        if workflow_run_id and workflow_run_id != int(step.workflow_run_id):
            stale_findings.append(f"{artifact_type} comes from workflow run #{workflow_run_id}, not the active run #{step.workflow_run_id}")
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


def _materialize_step_context(db: Session, step: WorkflowStepRow) -> dict[str, Any]:
    snapshot = _step_context_snapshot(db, step)
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
    lines = [snapshot["prompt"]]
    if snapshot["verification_status"] != "fresh":
        lines.extend([
            "",
            "## Stale Memory Verification",
            *(f"- {item}" for item in snapshot["stale_findings"]),
        ])
    return "\n".join(lines)
    requirement = _require_requirement(db, step.requirement_id)
    parts = [
        f"[workflow_step:{step.step_type}] {step.title}",
        f"Requirement #{requirement.id}: {requirement.title}",
        requirement.description_markdown,
    ]
    target_path = _effective_target_project_path(db, requirement, step_type=str(step.step_type or ""))
    if target_path:
        parts.append(f"Target project path: {target_path}")
        parts.append("IMPORTANT: Write actual source code files in the target project, not just documentation.")
        project_policy_summary = project_policy_summary_markdown(db, target_path)
        if project_policy_summary:
            parts.append(project_policy_summary)
    approval_policy = _json_loads(getattr(step, "approval_policy_json", None), {})
    capability_lines = _approval_policy_markdown_lines(approval_policy)
    if capability_lines:
        parts.append("\n## Capability Contract")
        parts.extend(capability_lines)
    parts.append(f"\n## Done When\n{step.done_when_markdown}")

    # Include handoff summaries from completed predecessor steps (Markdown, not raw JSON)
    deps = db.query(WorkflowStepDependencyRow).filter(WorkflowStepDependencyRow.step_id == step.id).all()
    for dep in deps:
        pred = db.query(WorkflowStepRow).filter(WorkflowStepRow.id == dep.depends_on_step_id).first()
        if pred and pred.handoff_summary_markdown:
            parts.append(f"\n## Prior Step: {pred.title}\n{pred.handoff_summary_markdown}")

    # Include bound input artifacts — convert plan JSONs to concise Markdown summaries
    bindings = db.query(StepInputBindingRow).filter(StepInputBindingRow.step_id == step.id).all()
    for binding in bindings:
        artifact = db.query(ArtifactRow).filter(ArtifactRow.id == binding.artifact_id).first()
        if not artifact:
            continue
        if artifact.artifact_type == "implementation_plan":
            # Convert plan JSON into a concise Markdown summary for the agent
            plan_md = _plan_artifact_to_markdown(artifact)
            if plan_md:
                parts.append(f"\n## Implementation Plan\n{plan_md}")
        elif artifact.artifact_type == "delivery_contract":
            delivery_md = _delivery_contract_artifact_to_markdown(artifact)
            if delivery_md:
                parts.append(f"\n## Delivery Contract\n{delivery_md}")
        elif artifact.artifact_type == "validation_plan":
            validation_md = _validation_plan_artifact_to_markdown(artifact)
            if validation_md:
                parts.append(f"\n## Validation Contract\n{validation_md}")
        elif artifact.human_readable_body:
            parts.append(f"\n## {artifact.artifact_type}: {artifact.content_summary}")
            parts.append(artifact.human_readable_body[:3000])
    return "\n".join(parts)


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
    if step_type in {"research", "synthesis", "review", "test", "implementation", "bugfix"}:
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


def _resolve_step_skill(db: Session, step: WorkflowStepRow) -> str:
    description = _step_task_description(db, step)
    suggestion = suggest_task_execution(db, description=description, preferred_agent_id=step.assigned_agent_id)
    return suggestion.skill_name or "content-strategy"


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
        "synthesis": "synthesis_report",
        "implementation": "step_output",
        "bugfix": "step_output",
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
    _create_or_update_artifact(
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
    if str(step.step_type or "") not in {"implementation", "bugfix", "review", "test"}:
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
    if str(step.step_type or "") in {"review", "test"} and current_tier == "max":
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
    if allow_escalation and "review_or_test_blocker" in when and str(failed_step.step_type or "") in {"review", "test"}:
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
    if step_type in {"review", "test"} and target_tier == "max" and int(project_change_metrics.get("changed_project_count") or 0) <= 1:
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
        "synthesis": "implementation_context",
        "implementation": "implementation_context",
        "bugfix": "bugfix_context",
        "review": "review_context",
        "test": "test_context",
        "closeout": "test_context",
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
    review_execution_profile: dict[str, Any] | None = None,
    test_execution_profile: dict[str, Any] | None = None,
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
    reviewer_agent_id = _secondary_agent_id(db, exclude={bugfix_agent_id})
    tester_agent_id = _secondary_agent_id(db, exclude={bugfix_agent_id, reviewer_agent_id})
    inherited_targets = _json_loads(failed_step.validation_targets_json, [])
    review_targets = [{"check_key": "review_passed", "method": "manual_review"}]
    test_targets = [{"check_key": "validation_passed", "method": "agent_validation"}]
    if failed_step.step_type == "review" and isinstance(inherited_targets, list) and inherited_targets:
        review_targets = inherited_targets
    if failed_step.step_type == "test" and isinstance(inherited_targets, list) and inherited_targets:
        test_targets = inherited_targets
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

    review_step = WorkflowStepRow(
        workflow_run_id=workflow_run.id,
        requirement_id=requirement.id,
        step_key=f"review-{bugfix_step.id}",
        step_type="review",
        title=f"Review bugfix for {requirement.title}",
        status="pending",
        sequence_no=next_sequence + 10,
        assigned_agent_id=reviewer_agent_id,
        assigned_workflow_role="reviewer",
        branch_from_step_id=failed_step.id,
        context_scope="verification",
        done_when_markdown="Bugfix review report is created and review check is passed.",
        file_scope_json=failed_step.file_scope_json,
        validation_targets_json=json.dumps(review_targets),
        failure_policy_json=json.dumps({"on_failure": "bugfix", "max_retries": 0}),
        approval_policy_json=json.dumps(_derived_approval_policy(
            "review",
            base_approval_policy,
            execution_profile=review_execution_profile or _step_execution_profile(failed_step),
            requirement=requirement,
        )),
        execution_profile_json=json.dumps(review_execution_profile or _step_execution_profile(failed_step)),
    )
    db.add(review_step)
    db.flush()

    test_step = WorkflowStepRow(
        workflow_run_id=workflow_run.id,
        requirement_id=requirement.id,
        step_key=f"test-{bugfix_step.id}",
        step_type="test",
        title=f"Re-validate bugfix for {requirement.title}",
        status="pending",
        sequence_no=next_sequence + 20,
        assigned_agent_id=tester_agent_id,
        assigned_workflow_role="tester",
        branch_from_step_id=failed_step.id,
        context_scope="verification",
        done_when_markdown="Retest completes with a passing test report.",
        file_scope_json=failed_step.file_scope_json,
        validation_targets_json=json.dumps(test_targets),
        failure_policy_json=json.dumps({"on_failure": "bugfix", "max_retries": 0}),
        approval_policy_json=json.dumps(_derived_approval_policy(
            "test",
            base_approval_policy,
            execution_profile=test_execution_profile or _step_execution_profile(failed_step),
            requirement=requirement,
        )),
        execution_profile_json=json.dumps(test_execution_profile or _step_execution_profile(failed_step)),
    )
    db.add(test_step)
    db.flush()

    db.add(
        WorkflowStepDependencyRow(
            step_id=review_step.id,
            depends_on_step_id=bugfix_step.id,
            dependency_kind="output_required",
            required_artifact_types_json=json.dumps(["step_output"]),
            is_blocking=True,
        )
    )
    db.add(
        WorkflowStepDependencyRow(
            step_id=test_step.id,
            depends_on_step_id=review_step.id,
            dependency_kind="review_required",
            required_artifact_types_json=json.dumps(["review_report"]),
            is_blocking=True,
        )
    )

    closeout_step = db.query(WorkflowStepRow).filter(
        WorkflowStepRow.workflow_run_id == workflow_run.id,
        WorkflowStepRow.step_type == "closeout",
    ).first()
    if closeout_step is not None:
        closeout_step.sequence_no = next_sequence + 30
        existing_deps = db.query(WorkflowStepDependencyRow).filter(WorkflowStepDependencyRow.step_id == closeout_step.id).all()
        for dep in existing_deps:
            db.delete(dep)
        db.flush()
        db.add(
            WorkflowStepDependencyRow(
                step_id=closeout_step.id,
                depends_on_step_id=test_step.id,
                dependency_kind="test_required",
                required_artifact_types_json=json.dumps(["test_report"]),
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
    step.status = "completed"
    step.started_at = step.started_at or utcnow()
    step.completed_at = utcnow()
    _finalize_requirement(db, requirement, workflow_run, step, artifact)


def _finalize_requirement(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    step: WorkflowStepRow,
    artifact: ArtifactRow,
):
    _mark_step_targets_passed(db, requirement, step, artifact)
    workflow_run.status = "completed"
    workflow_run.completed_at = utcnow()
    requirement.status = "done"
    requirement.completed_at = utcnow()
    delivery_contract = _delivery_contract_payload(db, requirement.id)
    auto_publish_allowed = bool(delivery_contract.get("auto_publish_allowed"))
    required_checks = [str(item) for item in delivery_contract.get("required_checks") or [] if str(item).strip()]
    publish_status = "published" if auto_publish_allowed and not required_checks else (
        "blocked" if str(delivery_contract.get("release_mode") or "manual") == "disabled" else "review_ready"
    )
    review_surface = _create_artifact(
        db,
        requirement_id=requirement.id,
        workflow_run_id=workflow_run.id,
        artifact_type="review_surface",
        content_summary=f"Review-ready bundle for requirement #{requirement.id}",
        human_readable_body=_delivery_review_surface_summary(requirement, db),
        machine_readable_payload={
            "requirement_id": _as_int(requirement.id),
            "workflow_run_id": _as_int(workflow_run.id),
            "branch_name": delivery_contract.get("branch_name"),
            "validation_checks": _validation_check_statuses(db, _as_int(requirement.id)),
            "generated_at": utcnow().isoformat(),
        },
    )
    _record_delivery_state(
        db,
        requirement,
        workflow_run,
        publish_status=publish_status,
        confirmed_checks=required_checks if publish_status == "published" else [],
        publish_note="auto-published by release gate" if publish_status == "published" else None,
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
    _schedule_advance_queue()


def _schedule_advance_queue() -> None:
    """Fire-and-forget: pick the next queued ready requirement and start it."""
    def _run() -> None:
        db = SessionLocal()
        try:
            advance_requirement_queue(db)
        except Exception:
            _logger.debug("Queue advance failed (non-critical)", exc_info=True)
        finally:
            db.close()
    threading.Thread(target=_run, daemon=True).start()


def advance_requirement_queue(db: Session) -> dict:
    """Run the portfolio scheduler and start every candidate that fits the current window."""
    from server.services.portfolio_scheduler import execute_portfolio_schedule

    result = execute_portfolio_schedule(db)
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

    manual_checks = payload.get("manual_checks") or []
    if isinstance(manual_checks, list) and manual_checks:
        lines.extend(["", "## Manual Checks"])
        for check in manual_checks:
            if not isinstance(check, dict):
                continue
            lines.append(
                f"- `{check.get('check_key', '')}` via `{check.get('method', 'manual_review')}` "
                f"owned by `{check.get('owner_role', 'reviewer')}`."
            )

    automated_checks = payload.get("automated_checks") or []
    if isinstance(automated_checks, list) and automated_checks:
        lines.extend(["", "## Automated Checks"])
        for check in automated_checks:
            if not isinstance(check, dict):
                continue
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
    checks_by_key = {
        str(check.check_key): check
        for check in db.query(RequirementAcceptanceCheckRow).filter(
            RequirementAcceptanceCheckRow.requirement_id == requirement.id
        ).all()
    }
    failed_checks: list[dict[str, Any]] = []
    for target in _json_loads(step.validation_targets_json, []):
        if not isinstance(target, dict):
            continue
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

    return {
        "requirement_id": _as_int(requirement.id),
        "requirement_title": str(requirement.title),
        "workflow_run_id": _as_int(workflow_run.id) if workflow_run is not None else None,
        "task_id": _as_int(task.id),
        "step_id": _as_int(step.id),
        "step_key": str(step.step_key),
        "step_type": str(step.step_type),
        "verification_type": "manual" if step.step_type == "review" else "automated",
        "bugfix_owner_role": str(validation_plan.get("bugfix_owner_role") or "implementer"),
        "root_failure_step_id": root_failure_step_id,
        "bugfix_depth": _bugfix_branch_depth(db, _as_int(workflow_run.id), step) if workflow_run is not None else 0,
        "error_fingerprint": error_fingerprint,
        "target_project_path": _effective_target_project_path(db, requirement, step_type=str(step.step_type or "")),
        "validation_targets": _json_loads(step.validation_targets_json, []),
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


def _delivery_review_surface_summary(requirement: RequirementRow, db: Session) -> str:
    check_lines = [
        f"`{check['check_key']}`={check['status']}"
        for check in _validation_check_statuses(db, _as_int(requirement.id))
    ]
    return (
        f"Requirement #{requirement.id} is review-ready for `{requirement.title}`. "
        f"Validation: {', '.join(check_lines) if check_lines else 'no checks recorded'}."
    )


def _delivery_state_payload(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow | None,
    *,
    publish_status: str,
    confirmed_checks: list[str] | None = None,
    publish_note: str | None = None,
) -> dict[str, Any]:
    contract = _delivery_contract_payload(db, _as_int(requirement.id))
    required_checks = [str(item) for item in contract.get("required_checks") or [] if str(item).strip()]
    confirmed = [str(item) for item in (confirmed_checks or []) if str(item).strip()]
    pending = [check for check in required_checks if check not in confirmed]
    blockers: list[str] = []
    if str(contract.get("release_mode") or "manual") == "disabled":
        blockers.append("publish disabled by project policy")
    blockers.extend([f"required check pending: {check}" for check in pending])
    return {
        "branch_name": contract.get("branch_name"),
        "branch_strategy": contract.get("branch_strategy"),
        "base_branch": contract.get("base_branch"),
        "review_status": "review_ready",
        "publish_status": publish_status,
        "release_mode": contract.get("release_mode"),
        "requires_manual_approval": bool(contract.get("requires_manual_approval")),
        "required_checks": required_checks,
        "confirmed_checks": confirmed,
        "pending_checks": pending,
        "publish_blockers": blockers,
        "review_surface_summary": _delivery_review_surface_summary(requirement, db),
        "rollback_hint_markdown": contract.get("rollback_hint_markdown"),
        "review_ready_at": utcnow().isoformat(),
        "published_at": utcnow().isoformat() if publish_status == "published" else None,
        "publish_note": publish_note,
        "workflow_run_id": _as_int(workflow_run.id) if workflow_run is not None else None,
    }


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
    required_checks = payload.get("required_checks") or []
    if isinstance(required_checks, list) and required_checks:
        lines.extend(["", "## Required Checks", *[f"- `{item}`" for item in required_checks]])
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
    publish_status: str,
    confirmed_checks: list[str] | None = None,
    publish_note: str | None = None,
) -> ArtifactRow:
    payload = _delivery_state_payload(
        db,
        requirement,
        workflow_run,
        publish_status=publish_status,
        confirmed_checks=confirmed_checks,
        publish_note=publish_note,
    )
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
    agent = db.query(AgentRow).order_by(AgentRow.id.asc()).first()
    if agent is None:
        raise ValueError("No agents available")
    return str(agent.id)


def _secondary_agent_id(db: Session, exclude: set[str]) -> str:
    for preferred_id in ["dev_rel", "cro_optimizer", "seo_strategist", "growth_lead", "content_writer", "launch_strategist"]:
        if preferred_id in exclude:
            continue
        agent = db.query(AgentRow).filter(AgentRow.id == preferred_id).first()
        if agent is not None:
            return str(agent.id)
    return _fallback_agent_id(db)
