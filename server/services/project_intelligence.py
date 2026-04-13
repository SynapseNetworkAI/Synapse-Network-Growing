"""Project readiness, routing, and score helpers for cross-project optimization."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from server.database import ApprovalRequestRow, ApprovalRow, ArtifactRow, OptimizationSignalRow, ProjectOnboardingRow, RequirementRow, TaskRow
from server.services.acceptance import acceptance_contract_for_requirement
from server.services.requirement_approval import (
    evaluate_requirement_execution_approval,
    normalize_requirement_approval_status,
    requirement_approval_contract_for_requirement,
)
from server.services.project_onboarding import project_onboarding_to_dict
from server.services.project_policy import list_project_policies, project_policy_to_dict, resolve_project_policies_for_target


_PRIORITY_SCORE = {"high": 30.0, "normal": 10.0, "low": 0.0}
_STATUS_ADJUSTMENT = {
    "done": -100.0,
    "blocked": -20.0,
    "needs_revision": -10.0,
    "deleted": -200.0,
}

_PROJECT_HINTS: dict[str, list[str]] = {
    "synapse-network-growing": [
        "growing",
        "ops",
        "operations",
        "control plane",
        "dashboard",
        "requirement",
        "requirements",
        "requirement pool",
        "workflow",
        "onboarding",
        "project policy",
        "policy",
        "validation contract",
        "delivery gate",
        "bugfix loop",
        "需求",
        "需求池",
        "项目策略",
        "编排",
        "工作流",
    ],
    "synapse-network": [
        "gateway",
        "settlement",
        "runtime",
        "admin",
        "gateway-admin",
        "admin-front",
        "frontend",
        "finance",
        "vault",
        "withdrawal",
        "reconciliation",
        "payment",
        "product",
        "结算",
        "网关",
        "控制台",
    ],
    "synapse-network-provider": [
        "provider",
        "service provider",
        "provider runtime",
        "provider-service",
        "api seller",
        "seller onboarding",
        "卖家",
        "服务提供者",
        "provider onboarding",
    ],
    "synapse-network-sdk": [
        "sdk",
        "python sdk",
        "typescript sdk",
        "mcp",
        "client integration",
        "consumer integration",
        "developer integration",
        "接入",
        "客户端",
        "python client",
        "typescript client",
    ],
    "agents-memory": [
        "agents-memory",
        "memory",
        "memory sync",
        "knowledge base",
        "constraints",
        "constraint",
        "standards",
        "documentation",
        "docs governance",
        "wiki",
        "记忆",
        "文档",
        "约束",
        "标准",
    ],
    "spec2flow": [
        "spec2flow",
        "scheduler",
        "workflow engine",
        "task graph",
        "spec driven",
        "pipeline",
    ],
}


def _split_target_paths(value: str | None) -> list[str]:
    if not value:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for raw in value.splitlines():
        candidate = raw.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _extract_tokens(*parts: str | None) -> set[str]:
    text = " ".join(part or "" for part in parts).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text)
        if token not in {"repo", "project", "system", "agent", "network", "synapse"}
    }


def _latest_onboardings_by_root(db: Session) -> dict[str, dict[str, Any]]:
    rows = db.query(ProjectOnboardingRow).order_by(ProjectOnboardingRow.updated_at.desc(), ProjectOnboardingRow.id.desc()).all()
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        root = str(row.root_path)
        if root in latest:
            continue
        latest[root] = project_onboarding_to_dict(row)
    return latest


def _requirement_project_roots(db: Session, requirement: RequirementRow) -> list[str]:
    policies = resolve_project_policies_for_target(db, getattr(requirement, "target_project_path", None), require_active=False)
    roots = [str(policy.root_path) for policy in policies]
    if roots:
        return roots
    return _split_target_paths(getattr(requirement, "target_project_path", None))


def _latest_delivery_state_payloads(db: Session) -> dict[int, dict[str, Any]]:
    payloads: dict[int, dict[str, Any]] = {}
    rows = db.query(ArtifactRow).filter(ArtifactRow.artifact_type == "delivery_state").order_by(ArtifactRow.id.desc()).all()
    for row in rows:
        requirement_id = int(row.requirement_id)
        if requirement_id in payloads:
            continue
        payload = _json_loads(row.machine_readable_payload, {})
        payloads[requirement_id] = payload if isinstance(payload, dict) else {}
    return payloads


def build_project_catalog(db: Session) -> dict[str, dict[str, Any]]:
    policies = [project_policy_to_dict(row) for row in list_project_policies(db)]
    latest_onboardings = _latest_onboardings_by_root(db)
    requirements = db.query(RequirementRow).all()

    total_requirements = defaultdict(int)
    completed_requirements = defaultdict(int)
    active_requirements = defaultdict(int)
    planned_requirements = defaultdict(int)
    bugged_requirements = defaultdict(set)
    blocked_delivery = defaultdict(int)
    manual_overrides = defaultdict(int)

    requirement_by_id = {int(row.id): row for row in requirements}
    requirement_roots: dict[int, list[str]] = {
        int(row.id): _requirement_project_roots(db, row)
        for row in requirements
    }

    for row in requirements:
        if str(row.status) == "deleted":
            continue
        for root in requirement_roots[int(row.id)]:
            total_requirements[root] += 1
            if str(row.status) == "done":
                completed_requirements[root] += 1
            if str(row.status) in {"in_progress", "paused"}:
                active_requirements[root] += 1
            if int(row.current_plan_version or 0) > 0:
                planned_requirements[root] += 1

    for artifact in db.query(ArtifactRow).filter(ArtifactRow.artifact_type == "bug_report").all():
        requirement = requirement_by_id.get(int(artifact.requirement_id))
        if requirement is None or str(requirement.status) == "deleted":
            continue
        for root in requirement_roots.get(int(requirement.id), []):
            bugged_requirements[root].add(int(requirement.id))

    for requirement_id, payload in _latest_delivery_state_payloads(db).items():
        publish_status = str(payload.get("publish_status") or "")
        if publish_status not in {"blocked", "review_ready"}:
            continue
        for root in requirement_roots.get(requirement_id, []):
            blocked_delivery[root] += 1

    for approval_request in db.query(ApprovalRequestRow).all():
        requirement = requirement_by_id.get(int(approval_request.requirement_id or 0))
        if requirement is None or str(requirement.status) == "deleted":
            continue
        for root in requirement_roots.get(int(requirement.id), []):
            manual_overrides[root] += 1

    tasks_by_id = {int(row.id): row for row in db.query(TaskRow).all()}
    for approval in db.query(ApprovalRow).all():
        task = tasks_by_id.get(int(approval.task_id))
        if task is None:
            continue
        roots: set[str] = set()
        if str(task.project_id or "").strip():
            roots.add(str(task.project_id))
        for step in task.workflow_steps:
            requirement = requirement_by_id.get(int(step.requirement_id))
            if requirement is None or str(requirement.status) == "deleted":
                continue
            roots.update(requirement_roots.get(int(requirement.id), []))
        for root in roots:
            manual_overrides[root] += 1

    catalog: dict[str, dict[str, Any]] = {}
    for policy in policies:
        root = str(policy["root_path"])
        onboarding = latest_onboardings.get(root)
        readiness_status = str(onboarding.get("readiness_status")) if onboarding else "policy_only"
        readiness_score = int(onboarding.get("readiness_score") or 0) if onboarding else (70 if str(policy["status"]) == "active" else 0)
        total = total_requirements[root]
        bug_count = len(bugged_requirements[root])
        validation_pass_rate = 1.0 if total == 0 else round(max(total - bug_count, 0) / total, 2)
        automation_coverage = 0.0 if total == 0 else round(planned_requirements[root] / total, 2)
        automation_ready = str(policy["status"]) == "active" and readiness_status in {"ready", "policy_only"}
        notes = str(onboarding.get("notes") or policy.get("notes") or "") if onboarding else str(policy.get("notes") or "")
        catalog[root] = {
            "project_key": str(policy["project_key"]),
            "display_name": str(policy["display_name"]),
            "root_path": root,
            "policy_status": str(policy["status"]),
            "release_mode": str(policy["release_mode"]),
            "requires_manual_approval": bool(policy["requires_manual_approval"]),
            "readiness_status": readiness_status,
            "readiness_score": readiness_score,
            "automation_ready": automation_ready,
            "onboarding_present": onboarding is not None,
            "active_requirement_count": active_requirements[root],
            "completed_requirement_count": completed_requirements[root],
            "total_requirement_count": total,
            "bug_report_count": bug_count,
            "blocked_publish_count": blocked_delivery[root],
            "manual_override_count": manual_overrides[root],
            "validation_pass_rate": validation_pass_rate,
            "automation_coverage": automation_coverage,
            "notes": notes,
            "agents_memory_namespace": str(onboarding.get("agents_memory_namespace") or "") if onboarding else "",
        }
    return catalog


def _project_match_score(project: dict[str, Any], text: str) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    text_norm = _normalize_text(text)
    matched: set[str] = set()

    for phrase in _PROJECT_HINTS.get(str(project["project_key"]), []):
        phrase_norm = _normalize_text(phrase)
        if phrase_norm and phrase_norm in text_norm and phrase_norm not in matched:
            matched.add(phrase_norm)
            score += 12.0 if len(phrase_norm) >= 5 else 8.0
            reasons.append(phrase)

    token_fields = _extract_tokens(
        str(project["project_key"]),
        str(project["display_name"]),
        str(project.get("notes") or ""),
        str(project.get("agents_memory_namespace") or ""),
        Path(str(project["root_path"])).name,
    )
    for token in token_fields:
        if token in text_norm and token not in matched:
            matched.add(token)
            score += 4.0
            reasons.append(token)

    if not reasons:
        return 0.0, []

    if str(project["readiness_status"]) == "ready":
        score += 6.0
    elif str(project["readiness_status"]) == "policy_only":
        score += 3.0
    elif str(project["readiness_status"]) == "needs_setup":
        score -= 12.0

    if str(project["policy_status"]) != "active":
        score -= 100.0

    return score, reasons


def _latest_routing_decision_payload(db: Session, requirement_id: int) -> dict[str, Any] | None:
    row = db.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == "routing_decision",
    ).order_by(ArtifactRow.id.desc()).first()
    if row is None:
        return None
    payload = _json_loads(row.machine_readable_payload, {})
    return payload if isinstance(payload, dict) else None


def _latest_routing_decision_payloads(db: Session, requirement_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not requirement_ids:
        return {}
    payloads: dict[int, dict[str, Any]] = {}
    rows = db.query(ArtifactRow).filter(
        ArtifactRow.requirement_id.in_(requirement_ids),
        ArtifactRow.artifact_type == "routing_decision",
    ).order_by(ArtifactRow.id.desc()).all()
    for row in rows:
        requirement_id = int(row.requirement_id)
        if requirement_id in payloads:
            continue
        payload = _json_loads(row.machine_readable_payload, {})
        if isinstance(payload, dict):
            payloads[requirement_id] = payload
    return payloads


def _aggregate_readiness_status(projects: list[dict[str, Any]]) -> str:
    if not projects:
        return "unrouted"
    statuses = {str(project.get("readiness_status") or "unknown") for project in projects}
    if statuses <= {"ready", "policy_only"}:
        return "ready" if "ready" in statuses else "policy_only"
    if "needs_setup" in statuses:
        return "needs_setup"
    return "mixed"


def _routing_context_from_projects(
    projects: list[dict[str, Any]],
    *,
    routing_mode: str,
    skipped_projects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selected_paths = [str(project["root_path"]) for project in projects]
    selected_names = [str(project["display_name"]) for project in projects]
    selected_keys = [str(project["project_key"]) for project in projects]
    readiness_status = _aggregate_readiness_status(projects)
    automation_ready = bool(projects) and all(bool(project.get("automation_ready")) for project in projects)

    if routing_mode == "explicit":
        summary = "Explicit target project routing."
    elif routing_mode == "auto":
        summary = "Auto-routed requirement to matching managed projects."
    else:
        summary = "Requirement is not routed to a managed project yet."

    if projects:
        summary += f" Projects: {', '.join(selected_names)}."
    if skipped_projects:
        summary += " Skipped candidates: " + ", ".join(str(item["display_name"]) for item in skipped_projects) + "."
    if projects and not automation_ready:
        missing = []
        for project in projects:
            if not bool(project.get("automation_ready")):
                missing.append(f"{project['display_name']}({project['readiness_status']})")
        if missing:
            summary += " Automation not ready: " + ", ".join(missing) + "."

    return {
        "routing_mode": routing_mode,
        "target_project_path": "\n".join(selected_paths) if selected_paths else None,
        "summary": summary,
        "automation_ready": automation_ready,
        "readiness_status": readiness_status,
        "routed_project_keys": selected_keys,
        "routed_display_names": selected_names,
        "skipped_project_keys": [str(project["project_key"]) for project in skipped_projects or []],
        "project_scorecards": projects,
    }


def resolve_requirement_routing(
    db: Session,
    *,
    title: str,
    description_markdown: str,
    target_project_path: str | None,
    project_catalog: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    catalog = project_catalog or build_project_catalog(db)
    if target_project_path:
        selected: list[dict[str, Any]] = []
        for root in _split_target_paths(target_project_path):
            if root in catalog:
                selected.append(catalog[root])
            else:
                selected.append(
                    {
                        "project_key": Path(root).name.lower(),
                        "display_name": Path(root).name,
                        "root_path": root,
                        "policy_status": "unknown",
                        "release_mode": "manual",
                        "requires_manual_approval": True,
                        "readiness_status": "unknown",
                        "readiness_score": 0,
                        "automation_ready": False,
                        "onboarding_present": False,
                        "active_requirement_count": 0,
                        "completed_requirement_count": 0,
                        "total_requirement_count": 0,
                        "bug_report_count": 0,
                        "blocked_publish_count": 0,
                        "validation_pass_rate": 0.0,
                        "automation_coverage": 0.0,
                        "notes": "",
                        "agents_memory_namespace": "",
                    }
                )
        return _routing_context_from_projects(selected, routing_mode="explicit")

    text = f"{title}\n{description_markdown}"
    scored: list[dict[str, Any]] = []
    for project in catalog.values():
        match_score, reasons = _project_match_score(project, text)
        if match_score <= 0:
            continue
        candidate = dict(project)
        candidate["match_score"] = round(match_score, 2)
        candidate["match_reasons"] = reasons
        scored.append(candidate)

    if not scored:
        return _routing_context_from_projects([], routing_mode="unrouted")

    scored.sort(
        key=lambda item: (
            float(item.get("match_score") or 0.0),
            int(item.get("readiness_score") or 0),
            int(item.get("total_requirement_count") or 0),
        ),
        reverse=True,
    )
    top_score = float(scored[0]["match_score"])
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in scored:
        match_score = float(candidate.get("match_score") or 0.0)
        if match_score < 10.0 or match_score < top_score - 4.0:
            continue
        if bool(candidate.get("automation_ready")):
            selected.append(candidate)
        else:
            skipped.append(candidate)

    if not selected and scored and bool(scored[0].get("automation_ready")):
        selected = [scored[0]]
    if not selected:
        return _routing_context_from_projects([], routing_mode="unrouted", skipped_projects=skipped or scored[:1])
    return _routing_context_from_projects(selected, routing_mode="auto", skipped_projects=skipped)


def build_signal_requirement_context_map(
    db: Session,
    *,
    project_catalog: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, float]]:
    from server.services.optimization_signals import build_optimization_signal_score_breakdown

    project_map = project_catalog or build_project_catalog(db)
    contexts: dict[str, dict[str, float]] = {}
    for row in db.query(OptimizationSignalRow).all():
        breakdown = build_optimization_signal_score_breakdown(row, project_map=project_map)
        contexts[f"optimization-signal:{int(row.id)}"] = {
            "impact": round(float(breakdown.get("impact") or 0.0) * 0.35, 2),
            "risk": round(float(breakdown.get("risk") or 0.0) * 0.3, 2),
            "confidence_component": round(float(breakdown.get("confidence_component") or 0.0) * 0.4, 2),
            "urgency": round(float(breakdown.get("urgency") or 0.0) * 0.35, 2),
            "implementation_cost_adjustment": round(float(breakdown.get("implementation_cost_adjustment") or 0.0) * 0.35, 2),
        }
    return contexts


def build_requirement_score_breakdown(
    db: Session,
    requirement: RequirementRow,
    *,
    project_catalog: dict[str, dict[str, Any]] | None = None,
    signal_contexts: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    routing = resolve_requirement_routing(
        db,
        title=str(getattr(requirement, "title", "") or ""),
        description_markdown=str(getattr(requirement, "description_markdown", "") or ""),
        target_project_path=getattr(requirement, "target_project_path", None),
        project_catalog=project_catalog,
    )
    priority = _PRIORITY_SCORE.get(str(getattr(requirement, "priority", "normal")), 10.0)
    created = getattr(requirement, "created_at", None) or datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - created).total_seconds() / 86400
    aging = min(age_days * 2.0, 30.0)
    status_adjustment = _STATUS_ADJUSTMENT.get(str(getattr(requirement, "status", "")), 0.0)
    blocker_penalty = float(int(getattr(requirement, "blocked_by_count", 0) or 0) * -15)

    project_scorecards = list(routing.get("project_scorecards") or [])
    if project_scorecards:
        avg_readiness = sum(int(item.get("readiness_score") or 0) for item in project_scorecards) / len(project_scorecards)
        readiness_adjustment = round((avg_readiness - 50.0) / 5.0, 2)
        bug_pressure = float(min(sum(int(item.get("bug_report_count") or 0) for item in project_scorecards) * 6, 18))
        delivery_pressure = float(min(sum(int(item.get("blocked_publish_count") or 0) for item in project_scorecards) * 5, 15))
        manual_escalation_pressure = float(min(sum(int(item.get("manual_override_count") or 0) for item in project_scorecards) * 4, 12))
        avg_automation_coverage = sum(float(item.get("automation_coverage") or 0.0) for item in project_scorecards) / len(project_scorecards)
        automation_gap = round(max(0.0, 0.7 - avg_automation_coverage) * 10.0, 2)
    else:
        readiness_adjustment = 0.0
        bug_pressure = 0.0
        delivery_pressure = 0.0
        manual_escalation_pressure = 0.0
        automation_gap = 0.0

    if str(routing.get("readiness_status") or "") == "needs_setup":
        readiness_adjustment -= 10.0
    elif str(routing.get("readiness_status") or "") == "mixed":
        readiness_adjustment -= 5.0

    signal_impact = 0.0
    signal_risk = 0.0
    signal_confidence = 0.0
    signal_urgency = 0.0
    implementation_cost_adjustment = 0.0
    source_ref = str(getattr(requirement, "source_ref", "") or "")
    if str(getattr(requirement, "source", "")) == "optimization_signal" and source_ref.startswith("optimization-signal:"):
        if signal_contexts is not None:
            signal_context = signal_contexts.get(source_ref, {})
        else:
            from server.services.optimization_signals import get_optimization_signal_requirement_context

            signal_context = get_optimization_signal_requirement_context(db, source_ref)
        signal_impact = float(signal_context.get("impact") or 0.0)
        signal_risk = float(signal_context.get("risk") or 0.0)
        signal_confidence = float(signal_context.get("confidence_component") or 0.0)
        signal_urgency = float(signal_context.get("urgency") or 0.0)
        implementation_cost_adjustment = float(signal_context.get("implementation_cost_adjustment") or 0.0)

    total = round(
        priority
        + aging
        + status_adjustment
        + blocker_penalty
        + readiness_adjustment
        + bug_pressure
        + delivery_pressure
        + manual_escalation_pressure
        + signal_impact
        + signal_risk
        + signal_confidence
        + signal_urgency
        + implementation_cost_adjustment
        + automation_gap,
        2,
    )
    return {
        "total": total,
        "priority": round(priority, 2),
        "aging": round(aging, 2),
        "status_adjustment": round(status_adjustment, 2),
        "blocker_penalty": round(blocker_penalty, 2),
        "readiness_adjustment": round(readiness_adjustment, 2),
        "bug_pressure": round(bug_pressure, 2),
        "delivery_pressure": round(delivery_pressure, 2),
        "manual_escalation_pressure": round(manual_escalation_pressure, 2),
        "signal_impact": round(signal_impact, 2),
        "signal_risk": round(signal_risk, 2),
        "signal_confidence": round(signal_confidence, 2),
        "signal_urgency": round(signal_urgency, 2),
        "implementation_cost_adjustment": round(implementation_cost_adjustment, 2),
        "automation_gap": round(automation_gap, 2),
        "routing_context": routing,
    }


def serialize_requirement(
    db: Session,
    requirement: RequirementRow,
    *,
    score: dict[str, Any] | None = None,
    stored_routing: dict[str, Any] | None = None,
    project_catalog: dict[str, dict[str, Any]] | None = None,
    signal_contexts: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    score = score or build_requirement_score_breakdown(
        db,
        requirement,
        project_catalog=project_catalog,
        signal_contexts=signal_contexts,
    )
    routing = dict(score.get("routing_context") or {})
    stored_routing = stored_routing or _latest_routing_decision_payload(db, int(requirement.id))
    if stored_routing and str(stored_routing.get("target_project_path") or "") == str(getattr(requirement, "target_project_path", None) or ""):
        if stored_routing.get("routing_mode"):
            routing["routing_mode"] = stored_routing["routing_mode"]
        if stored_routing.get("summary"):
            routing["summary"] = stored_routing["summary"]
        if stored_routing.get("skipped_project_keys") is not None:
            routing["skipped_project_keys"] = list(stored_routing.get("skipped_project_keys") or [])
    from server.services.requirement_sources import requirement_intake_metadata_for_requirement
    workflow_run = None
    active_workflow_run_id = int(requirement.active_workflow_run_id) if requirement.active_workflow_run_id is not None else None
    if active_workflow_run_id is not None:
        from server.database import WorkflowRunRow

        workflow_run = db.query(WorkflowRunRow).filter(WorkflowRunRow.id == active_workflow_run_id).first()
    approval_decision = evaluate_requirement_execution_approval(requirement, workflow_run=workflow_run)
    return {
        "id": int(requirement.id),
        "title": str(requirement.title),
        "description_markdown": str(requirement.description_markdown),
        "status": str(requirement.status),
        "priority": str(requirement.priority),
        "source": str(requirement.source),
        "source_ref": requirement.source_ref,
        "intake_metadata": requirement_intake_metadata_for_requirement(requirement),
        "target_project_path": getattr(requirement, "target_project_path", None),
        "acceptance_contract": acceptance_contract_for_requirement(requirement),
        "approval_status": normalize_requirement_approval_status(getattr(requirement, "approval_status", None)),
        "approval_contract": requirement_approval_contract_for_requirement(requirement),
        "approval_source": str(approval_decision.get("approval_source") or "human"),
        "approval_router": dict(approval_decision.get("approval_router") or {}),
        "approval_recommendation": dict(approval_decision.get("approval_recommendation") or {}),
        "approval_requested_at": getattr(requirement, "approval_requested_at", None),
        "approved_at": getattr(requirement, "approved_at", None),
        "current_plan_version": int(requirement.current_plan_version or 0),
        "blocked_by_count": int(requirement.blocked_by_count or 0),
        "active_workflow_run_id": int(requirement.active_workflow_run_id) if requirement.active_workflow_run_id is not None else None,
        "started_at": requirement.started_at,
        "completed_at": requirement.completed_at,
        "created_at": requirement.created_at,
        "updated_at": requirement.updated_at,
        "routing_context": routing,
        "score_breakdown": {
            key: value
            for key, value in score.items()
            if key != "routing_context"
        },
    }


def build_requirement_serialization_context(
    db: Session,
    requirements: list[RequirementRow],
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, float]]]:
    project_catalog = build_project_catalog(db)
    signal_contexts = build_signal_requirement_context_map(db, project_catalog=project_catalog)
    score_map = {
        int(row.id): build_requirement_score_breakdown(
            db,
            row,
            project_catalog=project_catalog,
            signal_contexts=signal_contexts,
        )
        for row in requirements
    }
    stored_routing = _latest_routing_decision_payloads(db, [int(row.id) for row in requirements])
    return score_map, stored_routing, project_catalog, signal_contexts
