"""Requirement-first workflow orchestration built on top of task runtime compatibility."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import threading
from datetime import datetime, timezone
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
from server.services.copilot_sdk_state import copilot_runtime_paths, load_runtime_state, save_runtime_state, task_output_dir
from server.services.execution_resolver import suggest_task_execution
from server.services.project_policy import project_policy_summary_markdown, resolve_project_policies_for_target
from server.services.project_intelligence import build_requirement_score_breakdown, resolve_requirement_routing, serialize_requirement
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

import logging as _logging
_logger = _logging.getLogger("ops-dashboard.workflow_orchestrator")


def _clear_role_sessions() -> None:
    """Clear runtime role-session caches when a requirement reaches a terminal state."""
    try:
        from server.services.task_runtime import clear_runtime_session_caches
        clear_runtime_session_caches()
    except Exception:
        _logger.debug("Failed to clear role sessions (non-critical)", exc_info=True)


def _snapshot_file_changes(task: TaskRow, requirement: RequirementRow) -> None:
    """Capture `git diff HEAD` in the target project and save to the task output dir."""
    try:
        raw_path = str(requirement.target_project_path) if requirement.target_project_path else None
        # Support multiple paths (newline-separated) — use the first valid directory
        target_path: str | None = None
        if raw_path:
            for line in raw_path.splitlines():
                candidate = line.strip()
                if candidate and Path(candidate).is_dir():
                    target_path = candidate
                    break
        output_path = str(task.output_path) if task.output_path else None
        if not target_path or not output_path:
            return
        target_dir = Path(target_path)
        if not target_dir.is_dir():
            return
        result = subprocess.run(
            ["git", "diff", "HEAD", "--unified=5"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=15,
        )
        diff_text = result.stdout

        changed_files: list[dict] = []
        current: dict | None = None
        for line in diff_text.splitlines(keepends=True):
            if line.startswith("diff --git "):
                if current:
                    changed_files.append(current)
                current = {"filename": "", "additions": 0, "deletions": 0, "patch": ""}
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
            changed_files.append(current)
        changed_files = [f for f in changed_files if f["filename"]]

        snapshot = {
            "changed_files": changed_files,
            "target_project_path": target_path,
            "source": "snapshot",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "task_id": int(task.id),
        }
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "file-changes.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2)
        )
        _logger.info(
            "Saved file-changes snapshot for task %s: %d files changed",
            task.id, len(changed_files),
        )
    except Exception:
        _logger.debug("Failed to snapshot file changes for task %s (non-critical)", task.id, exc_info=True)


def _record_step_event(db: Session, step_id: int, event_type: str, detail: str | None = None):
    db.add(WorkflowStepEventRow(step_id=step_id, event_type=event_type, detail=detail))


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

    if lines == [PRIMARY_GROWING_PROJECT]:
        lines.append(PRIMARY_SYNAPSE_PROJECT)

    if not lines:
        return None
    return "\n".join(lines)


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
    _replace_dependencies(db, requirement.id, body.depends_on_requirement_ids)
    _refresh_requirement_dependency_state(db, requirement)
    db.commit()

    detail = build_requirement_detail(db, requirement.id)
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
    return build_requirement_detail(db, requirement.id)


def delete_requirement(db: Session, requirement_id: int) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    if requirement.status == "deleted":
        return build_requirement_detail(db, requirement.id)
    _soft_delete_requirement_tree(db, requirement, visited=set())
    db.commit()
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
    return build_requirement_detail(db, requirement.id)


def start_requirement(db: Session, requirement_id: int) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    resolve_project_policies_for_target(
        db,
        _normalize_target_project_path(requirement.target_project_path),
        require_active=bool(requirement.target_project_path),
    )
    # ── Serial execution guard: only one requirement may be in_progress at a time ──
    running_count = db.query(RequirementRow).filter(
        RequirementRow.status == "in_progress",
        RequirementRow.id != requirement_id,
    ).count()
    if running_count > 0:
        raise ValueError("另一个需求正在执行中，请等待完成后再启动。")
    _refresh_requirement_dependency_state(db, requirement)
    if requirement.blocked_by_count > 0:
        raise ValueError("Requirement is blocked by unfinished dependencies.")
    workflow_run = _active_workflow_run(db, requirement)
    if workflow_run is None:
        raise ValueError("Requirement has no active workflow run. Plan it first.")

    if workflow_run.status == "completed":
        return build_requirement_detail(db, requirement.id)

    requirement.status = "in_progress"
    if workflow_run.started_at is None:
        workflow_run.started_at = utcnow()
    workflow_run.status = "running"
    if requirement.started_at is None:
        requirement.started_at = utcnow()
    db.commit()

    _dispatch_next_step_for_requirement(requirement.id)
    db.expire_all()

    fresh_db = SessionLocal()
    try:
        return build_requirement_detail(fresh_db, requirement.id)
    finally:
        fresh_db.close()


def pause_requirement(db: Session, requirement_id: int) -> RequirementDetailOut:
    requirement = _require_requirement(db, requirement_id)
    _ensure_requirement_not_deleted(requirement)
    workflow_run = _active_workflow_run(db, requirement)
    if workflow_run is None or requirement.status != "in_progress":
        raise ValueError("Requirement is not currently running.")

    running_steps = db.query(WorkflowStepRow).filter(
        WorkflowStepRow.workflow_run_id == workflow_run.id,
        WorkflowStepRow.status.in_(tuple(RUNNING_STEP_STATUSES)),
    ).all()
    if not running_steps:
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
    return build_requirement_detail(db, requirement.id)


def pause_task(db: Session, task_id: int) -> TaskRow:
    """Pause a running task and cascade the pause to its parent requirement.

    Sets the task status to 'paused', terminates the runtime, resets the linked
    workflow step back to 'ready', and pauses the parent requirement if it is
    currently in_progress.
    """
    task = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if task is None:
        raise ValueError(f"Task #{task_id} not found")
    task_status = _as_text(cast(Any, task).status)
    if task_status != "running":
        raise ValueError(f"Task #{task_id} is not running (status={task_status})")

    _terminate_task_runtime(task)
    cast(Any, task).status = "cancelled"
    cast(Any, task).last_error_message = "Paused by user"
    db.add(TaskLogRow(task_id=task_id, event_type="paused", detail="Task paused by user"))

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
        _record_step_event(db, step.id, "status_change", "ready (task paused by user)")

        # Cascade to parent requirement
        parent_req = db.query(RequirementRow).filter(
            RequirementRow.id == step.requirement_id
        ).first()
        if parent_req is not None and _as_text(cast(Any, parent_req).status) == "in_progress":
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
        _record_step_event(db, step.id, "status_change", "running")
        db.commit()
        return

    if task.status == "pending_approval":
        step.status = "waiting_approval"
        step.runtime_session_id = task.runtime_session_id
        step.runtime_backend = task.runtime_backend or ""
        step.started_at = step.started_at or task.started_at or utcnow()
        run.status = "running"
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
        _record_step_event(db, step.id, "status_change", "completed")
        artifact = _create_step_completion_artifact(db, step, task)
        _mark_step_targets_passed(db, step, artifact)
        _bind_output_to_followup_steps(db, step, artifact)
        # Snapshot git diff now, before the next step is dispatched
        _snapshot_file_changes(task, requirement)
        _am_push_task_completed(task, step, requirement)
        if step.step_type == "closeout":
            _finalize_requirement(db, requirement, run, step, artifact)
        else:
            should_dispatch_next = True

    elif task.status in {"failed", "rejected"}:
        step.status = "failed"
        step.started_at = step.started_at or task.started_at or utcnow()
        step.completed_at = task.completed_at or utcnow()
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
        failure_route = _resolve_failure_route(step, error_text)
        if failure_route == "requirement_revision":
            _create_requirement_revision_request(db, requirement, run, step, error_artifact, error_text)
        elif step.step_type in {"implementation", "review", "test", "bugfix"}:
            _create_bugfix_branch(db, requirement, run, step, error_artifact)
            should_dispatch_next = True
        else:
            run.status = "failed"
            requirement.status = "needs_revision"

    _refresh_run_status(db, requirement, run)
    db.commit()

    if should_dispatch_next:
        _dispatch_next_step_for_requirement(requirement.id)


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
            if step.step_type == "closeout":
                _auto_complete_closeout(db, requirement, workflow_run, step)
                _record_step_event(db, step.id, "status_change", "completed (auto-closeout)")
                db.commit()
                return

            task, persona, skill_name = _prepare_step_task(db, step)
            step.status = "running"
            step.started_at = step.started_at or utcnow()
            step.compatibility_task_id = _as_int(task.id)
            workflow_run.status = "running"
            requirement.status = "in_progress"
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
                    if s:
                        s.status = "ready"
                    if t:
                        cast(Any, t).status = "failed"
                        cast(Any, t).last_error_message = "dispatch failed"
                        cast(Any, t).completed_at = utcnow()
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
        db.add(TaskLogRow(task_id=task.id, event_type="paused", detail="Requirement paused by user"))

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
            file_scope_json=json.dumps(step_packet.get("file_scope") or {}),
            validation_targets_json=json.dumps(step_packet.get("validation_targets") or []),
            failure_policy_json=json.dumps(step_packet.get("failure_policy") or {}),
            approval_policy_json=json.dumps({}),
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


def _prepare_step_task(db: Session, step: WorkflowStepRow) -> tuple[TaskRow, dict, str]:
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
    description = _step_task_description(db, step)
    suggestion = suggest_task_execution(db, description=description, preferred_agent_id=str(agent.id))
    skill_name = suggestion.skill_name or "content-strategy"
    task = TaskRow(
        description=description,
        agent_id=str(agent.id),
        status="running",
        requires_approval=False,
        priority="high" if step.step_type in {"test", "bugfix"} else "normal",
        project_id=project_id,
        agent_group=agent_group,
        skill_name=skill_name,
        runtime_backend="",
        started_at=utcnow(),
    )
    db.add(task)
    db.flush()
    db.add(TaskLogRow(task_id=task.id, event_type="created", detail=description))
    db.add(TaskLogRow(task_id=task.id, event_type="started", detail=f"workflow_step={step.id} skill={skill_name}"))
    persona = _load_full_persona(str(agent.id))
    return task, persona, skill_name


def _step_task_description(db: Session, step: WorkflowStepRow) -> str:
    requirement = _require_requirement(db, step.requirement_id)
    parts = [
        f"[workflow_step:{step.step_type}] {step.title}",
        f"Requirement #{requirement.id}: {requirement.title}",
        requirement.description_markdown,
    ]
    target_path = _normalize_target_project_path(getattr(requirement, "target_project_path", None))
    if target_path:
        parts.append(f"Target project path: {target_path}")
        parts.append("IMPORTANT: Write actual source code files in the target project, not just documentation.")
        project_policy_summary = project_policy_summary_markdown(db, target_path)
        if project_policy_summary:
            parts.append(project_policy_summary)
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
            lines.append(f"{i}. **{s.get('title', s.get('step_key', ''))}** ({role}): {done}")

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
        "runtime_session_id": task.runtime_session_id,
        "output_path": task.output_path,
        "output_content": body,
        "execution_time_ms": task.execution_time_ms,
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


def _bind_output_to_followup_steps(db: Session, step: WorkflowStepRow, artifact: ArtifactRow):
    dependents = db.query(WorkflowStepDependencyRow).filter(
        WorkflowStepDependencyRow.depends_on_step_id == step.id
    ).all()
    purpose = {
        "implementation": "implementation_context",
        "bugfix": "bugfix_context",
        "review": "review_context",
        "test": "test_context",
        "closeout": "test_context",
    }.get(step.step_type, "implementation_context")
    for dep in dependents:
        _bind_artifact(db, dep.step_id, artifact.id, purpose, True)


def _mark_step_targets_passed(db: Session, step: WorkflowStepRow, artifact: ArtifactRow):
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
        check.status = "passed"
        check.verified_by_step_id = step.id
        check.evidence_artifact_id = artifact.id


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
        approval_policy_json=json.dumps({}),
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
        validation_targets_json=json.dumps([{"check_key": "review_passed", "method": "manual_review"}]),
        failure_policy_json=json.dumps({"on_failure": "bugfix", "max_retries": 0}),
        approval_policy_json=json.dumps({}),
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
        validation_targets_json=json.dumps([{"check_key": "validation_passed", "method": "agent_validation"}]),
        failure_policy_json=json.dumps({"on_failure": "bugfix", "max_retries": 0}),
        approval_policy_json=json.dumps({}),
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


def _refresh_run_status(db: Session, requirement: RequirementRow, workflow_run: WorkflowRunRow):
    if requirement.status == "needs_revision":
        workflow_run.status = "cancelled"
        return
    steps = db.query(WorkflowStepRow).filter(WorkflowStepRow.workflow_run_id == workflow_run.id).all()
    if not steps:
        workflow_run.status = "pending"
        return
    if any(step.status in RUNNING_STEP_STATUSES for step in steps):
        workflow_run.status = "running"
        requirement.status = "in_progress"
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
    workflow_run.status = "running"
    requirement.status = "in_progress"


def _auto_complete_closeout(db: Session, requirement: RequirementRow, workflow_run: WorkflowRunRow, step: WorkflowStepRow):
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
    _mark_step_targets_passed(db, step, artifact)
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
    """Start the next highest-priority 'ready' requirement if nothing is in_progress.

    Returns {"started": req_id} or {"skipped": reason}.
    """
    # Check if anything is already executing
    active = db.query(RequirementRow).filter(
        RequirementRow.status == "in_progress"
    ).first()
    if active:
        return {"skipped": f"requirement #{active.id} already in_progress"}

    # Halt if any requirement is paused — wait for user to resume or start a new task
    paused = db.query(RequirementRow).filter(
        RequirementRow.status == "paused"
    ).first()
    if paused:
        return {"skipped": f"requirement #{paused.id} is paused; resume it or start a new task first"}

    # Find candidates: ready, unblocked, no workflow run yet
    candidates = db.query(RequirementRow).filter(
        RequirementRow.status == "ready",
        RequirementRow.blocked_by_count == 0,
        RequirementRow.active_workflow_run_id.is_(None),
    ).all()

    if not candidates:
        return {"skipped": "no ready requirements"}

    scored_candidates: list[tuple[RequirementRow, dict[str, Any]]] = []
    skipped_not_ready: list[str] = []
    for candidate in candidates:
        score = build_requirement_score_breakdown(db, candidate)
        routing = dict(score.get("routing_context") or {})
        if candidate.target_project_path and not bool(routing.get("automation_ready")):
            skipped_not_ready.append(
                f"#{candidate.id}({routing.get('readiness_status') or 'unknown'})"
            )
            continue
        scored_candidates.append((candidate, score))

    if not scored_candidates:
        if skipped_not_ready:
            return {"skipped": "no automation-ready requirements: " + ", ".join(skipped_not_ready)}
        return {"skipped": "no ready requirements"}

    scored_candidates.sort(key=lambda item: float(item[1].get("total") or 0.0), reverse=True)
    next_req = scored_candidates[0][0]
    req_id = _as_int(next_req.id)

    _logger.info("Queue advance: starting requirement #%s '%s'", req_id, next_req.title[:60])
    try:
        plan_requirement(db, req_id)
        start_requirement(db, req_id)
        return {"started": req_id}
    except Exception as exc:
        _logger.warning("Queue advance failed for req #%s: %s", req_id, exc)
        return {"skipped": str(exc)}


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
        "target_project_path": _normalize_target_project_path(requirement.target_project_path),
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
    required_checks = [str(item) for item in payload.get("required_checks") or [] if str(item).strip()]
    if required_checks:
        lines.extend(["", "## Required Checks", *[f"- `{item}`" for item in required_checks]])
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
    return "\n".join(
        [
            f"# Plan\n",
            f"## Goal\n\n{planner_output.get('goal_summary', '')}",
            "## Role Assignments",
            f"- Implementer: {assignments.implementer_agent_id}",
            f"- Reviewer: {assignments.reviewer_agent_id}",
            f"- Tester: {assignments.tester_agent_id}",
            "## Project Intelligence",
            *( [f"- {line}" for line in intelligence_summary.splitlines() if line.strip()] or ["- No project routing intelligence was attached."] ),
            "## Delivery Contract",
            *(delivery_summary_lines or ["- Delivery contract will be generated for branch/review-ready/publish/rollback."]),
            "## Validation Contract",
            *(validation_summary_lines or ["- Validation contract will be generated for review/test/closeout."]),
            "## Steps",
            *[
                f"- {step.get('step_key')}: {step.get('title')}"
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
    if requirement.active_workflow_run_id:
        run = db.query(WorkflowRunRow).filter(WorkflowRunRow.id == requirement.active_workflow_run_id).first()
        if run is not None:
            return run
    return db.query(WorkflowRunRow).filter(WorkflowRunRow.requirement_id == requirement.id).order_by(WorkflowRunRow.id.desc()).first()


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
