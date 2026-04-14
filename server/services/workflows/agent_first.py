"""Agent-first requirement, execution, validation, and release flow."""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, cast

import yaml
from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.config import ORCHESTRATION_BACKEND, PROJECT_ROOT
from server.database import (
    AgentRow,
    ApprovalRow,
    ApprovalRequestRow,
    ArtifactRow,
    CodexSessionRow,
    DeploymentRecordRow,
    ExecutionNodeRow,
    ExecutionRunRow,
    ProjectRow,
    ReleaseRecordRow,
    RequirementRow,
    RequirementAttachmentRow,
    RequirementAcceptanceCheckRow,
    StepInputBindingRow,
    TaskLogRow,
    TaskRow,
    ValidationRecordRow,
    WorkflowRunRow,
    WorkflowStepEventRow,
    WorkflowStepDependencyRow,
    WorkflowStepRow,
    SessionLocal,
    utcnow,
)
from server.schemas import (
    AgentFirstRequirementApprovalOut,
    AgentFirstRequirementDetailOut,
    AgentFirstRequirementOut,
    ExecutionActivityEventOut,
    ExecutionChangedFileOut,
    ExecutionFilePreviewOut,
    ExecutionNodeOut,
    ExecutionRuntimeSummaryOut,
    ExecutionRunDetailOut,
    ExecutionRunOut,
    ReleaseCandidateOut,
    ReleaseDetailOut,
    ReleaseRecordSlimOut,
    ProjectOut,
    RequirementAttachmentOut,
    ValidationCheckResultOut,
    ValidationRecordSlimOut,
    VerificationPlanOut,
)
from server.logging_utils import get_logger, log_event
from server.services.agents.execution_resolver import suggest_task_execution
from server.services.delivery.deployment_governance import (
    list_requirement_deployment_records,
    trigger_requirement_deployment,
)
from server.services.delivery.pull_request import sync_requirement_review_pr
from server.services.delivery.vcs import execute_requirement_delivery_vcs, prepare_requirement_delivery_branch
from server.services.projects.policy import (
    project_policy_summary_markdown,
    project_policy_to_dict,
    resolve_project_policies_for_target,
)
from server.services.projects.project_center import ensure_projects_materialized, get_project, project_to_dict, resolve_project
from server.services.requirements.acceptance import normalize_acceptance_contract
from server.services.requirements.attachments import (
    persist_requirement_attachments,
    requirement_attachment_context_files,
    serialize_requirement_attachment,
)
from server.services.runtime.alerting import build_ops_url, deliver_lark_notification, notification_service_label
from server.services.runtime.task_runner import dispatch
from server.services.requirements.approval import (
    evaluate_requirement_execution_approval,
    normalize_requirement_approval_status,
)
from server.services.workflows.planner_provider import call_full_plan_provider, planner_model_name, planner_provider_name
from server.services.workflows.verification_agent import verify_with_agent
from server.services.workflows.orchestrator.file_changes import (
    _load_task_file_changes,
    _normalize_task_file_change_payload,
    _task_changed_files_from_payload,
)
from server.services.workflows.orchestrator import pause_task as pause_legacy_task
from server.services.agents.llm_adapter import get_provider

logger = get_logger("ops-dashboard.workflow_agent_first")
_MAX_EXECUTION_RETRIES = 1


def _testing_mode() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _json_load(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    return data


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _split_target_projects(value: str | None) -> list[str]:
    if not value:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in str(value).splitlines():
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug[:48] or "requirement"


def _parse_acceptance_markdown(requirement: RequirementRow) -> str:
    payload = _json_load(getattr(requirement, "acceptance_contract_json", None), {})
    if isinstance(payload, dict):
        return str(payload.get("markdown") or "").strip()
    return ""


def _parse_acceptance_contract(requirement: RequirementRow) -> dict[str, Any]:
    return normalize_acceptance_contract(
        _json_load(getattr(requirement, "acceptance_contract_json", None), {})
    )


def _parse_execution_plan(requirement: RequirementRow) -> dict[str, Any]:
    payload = _json_load(getattr(requirement, "execution_plan_json", None), {})
    return dict(payload) if isinstance(payload, dict) else {}


def _parse_run_plan_snapshot(run: ExecutionRunRow) -> dict[str, Any]:
    payload = _json_load(getattr(run, "plan_snapshot_json", None), {})
    return dict(payload) if isinstance(payload, dict) else {}


def _assets_status(requirement: RequirementRow) -> str:
    status = str(getattr(requirement, "assets_status", "") or "").strip()
    if status in {"pending", "ready", "failed"}:
        return status
    if str(getattr(requirement, "acceptance_contract_json", "") or "").strip():
        return "ready"
    if str(getattr(requirement, "execution_plan_json", "") or "").strip():
        return "ready"
    legacy_status = str(getattr(requirement, "status", "") or "").strip()
    if legacy_status in {"ready", "running", "blocked", "needs_revision", "delivery_ready", "done"}:
        return "ready"
    return "pending"


def _assets_error_message(requirement: RequirementRow) -> str | None:
    message = str(getattr(requirement, "assets_error_message", "") or "").strip()
    return message or None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _requirement_status_from_phase(phase: str) -> str:
    token = str(phase or "draft").strip() or "draft"
    if token == "deleted":
        return "deleted"
    if token in {"draft", "planning"}:
        return "draft"
    if token in {"branch_preparing", "branch_prepared", "ready"}:
        return "ready"
    if token == "awaiting_execution_approval":
        return "blocked"
    if token in {"executing", "verifying"}:
        return "running"
    if token in {"blocked", "recovering"}:
        return "blocked"
    if token == "needs_revision":
        return "needs_revision"
    if token in {"delivery_ready", "pr_opened"}:
        return "delivery_ready"
    if token == "done":
        return "done"
    return token


def _execution_status_from_phase(phase: str) -> str:
    token = str(phase or "queued").strip() or "queued"
    if token == "queued":
        return "queued"
    if token == "branch_preparing":
        return "queued"
    if token == "executing":
        return "running"
    if token == "verifying":
        return "validating"
    if token == "delivery_ready":
        return "succeeded"
    if token == "pr_opening":
        return "succeeded"
    if token == "completed":
        return "succeeded"
    if token in {"blocked", "recovering"}:
        return "blocked"
    return token


def _latest_task_for_run(db: Session, run: ExecutionRunRow) -> TaskRow | None:
    if run.latest_task_id is None:
        return None
    return db.query(TaskRow).filter(TaskRow.id == run.latest_task_id).first()


def _latest_session_for_run_task(db: Session, run: ExecutionRunRow) -> CodexSessionRow | None:
    if run.latest_task_id is None:
        return None
    return (
        db.query(CodexSessionRow)
        .filter(CodexSessionRow.current_task_id == run.latest_task_id)
        .order_by(CodexSessionRow.id.desc())
        .first()
    )


def _is_current_execution(db: Session, run: ExecutionRunRow) -> bool:
    latest = _latest_execution_run(db, int(run.requirement_id))
    return latest is not None and int(latest.id) == int(run.id)


def _execution_allowed_actions(
    run: ExecutionRunRow,
    release: ReleaseRecordRow | None = None,
    *,
    is_current_execution: bool = True,
    has_paused_node: bool = False,
) -> list[str]:
    phase = str(getattr(run, "phase", "") or run.status or "queued")
    status = str(getattr(run, "status", "") or _execution_status_from_phase(phase))
    actions = ["view", "view_requirement"]
    if not is_current_execution:
        if release is not None and int(getattr(release, "execution_run_id", 0) or 0) == int(run.id) and str(getattr(release, "pr_url", "") or "").strip():
            actions.append("view_pr")
        return sorted(set(actions))
    if phase in {"queued", "branch_preparing"} or status == "queued":
        actions.append("start")
    if phase == "executing" or status == "running":
        actions.append("pause")
    if status == "paused" or has_paused_node:
        actions.append("resume")
    if status in {"blocked", "failed"} or phase in {"blocked", "recovering"}:
        actions.append("retry")
    if status in {"succeeded", "completed"} or phase in {"delivery_ready", "pr_opening", "completed"}:
        if release is None or str(release.status or "") != "pr_opened":
            actions.append("open_pr")
        else:
            actions.append("view_pr")
    return sorted(set(actions))


def _requirement_allowed_actions(
    requirement: RequirementRow,
    latest_execution: ExecutionRunRow | None,
    latest_release: ReleaseRecordRow | None,
) -> list[str]:
    phase = str(getattr(requirement, "phase", "") or requirement.status or "draft")
    assets_status = _assets_status(requirement)
    actions = ["view"]
    if latest_execution is None and phase in {"draft", "planning", "awaiting_execution_approval", "needs_revision", "blocked"}:
        actions.append("edit")
    if latest_execution is None and assets_status == "ready" and phase in {"draft", "needs_revision"}:
        actions.append("submit")
    if latest_execution is None and _assets_status(requirement) == "failed" and phase in {"draft", "needs_revision", "blocked"}:
        actions.append("regenerate_assets")
    if phase == "awaiting_execution_approval" and str(requirement.approval_status or "") == "pending_approval":
        actions.extend(["approve", "reject"])
    if latest_execution is None and phase in {"draft", "planning", "awaiting_execution_approval", "needs_revision", "blocked"}:
        actions.append("delete")
    if latest_execution is not None:
        actions.append("view_execution")
    if latest_release is not None:
        actions.append("view_release")
        if str(latest_release.status or "") == "pr_opened":
            actions.append("view_pr")
    return sorted(set(actions))


def _derive_execution_recovery_status(
    db: Session,
    run: ExecutionRunRow,
    nodes: list[ExecutionNodeRow],
) -> tuple[str | None, CodexSessionRow | None]:
    task = _latest_task_for_run(db, run)
    session = _latest_session_for_run_task(db, run)
    if task is None:
        return None, session
    task_status = str(getattr(task, "status", "") or "")
    runtime_backend = str(getattr(task, "runtime_backend", "") or "").strip()
    runtime_session_id = str(getattr(task, "runtime_session_id", "") or "").strip()
    if task_status != "running":
        return None, session
    if runtime_backend == "codex_cli":
        if runtime_session_id or session is not None:
            return "recovering", session
        return None, session
    return None, session


def _execution_reason_payload(
    run: ExecutionRunRow,
    requirement: RequirementRow,
    *,
    validation: ValidationRecordRow | None = None,
    release: ReleaseRecordRow | None = None,
    nodes: list[ExecutionNodeRow] | None = None,
) -> tuple[str | None, str | None, str | None]:
    phase = str(getattr(run, "phase", "") or run.status or "queued")
    status = str(getattr(run, "status", "") or _execution_status_from_phase(phase))
    if status == "queued" or phase in {"queued", "branch_preparing"}:
        if bool(run.approval_required) and str(requirement.approval_status or "") not in {"approved", "waived"}:
            return "等待审批", "approval_blocked", "Requirement must be approved before execution starts."
        if release is not None and int(getattr(release, "execution_run_id", 0) or 0) == int(run.id) and str(release.status or "") == "release_blocked":
            message = str(getattr(release, "notes", "") or "").strip() or "Delivery branch preparation is blocked."
            return f"启动失败：{message}", "branch_preparation_blocked", message
        if str(getattr(run, "recovery_status", "") or "").strip():
            message = f"Execution is recovering: {str(run.recovery_status)}"
            return "等待恢复", "runtime_recovery_blocked", message
        if phase == "branch_preparing":
            return "等待分支准备", None, None
        return "等待启动", None, None
    if status in {"blocked", "failed"} or phase in {"blocked", "recovering"}:
        if validation is not None:
            validation_status = str(getattr(validation, "status", "") or "").strip()
            if validation_status in {"needs_revision", "failed", "inconclusive"}:
                summary = str(getattr(validation, "summary_markdown", "") or "").strip()
                reasoning = str(getattr(validation, "reasoning_markdown", "") or "").strip()
                suggested = str(getattr(validation, "suggested_next_action", "") or "").strip()
                resolution_path = str(getattr(validation, "resolution_path", "") or "").strip()
                resolution_reason = str(getattr(validation, "resolution_reason", "") or "").strip()
                followup_requirement_id = int(getattr(validation, "followup_requirement_id", 0) or 0) or None
                if resolution_path == "create_followup_requirement":
                    message = resolution_reason or summary or reasoning or "Verification created a follow-up requirement."
                    if followup_requirement_id is not None:
                        message = f"{message} Follow-up requirement: #{followup_requirement_id}"
                    return None, "verification_followup_requirement", message
                if resolution_path == "route_to_human":
                    return None, "verification_routed_to_human", resolution_reason or summary or reasoning or "Verification requires human review."
                if validation_status == "needs_revision":
                    message = summary or reasoning or "Verification agent requested revisions before execution can continue."
                    if suggested:
                        message = f"{message} Suggested action: {suggested}"
                    return None, "verification_needs_revision", message
                if validation_status == "failed":
                    return None, "verification_failed", summary or reasoning or "Verification failed for this execution."
                return None, "verification_inconclusive", summary or reasoning or "Verification was inconclusive and needs more evidence."
        if release is not None and int(getattr(release, "execution_run_id", 0) or 0) == int(run.id) and str(release.status or "") == "release_blocked":
            message = str(getattr(release, "notes", "") or "").strip() or "Delivery branch preparation is blocked."
            return None, "branch_preparation_blocked", message
        if phase == "recovering" or str(getattr(run, "recovery_status", "") or "").strip():
            return None, "runtime_recovery_blocked", "Execution recovery is still in progress or failed."
        if nodes and any(str(getattr(node, "status", "") or "") == "paused" for node in nodes):
            return None, "manual_pause", "Execution was paused and can be resumed."
    return None, None, None


def reconcile_execution_state(db: Session, execution_run_id: int | ExecutionRunRow) -> ExecutionRunRow:
    run = execution_run_id if isinstance(execution_run_id, ExecutionRunRow) else db.query(ExecutionRunRow).filter(ExecutionRunRow.id == execution_run_id).first()
    if run is None:
        raise ValueError("Execution run not found.")
    original_status = str(getattr(run, "status", "") or "").strip()
    nodes = (
        db.query(ExecutionNodeRow)
        .filter(ExecutionNodeRow.execution_run_id == run.id)
        .order_by(ExecutionNodeRow.sequence_no.asc(), ExecutionNodeRow.id.asc())
        .all()
    )
    if not nodes:
        current_status = str(getattr(run, "status", "") or "queued")
        current_phase = str(getattr(run, "phase", "") or "")
        if current_phase and not (current_phase == "queued" and current_status not in {"", "queued"}):
            run.phase = current_phase
        elif current_status == "running":
            run.phase = "executing"
        elif current_status == "validating":
            run.phase = "verifying"
        elif current_status in {"failed", "paused", "blocked"}:
            run.phase = "blocked"
        elif current_status == "succeeded":
            run.phase = "completed"
        else:
            run.phase = "queued"
        run.status = "failed" if original_status == "failed" and run.phase == "blocked" else _execution_status_from_phase(run.phase)
        run.recovery_status = None
        db.flush()
        return run
    statuses: list[str] = []
    for node in nodes:
        task = db.query(TaskRow).filter(TaskRow.id == node.task_id).first() if node.task_id else None
        task_status = _node_task_status(task)
        if task_status == "completed":
            node.status = "completed"
            node.runtime_backend = str(getattr(task, "runtime_backend", "") or "") or node.runtime_backend
            node.runtime_provider = str(getattr(task, "runtime_provider", "") or "") or node.runtime_provider
            node.runtime_model = str(getattr(task, "runtime_model", "") or "") or node.runtime_model
            node.summary_markdown = str(getattr(task, "output_content", "") or "").strip()[:4000] or node.summary_markdown
            node.completed_at = getattr(task, "completed_at", None) or utcnow()
        elif task_status in {"failed", "rejected"}:
            node.status = "failed"
            node.summary_markdown = str(getattr(task, "last_error_message", "") or "").strip() or node.summary_markdown
            node.completed_at = getattr(task, "completed_at", None) or utcnow()
        elif task_status in {"running", "pending_approval"}:
            node.status = "running"
            node.started_at = getattr(task, "started_at", None) or node.started_at or utcnow()
        elif task_status in {"paused", "cancelled"}:
            node.status = "paused"
        statuses.append(str(node.status or "queued"))
    validation = (
        db.query(ValidationRecordRow)
        .filter(ValidationRecordRow.execution_run_id == run.id)
        .order_by(ValidationRecordRow.id.desc())
        .first()
    )
    latest_release = _latest_release(db, int(run.requirement_id))
    recovery_status, _session = _derive_execution_recovery_status(db, run, nodes)
    if recovery_status == "recovering":
        run.phase = "recovering"
    elif "running" in statuses:
        run.phase = "executing"
    elif "failed" in statuses:
        run.phase = "blocked"
    elif "paused" in statuses:
        run.phase = "blocked"
    elif all(status == "completed" for status in statuses):
        if validation is None:
            run.phase = "verifying"
            if run.verification_requested_at is None:
                run.verification_requested_at = utcnow()
                db.flush()
                _enqueue_execution_verification(int(run.id))
        elif str(validation.status or "") == "passed":
            if latest_release is not None and str(latest_release.status or "") == "pr_opened":
                run.phase = "completed"
            elif latest_release is not None and str(latest_release.status or "") == "branch_prepared":
                run.phase = "delivery_ready"
            else:
                run.phase = "delivery_ready"
        else:
            run.phase = "blocked"
    else:
        run.phase = "queued"
    run.status = "failed" if original_status == "failed" and run.phase == "blocked" else _execution_status_from_phase(str(run.phase or "queued"))
    run.recovery_status = recovery_status
    run.updated_at = utcnow()
    db.flush()
    return run


def reconcile_requirement_state(db: Session, requirement_id: int | RequirementRow) -> RequirementRow:
    requirement = requirement_id if isinstance(requirement_id, RequirementRow) else db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    if str(getattr(requirement, "workflow_family", "agent_first") or "agent_first") != "agent_first":
        db.flush()
        return requirement
    latest_execution = _latest_execution_run(db, int(requirement.id))
    latest_release = _latest_release(db, int(requirement.id))
    validation = _latest_validation(db, int(requirement.id))
    assets_status = _assets_status(requirement)
    approval_status = str(requirement.approval_status or "pending_approval")
    legacy_status = str(getattr(requirement, "status", "") or "").strip()
    current_phase = str(getattr(requirement, "phase", "") or "").strip()
    recovery_status: str | None = None
    if latest_execution is not None:
        latest_execution = reconcile_execution_state(db, latest_execution)
        recovery_status = str(getattr(latest_execution, "recovery_status", "") or "").strip() or None
    if str(requirement.status or "") == "deleted":
        requirement.phase = "deleted"
    elif recovery_status == "recovering":
        requirement.phase = "recovering"
    elif latest_execution is not None:
        execution_phase = str(getattr(latest_execution, "phase", "") or latest_execution.status or "queued")
        if execution_phase in {"queued", "branch_preparing"}:
            requirement.phase = "branch_preparing" if execution_phase == "branch_preparing" else "branch_prepared"
        elif execution_phase in {"executing", "verifying", "recovering"}:
            requirement.phase = execution_phase
        elif execution_phase == "delivery_ready":
            requirement.phase = "delivery_ready"
        elif execution_phase == "completed":
            requirement.phase = "done" if latest_release is not None and str(latest_release.status or "") == "pr_opened" else "delivery_ready"
        elif execution_phase == "blocked":
            resolution_path = str(getattr(validation, "resolution_path", "") or "").strip() if validation is not None else ""
            if resolution_path in {"create_followup_requirement", "route_to_human"}:
                requirement.phase = "blocked"
            else:
                requirement.phase = "needs_revision" if validation is not None and str(validation.status or "") in {"failed", "needs_revision"} else "blocked"
        else:
            requirement.phase = "branch_prepared"
    elif latest_release is not None and str(latest_release.status or "") == "pr_opened":
        requirement.phase = "done"
    elif latest_release is not None and str(latest_release.status or "") == "branch_prepared":
        requirement.phase = "delivery_ready" if validation is not None and str(validation.status or "") == "passed" else "branch_prepared"
    elif approval_status == "rejected":
        requirement.phase = "needs_revision"
    elif approval_status == "pending_approval" and _approval_required(db, requirement):
        requirement.phase = "awaiting_execution_approval"
    elif approval_status in {"approved", "waived"} and assets_status == "ready":
        requirement.phase = "branch_prepared"
    elif assets_status == "failed":
        requirement.phase = "blocked"
    elif assets_status == "pending":
        requirement.phase = "planning"
    elif legacy_status == "needs_revision":
        requirement.phase = "needs_revision"
    elif current_phase and not (current_phase == "draft" and legacy_status not in {"", "draft"}):
        requirement.phase = current_phase
    elif legacy_status == "running":
        requirement.phase = "executing"
    elif legacy_status == "ready":
        requirement.phase = "branch_prepared"
    elif legacy_status == "blocked":
        requirement.phase = "blocked"
    elif legacy_status == "delivery_ready":
        requirement.phase = "delivery_ready"
    elif legacy_status == "done":
        requirement.phase = "done"
    else:
        requirement.phase = "draft"
    requirement.status = _requirement_status_from_phase(str(requirement.phase or "draft"))
    requirement.recovery_status = recovery_status
    db.flush()
    return requirement


def reconcile_runtime_recovery(db: Session) -> None:
    runs = (
        db.query(ExecutionRunRow)
        .join(RequirementRow, RequirementRow.id == ExecutionRunRow.requirement_id)
        .filter(RequirementRow.workflow_family == "agent_first")
        .all()
    )
    for run in runs:
        reconcile_execution_state(db, run)
        reconcile_requirement_state(db, int(run.requirement_id))
    db.commit()


def _acceptance_contract_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    done_criteria = [str(item).strip() for item in payload.get("done_criteria") or [] if str(item).strip()]
    verification_checks = [
        item for item in payload.get("verification_checks") or [] if isinstance(item, dict) and str(item.get("label") or "").strip()
    ]
    scope_constraints = [str(item).strip() for item in payload.get("scope_constraints") or [] if str(item).strip()]
    delivery_expectation = str(payload.get("delivery_expectation") or "").strip()

    if done_criteria:
        lines.append("### Done Criteria")
        lines.extend([f"- {item}" for item in done_criteria])
    if verification_checks:
        if lines:
            lines.append("")
        lines.append("### Verification Focus")
        for item in verification_checks:
            label = str(item.get("label") or "").strip()
            kind = str(item.get("kind") or "evidence").strip() or "evidence"
            suffix = " (command evidence)" if kind == "command" else " (evidence review)" if kind == "evidence" else ""
            lines.append(f"- {label}{suffix}")
    if scope_constraints:
        if lines:
            lines.append("")
        lines.append("### Scope Constraints")
        lines.extend([f"- {item}" for item in scope_constraints])
    if delivery_expectation:
        if lines:
            lines.append("")
        lines.append("### Delivery Expectation")
        lines.append(f"- {delivery_expectation}")
    return "\n".join(lines).strip()


def _fallback_acceptance_contract(
    *,
    title: str,
    description_markdown: str,
    target_project_path: str | None,
    required_checks: list[str] | None = None,
) -> dict[str, Any]:
    subject = str(title or "").strip() or "this requirement"
    description = " ".join(str(description_markdown or "").split())
    scope_hint = Path(target_project_path).name if str(target_project_path or "").strip() else "the target project"
    contract = normalize_acceptance_contract(
        {
            "done_criteria": [
                f"{subject} is delivered in {scope_hint} and matches the requested outcome.",
                "The change is observable in code, UI, API behavior, or persisted runtime evidence.",
                "No unrelated regressions are introduced outside the requested scope.",
            ],
            "verification_checks": [
                {"label": "Verification agent should review changed files, raw execution output, and any targeted command evidence from this run.", "command": None, "kind": "evidence"}
            ],
            "scope_constraints": [
                f"Keep edits scoped to `{scope_hint}` unless the requirement explicitly calls for wider coordination.",
                "Do not introduce unrelated refactors while delivering this requirement.",
            ],
            "delivery_expectation": "Prepare a branch and PR-ready delivery record when implementation succeeds.",
        }
    )
    if description:
        contract["done_criteria"] = list(contract.get("done_criteria") or []) + [f"Delivered behavior satisfies: {description[:220].rstrip(' ,.;')}."]
    contract["markdown"] = _acceptance_contract_markdown(contract)
    return contract


_ACCEPTANCE_SYSTEM_PROMPT = """You generate requirement acceptance contracts for an agent-driven software delivery system.
Return strict JSON only with this schema:
{
  "done_criteria": ["short, observable completion criteria"],
  "verification_checks": [
    {"label": "what the later verification agent should look for", "command": "optional command", "kind": "command|evidence"}
  ],
  "scope_constraints": ["scope boundary"],
  "delivery_expectation": "short delivery expectation"
}

Rules:
- Produce 3 to 5 concrete acceptance items total.
- Focus on outcome and scope, not implementation steps.
- Keep wording concise and actionable.
- Do not over-specify repo-wide test commands; the verification agent will design final verification after execution evidence exists.
- Only include explicit commands when the requirement itself makes a concrete targeted command unavoidable.
- Do not add markdown fences or commentary.
"""

_PLAN_BRIEF_SYSTEM_PROMPT = """You are the plan agent in an agent-first software delivery harness.
Read the requirement, acceptance contract, target paths, and delivery context.
Return a concise but complete Markdown execution plan that a human can read directly.

Rules:
- Write a real delivery plan, not JSON and not a workflow skeleton.
- Do not include generic headings like "Research context", "Plan implementation", or "Close requirement" unless the requirement truly needs them.
- Focus on the scoped change, likely files or areas, verification approach, risks, and delivery outcome.
- Prefer direct implementation wording over meta-process wording.
- Do not wrap the response in code fences.
"""


def _generate_acceptance_contract_with_agent(
    *,
    title: str,
    description_markdown: str,
    target_project_path: str | None,
    required_checks: list[str] | None = None,
) -> dict[str, Any]:
    if _testing_mode():
        raise RuntimeError("skip_external_acceptance_generation_during_tests")
    prompt = "\n".join(
        [
            f"Title: {title}",
            f"Target project path: {target_project_path or '-'}",
            f"Known required checks: {', '.join(required_checks or []) or 'none'}",
            "",
            description_markdown.strip(),
        ]
    ).strip()
    provider_name = planner_provider_name()
    provider = get_provider(provider_name)
    model_name = planner_model_name(provider_name)
    text, _tokens = call_full_plan_provider(
        provider_name=provider_name,
        provider=provider,
        prompt=prompt,
        model_name=model_name,
        system_prompt=_ACCEPTANCE_SYSTEM_PROMPT,
    )
    payload = json.loads(str(text or "").strip())
    if not isinstance(payload, dict):
        raise ValueError("acceptance contract payload must be an object")
    contract = normalize_acceptance_contract(payload)
    contract["markdown"] = _acceptance_contract_markdown(contract)
    return contract


def _strip_markdown_fence(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:markdown|md)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    return value.strip()


def _verification_strategy_lines(contract: dict[str, Any]) -> list[str]:
    checks = [
        item for item in contract.get("verification_checks") or []
        if isinstance(item, dict) and str(item.get("label") or "").strip()
    ]
    if not checks:
        return ["Provide execution evidence that proves the requested outcome is complete."]
    lines: list[str] = []
    for item in checks:
        label = str(item.get("label") or "").strip()
        command = str(item.get("command") or "").strip()
        kind = str(item.get("kind") or "evidence").strip() or "evidence"
        if command:
            lines.append(f"{label} (`{command}`)")
        elif kind == "manual":
            lines.append(f"{label} (reason about the result from evidence and raw output)")
        else:
            lines.append(label)
    return lines


def _fallback_plan_brief_markdown(
    db: Session,
    requirement: RequirementRow,
    *,
    acceptance_contract: dict[str, Any],
) -> str:
    targets = _target_projects_for_requirement(db, requirement)
    attachment_lines = _attachment_prompt_lines(db, int(requirement.id))
    target_lines = "\n".join([f"- `{item}`" for item in targets]) if targets else "- Scope to the selected project."
    attachment_markdown = ("\n".join(attachment_lines) + "\n\n") if attachment_lines else ""
    verification_lines = "\n".join([f"- {item}" for item in _verification_strategy_lines(acceptance_contract)])
    risks = "\n".join(
        [
            "- Keep edits scoped to the selected project and avoid unrelated regressions.",
            "- Capture commands run, changed files, and raw output so the verification agent can make a decision.",
        ]
    )
    delivery_expectation = str(acceptance_contract.get("delivery_expectation") or "").strip() or "Prepare a PR-ready branch when implementation and verification pass."
    return (
        f"## Summary\n\n"
        f"{str(requirement.title or '').strip()}\n\n"
        f"{str(requirement.description_markdown or '').strip()}\n\n"
        f"## Planned Changes\n\n"
        f"{target_lines}\n\n"
        f"{attachment_markdown}"
        f"## Implementation Approach\n\n"
        f"- Implement the requested change directly in the scoped project.\n"
        f"- Update code, docs, and tests together only where the requirement explicitly calls for them.\n"
        f"- Keep the final output explicit about files changed, commands run, and remaining risk.\n\n"
        f"## Verification Strategy\n\n"
        f"{verification_lines}\n\n"
        f"## Risks\n\n"
        f"{risks}\n\n"
        f"## Delivery\n\n"
        f"- {delivery_expectation}"
    ).strip()


def _generate_plan_brief_markdown_with_agent(
    db: Session,
    requirement: RequirementRow,
    *,
    acceptance_contract: dict[str, Any],
) -> str:
    if _testing_mode():
        raise RuntimeError("skip_external_plan_generation_during_tests")
    provider_name = planner_provider_name()
    provider = get_provider(provider_name)
    model_name = planner_model_name(provider_name)
    targets = _target_projects_for_requirement(db, requirement)
    acceptance_markdown = str(acceptance_contract.get("markdown") or "").strip() or _acceptance_contract_markdown(acceptance_contract)
    attachment_lines = _attachment_prompt_lines(db, int(requirement.id))
    prompt = "\n".join(
        [
            f"# Requirement #{int(requirement.id)}",
            "",
            "## Title",
            str(requirement.title or "").strip(),
            "",
            "## Description",
            str(requirement.description_markdown or "").strip(),
            "",
            "## Target Projects",
            *([f"- {item}" for item in targets] or ["- Scope to the selected project."]),
            "",
            *attachment_lines,
            *([""] if attachment_lines else []),
            "## Acceptance Contract",
            acceptance_markdown or "- Deliver the requested outcome and provide enough evidence for verification.",
            "",
            "Write the execution plan as direct Markdown for the operator and execution agent.",
            "Cover the implementation path, affected areas, verification approach, risks, and delivery outcome.",
        ]
    ).strip()
    text, _tokens = call_full_plan_provider(
        provider_name=provider_name,
        provider=provider,
        prompt=prompt,
        model_name=model_name,
        system_prompt=_PLAN_BRIEF_SYSTEM_PROMPT,
    )
    plan_markdown = _strip_markdown_fence(text)
    if not plan_markdown:
        raise ValueError("plan agent returned empty markdown")
    return plan_markdown


def _required_checks_for_target(db: Session, target_project_path: str | None) -> list[str]:
    policies = resolve_project_policies_for_target(db, target_project_path, require_active=False)
    commands: list[str] = []
    seen: set[str] = set()
    for policy in policies:
        for command in list(project_policy_to_dict(policy).get("required_checks") or []):
            cleaned = str(command).strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                commands.append(cleaned)
    return commands


def _acceptance_contract_payload(db: Session, body, *, target_project_path: str | None = None) -> dict[str, Any]:
    provided_contract = normalize_acceptance_contract(dict(body.acceptance_contract or {}))
    provided_markdown = str(getattr(body, "acceptance_criteria_markdown", "") or "").strip()
    if provided_markdown:
        provided_contract["markdown"] = provided_markdown
    if str(provided_contract.get("markdown") or "").strip() and list(provided_contract.get("done_criteria") or []):
        return provided_contract
    required_checks = _required_checks_for_target(db, target_project_path or str(getattr(body, "target_project_path", "") or "") or None)
    try:
        contract = _generate_acceptance_contract_with_agent(
            title=str(getattr(body, "title", "") or ""),
            description_markdown=str(getattr(body, "description_markdown", "") or ""),
            target_project_path=target_project_path or str(getattr(body, "target_project_path", "") or "") or None,
            required_checks=required_checks,
        )
    except Exception:
        contract = _fallback_acceptance_contract(
            title=str(getattr(body, "title", "") or ""),
            description_markdown=str(getattr(body, "description_markdown", "") or ""),
            target_project_path=target_project_path or str(getattr(body, "target_project_path", "") or "") or None,
            required_checks=required_checks,
        )
    if provided_markdown:
        contract["markdown"] = provided_markdown
    return normalize_acceptance_contract(contract)


def _log_workflow_event(
    event: str,
    *,
    requirement: RequirementRow | None = None,
    execution: ExecutionRunRow | None = None,
    release: ReleaseRecordRow | None = None,
    validation: ValidationRecordRow | None = None,
    **fields: Any,
) -> None:
    payload = dict(fields)
    if requirement is not None:
        payload.setdefault("requirement_id", int(requirement.id))
        payload.setdefault("requirement_status", str(requirement.status or ""))
        payload.setdefault("approval_status", str(requirement.approval_status or ""))
        payload.setdefault("priority", str(requirement.priority or ""))
        payload.setdefault("target_project_path", str(requirement.target_project_path or "").strip() or None)
    if execution is not None:
        payload.setdefault("execution_id", int(execution.id))
        payload.setdefault("execution_status", str(execution.status or ""))
        payload.setdefault("execution_mode", str(execution.execution_mode or ""))
        payload.setdefault("validation_profile", str(execution.validation_profile or ""))
    if release is not None:
        payload.setdefault("release_id", int(release.id))
        payload.setdefault("release_status", str(release.status or ""))
        payload.setdefault("branch_name", str(release.branch_name or "").strip() or None)
        payload.setdefault("pr_number", int(release.pr_number) if release.pr_number is not None else None)
    if validation is not None:
        payload.setdefault("validation_id", int(validation.id) if validation.id is not None else None)
        payload.setdefault("validation_status", str(validation.status or ""))
        payload.setdefault("validation_profile", str(validation.profile or ""))
    log_event(logger, event, **payload)


def _project_for_requirement(db: Session, requirement: RequirementRow) -> ProjectRow | None:
    ensure_projects_materialized(db)
    return resolve_project(
        db,
        project_id=int(requirement.project_id) if getattr(requirement, "project_id", None) is not None else None,
        project_key=str(getattr(requirement, "project_key", "") or "") or None,
        target_project_path=str(getattr(requirement, "target_project_path", "") or "") or None,
    )


def _resolve_project_for_body(db: Session, body) -> ProjectRow | None:
    ensure_projects_materialized(db)
    body_project_id = getattr(body, "project_id", None)
    if body_project_id is not None:
        return get_project(db, int(body_project_id))
    return resolve_project(
        db,
        project_key=None,
        target_project_path=str(getattr(body, "target_project_path", "") or "") or None,
    )


def _resolved_target_project_path(project: ProjectRow | None, *, override: str | None = None, fallback: str | None = None) -> str | None:
    cleaned_override = str(override or "").strip()
    if cleaned_override:
        return cleaned_override
    if project is not None and str(getattr(project, "root_path", "") or "").strip():
        return str(project.root_path or "").strip() or None
    cleaned_fallback = str(fallback or "").strip()
    return cleaned_fallback or None


def _target_projects_for_requirement(db: Session, requirement: RequirementRow) -> list[str]:
    project = _project_for_requirement(db, requirement)
    if project is not None:
        resolved = _resolved_target_project_path(
            project,
            override=str(getattr(requirement, "target_project_path_override", "") or "") or None,
            fallback=str(getattr(requirement, "target_project_path", "") or "") or None,
        )
        if resolved:
            return [resolved]
    policies = resolve_project_policies_for_target(
        db,
        getattr(requirement, "target_project_path", None),
        require_active=False,
    )
    if policies:
        return [str(policy.root_path) for policy in policies]
    return _split_target_projects(getattr(requirement, "target_project_path", None))


def _requirement_attachment_rows(db: Session, requirement_id: int):
    return (
        db.query(RequirementAttachmentRow)
        .filter(RequirementAttachmentRow.requirement_id == requirement_id)
        .order_by(RequirementAttachmentRow.id.asc())
        .all()
    )


def _requirement_attachment_context_files(db: Session, requirement_id: int) -> list[str]:
    rows = _requirement_attachment_rows(db, requirement_id)
    return requirement_attachment_context_files(requirement_id, rows) if rows else []


def _attachment_prompt_lines(db: Session, requirement_id: int) -> list[str]:
    rows = _requirement_attachment_rows(db, requirement_id)
    if not rows:
        return []
    lines = ["## Attachments"]
    for row in rows:
        lines.append(
            f"- {row.file_name} ({row.attachment_kind}, {row.content_type}, {int(row.size_bytes or 0)} bytes) @ {row.stored_path}"
        )
    return lines


def requirement_attachment_file_path(db: Session, requirement_id: int, attachment_id: int) -> tuple[RequirementAttachmentRow, Path]:
    row = (
        db.query(RequirementAttachmentRow)
        .filter(
            RequirementAttachmentRow.requirement_id == requirement_id,
            RequirementAttachmentRow.id == attachment_id,
        )
        .first()
    )
    if row is None:
        raise ValueError("Requirement attachment not found.")
    base = PROJECT_ROOT.resolve()
    file_path = (base / str(row.stored_path or "")).resolve()
    try:
        file_path.relative_to(base)
    except ValueError as exc:
        raise ValueError("Requirement attachment path is invalid.") from exc
    if not file_path.exists():
        raise ValueError("Requirement attachment file is missing.")
    return row, file_path


def _primary_project_policy(db: Session, requirement: RequirementRow):
    project = _project_for_requirement(db, requirement)
    if project is not None:
        policies = resolve_project_policies_for_target(db, str(getattr(project, "root_path", "") or "") or None, require_active=False)
        return policies[0] if policies else None
    policies = resolve_project_policies_for_target(
        db,
        getattr(requirement, "target_project_path", None),
        require_active=False,
    )
    return policies[0] if policies else None


def _approval_required(db: Session, requirement: RequirementRow) -> bool:
    project = _project_for_requirement(db, requirement)
    if project is not None:
        policies = resolve_project_policies_for_target(
            db,
            str(getattr(project, "root_path", "") or "") or None,
            require_active=False,
        )
        if any(bool(getattr(policy, "requires_manual_approval", False)) for policy in policies):
            return True
    policies = resolve_project_policies_for_target(
        db,
        getattr(requirement, "target_project_path", None),
        require_active=False,
    )
    if any(bool(getattr(policy, "requires_manual_approval", False)) for policy in policies):
        return True
    return str(getattr(requirement, "priority", "normal")) == "high"


def _approval_source_label(decision: dict[str, Any], approval_status: str) -> str:
    if approval_status == "waived" or str(decision.get("approval_source") or "") == "waived":
        return "policy_waived"
    if approval_status == "approved":
        if bool(decision.get("needs_human_gate")) or str(decision.get("approval_source") or "") == "human":
            return "manual_required"
        return "agent_auto_approved"
    return "manual_required"


def _approval_risk_flags(decision: dict[str, Any]) -> list[str]:
    router = dict(decision.get("approval_router") or {})
    flags = [
        str(item).strip()
        for item in [*(router.get("hard_rule_hits") or []), *(router.get("soft_rule_hits") or [])]
        if str(item).strip()
    ]
    recommendation = dict(decision.get("approval_recommendation") or {})
    if str(recommendation.get("action") or "") == "revise":
        flags.append("clarification_required")
    return flags


def _approval_summary(
    db: Session,
    requirement: RequirementRow,
    *,
    latest_execution_id: int | None = None,
    auto_started: bool = False,
    pending_execution_start: bool = False,
) -> AgentFirstRequirementApprovalOut:
    """Build a stable approval summary for requirement and submit/detail responses."""
    decision = evaluate_requirement_execution_approval(requirement)
    approval_status = normalize_requirement_approval_status(getattr(requirement, "approval_status", None))
    if approval_status == "rejected":
        approval_decision = "rejected"
    elif approval_status in {"approved", "waived"}:
        approval_decision = approval_status
    else:
        approval_decision = "pending_manual_approval"
    return AgentFirstRequirementApprovalOut(
        approval_decision=approval_decision,
        approval_status=approval_status,
        approval_reason=str(decision.get("reason") or "").strip() or None,
        approval_source=_approval_source_label(decision, approval_status),
        approval_agent_id="approval_agent" if str(decision.get("approval_source") or "") == "agent" else None,
        approval_agent_label="Approval Agent" if str(decision.get("approval_source") or "") == "agent" else None,
        approval_recommendation=str((decision.get("approval_recommendation") or {}).get("action") or "").strip() or None,
        approval_confidence=_float_or_none((decision.get("approval_recommendation") or {}).get("confidence")),
        required_approver_roles=[str(item) for item in decision.get("required_approver_roles") or [] if str(item).strip()],
        risk_flags=_approval_risk_flags(decision),
        pending_execution_start=pending_execution_start,
        auto_started=auto_started,
        execution_run_id=latest_execution_id,
    )


def _latest_pending_requirement_approval(db: Session, requirement_id: int) -> ApprovalRequestRow | None:
    return (
        db.query(ApprovalRequestRow)
        .filter(
            ApprovalRequestRow.requirement_id == requirement_id,
            ApprovalRequestRow.approval_type == "requirement_execution_approval",
            ApprovalRequestRow.status == "pending",
        )
        .order_by(ApprovalRequestRow.id.desc())
        .first()
    )


def _resolve_requirement_approval_requests(
    db: Session,
    *,
    requirement_id: int,
    status: str,
    reviewer: str,
    comment: str,
) -> None:
    rows = db.query(ApprovalRequestRow).filter(
        ApprovalRequestRow.requirement_id == requirement_id,
        ApprovalRequestRow.approval_type == "requirement_execution_approval",
        ApprovalRequestRow.status == "pending",
    ).all()
    decided_at = utcnow()
    for row in rows:
        row.status = status
        row.reviewer = reviewer
        row.comment = comment
        row.decided_at = decided_at


def _ensure_requirement_approval_request(
    db: Session,
    *,
    requirement: RequirementRow,
    reviewer: str,
    comment: str,
) -> None:
    pending = _latest_pending_requirement_approval(db, int(requirement.id))
    requirement.approval_requested_at = requirement.approval_requested_at or utcnow()
    if pending is None:
        db.add(
            ApprovalRequestRow(
                requirement_id=int(requirement.id),
                workflow_run_id=None,
                step_id=None,
                approval_type="requirement_execution_approval",
                status="pending",
                reviewer=reviewer,
                comment=comment,
            )
        )
        return
    pending.reviewer = reviewer
    pending.comment = comment


def _requirement_to_out(db: Session, requirement: RequirementRow) -> AgentFirstRequirementOut:
    requirement = reconcile_requirement_state(db, requirement)
    latest_execution = _latest_execution_run(db, int(requirement.id))
    if latest_execution is not None:
        latest_execution = reconcile_execution_state(db, latest_execution)
    latest_release = (
        db.query(ReleaseRecordRow)
        .filter(ReleaseRecordRow.requirement_id == requirement.id)
        .order_by(ReleaseRecordRow.id.desc())
        .first()
    )
    project = _project_for_requirement(db, requirement)
    return AgentFirstRequirementOut(
        id=int(requirement.id),
        title=str(requirement.title or ""),
        description_markdown=str(requirement.description_markdown or ""),
        acceptance_criteria_markdown=_parse_acceptance_markdown(requirement),
        status=str(requirement.status or "draft"),
        priority=str(requirement.priority or "normal"),
        source=str(requirement.source or "manual"),
        source_ref=str(requirement.source_ref or "").strip() or None,
        linked_requirement_id=int(getattr(requirement, "linked_requirement_id", 0) or 0) or None,
        followup_requirement_id=int(getattr(requirement, "followup_requirement_id", 0) or 0) or None,
        resolution_path=str(getattr(requirement, "resolution_path", "") or "").strip() or None,
        project_id=int(project.id) if project is not None else (int(requirement.project_id) if getattr(requirement, "project_id", None) is not None else None),
        project_key=str(getattr(project, "project_key", "") or "").strip() or (str(getattr(requirement, "project_key", "") or "").strip() or None),
        project_display_name=str(getattr(project, "display_name", "") or "").strip() or (str(getattr(requirement, "project_display_name", "") or "").strip() or None),
        target_project_path=str(requirement.target_project_path or "").strip() or None,
        target_project_path_override=str(getattr(requirement, "target_project_path_override", "") or "").strip() or None,
        target_projects=_target_projects_for_requirement(db, requirement),
        approval_required=_approval_required(db, requirement),
        approval_status=str(requirement.approval_status or "pending_approval"),
        phase=str(getattr(requirement, "phase", "") or requirement.status or "draft"),
        allowed_actions=_requirement_allowed_actions(requirement, latest_execution, latest_release),
        pending_operations=[],
        recovery_status=str(getattr(requirement, "recovery_status", "") or "").strip() or None,
        assets_status=_assets_status(requirement),
        assets_error_message=_assets_error_message(requirement),
        created_at=requirement.created_at,
        updated_at=requirement.updated_at,
        active_execution_run_id=int(latest_execution.id) if latest_execution is not None and str(latest_execution.status or "") in {"queued", "running", "paused", "validating", "blocked"} else None,
        latest_execution_run_id=int(latest_execution.id) if latest_execution is not None else None,
        latest_release_status=str(latest_release.status or "") if latest_release is not None else None,
    )


def _policy_summary_markdown(db: Session, requirement: RequirementRow) -> str:
    target_project_path = getattr(requirement, "target_project_path", None)
    if not str(target_project_path or "").strip():
        return ""
    return project_policy_summary_markdown(db, target_project_path)


def _service_name_for_requirement(db: Session, requirement: RequirementRow) -> str:
    policy = _primary_project_policy(db, requirement)
    return notification_service_label(
        display_name=str(getattr(policy, "display_name", "") or "").strip() or None,
        project_key=str(getattr(policy, "project_key", "") or "").strip() or None,
    )


def _notify_requirement_created(db: Session, requirement: RequirementRow) -> None:
    service_name = _service_name_for_requirement(db, requirement)
    deliver_lark_notification(
        db,
        channel="requirement",
        event_type="requirement_created",
        event_key=f"requirement:requirement_created:{int(requirement.id)}",
        object_type="requirement",
        object_key=str(int(requirement.id)),
        service_name=service_name,
        status_or_severity=str(requirement.priority or "normal"),
        summary=f"Requirement #{int(requirement.id)} 已创建：{str(requirement.title or '').strip()}",
        next_action="确认 requirement 描述与验收标准完整，然后通过 submit 进入自动审批与执行。",
        actor_or_source=str(requirement.source or "system"),
        occurred_at=requirement.created_at,
        object_refs={
            "requirement_id": int(requirement.id),
            "project_key": str(getattr(_primary_project_policy(db, requirement), "project_key", "") or "").strip() or None,
        },
        links={"需求": build_ops_url(f"/requirements/{int(requirement.id)}") or ""},
    )


def _notify_requirement_approval(
    db: Session,
    requirement: RequirementRow,
    approval: AgentFirstRequirementApprovalOut,
) -> None:
    if approval.approval_decision not in {"approved", "waived", "pending_manual_approval"}:
        return
    event_type = "approval_auto_approved" if approval.approval_decision in {"approved", "waived"} else "approval_manual_required"
    event_key = f"requirement:{event_type}:{int(requirement.id)}:{approval.approval_status}"
    next_action = (
        "Execution 已自动创建并启动，进入执行面观察 run、validate 和 incident。"
        if approval.auto_started
        else "请在需求面查看原因，并决定是否批准执行。"
    )
    deliver_lark_notification(
        db,
        channel="requirement",
        event_type=event_type,
        event_key=event_key,
        object_type="requirement",
        object_key=str(int(requirement.id)),
        service_name=_service_name_for_requirement(db, requirement),
        status_or_severity=approval.approval_status,
        summary=approval.approval_reason or f"Requirement #{int(requirement.id)} approval updated.",
        next_action=next_action,
        actor_or_source=approval.approval_source or "system",
        occurred_at=utcnow(),
        object_refs={
            "requirement_id": int(requirement.id),
            "execution_id": approval.execution_run_id,
        },
        links={
            "需求": build_ops_url(f"/requirements/{int(requirement.id)}") or "",
            "执行": build_ops_url(f"/executions/{approval.execution_run_id}") or "" if approval.execution_run_id else "",
        },
    )


def _notify_execution_error(db: Session, run: ExecutionRunRow, requirement: RequirementRow, node: ExecutionNodeRow | None) -> None:
    service_name = _service_name_for_requirement(db, requirement)
    object_key = str(int(run.id))
    task_token = str(int(node.task_id)) if node is not None and node.task_id is not None else str(int(run.latest_task_id)) if run.latest_task_id is not None else "no-task"
    status_token = str(run.status or "blocked")
    summary = (
        f"Execution #{int(run.id)} for requirement #{int(requirement.id)} entered {status_token}."
        if node is None
        else f"Execution #{int(run.id)} node `{str(node.node_key or '')}` entered {str(node.status or status_token)}."
    )
    next_action = "查看执行面确认失败节点、错误摘要与恢复动作；必要时进入错误日志页继续排查。"
    deliver_lark_notification(
        db,
        channel="alert",
        event_type="execution_error",
        event_key=f"alert:execution_error:run:{object_key}:task:{task_token}:status:{status_token}",
        object_type="execution_run",
        object_key=object_key,
        service_name=service_name,
        status_or_severity=str(run.status or "blocked"),
        summary=summary,
        next_action=next_action,
        actor_or_source="runtime",
        occurred_at=utcnow(),
        object_refs={
            "requirement_id": int(requirement.id),
            "execution_id": int(run.id),
        },
        links={
            "执行": build_ops_url(f"/executions/{int(run.id)}") or "",
            "需求": build_ops_url(f"/requirements/{int(requirement.id)}") or "",
        },
    )


def _notify_pr_opened(db: Session, requirement: RequirementRow, release: ReleaseRecordRow) -> None:
    service_name = _service_name_for_requirement(db, requirement)
    deliver_lark_notification(
        db,
        channel="release",
        event_type="pr_opened",
        event_key=f"release:pr_opened:{int(requirement.id)}:{str(release.pr_number or release.pr_url or release.branch_name or '')}",
        object_type="release",
        object_key=str(int(release.id)),
        service_name=service_name,
        status_or_severity=str(release.status or "pr_opened"),
        summary=f"Requirement #{int(requirement.id)} 已创建 PR：{str(requirement.title or '').strip()}",
        next_action="进入发布面确认 PR、对比链接与后续 staging / production promotion。",
        actor_or_source="system",
        occurred_at=release.delivered_at or utcnow(),
        object_refs={
            "requirement_id": int(requirement.id),
            "release_id": int(release.id),
        },
        links={
            "发布": build_ops_url(f"/releases/{int(requirement.id)}") or "",
            "需求": build_ops_url(f"/requirements/{int(requirement.id)}") or "",
            "PR": str(release.pr_url or "").strip(),
            "Compare": str(release.compare_url or "").strip(),
        },
    )


def build_requirement_detail(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    return _build_requirement_detail(db, requirement_id)


def _build_requirement_detail(
    db: Session,
    requirement_id: int,
    *,
    latest_execution_id_override: int | None = None,
    approval_override: AgentFirstRequirementApprovalOut | None = None,
) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    requirement = reconcile_requirement_state(db, requirement)
    latest_execution = _latest_execution_run(db, requirement_id)
    if latest_execution is not None:
        latest_execution = reconcile_execution_state(db, latest_execution)
    latest_release = (
        db.query(ReleaseRecordRow)
        .filter(ReleaseRecordRow.requirement_id == requirement_id)
        .order_by(ReleaseRecordRow.id.desc())
        .first()
    )
    project = _project_for_requirement(db, requirement)
    return AgentFirstRequirementDetailOut(
        requirement=_requirement_to_out(db, requirement),
        policy_summary_markdown=_policy_summary_markdown(db, requirement),
        project=ProjectOut(**project_to_dict(project)) if project is not None else None,
        latest_execution_id=latest_execution_id_override if latest_execution_id_override is not None else (int(latest_execution.id) if latest_execution is not None else None),
        latest_release_id=int(latest_release.id) if latest_release is not None else None,
        latest_release=_release_to_out(latest_release),
        approval=approval_override or _approval_summary(
            db,
            requirement,
            latest_execution_id=latest_execution_id_override if latest_execution_id_override is not None else (int(latest_execution.id) if latest_execution is not None else None),
        ),
        phase=str(getattr(requirement, "phase", "") or requirement.status or "draft"),
        allowed_actions=_requirement_allowed_actions(requirement, latest_execution, latest_release),
        pending_operations=[],
        recovery_status=str(getattr(requirement, "recovery_status", "") or "").strip() or None,
        assets_status=_assets_status(requirement),
        assets_error_message=_assets_error_message(requirement),
        acceptance_contract=_parse_acceptance_contract(requirement),
        execution_plan=_parse_execution_plan(requirement),
        attachments=[
            RequirementAttachmentOut(**serialize_requirement_attachment(item))
            for item in _requirement_attachment_rows(db, requirement_id)
        ],
        followup_requirement_id=int(getattr(requirement, "followup_requirement_id", 0) or 0) or None,
        resolution_path=str(getattr(requirement, "resolution_path", "") or "").strip() or None,
    )


def list_requirements(db: Session, *, status: str | None = None, search: str | None = None) -> list[AgentFirstRequirementOut]:
    ensure_projects_materialized(db)
    rows = db.query(RequirementRow).order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc()).all()
    result: list[AgentFirstRequirementOut] = []
    search_value = str(search or "").strip().lower()
    for row in rows:
        item = _requirement_to_out(db, row)
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


def create_requirement(db: Session, body) -> AgentFirstRequirementDetailOut:
    ensure_projects_materialized(db)
    project = _resolve_project_for_body(db, body)
    if project is None:
        raise ValueError("Requirement must be attached to a valid project.")
    target_project_path = _resolved_target_project_path(
        project,
        override=str(getattr(body, "target_project_path_override", "") or "") or None,
        fallback=str(getattr(body, "target_project_path", "") or "") or None,
    )
    initial_acceptance_contract = normalize_acceptance_contract(dict(getattr(body, "acceptance_contract", None) or {}))
    provided_markdown = str(getattr(body, "acceptance_criteria_markdown", "") or "").strip()
    if provided_markdown:
        initial_acceptance_contract["markdown"] = provided_markdown
    requirement = RequirementRow(
        title=body.title.strip(),
        description_markdown=body.description_markdown.strip(),
        status="draft",
        phase="draft",
        priority=body.priority,
        source=body.source,
        source_ref=body.source_ref,
        intake_metadata_json=_json_dump(body.intake_metadata or {}),
        project_id=int(project.id),
        project_key=str(project.project_key or ""),
        project_display_name=str(project.display_name or ""),
        target_project_path=target_project_path,
        target_project_path_override=str(getattr(body, "target_project_path_override", "") or "").strip() or None,
        acceptance_contract_json=_json_dump(initial_acceptance_contract),
        execution_plan_json=_json_dump({}),
        approval_status="pending_approval",
        approval_contract_json=_json_dump(body.approval_contract or {}),
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    persisted_attachments = persist_requirement_attachments(int(requirement.id), getattr(body, "attachments", None))
    if persisted_attachments:
        for attachment in persisted_attachments:
            db.add(attachment)
        intake_metadata = _json_load(getattr(requirement, "intake_metadata_json", None), {})
        if not isinstance(intake_metadata, dict):
            intake_metadata = {}
        intake_metadata["attachment_count"] = len(persisted_attachments)
        intake_metadata["attachment_context_files"] = requirement_attachment_context_files(
            int(requirement.id),
            persisted_attachments,
        )
        requirement.intake_metadata_json = _json_dump(intake_metadata)
        db.commit()
        db.refresh(requirement)
    approval_required = _approval_required(db, requirement)
    requirement.approval_status = "pending_approval" if approval_required else "waived"
    requirement.phase = "planning"
    requirement.assets_status = "pending"
    requirement.assets_error_message = None
    requirement.approval_contract_json = _json_dump(
        {
            **_json_load(getattr(requirement, "approval_contract_json", None), {}),
            "required": approval_required,
        }
    )
    db.commit()
    db.refresh(requirement)
    if _testing_mode():
        _ensure_generated_requirement_assets(db, requirement)
        db.commit()
        db.refresh(requirement)
    else:
        _enqueue_requirement_asset_generation(int(requirement.id))
    _notify_requirement_created(db, requirement)
    _log_workflow_event(
        "requirement_created",
        requirement=requirement,
        source=str(requirement.source or "").strip() or None,
        source_ref=str(requirement.source_ref or "").strip() or None,
        acceptance_generated=bool(_parse_acceptance_markdown(requirement)),
    )
    db.commit()
    return build_requirement_detail(db, int(requirement.id))


def update_requirement(db: Session, requirement_id: int, body) -> AgentFirstRequirementDetailOut:
    ensure_projects_materialized(db)
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    project = _project_for_requirement(db, requirement)
    if body.title is not None:
        requirement.title = body.title.strip()
    if body.description_markdown is not None:
        requirement.description_markdown = body.description_markdown.strip()
    if getattr(body, "acceptance_criteria_markdown", None) is not None:
        requirement.acceptance_contract_json = _json_dump(
            {
                **_json_load(getattr(requirement, "acceptance_contract_json", None), {}),
                "markdown": str(body.acceptance_criteria_markdown or "").strip(),
            }
        )
    if getattr(body, "acceptance_contract", None) is not None:
        contract = normalize_acceptance_contract(dict(getattr(body, "acceptance_contract", None) or {}))
        if not str(contract.get("markdown") or "").strip():
            contract["markdown"] = _acceptance_contract_markdown(contract)
        requirement.acceptance_contract_json = _json_dump(contract)
    if body.priority is not None:
        requirement.priority = body.priority
    if body.source_ref is not None:
        requirement.source_ref = body.source_ref
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
    if body.target_project_path is not None:
        requirement.target_project_path = body.target_project_path.strip() or None
    requirement.target_project_path = _resolved_target_project_path(
        project,
        override=str(getattr(requirement, "target_project_path_override", "") or "") or None,
        fallback=str(getattr(requirement, "target_project_path", "") or "") or None,
    )
    requirement.updated_at = utcnow()
    _log_workflow_event(
        "requirement_updated",
        requirement=requirement,
        edited_fields=[
            field
            for field in ["title", "description_markdown", "acceptance_criteria_markdown", "priority", "source_ref", "project_id", "target_project_path_override", "target_project_path", "execution_plan"]
            if getattr(body, field, None) is not None
        ],
    )
    if getattr(body, "execution_plan", None) is not None:
        current_plan = _parse_execution_plan(requirement)
        next_plan = dict(current_plan)
        incoming_plan = dict(getattr(body, "execution_plan", None) or {})
        next_plan.update({key: value for key, value in incoming_plan.items() if value is not None})
        if str(next_plan.get("summary_markdown") or "").strip():
            requirement.execution_plan_json = _json_dump(next_plan)
            requirement.current_plan_version = int(getattr(requirement, "current_plan_version", 0) or 0) + 1
    db.commit()
    return build_requirement_detail(db, requirement_id)


def submit_requirement(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    requirement = reconcile_requirement_state(db, requirement)
    if str(requirement.status or "") == "deleted":
        raise ValueError("Deleted requirement cannot be submitted.")
    if str(getattr(requirement, "phase", "") or "") in {"executing", "verifying", "delivery_ready", "pr_opened", "done"}:
        return _build_requirement_detail(db, requirement_id)
    if not str(requirement.title or "").strip():
        raise ValueError("Requirement title is required before submit.")
    if not str(requirement.description_markdown or "").strip():
        raise ValueError("Requirement description is required before submit.")
    if _assets_status(requirement) == "pending":
        raise ValueError("验收标准与执行计划仍在生成中，请稍后再提交。")
    if _assets_status(requirement) == "failed":
        raise ValueError(_assets_error_message(requirement) or "计划生成失败，请先重新生成。")
    decision = evaluate_requirement_execution_approval(requirement)
    approval_status = normalize_requirement_approval_status(decision.get("approval_status"))
    approval_reason = str(decision.get("reason") or "Requirement requires approval before automatic execution").strip()
    requirement.updated_at = utcnow()
    if approval_status in {"approved", "waived"}:
        requirement.approval_status = approval_status
        requirement.approved_at = requirement.approved_at or utcnow()
        requirement.approval_requested_at = None
        requirement.phase = "branch_prepared"
        requirement.status = _requirement_status_from_phase(requirement.phase)
        _resolve_requirement_approval_requests(
            db,
            requirement_id=int(requirement.id),
            status="approved",
            reviewer="system",
            comment=approval_reason or "Automatically approved for execution",
        )
        execution_plan = _ensure_execution_plan(db, requirement)
        db.commit()
        _log_workflow_event(
            "requirement_execution_plan_generated",
            requirement=requirement,
            planning_mode=str(execution_plan.get("planning_mode") or "fallback"),
            planned_steps=len(list(execution_plan.get("steps") or [])),
            planned_checks=len(list(execution_plan.get("planned_checks") or [])),
        )
        execution = create_execution_run(db, int(requirement.id))
        auto_started = False
        pending_execution_start = False
        try:
            start_execution_run(db, int(execution.execution.id))
            auto_started = True
        except ValueError:
            pending_execution_start = True
        detail = _build_requirement_detail(
            db,
            requirement_id,
            latest_execution_id_override=int(execution.execution.id),
            approval_override=_approval_summary(
                db,
                requirement,
                latest_execution_id=int(execution.execution.id),
                auto_started=auto_started,
                pending_execution_start=pending_execution_start,
            ),
        )
        _log_workflow_event(
            "requirement_submitted",
            requirement=requirement,
            execution=db.query(ExecutionRunRow).filter(ExecutionRunRow.id == int(execution.execution.id)).first(),
            approval_decision=approval_status,
            approval_reason=approval_reason,
            auto_started=auto_started,
            pending_execution_start=pending_execution_start,
        )
        _notify_requirement_approval(db, requirement, detail.approval)
        db.commit()
        return detail

    requirement.approval_status = "pending_approval"
    requirement.approved_at = None
    requirement.phase = "awaiting_execution_approval"
    requirement.status = _requirement_status_from_phase(requirement.phase)
    reviewer = str(decision.get("reviewer") or "operator").strip() or "operator"
    _ensure_requirement_approval_request(
        db,
        requirement=requirement,
        reviewer=reviewer,
        comment=approval_reason,
    )
    db.commit()
    detail = _build_requirement_detail(
        db,
        requirement_id,
        approval_override=_approval_summary(db, requirement, pending_execution_start=False),
    )
    _log_workflow_event(
        "requirement_submitted",
        requirement=requirement,
        approval_decision=approval_status,
        approval_reason=approval_reason,
        pending_execution_start=False,
    )
    _notify_requirement_approval(db, requirement, detail.approval)
    db.commit()
    return detail


def approve_requirement(
    db: Session,
    requirement_id: int,
    *,
    reviewer: str = "operator",
    comment: str | None = None,
) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    requirement = reconcile_requirement_state(db, requirement)
    if str(requirement.approval_status or "") == "approved":
        return _build_requirement_detail(db, requirement_id)
    if str(requirement.approval_status or "") not in {"pending_approval", "rejected"}:
        raise ValueError("Requirement is not awaiting manual approval.")
    requirement.approval_status = "approved"
    requirement.approved_at = utcnow()
    requirement.approval_requested_at = None
    requirement.phase = "branch_prepared"
    requirement.status = _requirement_status_from_phase(requirement.phase)
    requirement.updated_at = utcnow()
    _ensure_generated_requirement_assets(db, requirement)
    _resolve_requirement_approval_requests(
        db,
        requirement_id=int(requirement.id),
        status="approved",
        reviewer=reviewer,
        comment=str(comment or "Approved for autonomous execution"),
    )
    execution_plan = _ensure_execution_plan(db, requirement)
    db.commit()
    _log_workflow_event(
        "requirement_execution_plan_generated",
        requirement=requirement,
        planning_mode=str(execution_plan.get("planning_mode") or "fallback"),
        planned_steps=len(list(execution_plan.get("steps") or [])),
        planned_checks=len(list(execution_plan.get("planned_checks") or [])),
    )
    execution = create_execution_run(db, int(requirement.id))
    auto_started = False
    pending_execution_start = False
    try:
        start_execution_run(db, int(execution.execution.id))
        auto_started = True
    except ValueError:
        pending_execution_start = True
    detail = _build_requirement_detail(
        db,
        requirement_id,
        latest_execution_id_override=int(execution.execution.id),
        approval_override=_approval_summary(
            db,
            requirement,
            latest_execution_id=int(execution.execution.id),
            auto_started=auto_started,
            pending_execution_start=pending_execution_start,
        ),
    )
    _log_workflow_event(
        "requirement_approved",
        requirement=requirement,
        execution=db.query(ExecutionRunRow).filter(ExecutionRunRow.id == int(execution.execution.id)).first(),
        reviewer=reviewer,
        approval_comment=str(comment or "").strip() or None,
        auto_started=auto_started,
        pending_execution_start=pending_execution_start,
    )
    _notify_requirement_approval(db, requirement, detail.approval)
    db.commit()
    return detail


def reject_requirement(
    db: Session,
    requirement_id: int,
    *,
    reviewer: str = "operator",
    comment: str | None = None,
) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    requirement.approval_status = "rejected"
    requirement.approved_at = None
    requirement.approval_requested_at = None
    requirement.phase = "needs_revision"
    requirement.status = _requirement_status_from_phase(requirement.phase)
    requirement.updated_at = utcnow()
    _resolve_requirement_approval_requests(
        db,
        requirement_id=int(requirement.id),
        status="rejected",
        reviewer=reviewer,
        comment=str(comment or "Rejected pending revision"),
    )
    db.commit()
    detail = _build_requirement_detail(
        db,
        requirement_id,
        approval_override=_approval_summary(db, requirement),
    )
    _log_workflow_event(
        "requirement_rejected",
        requirement=requirement,
        reviewer=reviewer,
        approval_comment=str(comment or "").strip() or None,
    )
    db.commit()
    return detail


def revise_requirement(db: Session, requirement_id: int, body) -> AgentFirstRequirementDetailOut:
    detail = update_requirement(db, requirement_id, body)
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    requirement.phase = "draft"
    requirement.status = _requirement_status_from_phase(requirement.phase)
    requirement.updated_at = utcnow()
    db.commit()
    return build_requirement_detail(db, requirement_id)


def cancel_requirement(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    requirement.phase = "blocked"
    requirement.status = "cancelled"
    requirement.completed_at = utcnow()
    db.commit()
    return build_requirement_detail(db, requirement_id)


def delete_requirement(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    requirement = reconcile_requirement_state(db, requirement)
    latest_execution = _latest_execution_run(db, int(requirement.id))
    if latest_execution is not None:
        raise ValueError("Requirements with execution history cannot be deleted.")
    if str(getattr(requirement, "phase", "") or requirement.status or "draft") not in {
        "draft",
        "planning",
        "awaiting_execution_approval",
        "needs_revision",
        "blocked",
    }:
        raise ValueError("Only pre-execution requirements can be deleted.")
    requirement.phase = "deleted"
    requirement.status = "deleted"
    requirement.updated_at = utcnow()
    _log_workflow_event("requirement_deleted", requirement=requirement)
    db.commit()
    return build_requirement_detail(db, requirement_id)


def regenerate_requirement_plan(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    plan = _generate_execution_plan(db, requirement)
    requirement.execution_plan_json = _json_dump(plan)
    requirement.current_plan_version = int(getattr(requirement, "current_plan_version", 0) or 0) + 1
    requirement.updated_at = utcnow()
    _log_workflow_event(
        "requirement_execution_plan_generated",
        requirement=requirement,
        planning_mode=str(plan.get("planning_mode") or "fallback"),
        planned_steps=len(list(plan.get("steps") or [])),
        planned_checks=len(list(plan.get("planned_checks") or [])),
        regenerated=True,
    )
    db.commit()
    return build_requirement_detail(db, requirement_id)


def regenerate_requirement_assets(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    if str(requirement.status or "") not in {"draft", "ready", "blocked", "needs_revision"}:
        raise ValueError("Only pre-execution requirements can regenerate assets.")
    if _latest_execution_run(db, requirement_id) is not None:
        raise ValueError("Execution has already started; assets can no longer be regenerated.")
    requirement.phase = "planning"
    requirement.assets_status = "pending"
    requirement.assets_error_message = None
    requirement.updated_at = utcnow()
    db.commit()
    _enqueue_requirement_asset_generation(int(requirement.id))
    return build_requirement_detail(db, requirement_id)


def _shape_decision(db: Session, requirement: RequirementRow) -> dict[str, Any]:
    target_projects = _target_projects_for_requirement(db, requirement)
    description = str(requirement.description_markdown or "")
    complexity = "complex" if len(target_projects) > 1 or len(description) > 1600 else "simple"
    validation_profile = "strict" if len(target_projects) > 1 else "minimal"
    return {
        "execution_mode": "direct",
        "complexity": complexity,
        "validation_profile": validation_profile,
        "delivery_intent": "pr_required",
        "execution_steps": [{"node_key": "execute", "title": "Execute requirement"}],
        "planner_summary": "Agent-first execution uses a single primary execute node; planning and verification are handled by dedicated agents.",
    }


def _plan_markdown(payload: dict[str, Any]) -> str:
    summary = str(payload.get("summary_markdown") or "").strip()
    if summary:
        return summary
    lines = [f"## Goal\n\n{str(payload.get('goal_summary') or '').strip()}"]
    targets = [str(item).strip() for item in payload.get("target_files_or_areas") or [] if str(item).strip()]
    if targets:
        lines.extend(["", "## Target Areas", *[f"- {item}" for item in targets]])
    steps = [item for item in payload.get("steps") or [] if isinstance(item, dict)]
    if steps:
        lines.extend(["", "## Planned Steps"])
        for index, step in enumerate(steps, start=1):
            title = str(step.get("title") or step.get("step_key") or f"step_{index}").strip()
            done_when = str(step.get("done_when") or "").strip()
            lines.append(f"{index}. {title}")
            if done_when:
                lines.append(f"   - Done when: {done_when}")
    checks = [str(item).strip() for item in payload.get("planned_checks") or [] if str(item).strip()]
    if checks:
        lines.extend(["", "## Planned Checks", *[f"- {item}" for item in checks]])
    return "\n".join(lines).strip()


def _fallback_execution_plan_payload(db: Session, requirement: RequirementRow, shape: dict[str, Any]) -> dict[str, Any]:
    acceptance = _parse_acceptance_contract(requirement)
    targets = _target_projects_for_requirement(db, requirement)
    payload = {
        "planning_mode": "agent_first_fallback",
        "goal_summary": str(requirement.title or "").strip(),
        "target_files_or_areas": targets or [str(getattr(requirement, "target_project_path", "") or "").strip()],
        "steps": [{"step_key": "execute", "title": "Execute requirement", "step_type": "implementation", "scope": "implementation"}],
        "planned_checks": _verification_strategy_lines(acceptance),
        "risks": [
            "Keep edits scoped to the selected project and avoid unrelated regressions.",
            "Record sufficient execution evidence so validate and release can operate without guesswork.",
        ],
        "delivery_intent": str(shape.get("delivery_intent") or "pr_required"),
    }
    payload["summary_markdown"] = _fallback_plan_brief_markdown(db, requirement, acceptance_contract=acceptance)
    return payload


def _generate_execution_plan(db: Session, requirement: RequirementRow) -> dict[str, Any]:
    shape = _shape_decision(db, requirement)
    if _testing_mode():
        return _fallback_execution_plan_payload(db, requirement, shape)
    try:
        acceptance = _parse_acceptance_contract(requirement)
        targets = _target_projects_for_requirement(db, requirement)
        return {
            "planning_mode": "agent_plan_brief",
            "goal_summary": str(requirement.title or "").strip(),
            "target_files_or_areas": targets or [str(getattr(requirement, "target_project_path", "") or "").strip()],
            "steps": [{"step_key": "execute", "title": "Execute requirement", "step_type": "implementation", "scope": "implementation"}],
            "planned_checks": _verification_strategy_lines(acceptance),
            "risks": [
                "Keep edits scoped to the selected project and avoid unrelated regressions.",
                "Capture explicit execution evidence so the verification agent can make a release decision.",
            ],
            "delivery_intent": str(shape.get("delivery_intent") or "pr_required"),
            "summary_markdown": _generate_plan_brief_markdown_with_agent(
                db,
                requirement,
                acceptance_contract=acceptance,
            ),
        }
    except Exception:
        return _fallback_execution_plan_payload(db, requirement, shape)


def _ensure_execution_plan(db: Session, requirement: RequirementRow) -> dict[str, Any]:
    existing = _parse_execution_plan(requirement)
    if existing and str(existing.get("summary_markdown") or "").strip():
        return existing
    plan = _generate_execution_plan(db, requirement)
    requirement.execution_plan_json = _json_dump(plan)
    requirement.current_plan_version = int(getattr(requirement, "current_plan_version", 0) or 0) + 1
    requirement.updated_at = utcnow()
    db.flush()
    return plan


def _ensure_generated_requirement_assets(db: Session, requirement: RequirementRow) -> None:
    requirement.assets_status = "pending"
    requirement.assets_error_message = None
    acceptance = _parse_acceptance_contract(requirement)
    if not acceptance.get("done_criteria") or not str(acceptance.get("markdown") or "").strip():
        required_checks = _required_checks_for_target(db, getattr(requirement, "target_project_path", None))
        try:
            contract = _generate_acceptance_contract_with_agent(
                title=str(getattr(requirement, "title", "") or ""),
                description_markdown=str(getattr(requirement, "description_markdown", "") or ""),
                target_project_path=str(getattr(requirement, "target_project_path", "") or "") or None,
                required_checks=required_checks,
            )
        except Exception:
            contract = _fallback_acceptance_contract(
                title=str(getattr(requirement, "title", "") or ""),
                description_markdown=str(getattr(requirement, "description_markdown", "") or ""),
                target_project_path=str(getattr(requirement, "target_project_path", "") or "") or None,
                required_checks=required_checks,
            )
        requirement.acceptance_contract_json = _json_dump(contract)
    _ensure_execution_plan(db, requirement)
    requirement.assets_status = "ready"
    requirement.assets_error_message = None
    requirement.updated_at = utcnow()
    db.flush()


def _background_requirement_asset_generation(requirement_id: int) -> None:
    db = SessionLocal()
    try:
        requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
        if requirement is None:
            return
        _ensure_generated_requirement_assets(db, requirement)
        _log_workflow_event(
            "requirement_assets_generated",
            requirement=requirement,
            acceptance_generated=bool(_parse_acceptance_markdown(requirement)),
            plan_generated=bool(str(_parse_execution_plan(requirement).get("summary_markdown") or "").strip()),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
        if requirement is not None:
            requirement.assets_status = "failed"
            requirement.assets_error_message = str(exc)
            requirement.updated_at = utcnow()
            db.commit()
        log_event(
            logger,
            "requirement_assets_generation_failed",
            requirement_id=requirement_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    finally:
        db.close()


def _enqueue_requirement_asset_generation(requirement_id: int) -> None:
    threading.Thread(
        target=_background_requirement_asset_generation,
        args=(requirement_id,),
        daemon=True,
    ).start()


def _load_full_persona(agent_id: str) -> dict[str, Any]:
    persona_path = PROJECT_ROOT / "roles" / agent_id / "prompts" / "persona.md"
    if not persona_path.exists():
        return {"role": agent_id, "display_name": agent_id, "goal": "", "body": ""}
    text = persona_path.read_text(encoding="utf-8")
    frontmatter: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            frontmatter = yaml.safe_load(text[3:end]) or {}
            body = text[end + 3 :].strip()
    return {
        "role": agent_id,
        "display_name": frontmatter.get("display_name") or agent_id,
        "goal": frontmatter.get("goal") or "",
        "body": body,
    }


def create_execution_run(db: Session, requirement_id: int) -> ExecutionRunDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    active_run = _active_execution_run(db, int(requirement.id))
    if active_run is not None:
        raise ValueError(f"Requirement already has an active execution run: #{int(active_run.id)}.")
    requirement = reconcile_requirement_state(db, requirement)
    if str(requirement.status or "") not in {"ready", "blocked", "needs_revision"}:
        raise ValueError("Requirement must be ready before creating execution.")
    if _approval_required(db, requirement) and str(requirement.approval_status or "") not in {"approved", "waived"}:
        raise ValueError("Requirement must be approved before creating execution.")
    shape = _shape_decision(db, requirement)
    plan_snapshot = _ensure_execution_plan(db, requirement)
    run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode=str(shape["execution_mode"]),
        complexity=str(shape["complexity"]),
        status="queued",
        phase="queued",
        validation_profile=str(shape["validation_profile"]),
        delivery_intent=str(shape["delivery_intent"]),
        approval_required=_approval_required(db, requirement),
        planner_summary=str(plan_snapshot.get("summary_markdown") or shape["planner_summary"]),
        plan_snapshot_json=_json_dump(plan_snapshot),
        target_projects_json=_json_dump(_target_projects_for_requirement(db, requirement)),
    )
    db.add(run)
    db.flush()
    for index, step in enumerate(shape["execution_steps"], start=1):
        db.add(
            ExecutionNodeRow(
                execution_run_id=int(run.id),
                requirement_id=int(requirement.id),
                node_key=str(step["node_key"]),
                node_type="execute",
                title=str(step["title"]),
                status="queued",
                sequence_no=index,
            )
        )
    requirement.phase = "branch_prepared"
    requirement.status = _requirement_status_from_phase(requirement.phase)
    requirement.started_at = None
    requirement.completed_at = None
    _log_workflow_event(
        "execution_run_created",
        requirement=requirement,
        execution=run,
        target_projects=_target_projects_for_requirement(db, requirement),
        node_count=len(shape["execution_steps"]),
        planner_summary=str(plan_snapshot.get("summary_markdown") or shape["planner_summary"]),
    )
    db.commit()
    return build_execution_detail(db, int(run.id))


def list_execution_runs(db: Session) -> list[ExecutionRunOut]:
    rows = db.query(ExecutionRunRow).order_by(ExecutionRunRow.updated_at.desc(), ExecutionRunRow.id.desc()).all()
    return [build_execution_detail(db, int(row.id)).execution for row in rows]


def _latest_execution_run(db: Session, requirement_id: int) -> ExecutionRunRow | None:
    return (
        db.query(ExecutionRunRow)
        .filter(ExecutionRunRow.requirement_id == requirement_id)
        .order_by(ExecutionRunRow.id.desc())
        .first()
    )


def _active_execution_run(db: Session, requirement_id: int) -> ExecutionRunRow | None:
    return (
        db.query(ExecutionRunRow)
        .filter(
            ExecutionRunRow.requirement_id == requirement_id,
            ExecutionRunRow.status.in_(["queued", "running", "paused", "validating"]),
        )
        .order_by(ExecutionRunRow.id.desc())
        .first()
    )


def _node_task_status(task: TaskRow | None) -> str | None:
    if task is None:
        return None
    return str(getattr(task, "status", "") or "") or None


def _sync_execution_state(db: Session, run: ExecutionRunRow) -> ExecutionRunRow:
    return reconcile_execution_state(db, run)


def _build_task_description(db: Session, requirement: RequirementRow, run: ExecutionRunRow, node: ExecutionNodeRow) -> str:
    targets = _target_projects_for_requirement(db, requirement)
    attachment_lines = _attachment_prompt_lines(db, int(requirement.id))
    acceptance_contract = _parse_acceptance_contract(requirement)
    acceptance = str(acceptance_contract.get("markdown") or "").strip() or "Deliver the requested outcome and leave enough evidence for validate."
    plan = _parse_run_plan_snapshot(run) or _parse_execution_plan(requirement)
    plan_markdown = str(plan.get("summary_markdown") or "").strip()
    return "\n".join(
        [
            f"# Requirement #{int(requirement.id)}",
            "",
            f"## Title\n{requirement.title}",
            "",
            f"## Execution Node\n{node.title}",
            "",
            f"## Requirement Description\n{requirement.description_markdown}",
            "",
            f"## Acceptance\n{acceptance}",
            "",
            f"## Execution Plan\n{plan_markdown or 'Follow the generated execution plan and keep the change minimal.'}",
            "",
            "## Target Projects",
            *[f"- {item}" for item in targets],
            "",
            *attachment_lines,
            *([""] if attachment_lines else []),
            f"## Execution Mode\n{run.execution_mode}",
            "",
            "## Guardrails",
            "- Make the minimal necessary change.",
            "- Run only the checks needed to support the change before validate.",
            "- Summarize files changed, commands run, and remaining risk in the final output.",
        ]
    ).strip()


def _next_runnable_node(db: Session, run: ExecutionRunRow) -> ExecutionNodeRow | None:
    nodes = (
        db.query(ExecutionNodeRow)
        .filter(ExecutionNodeRow.execution_run_id == run.id)
        .order_by(ExecutionNodeRow.sequence_no.asc(), ExecutionNodeRow.id.asc())
        .all()
    )
    for node in nodes:
        if str(node.status or "") in {"queued", "paused"}:
            previous = [item for item in nodes if item.sequence_no < node.sequence_no]
            if all(str(item.status or "") == "completed" for item in previous):
                return node
    return None


def start_execution_run(db: Session, execution_run_id: int) -> ExecutionRunDetailOut:
    run = db.query(ExecutionRunRow).filter(ExecutionRunRow.id == execution_run_id).first()
    if run is None:
        raise ValueError("Execution run not found.")
    _sync_execution_state(db, run)
    current_execution = _latest_execution_run(db, int(run.requirement_id))
    if current_execution is None or int(current_execution.id) != int(run.id):
        raise ValueError("Only the current execution run can start.")
    if str(run.status or "") == "running":
        return build_execution_detail(db, execution_run_id)
    if str(run.status or "") not in {"queued", "paused", "blocked"}:
        raise ValueError("Only queued or paused execution runs can start.")
    requirement = db.query(RequirementRow).filter(RequirementRow.id == run.requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    if run.approval_required and str(requirement.approval_status or "") not in {"approved", "waived"}:
        raise ValueError("Requirement must be approved before execution starts.")
    _prepare_delivery_branch_for_execution(db, requirement, actor="system")
    db.refresh(run)
    db.refresh(requirement)
    node = _next_runnable_node(db, run)
    if node is None:
        raise ValueError("No runnable execution node found.")
    if node.task_id:
        task = db.query(TaskRow).filter(TaskRow.id == node.task_id).first()
        if task is not None and str(task.status or "") == "running":
            return build_execution_detail(db, execution_run_id)
    description = _build_task_description(db, requirement, run, node)
    suggestion = suggest_task_execution(db=db, description=description)
    if not suggestion.agent_id:
        raise ValueError("Unable to resolve an execution agent for this requirement.")
    persona = _load_full_persona(str(suggestion.agent_id))
    task = TaskRow(
        description=description,
        agent_id=str(suggestion.agent_id),
        status="running",
        requires_approval=False,
        priority=str(requirement.priority or "normal"),
        skill_name=str(suggestion.skill_name or "__direct_execution__"),
        started_at=utcnow(),
        runtime_backend=ORCHESTRATION_BACKEND,
        context_files=_json_dump(_requirement_attachment_context_files(db, int(requirement.id))),
    )
    db.add(task)
    db.flush()
    node.task_id = int(task.id)
    node.status = "running"
    node.started_at = utcnow()
    run.latest_task_id = int(task.id)
    run.phase = "executing"
    run.status = _execution_status_from_phase(run.phase)
    run.recovery_status = None
    run.started_at = run.started_at or utcnow()
    run.completed_at = None
    requirement.phase = "executing"
    requirement.status = _requirement_status_from_phase(requirement.phase)
    requirement.recovery_status = None
    requirement.completed_at = None
    _log_workflow_event(
        "execution_run_started",
        requirement=requirement,
        execution=run,
        task_id=int(task.id),
        node_key=str(node.node_key or ""),
        node_title=str(node.title or ""),
        agent_id=str(task.agent_id or ""),
        skill_name=str(task.skill_name or "__direct_execution__"),
        runtime_backend=str(task.runtime_backend or "").strip() or None,
    )
    db.commit()
    dispatch(task_id=int(task.id), agent_persona=persona, skill_name=str(task.skill_name or "__direct_execution__"))
    return build_execution_detail(db, execution_run_id)


def pause_execution_run(db: Session, execution_run_id: int) -> ExecutionRunDetailOut:
    run = db.query(ExecutionRunRow).filter(ExecutionRunRow.id == execution_run_id).first()
    if run is None:
        raise ValueError("Execution run not found.")
    current = _next_running_node(db, run)
    if current is None or current.task_id is None:
        raise ValueError("No running execution node found.")
    pause_legacy_task(db, int(current.task_id), reason="Paused from execution console")
    current.status = "paused"
    run.phase = "blocked"
    run.status = _execution_status_from_phase(run.phase)
    requirement = db.query(RequirementRow).filter(RequirementRow.id == run.requirement_id).first()
    if requirement is not None:
        requirement.phase = "blocked"
        requirement.status = _requirement_status_from_phase(requirement.phase)
    _log_workflow_event(
        "execution_run_paused",
        requirement=requirement,
        execution=run,
        task_id=int(current.task_id),
        node_key=str(current.node_key or ""),
    )
    db.commit()
    return build_execution_detail(db, execution_run_id)


def _next_running_node(db: Session, run: ExecutionRunRow) -> ExecutionNodeRow | None:
    nodes = (
        db.query(ExecutionNodeRow)
        .filter(ExecutionNodeRow.execution_run_id == run.id)
        .order_by(ExecutionNodeRow.sequence_no.asc(), ExecutionNodeRow.id.asc())
        .all()
    )
    for node in nodes:
        if str(node.status or "") == "running":
            return node
    return None


def _background_verify_execution(execution_run_id: int) -> None:
    db = SessionLocal()
    try:
        validate_execution_run(db, execution_run_id)
    except Exception as exc:
        db.rollback()
        log_event(
            logger,
            "execution_verification_failed",
            execution_id=execution_run_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    finally:
        db.close()


def _enqueue_execution_verification(execution_run_id: int) -> None:
    if _testing_mode():
        return
    threading.Thread(
        target=_background_verify_execution,
        args=(execution_run_id,),
        daemon=True,
    ).start()


def retry_execution_run(db: Session, execution_run_id: int) -> ExecutionRunDetailOut:
    run = db.query(ExecutionRunRow).filter(ExecutionRunRow.id == execution_run_id).first()
    if run is None:
        raise ValueError("Execution run not found.")
    original_status = str(run.status or "")
    _sync_execution_state(db, run)
    requirement = db.query(RequirementRow).filter(RequirementRow.id == run.requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    if str(run.status or "") == "running":
        return build_execution_detail(db, execution_run_id)
    if str(run.status or "") not in {"failed", "blocked"}:
        raise ValueError("Only failed or blocked execution runs can be retried.")
    if _retry_budget_exhausted(db, int(run.requirement_id)):
        raise ValueError(
            f"Execution retry limit reached ({_MAX_EXECUTION_RETRIES}). Please revise the requirement or route it to a follow-up flow."
        )
    active_run = _active_execution_run(db, int(run.requirement_id))
    if active_run is not None and int(active_run.id) != int(run.id):
        raise ValueError(f"Requirement already has an active execution run: #{int(active_run.id)}.")
    run.phase = "blocked"
    run.status = "failed" if original_status == "failed" else _execution_status_from_phase(run.phase)
    run.completed_at = run.completed_at or utcnow()
    requirement.phase = "needs_revision" if str(requirement.approval_status or "") == "rejected" else "branch_prepared"
    requirement.status = _requirement_status_from_phase(requirement.phase)
    requirement.updated_at = utcnow()
    _log_workflow_event(
        "execution_run_retry_requested",
        requirement=requirement,
        execution=run,
    )
    db.commit()
    detail = create_execution_run(db, int(run.requirement_id))
    replacement = db.query(ExecutionRunRow).filter(ExecutionRunRow.id == int(detail.execution.id)).first()
    _log_workflow_event(
        "execution_run_retried",
        requirement=requirement,
        execution=replacement,
        previous_execution_id=int(run.id),
    )
    db.commit()
    try:
        return start_execution_run(db, int(detail.execution.id))
    except ValueError as exc:
        db.rollback()
        _log_workflow_event(
            "execution_run_retry_start_blocked",
            requirement=requirement,
            execution=replacement,
            previous_execution_id=int(run.id),
            reason=str(exc),
        )
        db.commit()
        return build_execution_detail(db, int(detail.execution.id))


def _run_check(project_path: str, command: str) -> ValidationCheckResultOut:
    completed = subprocess.run(
        command,
        cwd=project_path,
        shell=True,
        text=True,
        capture_output=True,
        timeout=300,
    )
    output = (completed.stdout or completed.stderr or "").strip()
    return ValidationCheckResultOut(
        label=f"{Path(project_path).name}: {command}",
        command=command,
        project_path=project_path,
        status="passed" if completed.returncode == 0 else "failed",
        output_excerpt=output[:1200] or None,
    )


def _commands_from_execution_evidence(nodes: list[ExecutionNodeRow], db: Session) -> list[str]:
    """Extract deterministic check commands from completed execution evidence."""

    commands: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        if node.task_id is None:
            continue
        task = db.query(TaskRow).filter(TaskRow.id == node.task_id).first()
        body = str(getattr(task, "output_content", "") or node.summary_markdown or "")
        if not body:
            continue
        in_commands = False
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line:
                if in_commands:
                    break
                continue
            if line.lower().startswith("commands run:"):
                in_commands = True
                continue
            if in_commands and line.startswith("- `") and line.endswith("`"):
                command = line[3:-1].strip()
                if "..." in command:
                    continue
                if command and command not in seen:
                    seen.add(command)
                    commands.append(command)
            elif in_commands and not line.startswith("- "):
                break
    return commands


def _verification_payload_for_run(
    db: Session,
    *,
    requirement: RequirementRow,
    run: ExecutionRunRow,
    nodes: list[ExecutionNodeRow],
    checks: list[ValidationCheckResultOut],
) -> dict[str, Any]:
    changed_files = [item.model_dump() for item in _collect_execution_changed_files(db, nodes)]
    raw_task_output, _truncated = _execution_raw_output(nodes, db)
    plan_summary = _parse_run_plan_snapshot(run) or _parse_execution_plan(requirement)
    commands_run = _commands_from_execution_evidence(nodes, db)
    activity_stream = [
        item.model_dump()
        for item in _build_execution_activity_stream(run, nodes, None, [])
    ]
    attachments = [
        serialize_requirement_attachment(item)
        for item in _requirement_attachment_rows(db, int(requirement.id))
    ]
    return {
        "requirement": {
            "id": int(requirement.id),
            "title": str(requirement.title or ""),
            "description_markdown": str(requirement.description_markdown or ""),
            "priority": str(requirement.priority or "normal"),
            "target_project_path": str(requirement.target_project_path or "").strip() or None,
        },
        "attachments": attachments,
        "acceptance_contract": _parse_acceptance_contract(requirement),
        "execution_plan": plan_summary,
        "verification_strategy": list(plan_summary.get("planned_checks") or []),
        "execution_observability": {
            "execution_id": int(run.id),
            "status": str(run.status or "validating"),
            "validation_profile": str(run.validation_profile or "minimal"),
            "delivery_intent": str(run.delivery_intent or "pr_required"),
            "branch": str(getattr(_latest_release(db, int(requirement.id)), "branch_name", "") or "").strip() or None,
            "elapsed_ms": _elapsed_ms(run.started_at, run.completed_at),
            "nodes": [
                {
                    "node_key": str(node.node_key or ""),
                    "title": str(node.title or ""),
                    "status": str(node.status or ""),
                    "task_id": int(node.task_id) if node.task_id is not None else None,
                    "summary_markdown": str(node.summary_markdown or "").strip() or None,
                }
                for node in nodes
            ],
        },
        "commands_run": commands_run,
        "check_results": [item.model_dump() for item in checks],
        "changed_files": changed_files,
        "raw_task_output": raw_task_output,
        "activity_stream": activity_stream,
    }


def _retry_budget_exhausted(
    db: Session,
    requirement_id: int,
    *,
    retry_limit: int = _MAX_EXECUTION_RETRIES,
) -> bool:
    run_count = (
        db.query(ExecutionRunRow)
        .filter(ExecutionRunRow.requirement_id == requirement_id)
        .count()
    )
    return max(0, int(run_count) - 1) >= retry_limit


def _normalize_resolution_recommendation(result: dict[str, Any], verdict: str) -> str:
    if verdict == "passed":
        return "retry_execution"
    recommendation = str(result.get("resolution_recommendation") or "").strip()
    if recommendation in {"retry_execution", "create_followup_requirement", "revise_requirement", "route_to_human"}:
        return recommendation
    suggested = str(result.get("suggested_next_action") or "").strip()
    if suggested == "retry_execution":
        return "retry_execution"
    if suggested == "revise_requirement":
        return "revise_requirement"
    if verdict == "inconclusive":
        return "route_to_human"
    return "retry_execution"


def _resolve_validation_resolution(
    db: Session,
    *,
    requirement: RequirementRow,
    result: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    recommendation = _normalize_resolution_recommendation(result, str(result.get("status") or "inconclusive"))
    confidence = _float_or_none(result.get("resolution_confidence"))
    payload = dict(result.get("followup_requirement_payload") or {})
    target_project_path = str(getattr(requirement, "target_project_path", "") or "").strip() or None
    same_project = not payload.get("project_key") or str(payload.get("project_key") or "").strip() == str(getattr(requirement, "project_key", "") or "").strip()
    same_repo = not payload.get("target_project_path") or str(payload.get("target_project_path") or "").strip() == (target_project_path or "")
    scope_assessment = str(payload.get("scope_assessment") or "same_scope").strip() or "same_scope"
    same_scope = scope_assessment != "out_of_scope"
    high_risk_requirement = str(getattr(requirement, "priority", "normal") or "normal") == "high"
    low_confidence_recommendation = confidence is not None and confidence < 0.72
    retry_budget_hit = _retry_budget_exhausted(db, int(requirement.id))
    followup_fanout_blocked = bool(getattr(requirement, "followup_requirement_id", None))
    ownership_change_required = bool(payload.get("ownership_change_required"))
    rule_snapshot = {
        "same_project": same_project,
        "same_repo": same_repo,
        "same_scope": same_scope,
        "high_risk_requirement": high_risk_requirement,
        "low_confidence_recommendation": low_confidence_recommendation,
        "retry_budget_exhausted": retry_budget_hit,
        "followup_fanout_blocked": followup_fanout_blocked,
        "ownership_change_required": ownership_change_required,
    }
    verdict = str(result.get("status") or "inconclusive")
    if verdict == "passed":
        return "release_ready", rule_snapshot
    if recommendation == "revise_requirement":
        return "revise_requirement", rule_snapshot
    if (
        recommendation == "create_followup_requirement"
        and (not same_scope or not same_project or not same_repo or ownership_change_required or retry_budget_hit)
        and not high_risk_requirement
        and not low_confidence_recommendation
        and not followup_fanout_blocked
    ):
        return "create_followup_requirement", rule_snapshot
    if (
        high_risk_requirement
        or low_confidence_recommendation
        or followup_fanout_blocked
        or (recommendation == "create_followup_requirement" and same_scope and same_project and same_repo and not retry_budget_hit)
        or verdict == "inconclusive"
    ):
        return "route_to_human", rule_snapshot
    return "retry_execution", rule_snapshot


def _create_followup_requirement_from_validation(
    db: Session,
    *,
    requirement: RequirementRow,
    run: ExecutionRunRow,
    validation: ValidationRecordRow,
    result: dict[str, Any],
) -> RequirementRow:
    project = _project_for_requirement(db, requirement)
    payload = dict(result.get("followup_requirement_payload") or {})
    title = str(payload.get("title") or "").strip() or f"修复 verification 暴露的问题：{str(requirement.title or '').strip()}"
    priority = str(payload.get("priority") or getattr(requirement, "priority", "normal") or "normal").strip() or "normal"
    target_project_path = str(payload.get("target_project_path") or getattr(requirement, "target_project_path", "") or "").strip() or None
    description_markdown = str(payload.get("description_markdown") or "").strip() or "\n".join(
        [
            f"源需求 #{int(requirement.id)}: {str(requirement.title or '').strip()}",
            f"源执行 #{int(run.id)} 验证建议派生一个后续修复需求。",
            "",
            f"验证结论：{str(result.get('summary') or '').strip()}",
            "",
            f"原因：{str(result.get('resolution_reason') or result.get('reasoning') or '').strip()}",
        ]
    ).strip()
    followup = RequirementRow(
        title=title,
        description_markdown=description_markdown,
        status="draft",
        phase="planning",
        priority=priority if priority in {"low", "normal", "high"} else "normal",
        source="verification_followup",
        source_ref=f"validation:{int(validation.id)}",
        intake_metadata_json=_json_dump(
            {
                "resolution_path": "create_followup_requirement",
                "origin_requirement_id": int(requirement.id),
                "origin_execution_run_id": int(run.id),
                "origin_validation_id": int(validation.id),
            }
        ),
        project_id=int(project.id) if project is not None else (int(requirement.project_id) if getattr(requirement, "project_id", None) is not None else None),
        project_key=str(getattr(project, "project_key", "") or "").strip() or str(getattr(requirement, "project_key", "") or "").strip(),
        project_display_name=str(getattr(project, "display_name", "") or "").strip() or str(getattr(requirement, "project_display_name", "") or "").strip(),
        target_project_path=target_project_path or str(getattr(requirement, "target_project_path", "") or "").strip() or None,
        acceptance_contract_json=_json_dump({}),
        execution_plan_json=_json_dump({}),
        assets_status="pending",
        assets_error_message=None,
        approval_status="pending_approval",
        approval_contract_json=_json_dump({}),
        linked_requirement_id=int(requirement.id),
        origin_execution_run_id=int(run.id),
        origin_validation_id=int(validation.id),
        resolution_path="verification_followup",
    )
    db.add(followup)
    db.flush()
    approval_required = _approval_required(db, followup)
    followup.approval_status = "pending_approval" if approval_required else "waived"
    db.flush()
    if _testing_mode():
        _ensure_generated_requirement_assets(db, followup)
    return followup


def _persist_verification_result(
    db: Session,
    *,
    requirement: RequirementRow,
    run: ExecutionRunRow,
    checks: list[ValidationCheckResultOut],
    result: dict[str, Any],
) -> ValidationRecordRow:
    record = ValidationRecordRow(
        requirement_id=int(requirement.id),
        execution_run_id=int(run.id),
        profile=str(run.validation_profile or "minimal"),
        status=str(result.get("status") or "inconclusive"),
        summary_markdown=str(result.get("summary") or "").strip(),
        checks_json=_json_dump([check.model_dump() for check in checks]),
        verification_plan_json=_json_dump(result.get("verification_plan") or {}),
        verification_agent_id=str(result.get("verification_agent_id") or "verification_agent"),
        verification_agent_label=str(result.get("verification_agent_label") or "Verification Agent"),
        evidence_json=_json_dump([str(item).strip() for item in result.get("evidence_used") or [] if str(item).strip()]),
        reasoning_markdown=str(result.get("reasoning") or "").strip(),
        suggested_next_action=str(result.get("suggested_next_action") or "revise_requirement").strip() or "revise_requirement",
        resolution_recommendation=(
            None
            if str(result.get("status") or "") == "passed"
            else str(result.get("resolution_recommendation") or "").strip() or None
        ),
        resolution_confidence=_float_or_none(result.get("resolution_confidence")),
        resolution_reason=str(result.get("resolution_reason") or "").strip() or None,
        resolution_path=str(result.get("resolution_path") or "").strip() or None,
        followup_requirement_id=int(result.get("followup_requirement_id")) if result.get("followup_requirement_id") is not None else None,
        followup_requirement_payload_json=_json_dump(result.get("followup_requirement_payload") or {}),
    )
    db.add(record)
    db.flush()
    return record


def validate_execution_run(db: Session, execution_run_id: int) -> ExecutionRunDetailOut:
    run = db.query(ExecutionRunRow).filter(ExecutionRunRow.id == execution_run_id).first()
    if run is None:
        raise ValueError("Execution run not found.")
    _sync_execution_state(db, run)
    current_execution = _latest_execution_run(db, int(run.requirement_id))
    if current_execution is None or int(current_execution.id) != int(run.id):
        raise ValueError("Only the current execution run can be validated.")
    requirement = db.query(RequirementRow).filter(RequirementRow.id == run.requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    nodes = (
        db.query(ExecutionNodeRow)
        .filter(ExecutionNodeRow.execution_run_id == run.id)
        .order_by(ExecutionNodeRow.sequence_no.asc(), ExecutionNodeRow.id.asc())
        .all()
    )
    if not nodes or any(str(node.status or "") != "completed" for node in nodes):
        raise ValueError("All execute nodes must complete before validate.")
    checks: list[ValidationCheckResultOut] = []
    acceptance_contract = _parse_acceptance_contract(requirement)
    contract_checks = [
        item for item in acceptance_contract.get("verification_checks") or [] if isinstance(item, dict)
    ]
    project_path = str(getattr(requirement, "target_project_path", "") or "").strip()
    evidence_commands = _commands_from_execution_evidence(nodes, db)
    # Agent-first validation only auto-runs commands the execution agent actually
    # reported as part of its evidence. Acceptance contract commands remain
    # advisory context for the verification agent instead of becoming harness-
    # mandated root-level test sweeps.
    commands_to_run = evidence_commands
    for command in commands_to_run:
        checks.append(_run_check(project_path, command))
    for item in contract_checks:
        if str(item.get("command") or "").strip():
            continue
        checks.append(
            ValidationCheckResultOut(
                label=str(item.get("label") or "evidence review").strip() or "evidence review",
                status="passed",
                output_excerpt="Evidence-only verification item delegated to verification agent.",
            )
        )
    result = verify_with_agent(
        _verification_payload_for_run(
            db,
            requirement=requirement,
            run=run,
            nodes=nodes,
            checks=checks,
        ),
        skip_provider=_testing_mode(),
    )
    resolution_path, resolution_rules = _resolve_validation_resolution(
        db,
        requirement=requirement,
        result=result,
    )
    result["resolution_path"] = resolution_path
    result["resolution_reason"] = str(result.get("resolution_reason") or result.get("reasoning") or result.get("summary") or "").strip()
    result["resolution_rules"] = resolution_rules
    record = _persist_verification_result(
        db,
        requirement=requirement,
        run=run,
        checks=checks,
        result=result,
    )
    verdict = str(result.get("status") or "inconclusive")
    followup_requirement: RequirementRow | None = None
    if resolution_path == "create_followup_requirement":
        followup_requirement = _create_followup_requirement_from_validation(
            db,
            requirement=requirement,
            run=run,
            validation=record,
            result=result,
        )
        result["followup_requirement_id"] = int(followup_requirement.id)
        result["followup_requirement_payload"] = {
            **dict(result.get("followup_requirement_payload") or {}),
            "created_requirement_id": int(followup_requirement.id),
        }
        record.followup_requirement_id = int(followup_requirement.id)
        record.followup_requirement_payload_json = _json_dump(result.get("followup_requirement_payload") or {})
        requirement.followup_requirement_id = int(followup_requirement.id)
    requirement.resolution_path = resolution_path
    run.phase = "delivery_ready" if verdict == "passed" else "blocked"
    run.status = _execution_status_from_phase(run.phase)
    run.completed_at = run.completed_at or utcnow()
    if verdict == "passed":
        requirement.phase = "delivery_ready"
    elif resolution_path == "route_to_human":
        requirement.phase = "blocked"
    elif resolution_path == "create_followup_requirement":
        requirement.phase = "blocked"
    else:
        requirement.phase = "needs_revision"
    requirement.status = _requirement_status_from_phase(requirement.phase)
    _log_workflow_event(
        "execution_run_validated",
        requirement=requirement,
        execution=run,
        validation=record,
        checks_total=len(checks),
        checks_failed=len([check for check in checks if check.status != "passed"]),
        verification_agent_id=str(result.get("verification_agent_id") or "verification_agent"),
        suggested_next_action=str(result.get("suggested_next_action") or "revise_requirement"),
        resolution_path=resolution_path,
        followup_requirement_id=int(followup_requirement.id) if followup_requirement is not None else None,
    )
    db.commit()
    if followup_requirement is not None and not _testing_mode():
        _enqueue_requirement_asset_generation(int(followup_requirement.id))
    if verdict == "passed":
        _auto_open_pr_after_verification(db, requirement, actor="verification_agent")
    return build_execution_detail(db, execution_run_id)


def reset_execution_runtime_data(db: Session) -> dict[str, int]:
    runtime_artifact_query = db.query(ArtifactRow).filter(
        or_(
            ArtifactRow.workflow_run_id.is_not(None),
            ArtifactRow.step_id.is_not(None),
            ArtifactRow.producer_step_id.is_not(None),
        )
    )
    codex_session_count = db.query(CodexSessionRow).count()
    workflow_run_count = db.query(WorkflowRunRow).count()
    workflow_step_count = db.query(WorkflowStepRow).count()
    workflow_step_dependency_count = db.query(WorkflowStepDependencyRow).count()
    workflow_step_event_count = db.query(WorkflowStepEventRow).count()
    step_input_binding_count = db.query(StepInputBindingRow).count()
    runtime_artifact_count = runtime_artifact_query.count()
    acceptance_check_count = db.query(RequirementAcceptanceCheckRow).count()
    approval_request_count = db.query(ApprovalRequestRow).count()
    approval_count = db.query(ApprovalRow).count()
    task_log_count = db.query(TaskLogRow).count()
    task_count = db.query(TaskRow).count()
    release_count = db.query(ReleaseRecordRow).count()
    validation_count = db.query(ValidationRecordRow).count()
    node_count = db.query(ExecutionNodeRow).count()
    run_count = db.query(ExecutionRunRow).count()

    db.query(RequirementRow).update({"active_workflow_run_id": None}, synchronize_session=False)
    db.query(WorkflowRunRow).update({"planner_artifact_id": None}, synchronize_session=False)
    db.query(ReleaseRecordRow).delete(synchronize_session=False)
    db.query(ValidationRecordRow).delete(synchronize_session=False)
    db.query(ExecutionNodeRow).delete(synchronize_session=False)
    db.query(ExecutionRunRow).delete(synchronize_session=False)
    db.query(CodexSessionRow).delete(synchronize_session=False)
    db.query(ApprovalRequestRow).delete(synchronize_session=False)
    db.query(WorkflowStepEventRow).delete(synchronize_session=False)
    db.query(StepInputBindingRow).delete(synchronize_session=False)
    db.query(WorkflowStepDependencyRow).delete(synchronize_session=False)
    db.query(RequirementAcceptanceCheckRow).delete(synchronize_session=False)
    runtime_artifact_query.delete(synchronize_session=False)
    db.query(WorkflowStepRow).update({"branch_from_step_id": None}, synchronize_session=False)
    db.query(WorkflowStepRow).delete(synchronize_session=False)
    db.query(WorkflowRunRow).delete(synchronize_session=False)
    db.query(ApprovalRow).delete(synchronize_session=False)
    db.query(TaskLogRow).delete(synchronize_session=False)
    db.query(TaskRow).delete(synchronize_session=False)

    updated_requirements = 0
    for requirement in db.query(RequirementRow).all():
        current_status = str(requirement.status or "draft")
        if current_status in {"draft", "cancelled", "deleted"}:
            continue
        approval_status = str(requirement.approval_status or "pending_approval")
        if approval_status == "pending_approval":
            next_status = "blocked"
        elif approval_status == "rejected":
            next_status = "needs_revision"
        else:
            next_status = "ready"
        if (
            current_status != next_status
            or requirement.started_at is not None
            or requirement.completed_at is not None
        ):
            requirement.status = next_status
            requirement.started_at = None
            requirement.completed_at = None
            requirement.active_workflow_run_id = None
            requirement.updated_at = utcnow()
            updated_requirements += 1

    result = {
        "codex_sessions_deleted": int(codex_session_count),
        "workflow_runs_deleted": int(workflow_run_count),
        "workflow_steps_deleted": int(workflow_step_count),
        "workflow_step_dependencies_deleted": int(workflow_step_dependency_count),
        "workflow_step_events_deleted": int(workflow_step_event_count),
        "step_input_bindings_deleted": int(step_input_binding_count),
        "runtime_artifacts_deleted": int(runtime_artifact_count),
        "acceptance_checks_deleted": int(acceptance_check_count),
        "approval_requests_deleted": int(approval_request_count),
        "approvals_deleted": int(approval_count),
        "task_logs_deleted": int(task_log_count),
        "tasks_deleted": int(task_count),
        "execution_runs_deleted": int(run_count),
        "execution_nodes_deleted": int(node_count),
        "validation_records_deleted": int(validation_count),
        "release_records_deleted": int(release_count),
        "requirements_reset": int(updated_requirements),
    }
    log_event(logger, "execution_runtime_reset", **result)
    db.commit()
    return result


def _validation_record_to_out(record: ValidationRecordRow | None) -> ValidationRecordSlimOut | None:
    if record is None:
        return None
    checks_payload = _json_load(record.checks_json, [])
    checks: list[ValidationCheckResultOut] = []
    if isinstance(checks_payload, list):
        for item in checks_payload:
            if isinstance(item, dict):
                checks.append(ValidationCheckResultOut(**item))
    evidence_payload = _json_load(getattr(record, "evidence_json", None), [])
    evidence_used = [str(item).strip() for item in evidence_payload if str(item).strip()] if isinstance(evidence_payload, list) else []
    verification_plan_payload = _json_load(getattr(record, "verification_plan_json", None), {})
    followup_payload = _json_load(getattr(record, "followup_requirement_payload_json", None), {})
    return ValidationRecordSlimOut(
        id=int(record.id),
        requirement_id=int(record.requirement_id),
        execution_run_id=int(record.execution_run_id),
        profile=str(record.profile or "minimal"),
        status=str(record.status or "pending"),
        summary_markdown=str(record.summary_markdown or ""),
        checks=checks,
        verification_plan=VerificationPlanOut(**verification_plan_payload) if isinstance(verification_plan_payload, dict) and verification_plan_payload else None,
        verification_agent_id=str(getattr(record, "verification_agent_id", "") or "").strip() or None,
        verification_agent_label=str(getattr(record, "verification_agent_label", "") or "").strip() or None,
        evidence_used=evidence_used,
        reasoning_markdown=str(getattr(record, "reasoning_markdown", "") or ""),
        suggested_next_action=str(getattr(record, "suggested_next_action", "") or "").strip() or None,
        resolution_recommendation=str(getattr(record, "resolution_recommendation", "") or "").strip() or None,
        resolution_confidence=_float_or_none(getattr(record, "resolution_confidence", None)),
        resolution_reason=str(getattr(record, "resolution_reason", "") or "").strip() or None,
        resolution_path=str(getattr(record, "resolution_path", "") or "").strip() or None,
        followup_requirement_id=int(getattr(record, "followup_requirement_id", 0) or 0) or None,
        followup_requirement_payload=followup_payload if isinstance(followup_payload, dict) else {},
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _elapsed_ms(started_at, completed_at) -> int | None:
    if started_at is None:
        return None
    def _normalize_dt(value):
        if value is None:
            return None
        if getattr(value, "tzinfo", None) is None:
            return value.replace(tzinfo=utcnow().tzinfo)
        return value

    start = _normalize_dt(started_at)
    end_at = _normalize_dt(completed_at) or utcnow()
    return max(0, int((end_at - start).total_seconds() * 1000))


def _agent_label(db: Session, agent_id: str | None) -> str | None:
    cleaned = str(agent_id or "").strip()
    if not cleaned:
        return None
    row = db.query(AgentRow).filter(AgentRow.id == cleaned).first()
    if row is None:
        return cleaned
    return str(row.display_name or cleaned).strip() or cleaned


def _execution_node_task_payload(db: Session, node: ExecutionNodeRow) -> tuple[TaskRow | None, str | None, str | None]:
    task = db.query(TaskRow).filter(TaskRow.id == node.task_id).first() if node.task_id else None
    task_status = _node_task_status(task) if task is not None else None
    agent_id = str(task.agent_id or "").strip() or None if task is not None else None
    return task, task_status, agent_id


def _change_type(additions: int, deletions: int) -> str:
    if additions > 0 and deletions == 0:
        return "added"
    if deletions > 0 and additions == 0:
        return "deleted"
    return "modified"


def _collect_execution_changed_files(db: Session, nodes: list[ExecutionNodeRow]) -> list[ExecutionChangedFileOut]:
    merged: dict[tuple[str, str | None], dict[str, object]] = {}
    for node in nodes:
        if not node.task_id:
            continue
        task = db.query(TaskRow).filter(TaskRow.id == node.task_id).first()
        if task is None:
            continue
        payload = _normalize_task_file_change_payload(_load_task_file_changes(task))
        for change in _task_changed_files_from_payload(payload):
            path = str(change.get("filename") or "").strip()
            if not path:
                continue
            target_project_path = str(change.get("target_project_path") or "").strip() or None
            key = (path, target_project_path)
            current = merged.setdefault(
                key,
                {
                    "path": path,
                    "target_project_path": target_project_path,
                    "additions": 0,
                    "deletions": 0,
                    "patches": [],
                },
            )
            current["additions"] = int(current.get("additions") or 0) + int(change.get("additions") or 0)
            current["deletions"] = int(current.get("deletions") or 0) + int(change.get("deletions") or 0)
            patch = str(change.get("patch") or "")
            if patch:
                cast(list[str], current["patches"]).append(patch)
    results: list[ExecutionChangedFileOut] = []
    for (_, _), item in sorted(merged.items(), key=lambda pair: pair[0][0]):
        additions = int(item.get("additions") or 0)
        deletions = int(item.get("deletions") or 0)
        patches = cast(list[str], item.get("patches") or [])
        target_project_path = str(item.get("target_project_path") or "").strip() or None
        preview_available = bool(patches) or bool(target_project_path)
        results.append(
            ExecutionChangedFileOut(
                path=str(item.get("path") or ""),
                change_type=_change_type(additions, deletions),
                additions=additions,
                deletions=deletions,
                preview_available=preview_available,
            )
        )
    return results


def _build_execution_activity_stream(
    run: ExecutionRunRow,
    nodes: list[ExecutionNodeRow],
    validation: ValidationRecordRow | None,
    incidents: list[dict[str, object]],
) -> list[ExecutionActivityEventOut]:
    events: list[ExecutionActivityEventOut] = [
        ExecutionActivityEventOut(
            ts=run.created_at,
            event="run_created",
            status="completed",
            message="Execution run created.",
        )
    ]
    if run.started_at is not None:
        events.append(
            ExecutionActivityEventOut(
                ts=run.started_at,
                event="run_started",
                status=str(run.status or "running"),
                message="Execution run started.",
            )
        )
    for node in nodes:
        if node.started_at is not None:
            events.append(
                ExecutionActivityEventOut(
                    ts=node.started_at,
                    event="node_started",
                    status=str(node.status or "running"),
                    message=f"{str(node.title or node.node_key or 'Node')} started.",
                )
            )
        if node.completed_at is not None:
            events.append(
                ExecutionActivityEventOut(
                    ts=node.completed_at,
                    event="node_completed",
                    status=str(node.status or "completed"),
                    message=f"{str(node.title or node.node_key or 'Node')} completed.",
                )
            )
    if validation is not None:
        events.append(
            ExecutionActivityEventOut(
                ts=validation.created_at,
                event="validation_started",
                status=str(validation.status or "pending"),
                message="Validation started.",
            )
        )
        if str(validation.status or "") in {"passed", "failed"}:
            events.append(
                ExecutionActivityEventOut(
                    ts=validation.updated_at or validation.created_at,
                    event="validation_completed",
                    status=str(validation.status or "pending"),
                    message=f"Validation {str(validation.status or 'completed')}.",
                )
            )
    for incident in incidents:
        events.append(
            ExecutionActivityEventOut(
                ts=run.updated_at,
                event=str(incident.get("kind") or "incident"),
                status=str(run.status or ""),
                message=str(incident.get("summary") or "Execution incident recorded."),
            )
        )
    def _event_sort_key(item: ExecutionActivityEventOut):
        timestamp = item.ts
        if timestamp is None:
            return utcnow()
        if getattr(timestamp, "tzinfo", None) is None:
            return timestamp.replace(tzinfo=utcnow().tzinfo)
        return timestamp

    events.sort(key=_event_sort_key)
    return events


def _task_raw_output(task: TaskRow | None) -> tuple[str | None, bool]:
    if task is None:
        return None, False
    content = str(getattr(task, "output_content", "") or "")
    truncated = False
    if not content.strip():
        output_path = str(getattr(task, "output_path", "") or "").strip()
        if output_path:
            try:
                content = Path(output_path).read_text(encoding="utf-8")
            except Exception:
                content = ""
    if not content.strip():
        return None, False
    if len(content) > 16000:
        truncated = True
        content = content[:16000].rstrip() + "\n\n...[truncated]"
    return content, truncated


def _execution_raw_output(nodes: list[ExecutionNodeRow], db: Session) -> tuple[str | None, bool]:
    sections: list[str] = []
    truncated = False
    for node in nodes:
        if not node.task_id:
            continue
        task = db.query(TaskRow).filter(TaskRow.id == node.task_id).first()
        content, content_truncated = _task_raw_output(task)
        if not content:
            continue
        truncated = truncated or content_truncated
        sections.append(
            "\n".join(
                [
                    f"## {str(node.title or node.node_key or 'Task')}",
                    f"task #{int(node.task_id)} · {str(getattr(task, 'status', '') or node.status or '-')} · {str(getattr(task, 'runtime_model', '') or '').strip() or '-'}",
                    "",
                    content,
                ]
            ).strip()
        )
    if not sections:
        return None, False
    body = "\n\n".join(sections).strip()
    if len(body) > 24000:
        truncated = True
        body = body[:24000].rstrip() + "\n\n...[truncated]"
    return body, truncated


def _execution_file_preview(
    db: Session,
    execution_run_id: int,
    relative_path: str,
) -> ExecutionFilePreviewOut:
    run = db.query(ExecutionRunRow).filter(ExecutionRunRow.id == execution_run_id).first()
    if run is None:
        raise ValueError("Execution run not found.")
    nodes = (
        db.query(ExecutionNodeRow)
        .filter(ExecutionNodeRow.execution_run_id == run.id)
        .order_by(ExecutionNodeRow.sequence_no.asc(), ExecutionNodeRow.id.asc())
        .all()
    )
    normalized_path = str(relative_path or "").strip().lstrip("/")
    if not normalized_path:
        raise ValueError("Execution file path is required.")
    diff_chunks: list[str] = []
    target_project_path: str | None = None
    for node in nodes:
        if not node.task_id:
            continue
        task = db.query(TaskRow).filter(TaskRow.id == node.task_id).first()
        if task is None:
            continue
        payload = _normalize_task_file_change_payload(_load_task_file_changes(task))
        for change in _task_changed_files_from_payload(payload):
            if str(change.get("filename") or "").strip() != normalized_path:
                continue
            patch = str(change.get("patch") or "")
            if patch:
                diff_chunks.append(patch)
            if not target_project_path:
                target_project_path = str(change.get("target_project_path") or "").strip() or None
    if not diff_chunks and not target_project_path:
        raise ValueError("Execution file preview not found.")

    current_content: str | None = None
    truncated = False
    if target_project_path:
        target = (Path(target_project_path) / normalized_path).resolve()
        target_root = Path(target_project_path).resolve()
        if target_root == target or target_root in target.parents:
            if target.exists() and target.is_file():
                raw = target.read_text(encoding="utf-8", errors="replace")
                if len(raw) > 20000:
                    current_content = raw[:20000]
                    truncated = True
                else:
                    current_content = raw

    diff_patch = "\n".join(chunk for chunk in diff_chunks if chunk).strip() or None
    if diff_patch and len(diff_patch) > 20000:
        diff_patch = diff_patch[:20000]
        truncated = True
    return ExecutionFilePreviewOut(
        path=normalized_path,
        diff_patch=diff_patch,
        current_content=current_content,
        truncated=truncated,
    )


def build_execution_detail(db: Session, execution_run_id: int) -> ExecutionRunDetailOut:
    run = db.query(ExecutionRunRow).filter(ExecutionRunRow.id == execution_run_id).first()
    if run is None:
        raise ValueError("Execution run not found.")
    run = _sync_execution_state(db, run)
    requirement = db.query(RequirementRow).filter(RequirementRow.id == run.requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    requirement = reconcile_requirement_state(db, requirement)
    nodes = (
        db.query(ExecutionNodeRow)
        .filter(ExecutionNodeRow.execution_run_id == run.id)
        .order_by(ExecutionNodeRow.sequence_no.asc(), ExecutionNodeRow.id.asc())
        .all()
    )
    validation = (
        db.query(ValidationRecordRow)
        .filter(ValidationRecordRow.execution_run_id == run.id)
        .order_by(ValidationRecordRow.id.desc())
        .first()
    )
    release = _latest_release(db, int(requirement.id))
    is_current_execution = _is_current_execution(db, run)
    has_paused_node = any(str(getattr(node, "status", "") or "") == "paused" for node in nodes)
    latest_task = _latest_task_for_run(db, run)
    latest_session = _latest_session_for_run_task(db, run)
    node_out: list[ExecutionNodeOut] = []
    tokens_used_total = 0
    token_seen = False
    current_agent_id: str | None = None
    current_agent_label: str | None = None
    current_runtime_backend: str | None = None
    current_runtime_provider: str | None = None
    current_runtime_model: str | None = None
    for node in nodes:
        task, task_status, agent_id = _execution_node_task_payload(db, node)
        agent_label = _agent_label(db, agent_id)
        node_tokens = int(getattr(task, "tokens_used", 0) or 0) if task is not None else None
        if node_tokens is not None:
            tokens_used_total += node_tokens
            token_seen = True
        current_agent_id = agent_id or current_agent_id
        current_agent_label = agent_label or current_agent_label
        current_runtime_backend = (
            str(getattr(task, "runtime_backend", "") or "").strip()
            or str(node.runtime_backend or "").strip()
            or current_runtime_backend
        )
        current_runtime_provider = (
            str(getattr(task, "runtime_provider", "") or "").strip()
            or str(node.runtime_provider or "").strip()
            or current_runtime_provider
        )
        current_runtime_model = (
            str(getattr(task, "runtime_model", "") or "").strip()
            or str(node.runtime_model or "").strip()
            or current_runtime_model
        )
        node_out.append(
            ExecutionNodeOut(
                id=int(node.id),
                execution_run_id=int(node.execution_run_id),
                requirement_id=int(node.requirement_id),
                node_key=str(node.node_key or ""),
                node_type=str(node.node_type or "execute"),
                title=str(node.title or ""),
                status=str(node.status or "queued"),
                sequence_no=int(node.sequence_no or 1),
                task_id=int(node.task_id) if node.task_id is not None else None,
                task_status=task_status,
                agent_id=agent_id,
                agent_label=agent_label,
                runtime_backend=str(getattr(task, "runtime_backend", "") or "").strip() or str(node.runtime_backend or "").strip() or None,
                runtime_provider=str(getattr(task, "runtime_provider", "") or "").strip() or str(node.runtime_provider or "").strip() or None,
                runtime_model=str(getattr(task, "runtime_model", "") or "").strip() or str(node.runtime_model or "").strip() or None,
                tokens_used=node_tokens,
                elapsed_ms=_elapsed_ms(node.started_at, node.completed_at),
                summary_markdown=str(node.summary_markdown or "").strip() or None,
                started_at=node.started_at,
                completed_at=node.completed_at,
            )
        )
    execution = ExecutionRunOut(
        id=int(run.id),
        requirement_id=int(run.requirement_id),
        execution_mode=str(run.execution_mode or "direct"),
        complexity=str(run.complexity or "simple"),
        status=str(run.status or "queued"),
        phase=str(getattr(run, "phase", "") or run.status or "queued"),
        is_current_execution=is_current_execution,
        allowed_actions=_execution_allowed_actions(
            run,
            release,
            is_current_execution=is_current_execution,
            has_paused_node=has_paused_node,
        ),
        pending_operations=[],
        recovery_status=str(getattr(run, "recovery_status", "") or "").strip() or None,
        validation_profile=str(run.validation_profile or "minimal"),
        delivery_intent=str(run.delivery_intent or "pr_required"),
        approval_required=bool(run.approval_required),
        planner_summary=str(run.planner_summary or "").strip() or None,
        target_projects=_json_load(run.target_projects_json, []),
        latest_task_id=int(run.latest_task_id) if run.latest_task_id is not None else None,
        agent_id=current_agent_id,
        agent_label=current_agent_label,
        runtime_backend=current_runtime_backend,
        runtime_provider=current_runtime_provider,
        runtime_model=current_runtime_model,
        runtime_session_id=str(getattr(latest_task, "runtime_session_id", "") or "").strip() or None,
        resume_count=int(getattr(latest_session, "resume_count", 0) or 0) if latest_session is not None else None,
        last_heartbeat_at=getattr(latest_session, "last_heartbeat_at", None) if latest_session is not None else None,
        tokens_used_total=tokens_used_total if token_seen else None,
        elapsed_ms=_elapsed_ms(run.started_at, run.completed_at),
        current_branch=str(getattr(release, "branch_name", "") or "").strip() or None,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )
    queue_reason, blocking_reason_code, blocking_reason_message = _execution_reason_payload(
        run,
        requirement,
        validation=validation,
        release=release,
        nodes=nodes,
    )
    execution.queue_reason = queue_reason
    execution.blocking_reason_code = blocking_reason_code
    execution.blocking_reason_message = blocking_reason_message
    incidents: list[dict[str, object]] = []
    failed_node = next((node for node in nodes if str(node.status or "") == "failed"), None)
    if execution.status in {"blocked", "failed"}:
        incidents.append(
            {
                "kind": "execution_blocked",
                "summary": "Execution is blocked or failed. Retry or revise before validating again.",
            }
        )
        _notify_execution_error(db, run, requirement, failed_node)
        db.commit()
    changed_files = _collect_execution_changed_files(db, nodes)
    activity_stream = _build_execution_activity_stream(run, nodes, validation, incidents)
    raw_task_output, raw_task_output_truncated = _execution_raw_output(nodes, db)
    plan_summary = _parse_run_plan_snapshot(run) or _parse_execution_plan(requirement)
    validation_out = _validation_record_to_out(validation)
    return ExecutionRunDetailOut(
        execution=execution,
        requirement=_requirement_to_out(db, requirement),
        phase=str(getattr(run, "phase", "") or run.status or "queued"),
        is_current_execution=is_current_execution,
        allowed_actions=_execution_allowed_actions(
            run,
            release,
            is_current_execution=is_current_execution,
            has_paused_node=has_paused_node,
        ),
        pending_operations=[],
        recovery_status=str(getattr(run, "recovery_status", "") or "").strip() or None,
        queue_reason=queue_reason,
        blocking_reason_code=blocking_reason_code,
        blocking_reason_message=blocking_reason_message,
        nodes=node_out,
        validation=validation_out,
        verification_result=validation_out,
        verification_plan=validation_out.verification_plan if validation_out is not None else None,
        changed_files=changed_files,
        runtime_summary=ExecutionRuntimeSummaryOut(
            tokens_used_total=execution.tokens_used_total,
            elapsed_ms=execution.elapsed_ms,
            agent_id=execution.agent_id,
            agent_label=execution.agent_label,
            runtime_backend=execution.runtime_backend,
            runtime_provider=execution.runtime_provider,
            runtime_model=execution.runtime_model,
            current_branch=execution.current_branch,
        ),
        delivery_summary=_release_to_out(release),
        activity_stream=activity_stream,
        incidents=incidents,
        plan_summary=plan_summary,
        raw_task_output=raw_task_output,
        raw_task_output_truncated=raw_task_output_truncated,
    )


def _latest_validation(db: Session, requirement_id: int) -> ValidationRecordRow | None:
    return (
        db.query(ValidationRecordRow)
        .filter(ValidationRecordRow.requirement_id == requirement_id)
        .order_by(ValidationRecordRow.id.desc())
        .first()
    )


def _latest_release(db: Session, requirement_id: int) -> ReleaseRecordRow | None:
    return (
        db.query(ReleaseRecordRow)
        .filter(ReleaseRecordRow.requirement_id == requirement_id)
        .order_by(ReleaseRecordRow.id.desc())
        .first()
    )


def _release_to_out(release: ReleaseRecordRow | None) -> ReleaseRecordSlimOut | None:
    if release is None:
        return None
    return ReleaseRecordSlimOut(
        id=int(release.id),
        requirement_id=int(release.requirement_id),
        execution_run_id=int(release.execution_run_id) if release.execution_run_id is not None else None,
        project_id=int(release.project_id) if getattr(release, "project_id", None) is not None else None,
        project_key=str(release.project_key or "").strip() or None,
        project_display_name=str(getattr(release, "project_display_name", "") or "").strip() or None,
        target_project_path=str(release.target_project_path or "").strip() or None,
        status=str(release.status or "not_ready"),
        branch_name=str(release.branch_name or "").strip() or None,
        base_branch=str(release.base_branch or "").strip() or None,
        commit_sha=str(release.commit_sha or "").strip() or None,
        compare_url=str(release.compare_url or "").strip() or None,
        pr_url=str(release.pr_url or "").strip() or None,
        pr_number=int(release.pr_number) if release.pr_number is not None else None,
        notes=str(release.notes or "").strip() or None,
        prepared_at=release.prepared_at,
        delivered_at=release.delivered_at,
        created_at=release.created_at,
        updated_at=release.updated_at,
    )


def list_release_candidates(db: Session) -> list[ReleaseCandidateOut]:
    rows = (
        db.query(RequirementRow)
        .filter(RequirementRow.status.in_(["delivery_ready", "done"]))
        .order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc())
        .all()
    )
    result: list[ReleaseCandidateOut] = []
    for requirement in rows:
        validation = _latest_validation(db, int(requirement.id))
        if validation is None or str(validation.status or "") != "passed":
            continue
        result.append(
            ReleaseCandidateOut(
                requirement=_requirement_to_out(db, requirement),
                validation=_validation_record_to_out(validation),
                release=_release_to_out(_latest_release(db, int(requirement.id))),
            )
        )
    return result


def _release_record(db: Session, requirement: RequirementRow) -> ReleaseRecordRow:
    release = _latest_release(db, int(requirement.id))
    validation = _latest_validation(db, int(requirement.id))
    latest_execution = _latest_execution_run(db, int(requirement.id))
    project = _project_for_requirement(db, requirement)
    current_execution_id = (
        int(validation.execution_run_id)
        if validation is not None and validation.execution_run_id is not None
        else (int(latest_execution.id) if latest_execution is not None else None)
    )
    if release is not None:
        if current_execution_id is not None and release.execution_run_id != current_execution_id:
            release.execution_run_id = current_execution_id
        if project is not None:
            release.project_id = int(project.id)
            release.project_key = str(project.project_key or "")
            release.project_display_name = str(project.display_name or "")
            release.target_project_path = str(requirement.target_project_path or "").strip() or str(project.root_path or "").strip() or None
        return release
    release = ReleaseRecordRow(
        requirement_id=int(requirement.id),
        execution_run_id=current_execution_id,
        project_id=int(project.id) if project is not None else None,
        project_key=str(getattr(project, "project_key", "") or "").strip() or None,
        project_display_name=str(getattr(project, "display_name", "") or "").strip() or None,
        target_project_path=str(requirement.target_project_path or "").strip() or (str(getattr(project, "root_path", "") or "").strip() or None),
        status="ready",
    )
    db.add(release)
    db.flush()
    return release


def _release_branch_name(requirement: RequirementRow) -> str:
    return f"ops/req-{int(requirement.id)}-{_slugify(str(requirement.title or 'requirement'))}"


def _delivery_contract_for_requirement(
    db: Session,
    requirement: RequirementRow,
    *,
    commit_required: bool,
    push_required: bool,
) -> tuple[ProjectRow, dict[str, Any]]:
    project = _project_for_requirement(db, requirement)
    if project is None:
        raise ValueError("Requirement must resolve to a project before delivery preparation.")
    policy = _primary_project_policy(db, requirement)
    if policy is None:
        raise ValueError("Requirement project is not governed by a project policy.")
    policy_payload = project_policy_to_dict(policy)
    return project, {
        "branch_name": _release_branch_name(requirement),
        "base_branch": "main",
        "remote_name": "origin",
        "commit_required": commit_required,
        "push_required": push_required,
        "capability_matrix": policy_payload.get("capability_matrix") or {},
        "changed_target_project_paths": _target_projects_for_requirement(db, requirement),
    }


def _prepare_delivery_branch_for_execution(db: Session, requirement: RequirementRow, *, actor: str) -> ReleaseRecordRow:
    requirement.phase = "branch_preparing"
    requirement.status = _requirement_status_from_phase(requirement.phase)
    db.flush()
    project, delivery_contract = _delivery_contract_for_requirement(
        db,
        requirement,
        commit_required=False,
        push_required=False,
    )
    release = _release_record(db, requirement)
    vcs = prepare_requirement_delivery_branch(
        delivery_contract=delivery_contract,
        fallback_target_path=str(requirement.target_project_path or "").strip() or str(project.root_path or "").strip() or None,
    )
    release.execution_run_id = _latest_execution_run(db, int(requirement.id)).id if _latest_execution_run(db, int(requirement.id)) is not None else release.execution_run_id
    release.metadata_json = _json_dump({"actor": actor, "vcs": vcs})
    blockers = [str(item).strip() for item in (vcs.get("blockers") or []) if str(item).strip()]
    if blockers:
        release.status = "release_blocked"
        release.branch_name = str(vcs.get("branch_name") or release.branch_name or delivery_contract["branch_name"]).strip() or delivery_contract["branch_name"]
        release.base_branch = str(vcs.get("base_branch") or release.base_branch or delivery_contract["base_branch"]).strip() or delivery_contract["base_branch"]
        release.notes = "; ".join(blockers)
        _log_workflow_event(
            "execution_branch_preparation_blocked",
            requirement=requirement,
            release=release,
            actor=actor,
            blockers=blockers,
        )
        db.commit()
        raise ValueError("; ".join(blockers))

    release.status = "branch_prepared"
    requirement.phase = "branch_prepared"
    requirement.status = _requirement_status_from_phase(requirement.phase)
    release.branch_name = str(vcs.get("branch_name") or "").strip() or delivery_contract["branch_name"]
    release.base_branch = str(vcs.get("base_branch") or "").strip() or delivery_contract["base_branch"]
    release.prepared_at = release.prepared_at or utcnow()
    release.notes = None
    _log_workflow_event(
        "execution_branch_prepared",
        requirement=requirement,
        release=release,
        actor=actor,
        branch_name=release.branch_name,
    )
    db.commit()
    db.refresh(release)
    return release


def _auto_open_pr_after_verification(db: Session, requirement: RequirementRow, *, actor: str) -> ReleaseRecordRow | None:
    try:
        detail = open_release_pr(
            db,
            int(requirement.id),
            actor=actor,
            note="Auto-opened after verification passed",
        )
    except ValueError as exc:
        _log_workflow_event(
            "release_auto_pr_failed",
            requirement=requirement,
            actor=actor,
            blockers=[str(exc)],
        )
        db.commit()
        return _latest_release(db, int(requirement.id))
    return _latest_release(db, int(requirement.id)) if detail.release is not None else None


def prepare_release(db: Session, requirement_id: int, *, actor: str, note: str | None = None) -> ReleaseDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    validation = _latest_validation(db, requirement_id)
    if validation is None or str(validation.status or "") != "passed":
        raise ValueError("Requirement must pass validate before release preparation.")
    project, delivery_contract = _delivery_contract_for_requirement(
        db,
        requirement,
        commit_required=False,
        push_required=False,
    )
    release = _release_record(db, requirement)
    release.execution_run_id = int(validation.execution_run_id)
    vcs = execute_requirement_delivery_vcs(
        requirement_id=requirement_id,
        requirement_title=str(requirement.title or ""),
        delivery_contract=delivery_contract,
        fallback_target_path=str(requirement.target_project_path or "").strip() or str(project.root_path or "").strip() or None,
    )
    blockers = [str(item).strip() for item in (vcs.get("blockers") or []) if str(item).strip()]
    if blockers:
        release.status = "release_blocked"
        release.notes = "; ".join(blockers)
        _log_workflow_event(
            "release_preparation_blocked",
            requirement=requirement,
            release=release,
            actor=actor,
            blockers=blockers,
        )
    else:
        release.status = "branch_prepared"
        release.branch_name = str(vcs.get("branch_name") or "").strip() or delivery_contract["branch_name"]
        release.base_branch = "main"
        release.prepared_at = utcnow()
        release.notes = note
        _log_workflow_event(
            "release_prepared",
            requirement=requirement,
            release=release,
            actor=actor,
            compare_url=str(vcs.get("compare_url") or "").strip() or None,
        )
    release.metadata_json = _json_dump({"actor": actor, "vcs": vcs})
    db.commit()
    return build_release_detail(db, requirement_id)


def _compare_url(remote_url: str | None, base_branch: str, branch_name: str) -> str | None:
    value = str(remote_url or "").strip()
    if not value:
        return None
    if value.startswith("git@github.com:"):
        path = value.split(":", 1)[1]
        if path.endswith(".git"):
            path = path[:-4]
        return f"https://github.com/{path}/compare/{base_branch}...{branch_name}"
    match = re.match(r"https?://github\.com/(?P<path>.+?)(?:\.git)?/?$", value)
    if match:
        return f"https://github.com/{match.group('path')}/compare/{base_branch}...{branch_name}"
    return None


def open_release_pr(db: Session, requirement_id: int, *, actor: str, note: str | None = None) -> ReleaseDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    validation = _latest_validation(db, requirement_id)
    if validation is None or str(validation.status or "") != "passed":
        raise ValueError("Requirement must pass validate before opening a PR.")
    project, delivery_contract = _delivery_contract_for_requirement(
        db,
        requirement,
        commit_required=True,
        push_required=True,
    )
    release = _release_record(db, requirement)
    if str(release.status or "") == "pr_opened" and str(release.pr_url or "").strip():
        return build_release_detail(db, requirement_id)
    release.execution_run_id = int(validation.execution_run_id)
    delivery_contract["branch_name"] = release.branch_name or str(delivery_contract.get("branch_name") or "")
    delivery_contract["base_branch"] = release.base_branch or str(delivery_contract.get("base_branch") or "main")
    vcs = execute_requirement_delivery_vcs(
        requirement_id=requirement_id,
        requirement_title=str(requirement.title or ""),
        delivery_contract=delivery_contract,
        fallback_target_path=str(requirement.target_project_path or "").strip() or str(project.root_path or "").strip() or None,
    )
    blockers = [str(item).strip() for item in (vcs.get("blockers") or []) if str(item).strip()]
    if blockers:
        release.status = "release_blocked"
        release.notes = "; ".join(blockers)
        release.metadata_json = _json_dump({"actor": actor, "vcs": vcs})
        _log_workflow_event(
            "release_pr_blocked",
            requirement=requirement,
            release=release,
            actor=actor,
            blockers=blockers,
        )
        db.commit()
        return build_release_detail(db, requirement_id)
    first_repo = next((item for item in (vcs.get("repositories") or []) if isinstance(item, dict)), {})
    branch_name = str(vcs.get("branch_name") or release.branch_name or _release_branch_name(requirement)).strip()
    base_branch = str(vcs.get("base_branch") or release.base_branch or "main").strip() or "main"
    compare_url = _compare_url(first_repo.get("remote_url") if isinstance(first_repo, dict) else None, base_branch, branch_name)
    pr_sync = sync_requirement_review_pr(
        requirement_id=requirement_id,
        requirement_title=str(requirement.title or ""),
        branch_name=branch_name,
        base_branch=base_branch,
        compare_url=compare_url,
        latest_commit_sha=str(first_repo.get("commit_sha") or "").strip() or None if isinstance(first_repo, dict) else None,
        latest_remote_sha=str(first_repo.get("remote_sha") or "").strip() or None if isinstance(first_repo, dict) else None,
        last_pushed_at=None,
        review_surface_summary=str(validation.summary_markdown or ""),
        promotion_checklist=[{"label": check.label, "status": check.status} for check in _validation_record_to_out(validation).checks],
        vcs_payload=vcs,
    )
    release.status = "pr_opened"
    release.branch_name = branch_name
    release.base_branch = base_branch
    release.commit_sha = str(first_repo.get("commit_sha") or "").strip() or None if isinstance(first_repo, dict) else None
    release.compare_url = compare_url or str(pr_sync.get("compare_url") or "").strip() or None
    release.pr_url = str(pr_sync.get("pr_url") or "").strip() or None
    release.pr_number = int(pr_sync.get("pr_number")) if pr_sync.get("pr_number") is not None else None
    release.delivered_at = utcnow()
    release.notes = note
    release.metadata_json = _json_dump({"actor": actor, "vcs": vcs, "pr_sync": pr_sync})
    requirement.phase = "done"
    requirement.status = _requirement_status_from_phase(requirement.phase)
    requirement.completed_at = utcnow()
    _log_workflow_event(
        "release_pr_opened",
        requirement=requirement,
        release=release,
        actor=actor,
        pr_url=release.pr_url,
        compare_url=release.compare_url,
        commit_sha=release.commit_sha,
    )
    db.commit()
    _notify_pr_opened(db, requirement, release)
    db.commit()
    return build_release_detail(db, requirement_id)


def build_release_detail(db: Session, requirement_id: int) -> ReleaseDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    validation = _latest_validation(db, requirement_id)
    release = _latest_release(db, requirement_id)
    return ReleaseDetailOut(
        requirement=_requirement_to_out(db, requirement),
        validation=_validation_record_to_out(validation),
        release=_release_to_out(release),
        deployments=list_requirement_deployment_records(db, requirement_id),
    )


def deploy_release(
    db: Session,
    requirement_id: int,
    *,
    environment: str,
    actor: str,
    note: str | None = None,
) -> ReleaseDetailOut:
    release = _latest_release(db, requirement_id)
    if release is None or not str(release.commit_sha or "").strip():
        raise ValueError("Release must have a committed branch before deployment.")
    trigger_requirement_deployment(
        db,
        requirement_id,
        environment=environment,
        actor=actor,
        note=note,
        commit_sha=str(release.commit_sha),
    )
    return build_release_detail(db, requirement_id)


def rollback_release(
    db: Session,
    requirement_id: int,
    *,
    rollback_target_sha: str,
    actor: str,
    note: str | None = None,
) -> ReleaseDetailOut:
    trigger_requirement_deployment(
        db,
        requirement_id,
        environment="production",
        actor=actor,
        note=note,
        rollback_target_sha=rollback_target_sha,
        trigger_source="release_console",
    )
    release = _latest_release(db, requirement_id)
    if release is not None:
        release.status = "rolled_back"
        release.notes = note
        db.commit()
    return build_release_detail(db, requirement_id)
