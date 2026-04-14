"""Agent-first requirement, execution, validation, and release flow."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from server.config import ORCHESTRATION_BACKEND, PROJECT_ROOT
from server.database import (
    ApprovalRequestRow,
    DeploymentRecordRow,
    ExecutionNodeRow,
    ExecutionRunRow,
    ReleaseRecordRow,
    RequirementRow,
    TaskRow,
    ValidationRecordRow,
    utcnow,
)
from server.schemas import (
    AgentFirstRequirementApprovalOut,
    AgentFirstRequirementDetailOut,
    AgentFirstRequirementOut,
    ExecutionNodeOut,
    ExecutionRunDetailOut,
    ExecutionRunOut,
    ReleaseCandidateOut,
    ReleaseDetailOut,
    ReleaseRecordSlimOut,
    ValidationCheckResultOut,
    ValidationRecordSlimOut,
)
from server.services.agents.execution_resolver import suggest_task_execution
from server.services.delivery.deployment_governance import (
    list_requirement_deployment_records,
    trigger_requirement_deployment,
)
from server.services.delivery.pull_request import sync_requirement_review_pr
from server.services.delivery.vcs import execute_requirement_delivery_vcs
from server.services.projects.policy import (
    project_policy_summary_markdown,
    project_policy_to_dict,
    resolve_project_policies_for_target,
)
from server.services.runtime.alerting import build_ops_url, deliver_lark_notification, notification_service_label
from server.services.runtime.task_runner import dispatch
from server.services.requirements.approval import (
    evaluate_requirement_execution_approval,
    normalize_requirement_approval_status,
)
from server.services.workflows.orchestrator import pause_task as pause_legacy_task


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


def _target_projects_for_requirement(db: Session, requirement: RequirementRow) -> list[str]:
    policies = resolve_project_policies_for_target(
        db,
        getattr(requirement, "target_project_path", None),
        require_active=False,
    )
    if policies:
        return [str(policy.root_path) for policy in policies]
    return _split_target_projects(getattr(requirement, "target_project_path", None))


def _primary_project_policy(db: Session, requirement: RequirementRow):
    policies = resolve_project_policies_for_target(
        db,
        getattr(requirement, "target_project_path", None),
        require_active=False,
    )
    return policies[0] if policies else None


def _approval_required(db: Session, requirement: RequirementRow) -> bool:
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
    latest_execution = (
        db.query(ExecutionRunRow)
        .filter(ExecutionRunRow.requirement_id == requirement.id)
        .order_by(ExecutionRunRow.id.desc())
        .first()
    )
    latest_release = (
        db.query(ReleaseRecordRow)
        .filter(ReleaseRecordRow.requirement_id == requirement.id)
        .order_by(ReleaseRecordRow.id.desc())
        .first()
    )
    return AgentFirstRequirementOut(
        id=int(requirement.id),
        title=str(requirement.title or ""),
        description_markdown=str(requirement.description_markdown or ""),
        acceptance_criteria_markdown=_parse_acceptance_markdown(requirement),
        status=str(requirement.status or "draft"),
        priority=str(requirement.priority or "normal"),
        source=str(requirement.source or "manual"),
        source_ref=str(requirement.source_ref or "").strip() or None,
        target_project_path=str(requirement.target_project_path or "").strip() or None,
        target_projects=_target_projects_for_requirement(db, requirement),
        approval_required=_approval_required(db, requirement),
        approval_status=str(requirement.approval_status or "pending_approval"),
        created_at=requirement.created_at,
        updated_at=requirement.updated_at,
        active_execution_run_id=int(latest_execution.id) if latest_execution is not None and str(latest_execution.status or "") in {"queued", "running", "paused", "validating"} else None,
        latest_execution_run_id=int(latest_execution.id) if latest_execution is not None else None,
        latest_release_status=str(latest_release.status or "") if latest_release is not None else None,
    )


def _policy_summary_markdown(db: Session, requirement: RequirementRow) -> str:
    return project_policy_summary_markdown(
        db,
        getattr(requirement, "target_project_path", None),
    )


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
    latest_execution = (
        db.query(ExecutionRunRow)
        .filter(ExecutionRunRow.requirement_id == requirement_id)
        .order_by(ExecutionRunRow.id.desc())
        .first()
    )
    latest_release = (
        db.query(ReleaseRecordRow)
        .filter(ReleaseRecordRow.requirement_id == requirement_id)
        .order_by(ReleaseRecordRow.id.desc())
        .first()
    )
    return AgentFirstRequirementDetailOut(
        requirement=_requirement_to_out(db, requirement),
        policy_summary_markdown=_policy_summary_markdown(db, requirement),
        latest_execution_id=latest_execution_id_override if latest_execution_id_override is not None else (int(latest_execution.id) if latest_execution is not None else None),
        latest_release_id=int(latest_release.id) if latest_release is not None else None,
        approval=approval_override or _approval_summary(
            db,
            requirement,
            latest_execution_id=latest_execution_id_override if latest_execution_id_override is not None else (int(latest_execution.id) if latest_execution is not None else None),
        ),
    )


def list_requirements(db: Session, *, status: str | None = None, search: str | None = None) -> list[AgentFirstRequirementOut]:
    query = db.query(RequirementRow)
    if status:
        query = query.filter(RequirementRow.status == status)
    rows = query.order_by(RequirementRow.updated_at.desc(), RequirementRow.id.desc()).all()
    result: list[AgentFirstRequirementOut] = []
    search_value = str(search or "").strip().lower()
    for row in rows:
        item = _requirement_to_out(db, row)
        if search_value:
            haystack = "\n".join(
                [
                    item.title.lower(),
                    item.description_markdown.lower(),
                    (item.source_ref or "").lower(),
                    (item.target_project_path or "").lower(),
                ]
            )
            if search_value not in haystack and search_value != str(item.id):
                continue
        result.append(item)
    return result


def create_requirement(db: Session, body) -> AgentFirstRequirementDetailOut:
    requirement = RequirementRow(
        title=body.title.strip(),
        description_markdown=body.description_markdown.strip(),
        status="draft",
        priority=body.priority,
        source=body.source,
        source_ref=body.source_ref,
        intake_metadata_json=_json_dump(body.intake_metadata or {}),
        target_project_path=(body.target_project_path or "").strip() or None,
        acceptance_contract_json=_json_dump(
            body.acceptance_contract
            or {"markdown": str(getattr(body, "acceptance_criteria_markdown", "") or "").strip()}
        ),
        approval_status="pending_approval",
        approval_contract_json=_json_dump(body.approval_contract or {}),
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    approval_required = _approval_required(db, requirement)
    requirement.approval_status = "pending_approval" if approval_required else "waived"
    requirement.approval_contract_json = _json_dump(
        {
            **_json_load(getattr(requirement, "approval_contract_json", None), {}),
            "required": approval_required,
        }
    )
    db.commit()
    db.refresh(requirement)
    _notify_requirement_created(db, requirement)
    db.commit()
    return build_requirement_detail(db, int(requirement.id))


def update_requirement(db: Session, requirement_id: int, body) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
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
    if body.priority is not None:
        requirement.priority = body.priority
    if body.source_ref is not None:
        requirement.source_ref = body.source_ref
    if body.target_project_path is not None:
        requirement.target_project_path = body.target_project_path.strip() or None
    requirement.updated_at = utcnow()
    db.commit()
    return build_requirement_detail(db, requirement_id)


def submit_requirement(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    if str(requirement.status or "") == "deleted":
        raise ValueError("Deleted requirement cannot be submitted.")
    if not str(requirement.title or "").strip():
        raise ValueError("Requirement title is required before submit.")
    if not str(requirement.description_markdown or "").strip():
        raise ValueError("Requirement description is required before submit.")
    decision = evaluate_requirement_execution_approval(requirement)
    approval_status = normalize_requirement_approval_status(decision.get("approval_status"))
    approval_reason = str(decision.get("reason") or "Requirement requires approval before automatic execution").strip()
    requirement.updated_at = utcnow()
    if approval_status in {"approved", "waived"}:
        requirement.approval_status = approval_status
        requirement.approved_at = requirement.approved_at or utcnow()
        requirement.approval_requested_at = None
        requirement.status = "ready"
        _resolve_requirement_approval_requests(
            db,
            requirement_id=int(requirement.id),
            status="approved",
            reviewer="system",
            comment=approval_reason or "Automatically approved for execution",
        )
        db.commit()
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
        _notify_requirement_approval(db, requirement, detail.approval)
        db.commit()
        return detail

    requirement.approval_status = "pending_approval"
    requirement.approved_at = None
    requirement.status = "blocked"
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
    if str(requirement.approval_status or "") not in {"pending_approval", "rejected"}:
        raise ValueError("Requirement is not awaiting manual approval.")
    requirement.approval_status = "approved"
    requirement.approved_at = utcnow()
    requirement.approval_requested_at = None
    requirement.status = "ready"
    requirement.updated_at = utcnow()
    _resolve_requirement_approval_requests(
        db,
        requirement_id=int(requirement.id),
        status="approved",
        reviewer=reviewer,
        comment=str(comment or "Approved for autonomous execution"),
    )
    db.commit()
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
    requirement.status = "needs_revision"
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
    db.commit()
    return detail


def revise_requirement(db: Session, requirement_id: int, body) -> AgentFirstRequirementDetailOut:
    detail = update_requirement(db, requirement_id, body)
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    requirement.status = "ready"
    requirement.updated_at = utcnow()
    db.commit()
    return build_requirement_detail(db, requirement_id)


def cancel_requirement(db: Session, requirement_id: int) -> AgentFirstRequirementDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    requirement.status = "cancelled"
    requirement.completed_at = utcnow()
    db.commit()
    return build_requirement_detail(db, requirement_id)


def _shape_decision(db: Session, requirement: RequirementRow) -> dict[str, Any]:
    target_projects = _target_projects_for_requirement(db, requirement)
    description = str(requirement.description_markdown or "")
    title = str(requirement.title or "")
    text = f"{title}\n{description}".lower()
    deterministic = "validation clone" in text or "deterministic" in text or "branch delivery" in text
    if deterministic:
        return {
            "execution_mode": "deterministic",
            "complexity": "simple",
            "validation_profile": "release_candidate",
            "delivery_intent": "pr_required",
            "execution_steps": [{"node_key": "execute", "title": "Deterministic execution"}],
            "planner_summary": "Deterministic delivery validation requirement. Use a single execute node.",
        }
    if len(target_projects) > 1 or len(description) > 1600:
        steps = [
            {"node_key": f"execute_{index + 1}", "title": f"Execute on {Path(project).name}"}
            for index, project in enumerate(target_projects[:4] or [str(requirement.target_project_path or PROJECT_ROOT)])
        ]
        return {
            "execution_mode": "graph",
            "complexity": "complex" if len(target_projects) > 2 else "standard",
            "validation_profile": "strict" if len(target_projects) > 1 else "standard",
            "delivery_intent": "pr_required",
            "execution_steps": steps,
            "planner_summary": "Multi-project or long-form requirement. Expand execute into per-project nodes.",
        }
    return {
        "execution_mode": "direct",
        "complexity": "simple",
        "validation_profile": "minimal",
        "delivery_intent": "pr_required",
        "execution_steps": [{"node_key": "execute", "title": "Execute requirement"}],
        "planner_summary": "Simple requirement. Keep a single execute node and one final validate/deliver gate.",
    }


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
    if str(requirement.status or "") not in {"ready", "blocked", "needs_revision"}:
        raise ValueError("Requirement must be ready before creating execution.")
    if _approval_required(db, requirement) and str(requirement.approval_status or "") not in {"approved", "waived"}:
        raise ValueError("Requirement must be approved before creating execution.")
    shape = _shape_decision(db, requirement)
    run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode=str(shape["execution_mode"]),
        complexity=str(shape["complexity"]),
        status="queued",
        validation_profile=str(shape["validation_profile"]),
        delivery_intent=str(shape["delivery_intent"]),
        approval_required=_approval_required(db, requirement),
        planner_summary=str(shape["planner_summary"]),
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
    requirement.status = "running"
    requirement.started_at = utcnow()
    db.commit()
    return build_execution_detail(db, int(run.id))


def list_execution_runs(db: Session) -> list[ExecutionRunOut]:
    rows = db.query(ExecutionRunRow).order_by(ExecutionRunRow.updated_at.desc(), ExecutionRunRow.id.desc()).all()
    return [build_execution_detail(db, int(row.id)).execution for row in rows]


def _node_task_status(task: TaskRow | None) -> str | None:
    if task is None:
        return None
    return str(getattr(task, "status", "") or "") or None


def _sync_execution_state(db: Session, run: ExecutionRunRow) -> ExecutionRunRow:
    nodes = (
        db.query(ExecutionNodeRow)
        .filter(ExecutionNodeRow.execution_run_id == run.id)
        .order_by(ExecutionNodeRow.sequence_no.asc(), ExecutionNodeRow.id.asc())
        .all()
    )
    if not nodes:
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
        statuses.append(node.status)
    validation = (
        db.query(ValidationRecordRow)
        .filter(ValidationRecordRow.execution_run_id == run.id)
        .order_by(ValidationRecordRow.id.desc())
        .first()
    )
    requirement = db.query(RequirementRow).filter(RequirementRow.id == run.requirement_id).first()
    if "running" in statuses:
        run.status = "running"
        if requirement is not None:
            requirement.status = "running"
    elif "failed" in statuses:
        run.status = "blocked"
        if requirement is not None:
            requirement.status = "blocked"
    elif "paused" in statuses:
        run.status = "paused"
        if requirement is not None:
            requirement.status = "blocked"
    elif all(status == "completed" for status in statuses):
        if validation is None:
            run.status = "validating"
            if requirement is not None:
                requirement.status = "running"
        elif str(validation.status or "") == "passed":
            run.status = "succeeded"
            if requirement is not None and str(requirement.status or "") != "done":
                requirement.status = "delivery_ready"
        else:
            run.status = "failed"
            if requirement is not None:
                requirement.status = "needs_revision"
    else:
        run.status = "queued"
        if requirement is not None:
            requirement.status = "running"
    run.updated_at = utcnow()
    db.flush()
    return run


def _build_task_description(db: Session, requirement: RequirementRow, run: ExecutionRunRow, node: ExecutionNodeRow) -> str:
    targets = _target_projects_for_requirement(db, requirement)
    acceptance = _parse_acceptance_markdown(requirement) or "Deliver the requested outcome and leave enough evidence for validate."
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
            "## Target Projects",
            *[f"- {item}" for item in targets],
            "",
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
    requirement = db.query(RequirementRow).filter(RequirementRow.id == run.requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    if run.approval_required and str(requirement.approval_status or "") not in {"approved", "waived"}:
        raise ValueError("Requirement must be approved before execution starts.")
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
    )
    db.add(task)
    db.flush()
    node.task_id = int(task.id)
    node.status = "running"
    node.started_at = utcnow()
    run.latest_task_id = int(task.id)
    run.status = "running"
    run.started_at = run.started_at or utcnow()
    requirement.status = "running"
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
    run.status = "paused"
    requirement = db.query(RequirementRow).filter(RequirementRow.id == run.requirement_id).first()
    if requirement is not None:
        requirement.status = "blocked"
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


def retry_execution_run(db: Session, execution_run_id: int) -> ExecutionRunDetailOut:
    run = db.query(ExecutionRunRow).filter(ExecutionRunRow.id == execution_run_id).first()
    if run is None:
        raise ValueError("Execution run not found.")
    _sync_execution_state(db, run)
    node = (
        db.query(ExecutionNodeRow)
        .filter(ExecutionNodeRow.execution_run_id == run.id)
        .order_by(ExecutionNodeRow.sequence_no.desc(), ExecutionNodeRow.id.desc())
        .first()
    )
    if node is None:
        raise ValueError("Execution node not found.")
    node.status = "queued"
    node.task_id = None
    node.summary_markdown = None
    run.status = "queued"
    requirement = db.query(RequirementRow).filter(RequirementRow.id == run.requirement_id).first()
    if requirement is not None:
        requirement.status = "running"
    db.commit()
    return build_execution_detail(db, execution_run_id)


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


def validate_execution_run(db: Session, execution_run_id: int) -> ExecutionRunDetailOut:
    run = db.query(ExecutionRunRow).filter(ExecutionRunRow.id == execution_run_id).first()
    if run is None:
        raise ValueError("Execution run not found.")
    _sync_execution_state(db, run)
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
    evidence_commands = _commands_from_execution_evidence(nodes, db)
    profile = str(run.validation_profile or "minimal")
    policies = resolve_project_policies_for_target(
        db,
        getattr(requirement, "target_project_path", None),
        require_active=False,
    )
    if not policies:
        checks.append(
            ValidationCheckResultOut(
                label="execution record present",
                status="passed",
                output_excerpt="No project policy checks configured; execution evidence exists.",
            )
        )
    else:
        for policy in policies:
            payload = project_policy_to_dict(policy)
            project_path = str(payload.get("root_path") or "")
            required_checks = list(payload.get("required_checks") or [])
            if profile == "minimal" and evidence_commands:
                required_checks = evidence_commands
            if not required_checks:
                checks.append(
                    ValidationCheckResultOut(
                        label=f"{payload.get('project_key')}: no required checks",
                        project_path=project_path or None,
                        status="passed",
                        output_excerpt="Project policy does not require deterministic checks.",
                    )
                )
                continue
            for command in required_checks:
                checks.append(_run_check(project_path, str(command)))
    passed = all(check.status == "passed" for check in checks)
    summary = "Validation passed. Execute evidence and required checks are complete." if passed else "Validation failed. At least one required check did not pass."
    record = ValidationRecordRow(
        requirement_id=int(requirement.id),
        execution_run_id=int(run.id),
        profile=profile,
        status="passed" if passed else "failed",
        summary_markdown=summary,
        checks_json=_json_dump([check.model_dump() for check in checks]),
    )
    db.add(record)
    run.status = "succeeded" if passed else "failed"
    requirement.status = "delivery_ready" if passed else "needs_revision"
    db.commit()
    return build_execution_detail(db, execution_run_id)


def _validation_record_to_out(record: ValidationRecordRow | None) -> ValidationRecordSlimOut | None:
    if record is None:
        return None
    checks_payload = _json_load(record.checks_json, [])
    checks: list[ValidationCheckResultOut] = []
    if isinstance(checks_payload, list):
        for item in checks_payload:
            if isinstance(item, dict):
                checks.append(ValidationCheckResultOut(**item))
    return ValidationRecordSlimOut(
        id=int(record.id),
        requirement_id=int(record.requirement_id),
        execution_run_id=int(record.execution_run_id),
        profile=str(record.profile or "minimal"),
        status=str(record.status or "pending"),
        summary_markdown=str(record.summary_markdown or ""),
        checks=checks,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def build_execution_detail(db: Session, execution_run_id: int) -> ExecutionRunDetailOut:
    run = db.query(ExecutionRunRow).filter(ExecutionRunRow.id == execution_run_id).first()
    if run is None:
        raise ValueError("Execution run not found.")
    run = _sync_execution_state(db, run)
    requirement = db.query(RequirementRow).filter(RequirementRow.id == run.requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
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
    node_out = [
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
            task_status=_node_task_status(db.query(TaskRow).filter(TaskRow.id == node.task_id).first()) if node.task_id else None,
            runtime_backend=str(node.runtime_backend or "").strip() or None,
            runtime_provider=str(node.runtime_provider or "").strip() or None,
            runtime_model=str(node.runtime_model or "").strip() or None,
            summary_markdown=str(node.summary_markdown or "").strip() or None,
            started_at=node.started_at,
            completed_at=node.completed_at,
        )
        for node in nodes
    ]
    execution = ExecutionRunOut(
        id=int(run.id),
        requirement_id=int(run.requirement_id),
        execution_mode=str(run.execution_mode or "direct"),
        complexity=str(run.complexity or "simple"),
        status=str(run.status or "queued"),
        validation_profile=str(run.validation_profile or "minimal"),
        delivery_intent=str(run.delivery_intent or "pr_required"),
        approval_required=bool(run.approval_required),
        planner_summary=str(run.planner_summary or "").strip() or None,
        target_projects=_json_load(run.target_projects_json, []),
        latest_task_id=int(run.latest_task_id) if run.latest_task_id is not None else None,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )
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
    return ExecutionRunDetailOut(
        execution=execution,
        requirement=_requirement_to_out(db, requirement),
        nodes=node_out,
        validation=_validation_record_to_out(validation),
        incidents=incidents,
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
        project_key=str(release.project_key or "").strip() or None,
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
    if release is not None:
        return release
    primary = _primary_project_policy(db, requirement)
    release = ReleaseRecordRow(
        requirement_id=int(requirement.id),
        execution_run_id=None,
        project_key=str(getattr(primary, "project_key", "") or "").strip() or None,
        target_project_path=str(requirement.target_project_path or "").strip() or None,
        status="ready",
    )
    db.add(release)
    db.flush()
    return release


def _release_branch_name(requirement: RequirementRow) -> str:
    return f"ops/req-{int(requirement.id)}-{_slugify(str(requirement.title or 'requirement'))}"


def prepare_release(db: Session, requirement_id: int, *, actor: str, note: str | None = None) -> ReleaseDetailOut:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        raise ValueError("Requirement not found.")
    validation = _latest_validation(db, requirement_id)
    if validation is None or str(validation.status or "") != "passed":
        raise ValueError("Requirement must pass validate before release preparation.")
    policy = _primary_project_policy(db, requirement)
    if policy is None:
        raise ValueError("Requirement target project is not governed by a project policy.")
    release = _release_record(db, requirement)
    policy_payload = project_policy_to_dict(policy)
    delivery_contract = {
        "branch_name": _release_branch_name(requirement),
        "base_branch": "main",
        "remote_name": "origin",
        "commit_required": False,
        "push_required": False,
        "capability_matrix": policy_payload.get("capability_matrix") or {},
        "changed_target_project_paths": _target_projects_for_requirement(db, requirement),
    }
    vcs = execute_requirement_delivery_vcs(
        requirement_id=requirement_id,
        requirement_title=str(requirement.title or ""),
        delivery_contract=delivery_contract,
        fallback_target_path=str(requirement.target_project_path or "").strip() or None,
    )
    blockers = [str(item).strip() for item in (vcs.get("blockers") or []) if str(item).strip()]
    if blockers:
        release.status = "release_blocked"
        release.notes = "; ".join(blockers)
    else:
        release.status = "branch_prepared"
        release.branch_name = str(vcs.get("branch_name") or "").strip() or delivery_contract["branch_name"]
        release.base_branch = "main"
        release.prepared_at = utcnow()
        release.notes = note
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
    policy = _primary_project_policy(db, requirement)
    if policy is None:
        raise ValueError("Requirement target project is not governed by a project policy.")
    release = _release_record(db, requirement)
    policy_payload = project_policy_to_dict(policy)
    delivery_contract = {
        "branch_name": release.branch_name or _release_branch_name(requirement),
        "base_branch": release.base_branch or "main",
        "remote_name": "origin",
        "commit_required": True,
        "push_required": True,
        "capability_matrix": policy_payload.get("capability_matrix") or {},
        "changed_target_project_paths": _target_projects_for_requirement(db, requirement),
    }
    vcs = execute_requirement_delivery_vcs(
        requirement_id=requirement_id,
        requirement_title=str(requirement.title or ""),
        delivery_contract=delivery_contract,
        fallback_target_path=str(requirement.target_project_path or "").strip() or None,
    )
    blockers = [str(item).strip() for item in (vcs.get("blockers") or []) if str(item).strip()]
    if blockers:
        release.status = "release_blocked"
        release.notes = "; ".join(blockers)
        release.metadata_json = _json_dump({"actor": actor, "vcs": vcs})
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
    requirement.status = "done"
    requirement.completed_at = utcnow()
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
