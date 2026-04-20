"""Requirement lifecycle service for the declarative Workflow Factory.

This module is the public requirement API service. It intentionally does not
depend on the retired task/execution/step models.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from server.config import PROJECT_ROOT
from server.database import (
    HumanGateRequestRow,
    ProjectRow,
    ReleaseRecordRow,
    RequirementAttachmentRow,
    RequirementRow,
    ValidationRecordRow,
    WorkflowRunRow,
    utcnow,
)
from server.logging_utils import get_logger, log_event
from server.schemas import (
    AgentFirstRequirementDetailOut,
    AgentFirstRequirementOut,
    DeclarativeWorkflowRunSummaryOut,
    ProjectOut,
    RequirementAttachmentOut,
    RequirementProjectRefOut,
    ReleaseRecordSlimOut,
    WorkflowReadinessOut,
)
from server.services.projects.policy import project_policy_summary_markdown, resolve_project_policies_for_target
from server.services.projects.project_center import (
    ensure_projects_materialized,
    get_project,
    project_to_dict,
    resolve_project,
)
from server.services.requirements.acceptance import normalize_acceptance_contract
from server.services.requirements.attachments import (
    persist_requirement_attachments,
    requirement_attachment_context_files,
    serialize_requirement_attachment,
)
from server.services.runtime.alerting import build_ops_url, deliver_policy_notification, notification_service_label
from server.services.runtime.codex_session_registry import (
    build_planner_project_session_key,
    find_reusable_planner_project_session,
    upsert_planner_project_session,
)
from server.services.workflows.planner_provider import (
    PlannerRequest,
    generate_planner_text,
    resolve_planner_backend,
    resolve_planner_model,
)

logger = get_logger("ops-dashboard.requirements")

TERMINAL_INACTIVE_REQUIREMENT_STATES = {"cancelled", "deleted"}


def _testing_mode() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _auto_submit_enabled() -> bool:
    if not _testing_mode():
        return True
    return os.environ.get("OPS_AGENT_FIRST_AUTO_SUBMIT_IN_TESTS", "").lower() in {"1", "true", "yes", "on"}


def _json_load(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _split_target_projects(value: str | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in str(value or "").splitlines():
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug[:48] or "requirement"


def _parse_acceptance_contract(requirement: RequirementRow) -> dict[str, Any]:
    return normalize_acceptance_contract(_json_load(getattr(requirement, "acceptance_contract_json", None), {}))


def _parse_acceptance_markdown(requirement: RequirementRow) -> str:
    return str(_parse_acceptance_contract(requirement).get("markdown") or "").strip()


def _parse_execution_plan(requirement: RequirementRow) -> dict[str, Any]:
    payload = _json_load(getattr(requirement, "execution_plan_json", None), {})
    return dict(payload) if isinstance(payload, dict) else {}


def _acceptance_contract_markdown(contract: dict[str, Any]) -> str:
    lines = ["## Done Criteria"]
    for item in contract.get("done_criteria") or []:
        lines.append(f"- {item}")
    if contract.get("scope_constraints"):
        lines.extend(["", "## Scope Constraints"])
        lines.extend(f"- {item}" for item in contract.get("scope_constraints") or [])
    if contract.get("expected_evidence"):
        lines.extend(["", "## Expected Evidence"])
        lines.extend(f"- {item}" for item in contract.get("expected_evidence") or [])
    if contract.get("risk_notes"):
        lines.extend(["", "## Risk Notes"])
        lines.extend(f"- {item}" for item in contract.get("risk_notes") or [])
    delivery = str(contract.get("delivery_expectation") or "").strip()
    if delivery:
        lines.extend(["", "## Delivery Expectation", delivery])
    return "\n".join(lines).strip()


def _fallback_acceptance_contract(
    *,
    title: str,
    description_markdown: str,
    target_project_path: str | None = None,
    required_checks: list[str] | None = None,
) -> dict[str, Any]:
    done = [
        f"The requested outcome for `{title.strip() or 'requirement'}` is implemented.",
        "The change stays within the described scope and avoids unrelated rewrites.",
    ]
    expected = ["Changed files, verification output, and workflow artifacts are available in Ops Console."]
    for command in required_checks or []:
        expected.append(f"Required project check remains green: `{command}`")
    contract = normalize_acceptance_contract(
        {
            "done_criteria": done,
            "scope_constraints": [
                f"Target project path is {target_project_path}." if target_project_path else "Target project is resolved from project policy.",
                "Do not change credentials, funds, deployment, or auth behavior unless explicitly required.",
            ],
            "expected_evidence": expected,
            "risk_notes": ["Route high-risk production, auth, funds, or deployment effects to human gate."],
            "delivery_expectation": "Deliver through declarative workflow evidence and PR/release gates.",
        }
    )
    contract["markdown"] = _acceptance_contract_markdown(contract)
    return contract


def _required_checks_for_target(db: Session, target_project_path: str | None) -> list[str]:
    commands: list[str] = []
    seen: set[str] = set()
    for policy in resolve_project_policies_for_target(db, target_project_path, require_active=False):
        raw = _json_load(getattr(policy, "required_checks_json", None), [])
        for command in raw if isinstance(raw, list) else []:
            cleaned = str(command).strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                commands.append(cleaned)
    return commands


def _project_for_requirement(db: Session, requirement: RequirementRow) -> ProjectRow | None:
    ensure_projects_materialized(db)
    return resolve_project(
        db,
        project_id=int(requirement.project_id) if getattr(requirement, "project_id", None) is not None else None,
        project_key=str(getattr(requirement, "project_key", "") or "") or None,
        target_project_path=str(getattr(requirement, "target_project_path", "") or "") or None,
    )


def _resolve_project_for_body(db: Session, body: Any) -> ProjectRow | None:
    ensure_projects_materialized(db)
    body_project_id = getattr(body, "project_id", None)
    if body_project_id is not None:
        return get_project(db, int(body_project_id))
    return resolve_project(db, target_project_path=str(getattr(body, "target_project_path", "") or "") or None)


def _resolved_target_project_path(project: ProjectRow | None, *, override: str | None = None, fallback: str | None = None) -> str | None:
    if str(override or "").strip():
        return str(override or "").strip()
    if project is not None and str(getattr(project, "root_path", "") or "").strip():
        return str(project.root_path or "").strip()
    return str(fallback or "").strip() or None


def _target_projects_for_requirement(db: Session, requirement: RequirementRow) -> list[str]:
    project = _project_for_requirement(db, requirement)
    resolved = _resolved_target_project_path(
        project,
        override=str(getattr(requirement, "target_project_path_override", "") or "") or None,
        fallback=str(getattr(requirement, "target_project_path", "") or "") or None,
    )
    if resolved:
        return [resolved]
    return _split_target_projects(getattr(requirement, "target_project_path", None))


def _project_context_out(requirement: RequirementRow, project: ProjectRow | None) -> RequirementProjectRefOut:
    return RequirementProjectRefOut(
        project_id=int(project.id) if project is not None else (int(requirement.project_id) if getattr(requirement, "project_id", None) is not None else None),
        project_key=str(getattr(project, "project_key", "") or "").strip() or (str(getattr(requirement, "project_key", "") or "").strip() or None),
        project_display_name=str(getattr(project, "display_name", "") or "").strip() or (str(getattr(requirement, "project_display_name", "") or "").strip() or None),
        target_project_path=str(getattr(requirement, "target_project_path", "") or "").strip() or None,
        target_project_path_override=str(getattr(requirement, "target_project_path_override", "") or "").strip() or None,
    )


def _assets_status(requirement: RequirementRow) -> str:
    status = str(getattr(requirement, "assets_status", "") or "").strip()
    if status in {"pending", "ready", "failed"}:
        return status
    if str(getattr(requirement, "acceptance_contract_json", "") or "").strip() and str(getattr(requirement, "execution_plan_json", "") or "").strip():
        return "ready"
    return "pending"


def _assets_error_message(requirement: RequirementRow) -> str | None:
    return str(getattr(requirement, "assets_error_message", "") or "").strip() or None


def _requirement_status_from_phase(phase: str) -> str:
    token = str(phase or "draft").strip() or "draft"
    if token == "deleted":
        return "deleted"
    if token in {"draft", "planning"}:
        return "draft"
    if token in {"ready", "branch_prepared", "branch_preparing"}:
        return "ready"
    if token in {"blocked", "recovering"}:
        return "blocked"
    if token == "needs_revision":
        return "needs_revision"
    if token in {"executing", "verifying"}:
        return "running"
    if token in {"delivery_ready", "pr_opened"}:
        return "delivery_ready"
    if token in {"done", "completed"}:
        return "done"
    if token == "cancelled":
        return "cancelled"
    return "draft"


def _latest_release(db: Session, requirement_id: int) -> ReleaseRecordRow | None:
    return (
        db.query(ReleaseRecordRow)
        .filter(ReleaseRecordRow.requirement_id == requirement_id)
        .order_by(ReleaseRecordRow.id.desc())
        .first()
    )


def release_to_out(release: ReleaseRecordRow | None) -> ReleaseRecordSlimOut | None:
    if release is None:
        return None
    return ReleaseRecordSlimOut(
        id=int(release.id),
        requirement_id=int(release.requirement_id),
        workflow_run_id=int(getattr(release, "workflow_run_id", 0) or 0) or None,
        state=str(getattr(release, "delivery_state", "") or "pending"),
        project_id=int(release.project_id) if getattr(release, "project_id", None) is not None else None,
        project_key=str(release.project_key or "").strip() or None,
        project_display_name=str(getattr(release, "project_display_name", "") or "").strip() or None,
        target_project_path=str(release.target_project_path or "").strip() or None,
        status=str(release.status or "not_ready"),
        branch_name=str(release.branch_name or "").strip() or None,
        planned_branch_name=str(getattr(release, "planned_branch_name", "") or "").strip() or None,
        actual_branch_name=str(getattr(release, "actual_branch_name", "") or "").strip() or None,
        branch_reuse_status=str(getattr(release, "branch_reuse_status", "") or "").strip() or None,
        base_branch=str(release.base_branch or "").strip() or None,
        commit_sha=str(release.commit_sha or "").strip() or None,
        compare_url=str(release.compare_url or "").strip() or None,
        pr_url=str(release.pr_url or "").strip() or None,
        pr_number=int(release.pr_number) if release.pr_number is not None else None,
        notes=str(release.notes or "").strip() or None,
        blocker_kind=str(getattr(release, "blocker_kind", "") or "").strip() or None,
        delivery_blocker_type=str(getattr(release, "delivery_blocker_type", "") or "").strip() or None,
        failed_gate_name=str(getattr(release, "failed_gate_name", "") or "").strip() or None,
        delivery_failure_excerpt=str(getattr(release, "delivery_failure_excerpt", "") or "").strip() or None,
        delivery_failure_raw_output=str(getattr(release, "delivery_failure_raw_output", "") or "").strip() or None,
        repairable=bool(getattr(release, "repairable", False)),
        repairability=str(getattr(release, "repairability", "") or "manual_only"),
        repair_attempt_count=int(getattr(release, "repair_attempt_count", 0) or 0),
        next_action=str(getattr(release, "next_action", "") or "").strip() or None,
        workspace_mode="shared_checkout",
        prepared_at=release.prepared_at,
        delivered_at=release.delivered_at,
        created_at=release.created_at,
        updated_at=release.updated_at,
    )


def _active_workflow_run_summary(db: Session, requirement: RequirementRow) -> DeclarativeWorkflowRunSummaryOut | None:
    workflow_run_id = int(getattr(requirement, "active_workflow_run_id", 0) or 0)
    if workflow_run_id <= 0:
        return None
    run = db.query(WorkflowRunRow).filter(WorkflowRunRow.id == workflow_run_id).first()
    if run is None:
        return None
    pending_gate_count = (
        db.query(HumanGateRequestRow)
        .filter(HumanGateRequestRow.workflow_run_id == int(run.id), HumanGateRequestRow.status == "pending")
        .count()
    )
    return DeclarativeWorkflowRunSummaryOut(
        id=int(run.id),
        requirement_id=int(run.requirement_id),
        workflow_key=str(run.workflow_key or ""),
        current_state=str(run.current_state or ""),
        status=str(run.status or ""),
        resolution=str(run.resolution or "").strip() or None,
        risk_level=str(run.risk_level or "normal"),
        pending_human_gate_count=int(pending_gate_count or 0),
        updated_at=run.updated_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _workflow_state_for_requirement(requirement: RequirementRow) -> str:
    tokens = _requirement_lifecycle_tokens(requirement)
    if "deleted" in tokens:
        return "deleted"
    if "cancelled" in tokens:
        return "cancelled"
    active_summary_state = str(getattr(requirement, "workflow_state", "") or "").strip()
    if active_summary_state:
        return active_summary_state
    return str(getattr(requirement, "phase", "") or getattr(requirement, "status", "") or "draft").strip() or "draft"


def _requirement_lifecycle_tokens(requirement: RequirementRow) -> set[str]:
    return {
        str(getattr(requirement, "status", "") or "").strip(),
        str(getattr(requirement, "phase", "") or "").strip(),
        str(getattr(requirement, "workflow_state", "") or "").strip(),
    } - {""}


def _is_inactive_requirement(requirement: RequirementRow) -> bool:
    return bool(_requirement_lifecycle_tokens(requirement) & TERMINAL_INACTIVE_REQUIREMENT_STATES)


def _assert_requirement_can_progress(requirement: RequirementRow, action: str) -> None:
    tokens = _requirement_lifecycle_tokens(requirement)
    if "deleted" in tokens:
        raise ValueError(f"Deleted requirement cannot {action}.")
    if "cancelled" in tokens:
        raise ValueError(f"Cancelled requirement cannot {action}.")


def _requirement_allowed_actions(
    requirement: RequirementRow,
    latest_release: ReleaseRecordRow | None,
) -> list[str]:
    state = _workflow_state_for_requirement(requirement)
    assets_status = _assets_status(requirement)
    has_active_workflow = int(getattr(requirement, "active_workflow_run_id", 0) or 0) > 0
    actions = ["view"]
    if _is_inactive_requirement(requirement):
        return actions
    if has_active_workflow:
        actions.append("view_workflow")
    if not has_active_workflow and state in {"draft", "planning", "ready", "awaiting_operator"}:
        actions.append("edit")
    if not has_active_workflow and assets_status == "ready" and state in {"draft", "ready", "planning"}:
        actions.append("submit")
    if not has_active_workflow and assets_status in {"pending", "failed"}:
        actions.append("regenerate_assets")
    if not has_active_workflow and state in {"draft", "planning", "ready", "needs_revision"}:
        actions.append("delete")
        actions.append("cancel")
    if latest_release is not None:
        actions.append("view_release")
        if str(latest_release.status or "") == "pr_opened" and str(latest_release.pr_url or "").strip():
            actions.append("view_pr")
        elif str(latest_release.status or "") in {"ready", "branch_prepared", "not_ready"}:
            actions.append("open_pr")
    return sorted(set(actions))


def _pending_operations(requirement: RequirementRow) -> list[str]:
    if _is_inactive_requirement(requirement):
        return []
    if getattr(requirement, "active_workflow_run_id", None):
        return []
    if _assets_status(requirement) == "ready":
        return ["start_workflow"]
    return []


def _requirement_to_out(db: Session, requirement: RequirementRow) -> AgentFirstRequirementOut:
    latest_release = _latest_release(db, int(requirement.id))
    project = _project_for_requirement(db, requirement)
    project_context = _project_context_out(requirement, project)
    state = _workflow_state_for_requirement(requirement)
    return AgentFirstRequirementOut(
        id=int(requirement.id),
        title=str(requirement.title or ""),
        description_markdown=str(requirement.description_markdown or ""),
        acceptance_criteria_markdown=_parse_acceptance_markdown(requirement),
        state=state,
        attention_reason=str(getattr(requirement, "attention_reason", "") or "").strip() or None,
        failure_reason=str(getattr(requirement, "failure_reason", "") or "").strip() or None,
        requirement_plan_summary=str(_parse_execution_plan(requirement).get("summary_markdown") or "").strip() or None,
        project=project_context,
        current_attempt_id=None,
        current_delivery_id=int(latest_release.id) if latest_release is not None else None,
        status=str(requirement.status or "draft"),
        priority=str(requirement.priority or "normal"),
        source=str(requirement.source or "manual"),
        source_ref=str(requirement.source_ref or "").strip() or None,
        linked_requirement_id=int(getattr(requirement, "linked_requirement_id", 0) or 0) or None,
        followup_requirement_id=int(getattr(requirement, "followup_requirement_id", 0) or 0) or None,
        resolution_path=str(getattr(requirement, "resolution_path", "") or "").strip() or None,
        operating_manifest_id=int(getattr(requirement, "operating_manifest_id", 0) or 0) or None,
        goal_key=str(getattr(requirement, "goal_key", "") or "").strip() or None,
        requirement_candidate_id=int(getattr(requirement, "requirement_candidate_id", 0) or 0) or None,
        project_id=project_context.project_id,
        project_key=project_context.project_key,
        project_display_name=project_context.project_display_name,
        target_project_path=project_context.target_project_path,
        target_project_path_override=project_context.target_project_path_override,
        target_projects=_target_projects_for_requirement(db, requirement),
        phase=str(getattr(requirement, "phase", "") or "draft"),
        allowed_actions=_requirement_allowed_actions(requirement, latest_release),
        pending_operations=_pending_operations(requirement),
        recovery_status=str(getattr(requirement, "recovery_status", "") or "").strip() or None,
        assets_status=_assets_status(requirement),
        assets_error_message=_assets_error_message(requirement),
        created_at=requirement.created_at,
        updated_at=requirement.updated_at,
        active_workflow_run_id=int(getattr(requirement, "active_workflow_run_id", 0) or 0) or None,
        active_workflow_run_summary=_active_workflow_run_summary(db, requirement),
        latest_release_status=str(latest_release.status or "") if latest_release is not None else None,
    )


def _policy_summary_markdown(db: Session, requirement: RequirementRow) -> str:
    target_project_path = getattr(requirement, "target_project_path", None)
    return project_policy_summary_markdown(db, target_project_path) if str(target_project_path or "").strip() else ""


def _requirement_attachment_rows(db: Session, requirement_id: int) -> list[RequirementAttachmentRow]:
    return (
        db.query(RequirementAttachmentRow)
        .filter(RequirementAttachmentRow.requirement_id == requirement_id)
        .order_by(RequirementAttachmentRow.id.asc())
        .all()
    )


def _workflow_readiness_out(db: Session, requirement: RequirementRow) -> WorkflowReadinessOut:
    assets_status = _assets_status(requirement)
    summary = _active_workflow_run_summary(db, requirement)
    active_run_id = int(getattr(requirement, "active_workflow_run_id", 0) or 0) or None
    recommended_workflow_key = _select_declarative_workflow_key(requirement)
    if _is_inactive_requirement(requirement):
        blocking_reason = "requirement_deleted" if "deleted" in _requirement_lifecycle_tokens(requirement) else "requirement_cancelled"
        next_action = "none"
        can_start = False
    elif active_run_id or summary is not None:
        blocking_reason = None
        next_action = "view_workflow"
        can_start = False
    elif assets_status == "failed":
        blocking_reason = "asset_generation_failed"
        next_action = "generate_workflow_assets"
        can_start = True
    elif assets_status == "pending":
        blocking_reason = "acceptance_or_plan_pending"
        next_action = "generate_workflow_assets"
        can_start = True
    else:
        blocking_reason = None
        next_action = "start_workflow"
        can_start = True
    return WorkflowReadinessOut(
        requirement_id=int(requirement.id),
        assets_status=assets_status,
        active_workflow_run_id=active_run_id,
        active_workflow_run_summary=summary,
        blocking_reason=blocking_reason,
        next_action=next_action,
        can_start_workflow=can_start,
        recommended_workflow_key=recommended_workflow_key,
    )


def build_requirement_detail(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    latest_release = _latest_release(db, requirement_id)
    project = _project_for_requirement(db, requirement)
    state = _workflow_state_for_requirement(requirement)
    return AgentFirstRequirementDetailOut(
        requirement=_requirement_to_out(db, requirement),
        state=state,
        attention_reason=str(getattr(requirement, "attention_reason", "") or "").strip() or None,
        failure_reason=str(getattr(requirement, "failure_reason", "") or "").strip() or None,
        policy_summary_markdown=_policy_summary_markdown(db, requirement),
        project=ProjectOut(**project_to_dict(project)) if project is not None else None,
        active_workflow_run_id=int(getattr(requirement, "active_workflow_run_id", 0) or 0) or None,
        active_workflow_run_summary=_active_workflow_run_summary(db, requirement),
        latest_release_id=int(latest_release.id) if latest_release is not None else None,
        latest_release=release_to_out(latest_release),
        phase=str(getattr(requirement, "phase", "") or "draft"),
        allowed_actions=_requirement_allowed_actions(requirement, latest_release),
        pending_operations=_pending_operations(requirement),
        recovery_status=str(getattr(requirement, "recovery_status", "") or "").strip() or None,
        assets_status=_assets_status(requirement),
        assets_error_message=_assets_error_message(requirement),
        acceptance_contract=_parse_acceptance_contract(requirement),
        execution_plan=_parse_execution_plan(requirement),
        workflow_readiness=_workflow_readiness_out(db, requirement),
        attachments=[RequirementAttachmentOut(**serialize_requirement_attachment(item)) for item in _requirement_attachment_rows(db, requirement_id)],
        followup_requirement_id=int(getattr(requirement, "followup_requirement_id", 0) or 0) or None,
        resolution_path=str(getattr(requirement, "resolution_path", "") or "").strip() or None,
    )


def list_requirements(db: Session, *, status: str | None = None, search: str | None = None) -> list[AgentFirstRequirementOut]:
    ensure_projects_materialized(db)
    rows = db.query(RequirementRow).order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc()).all()
    search_value = str(search or "").strip().lower()
    result: list[AgentFirstRequirementOut] = []
    for row in rows:
        item = _requirement_to_out(db, row)
        if not status and item.status == "deleted":
            continue
        if status and item.status != status:
            continue
        if search_value:
            haystack = "\n".join(
                [
                    item.title.lower(),
                    item.description_markdown.lower(),
                    (item.source_ref or "").lower(),
                    (item.project_display_name or "").lower(),
                    (item.project_key or "").lower(),
                    (item.target_project_path or "").lower(),
                ]
            )
            if search_value not in haystack and search_value != str(item.id):
                continue
        result.append(item)
    return result


def _service_name_for_requirement(db: Session, requirement: RequirementRow) -> str:
    project = _project_for_requirement(db, requirement)
    return notification_service_label(
        display_name=str(getattr(project, "display_name", "") or "").strip() or None,
        project_key=str(getattr(project, "project_key", "") or "").strip() or None,
    )


def _notify_requirement_created(db: Session, requirement: RequirementRow) -> None:
    deliver_policy_notification(
        db,
        event_type="requirement_created",
        object_type="requirement",
        object_key=str(int(requirement.id)),
        service_name=_service_name_for_requirement(db, requirement),
        severity=str(requirement.priority or "normal"),
        risk_level="normal",
        summary=f"New requirement created: {requirement.title}",
        next_action="Inspect requirement and workflow readiness.",
        actor_or_source=str(requirement.source or "manual"),
        event_key=f"requirement_created:{int(requirement.id)}",
        object_refs={"requirement_id": int(requirement.id), "workflow_run_id": getattr(requirement, "active_workflow_run_id", None)},
        links={"需求": build_ops_url(f"/requirements/{int(requirement.id)}") or ""},
    )


def create_requirement(db: Session, body: Any) -> AgentFirstRequirementDetailOut:
    ensure_projects_materialized(db)
    project = _resolve_project_for_body(db, body)
    if project is None:
        raise ValueError("Requirement must be attached to a valid project.")
    target_project_path = _resolved_target_project_path(
        project,
        override=str(getattr(body, "target_project_path_override", "") or "") or None,
        fallback=str(getattr(body, "target_project_path", "") or "") or None,
    )
    acceptance = normalize_acceptance_contract(dict(getattr(body, "acceptance_contract", None) or {}))
    provided_markdown = str(getattr(body, "acceptance_criteria_markdown", "") or "").strip()
    if provided_markdown:
        acceptance["markdown"] = provided_markdown
    requirement = RequirementRow(
        title=str(body.title).strip(),
        description_markdown=str(body.description_markdown).strip(),
        status="draft",
        phase="draft",
        workflow_state="draft",
        priority=str(getattr(body, "priority", "normal") or "normal"),
        source=str(getattr(body, "source", "manual") or "manual"),
        source_ref=getattr(body, "source_ref", None),
        intake_metadata_json=_json_dump(getattr(body, "intake_metadata", None) or {}),
        operating_manifest_id=int(getattr(body, "operating_manifest_id", 0) or 0) or None,
        goal_key=str(getattr(body, "goal_key", "") or "").strip() or None,
        requirement_candidate_id=int(getattr(body, "requirement_candidate_id", 0) or 0) or None,
        project_id=int(project.id),
        project_key=str(project.project_key or ""),
        project_display_name=str(project.display_name or ""),
        target_project_path=target_project_path,
        target_project_path_override=str(getattr(body, "target_project_path_override", "") or "").strip() or None,
        acceptance_contract_json=_json_dump(acceptance),
        execution_plan_json=_json_dump({}),
        assets_status="pending",
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    attachments = persist_requirement_attachments(int(requirement.id), getattr(body, "attachments", None))
    if attachments:
        for attachment in attachments:
            db.add(attachment)
        metadata = _json_load(requirement.intake_metadata_json, {})
        metadata = metadata if isinstance(metadata, dict) else {}
        metadata["attachment_count"] = len(attachments)
        metadata["attachment_context_files"] = requirement_attachment_context_files(int(requirement.id), attachments)
        requirement.intake_metadata_json = _json_dump(metadata)
        db.commit()
        db.refresh(requirement)
    requirement.phase = "planning"
    requirement.workflow_state = "planning"
    requirement.status = "draft"
    requirement.updated_at = utcnow()
    db.commit()
    auto_submit_detail: AgentFirstRequirementDetailOut | None = None
    if _testing_mode():
        try:
            _ensure_declarative_workflow_assets(db, requirement)
            db.commit()
            db.refresh(requirement)
            auto_submit_detail = _auto_submit_ready_requirement(db, int(requirement.id), trigger="requirement_assets_generated_sync")
        except Exception as exc:  # pragma: no cover - surfaced in tests through status
            db.rollback()
            requirement.assets_status = "failed"
            requirement.assets_error_message = f"plan agent failure: {exc}"
            requirement.updated_at = utcnow()
            db.commit()
    else:
        _enqueue_requirement_asset_generation(int(requirement.id))
    _notify_requirement_created(db, requirement)
    log_event(logger, "requirement_created", requirement_id=int(requirement.id), source=requirement.source)
    db.commit()
    return auto_submit_detail or build_requirement_detail(db, int(requirement.id))


def update_requirement(db: Session, requirement_id: int, body: Any) -> AgentFirstRequirementDetailOut:
    ensure_projects_materialized(db)
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    _assert_requirement_can_progress(requirement, "be edited")
    project = _project_for_requirement(db, requirement)
    if getattr(body, "title", None) is not None:
        requirement.title = str(body.title).strip()
    if getattr(body, "description_markdown", None) is not None:
        requirement.description_markdown = str(body.description_markdown).strip()
    if getattr(body, "acceptance_criteria_markdown", None) is not None:
        contract = _parse_acceptance_contract(requirement)
        contract["markdown"] = str(body.acceptance_criteria_markdown or "").strip()
        requirement.acceptance_contract_json = _json_dump(contract)
    if getattr(body, "acceptance_contract", None) is not None:
        contract = normalize_acceptance_contract(dict(getattr(body, "acceptance_contract", None) or {}))
        if not str(contract.get("markdown") or "").strip():
            contract["markdown"] = _acceptance_contract_markdown(contract)
        requirement.acceptance_contract_json = _json_dump(contract)
    if getattr(body, "priority", None) is not None:
        requirement.priority = str(body.priority)
    if getattr(body, "source_ref", None) is not None:
        requirement.source_ref = body.source_ref
    if getattr(body, "intake_metadata", None) is not None:
        requirement.intake_metadata_json = _json_dump(body.intake_metadata or {})
    if getattr(body, "project_id", None) is not None:
        next_project = get_project(db, int(body.project_id))
        if next_project is None:
            raise ValueError("Project not found.")
        project = next_project
        requirement.project_id = int(next_project.id)
        requirement.project_key = str(next_project.project_key or "")
        requirement.project_display_name = str(next_project.display_name or "")
    if getattr(body, "target_project_path_override", None) is not None:
        requirement.target_project_path_override = str(body.target_project_path_override or "").strip() or None
    if getattr(body, "target_project_path", None) is not None:
        requirement.target_project_path = str(body.target_project_path or "").strip() or None
    requirement.target_project_path = _resolved_target_project_path(
        project,
        override=str(getattr(requirement, "target_project_path_override", "") or "") or None,
        fallback=str(getattr(requirement, "target_project_path", "") or "") or None,
    )
    if getattr(body, "execution_plan", None) is not None:
        current = _parse_execution_plan(requirement)
        current.update({key: value for key, value in dict(body.execution_plan or {}).items() if value is not None})
        requirement.execution_plan_json = _json_dump(current)
    requirement.updated_at = utcnow()
    db.commit()
    return build_requirement_detail(db, requirement_id)


def requirement_attachment_file_path(db: Session, requirement_id: int, attachment_id: int) -> tuple[RequirementAttachmentRow, Path]:
    row = (
        db.query(RequirementAttachmentRow)
        .filter(RequirementAttachmentRow.requirement_id == requirement_id, RequirementAttachmentRow.id == attachment_id)
        .first()
    )
    if row is None:
        raise ValueError("Attachment not found.")
    path = Path(str(row.stored_path)).expanduser()
    if not path.exists():
        raise ValueError("Attachment file not found.")
    return row, path


def _select_declarative_workflow_key(requirement: RequirementRow) -> str:
    text = " ".join(
        [
            str(getattr(requirement, "title", "") or ""),
            str(getattr(requirement, "description_markdown", "") or ""),
            str(getattr(requirement, "intake_metadata_json", "") or ""),
        ]
    ).lower()
    markers = ("gateway", "5xx", "api success", "latency", "timeout", "reliability", "provider api")
    return "gateway_reliability_repair" if any(marker in text for marker in markers) else "agent_self_repair"


def _ensure_declarative_workflow_assets(db: Session, requirement: RequirementRow) -> None:
    _assert_requirement_can_progress(requirement, "generate workflow assets")
    workflow_key = _select_declarative_workflow_key(requirement)
    acceptance = _parse_acceptance_contract(requirement)
    if not str(acceptance.get("markdown") or "").strip():
        acceptance = _fallback_acceptance_contract(
            title=str(requirement.title or ""),
            description_markdown=str(requirement.description_markdown or ""),
            target_project_path=str(getattr(requirement, "target_project_path", "") or "") or None,
            required_checks=_required_checks_for_target(db, getattr(requirement, "target_project_path", None)),
        )
        requirement.acceptance_contract_json = _json_dump(acceptance)
    requirement.execution_plan_json = _json_dump(
        {
            "planning_mode": "declarative_workflow_factory",
            "workflow_key": workflow_key,
            "goal_summary": str(requirement.title or "").strip(),
            "summary_markdown": (
                f"Use declarative workflow `{workflow_key}`. State Machine Runner initializes blackboard, "
                "executes registered atoms, persists evidence, and routes high-risk outcomes to human gate."
            ),
            "steps": [],
            "planned_checks": [],
            "risks": [],
        }
    )
    requirement.assets_status = "ready"
    requirement.assets_error_message = None
    if str(getattr(requirement, "workflow_state", "") or "") == "planning":
        requirement.workflow_state = "ready"
    if str(getattr(requirement, "phase", "") or "") == "planning":
        requirement.phase = "ready"
    if str(getattr(requirement, "status", "") or "") in {"draft", "planning"}:
        requirement.status = "ready"
    requirement.updated_at = utcnow()
    db.flush()


def _background_requirement_asset_generation(requirement_id: int) -> None:
    from server.database import SessionLocal

    db = SessionLocal()
    try:
        requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
        if requirement is None:
            return
        if _is_inactive_requirement(requirement):
            return
        _ensure_declarative_workflow_assets(db, requirement)
        db.commit()
        _auto_submit_ready_requirement(db, requirement_id, trigger="requirement_assets_generated")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
        if requirement is not None:
            requirement.assets_status = "failed"
            requirement.assets_error_message = f"plan agent failure: {exc}"
            requirement.updated_at = utcnow()
            db.commit()
        log_event(logger, "requirement_assets_generation_failed", requirement_id=requirement_id, error_type=type(exc).__name__, error_message=str(exc))
    finally:
        db.close()


def _enqueue_requirement_asset_generation(requirement_id: int) -> None:
    threading.Thread(target=_background_requirement_asset_generation, args=(requirement_id,), daemon=True).start()


def generate_requirement_workflow_assets(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    _assert_requirement_can_progress(requirement, "generate workflow assets")
    if int(getattr(requirement, "active_workflow_run_id", 0) or 0) > 0:
        return build_requirement_detail(db, requirement_id)
    _ensure_declarative_workflow_assets(db, requirement)
    db.commit()
    return build_requirement_detail(db, requirement_id)


def regenerate_requirement_assets(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    _assert_requirement_can_progress(requirement, "regenerate workflow assets")
    if getattr(requirement, "active_workflow_run_id", None):
        raise ValueError("Workflow has already started; assets can no longer be regenerated.")
    requirement.phase = "planning"
    requirement.status = "draft"
    requirement.workflow_state = "planning"
    requirement.assets_status = "pending"
    requirement.assets_error_message = None
    requirement.execution_plan_json = _json_dump({})
    requirement.updated_at = utcnow()
    db.commit()
    if _testing_mode():
        _ensure_declarative_workflow_assets(db, requirement)
        db.commit()
    else:
        _enqueue_requirement_asset_generation(int(requirement.id))
    return build_requirement_detail(db, requirement_id)


def regenerate_requirement_plan(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    _assert_requirement_can_progress(requirement, "regenerate workflow assets")
    _ensure_declarative_workflow_assets(db, requirement)
    db.commit()
    return build_requirement_detail(db, requirement_id)


def requirement_workflow_readiness(db: Session, requirement_id: int) -> WorkflowReadinessOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    return _workflow_readiness_out(db, requirement)


def _create_requirement_declarative_workflow(
    db: Session,
    requirement: RequirementRow,
    *,
    triggered_by: str,
    workflow_key: str | None = None,
    run_immediately: bool = True,
) -> WorkflowRunRow:
    from server.services.workflows.declarative import create_declarative_workflow_run

    selected = str(workflow_key or "").strip() or _select_declarative_workflow_key(requirement)
    workflow_risk = _workflow_risk_context_for_requirement(requirement)
    return create_declarative_workflow_run(
        db,
        requirement=requirement,
        workflow_key=selected,
        triggered_by=triggered_by,
        initial_blackboard={
            "trigger": {
                "source": triggered_by,
                "requirement_id": int(requirement.id),
                "title": str(requirement.title or ""),
                "source_kind": str(getattr(requirement, "source", "") or ""),
                "source_ref": str(getattr(requirement, "source_ref", "") or ""),
                "project_key": str(getattr(requirement, "project_key", "") or ""),
                "target_project_path": str(getattr(requirement, "target_project_path", "") or ""),
                "ops_failure_detected": True,
                "gateway_drift_detected": selected == "gateway_reliability_repair",
            },
            "risk_level": workflow_risk["risk_level"],
            "risk_flags": workflow_risk["risk_flags"],
            "requirement": {
                "id": int(requirement.id),
                "title": str(requirement.title or ""),
                "priority": str(getattr(requirement, "priority", "") or "normal"),
                "source": str(getattr(requirement, "source", "") or ""),
                "source_ref": str(getattr(requirement, "source_ref", "") or ""),
            },
            "acceptance": _parse_acceptance_contract(requirement),
            "plan": _parse_execution_plan(requirement),
        },
        run_immediately=run_immediately,
    )


def _workflow_risk_context_for_requirement(requirement: RequirementRow) -> dict[str, Any]:
    """Derive declarative workflow risk context from requirement intake metadata."""

    metadata = _json_load(getattr(requirement, "intake_metadata_json", None), {})
    metadata = metadata if isinstance(metadata, dict) else {}
    severity = str(metadata.get("severity") or getattr(requirement, "priority", "") or "normal").strip().lower()
    source_kind = str(metadata.get("source_kind") or getattr(requirement, "source", "") or "").strip().lower()
    explicit_flags = metadata.get("risk_flags") if isinstance(metadata.get("risk_flags"), list) else []
    flags = {str(item).strip().lower() for item in explicit_flags if str(item).strip()}
    if severity in {"high", "critical"}:
        flags.add("production")
    if source_kind == "workflow_incident":
        flags.add("production")
    risk_level = "critical" if severity == "critical" else "high" if flags or severity == "high" else "normal"
    return {"risk_level": risk_level, "risk_flags": sorted(flags)}


def start_requirement_workflow(
    db: Session,
    requirement_id: int,
    *,
    workflow_key: str | None = None,
    triggered_by: str = "operator",
    run_immediately: bool = True,
) -> dict[str, Any]:
    from server.services.workflows.declarative import workflow_run_detail

    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    _assert_requirement_can_progress(requirement, "start workflow")
    existing_run_id = int(getattr(requirement, "active_workflow_run_id", 0) or 0)
    if existing_run_id > 0:
        return workflow_run_detail(db, existing_run_id)
    if _assets_status(requirement) != "ready":
        _ensure_declarative_workflow_assets(db, requirement)
        db.flush()
    run = _create_requirement_declarative_workflow(
        db,
        requirement,
        triggered_by=triggered_by,
        workflow_key=workflow_key,
        run_immediately=run_immediately,
    )
    db.flush()
    return workflow_run_detail(db, int(run.id))


def _auto_submit_ready_requirement(db: Session, requirement_id: int, *, trigger: str) -> AgentFirstRequirementDetailOut | None:
    if not _auto_submit_enabled():
        return None
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None or getattr(requirement, "active_workflow_run_id", None):
        return None
    if _is_inactive_requirement(requirement):
        return None
    if _assets_status(requirement) != "ready":
        return None
    return submit_requirement(db, requirement_id)


def submit_requirement(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    _assert_requirement_can_progress(requirement, "be submitted")
    if getattr(requirement, "active_workflow_run_id", None):
        return build_requirement_detail(db, requirement_id)
    if not str(requirement.title or "").strip() or not str(requirement.description_markdown or "").strip():
        raise ValueError("Requirement title and description are required before submit.")
    if _assets_status(requirement) != "ready":
        if _assets_status(requirement) == "failed":
            raise ValueError(_assets_error_message(requirement) or "计划生成失败，请先重新生成。")
        raise ValueError("验收标准与执行计划仍在生成中，请稍后再提交。")
    requirement.updated_at = utcnow()
    requirement.phase = "ready"
    requirement.status = "ready"
    requirement.workflow_state = "ready"
    workflow_run = _create_requirement_declarative_workflow(db, requirement, triggered_by="requirement_submit")
    db.commit()
    detail = build_requirement_detail(db, requirement_id)
    log_event(logger, "requirement_declarative_workflow_created", requirement_id=int(requirement.id), workflow_run_id=int(workflow_run.id), workflow_key=workflow_run.workflow_key)
    db.commit()
    return detail


def revise_requirement(db: Session, requirement_id: int, body: Any) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    _assert_requirement_can_progress(requirement, "be revised")
    update_requirement(db, requirement_id, body)
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    requirement.phase = "draft"
    requirement.status = "draft"
    requirement.workflow_state = "draft"
    requirement.attention_reason = None
    requirement.updated_at = utcnow()
    db.commit()
    return build_requirement_detail(db, requirement_id)


def cancel_requirement(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    if str(getattr(requirement, "status", "") or "") == "deleted":
        raise ValueError("Deleted requirement cannot be closed.")
    if getattr(requirement, "active_workflow_run_id", None):
        raise ValueError("Requirements with workflow history cannot be closed; handle the workflow gate instead.")
    requirement.phase = "cancelled"
    requirement.status = "cancelled"
    requirement.workflow_state = "cancelled"
    requirement.completed_at = utcnow()
    db.commit()
    return build_requirement_detail(db, requirement_id)


def delete_requirement(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    if str(getattr(requirement, "status", "") or "") == "cancelled":
        raise ValueError("Closed requirement cannot be deleted.")
    if getattr(requirement, "active_workflow_run_id", None):
        raise ValueError("Requirements with workflow history cannot be deleted.")
    if str(getattr(requirement, "phase", "") or requirement.status or "draft") not in {"draft", "planning", "ready", "needs_revision", "blocked"}:
        raise ValueError("Only pre-workflow requirements can be deleted.")
    requirement.phase = "deleted"
    requirement.status = "deleted"
    requirement.workflow_state = "cancelled"
    requirement.updated_at = utcnow()
    db.commit()
    return build_requirement_detail(db, requirement_id)


def _raw_planning_prompt(db: Session, requirement: RequirementRow) -> str:
    return "\n".join(
        [
            "# Requirement",
            f"ID: {int(requirement.id)}",
            f"Title: {requirement.title}",
            "",
            "# Description",
            str(requirement.description_markdown or ""),
            "",
            "# Acceptance",
            _parse_acceptance_markdown(requirement) or json.dumps(_parse_acceptance_contract(requirement), ensure_ascii=False, indent=2),
        ]
    )


def _strip_markdown_fence(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:markdown|md)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    return value.strip()


def _generate_plan_brief_markdown_with_agent(
    db: Session,
    requirement: RequirementRow,
    *,
    acceptance_contract: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    planner_backend = resolve_planner_backend()
    model_name = resolve_planner_model(planner_backend)
    targets = _target_projects_for_requirement(db, requirement)
    target_path = Path(targets[0]).expanduser().resolve() if targets else PROJECT_ROOT.resolve()
    output_path = PROJECT_ROOT / "runtime" / "plans" / f"req-{int(requirement.id)}-plan.md"
    uses_codex_session = planner_backend in {"codex_cli", "codex_sdk"}
    metadata: dict[str, Any] = {
        "planning_mode": "adapter_plan",
        "planning_backend": planner_backend,
        "planning_project_root": str(target_path),
        "planning_requirement_id": int(requirement.id),
        "planning_target_roots": [str(Path(item).expanduser().resolve()) for item in targets] or [str(target_path)],
        "planning_model": model_name,
    }
    resume_session_id = None
    project_session = None
    if uses_codex_session:
        session_key = build_planner_project_session_key(project_root=target_path)
        metadata["planning_session_scope"] = "project"
        metadata["planning_session_key"] = session_key
        project_session = find_reusable_planner_project_session(db, project_root=target_path)
        previous_plan = _parse_execution_plan(requirement)
        previous_session_id = str(previous_plan.get("planning_session_id") or "").strip() or None
        resume_session_id = (str(getattr(project_session, "thread_id", "") or "").strip() if project_session else previous_session_id) or None
        metadata["planning_resume_source"] = "project" if project_session is not None else ("requirement" if previous_session_id else "new")
    else:
        metadata["planning_resume_source"] = "not_supported"
    response = generate_planner_text(
        PlannerRequest(
            prompt=_raw_planning_prompt(db, requirement),
            system_prompt="" if uses_codex_session else "Create a concise Markdown implementation plan.",
            raw_prompt=uses_codex_session,
            cwd=target_path,
            output_path=output_path,
            add_dirs=[PROJECT_ROOT],
            resume_session_id=resume_session_id,
            metadata=metadata,
        )
    )
    plan_markdown = _strip_markdown_fence(response.text)
    if not plan_markdown:
        raise ValueError("plan agent returned empty markdown")
    planning_session_id = str(metadata.get("planning_session_id") or "").strip()
    if planning_session_id:
        upsert_planner_project_session(
            db,
            project_root=target_path,
            thread_id=planning_session_id,
            status="completed",
            workflow_run_id=getattr(requirement, "active_workflow_run_id", None),
            resume_count=int(getattr(project_session, "resume_count", 0) or 0) + (1 if project_session is not None else 0),
            metadata=metadata,
        )
    return plan_markdown, metadata
