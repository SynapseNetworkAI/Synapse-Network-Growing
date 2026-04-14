"""Execution and approval KPI aggregation for agent roles."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import (
    AgentRow,
    ApprovalRequestRow,
    ArtifactRow,
    TaskRow,
    WorkflowStepRow,
)

TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled", "rejected"}
ACTIVE_TASK_STATUSES = {"running", "pending_approval"}


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_hours_between(start: datetime | None, end: datetime | None) -> float:
    start_utc = _to_utc(start)
    end_utc = _to_utc(end)
    if start_utc is None or end_utc is None:
        return 0.0
    return max(0.0, (end_utc - start_utc).total_seconds() / 3600.0)


def _latest_requirement_approval_payloads(db: Session) -> dict[int, dict[str, Any]]:
    payloads: dict[int, dict[str, Any]] = {}
    artifacts = (
        db.query(ArtifactRow)
        .filter(ArtifactRow.artifact_type == "requirement_approval_state")
        .order_by(ArtifactRow.id.asc())
        .all()
    )
    for artifact in artifacts:
        if artifact.requirement_id is None:
            continue
        payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
        if isinstance(payload, dict):
            payloads[int(artifact.requirement_id)] = payload
    return payloads


def build_role_kpi_snapshot(db: Session) -> dict[str, Any]:
    """Aggregate execution and approval KPI metrics by role."""

    agents = db.query(AgentRow).order_by(AgentRow.group.asc(), AgentRow.display_name.asc()).all()
    tasks = db.query(TaskRow).all()
    steps = db.query(WorkflowStepRow).all()
    approvals = db.query(ApprovalRequestRow).all()
    approval_payloads = _latest_requirement_approval_payloads(db)

    task_counts: dict[str, Counter[str]] = defaultdict(Counter)
    completed_counts: Counter[str] = Counter()
    active_counts: Counter[str] = Counter()
    pending_counts: Counter[str] = Counter()
    failed_counts: Counter[str] = Counter()
    reopened_counts: Counter[str] = Counter()
    approval_dependency_counts: Counter[str] = Counter()
    token_totals: Counter[str] = Counter()
    budget_totals: Counter[str] = Counter()
    completed_with_cost_counts: Counter[str] = Counter()
    requirement_sets: dict[str, set[int]] = defaultdict(set)
    task_requirement_ids: dict[int, set[int]] = defaultdict(set)

    for step in steps:
        if step.compatibility_task_id is not None and step.requirement_id is not None:
            task_requirement_ids[int(step.compatibility_task_id)].add(int(step.requirement_id))

    for task in tasks:
        role_id = str(task.agent_id or "").strip()
        if not role_id:
            continue
        status = str(task.status or "pending")
        task_counts[role_id][status] += 1
        if status == "completed":
            completed_counts[role_id] += 1
            token_totals[role_id] += int(task.tokens_used or 0)
            budget_totals[role_id] += int(task.budget_cost_points or 0)
            completed_with_cost_counts[role_id] += 1
        elif status in ACTIVE_TASK_STATUSES:
            active_counts[role_id] += 1
        elif status == "pending":
            pending_counts[role_id] += 1
        elif status in {"failed", "rejected"}:
            failed_counts[role_id] += 1
        if int(task.attempt_no or 1) > 1 or task.retry_of_task_id is not None:
            reopened_counts[role_id] += 1
        if bool(task.requires_approval) or status == "pending_approval":
            approval_dependency_counts[role_id] += 1
        if status not in TERMINAL_TASK_STATUSES:
            for requirement_id in task_requirement_ids.get(int(task.id), set()):
                requirement_sets[role_id].add(requirement_id)

    for step in steps:
        role_id = str(step.assigned_agent_id or "").strip()
        if not role_id:
            continue
        if step.requirement_id is not None and str(step.status or "pending") not in {"completed", "skipped", "cancelled"}:
            requirement_sets[role_id].add(int(step.requirement_id))

    role_rows: list[dict[str, Any]] = []
    total_backlog_count = 0
    for agent in agents:
        role_id = str(agent.id)
        status_mix = dict(task_counts.get(role_id) or {})
        task_count = sum(status_mix.values())
        completed_count = int(completed_counts.get(role_id, 0))
        active_task_count = int(active_counts.get(role_id, 0))
        pending_task_count = int(pending_counts.get(role_id, 0))
        failed_task_count = int(failed_counts.get(role_id, 0))
        backlog_count = active_task_count + pending_task_count
        total_backlog_count += backlog_count
        reopened_task_count = int(reopened_counts.get(role_id, 0))
        approval_dependency_count = int(approval_dependency_counts.get(role_id, 0))
        average_token_cost = (
            round(token_totals[role_id] / completed_with_cost_counts[role_id], 2)
            if completed_with_cost_counts[role_id]
            else 0.0
        )
        average_budget_cost_points = (
            round(budget_totals[role_id] / completed_with_cost_counts[role_id], 2)
            if completed_with_cost_counts[role_id]
            else 0.0
        )
        role_rows.append(
            {
                "role_id": role_id,
                "display_name": str(agent.display_name),
                "group": str(agent.group or ""),
                "mission": str((_json_loads(getattr(agent, "role_contract_json", None), {}) or {}).get("mission") or str(agent.goal)),
                "task_count": task_count,
                "completed_count": completed_count,
                "active_task_count": active_task_count,
                "pending_task_count": pending_task_count,
                "failed_task_count": failed_task_count,
                "backlog_count": backlog_count,
                "reopened_task_count": reopened_task_count,
                "approval_dependency_count": approval_dependency_count,
                "completion_rate": round((completed_count / task_count) * 100, 2) if task_count else 0.0,
                "reopen_rate": round((reopened_task_count / task_count) * 100, 2) if task_count else 0.0,
                "approval_dependency_rate": round((approval_dependency_count / task_count) * 100, 2) if task_count else 0.0,
                "average_token_cost": average_token_cost,
                "average_budget_cost_points": average_budget_cost_points,
                "tokens_used_total": int(token_totals.get(role_id, 0)),
                "budget_cost_points_total": int(budget_totals.get(role_id, 0)),
                "open_requirement_count": len(requirement_sets.get(role_id) or set()),
                "status_mix": status_mix,
            }
        )

    recommendation_by_requirement: dict[int, dict[str, Any]] = {}
    for requirement_id, payload in approval_payloads.items():
        recommendation = dict(payload.get("approval_recommendation") or {})
        if recommendation:
            recommendation_by_requirement[requirement_id] = recommendation

    approval_role_stats: dict[str, dict[str, Any]] = {}

    def _approval_role_entry(role_id: str) -> dict[str, Any]:
        if role_id not in approval_role_stats:
            approval_role_stats[role_id] = {
                "role_id": role_id,
                "assigned_count": 0,
                "pending_count": 0,
                "decided_count": 0,
                "average_turnaround_hours": 0.0,
                "disagreement_rate": 0.0,
                "route_to_human_rate": 0.0,
                "approve_recommendation_count": 0,
                "revise_recommendation_count": 0,
                "route_to_human_count": 0,
                "_turnaround_total_hours": 0.0,
                "_disagreement_checks": 0,
                "_disagreement_hits": 0,
            }
        return approval_role_stats[role_id]

    for recommendation in recommendation_by_requirement.values():
        role_id = str(recommendation.get("role") or "").strip()
        if not role_id:
            continue
        entry = _approval_role_entry(role_id)
        entry["assigned_count"] += 1
        action = str(recommendation.get("action") or "")
        if action == "approve":
            entry["approve_recommendation_count"] += 1
        elif action == "revise":
            entry["revise_recommendation_count"] += 1
        elif action == "route_to_human":
            entry["route_to_human_count"] += 1

    for approval in approvals:
        role_id = str(approval.reviewer or "").strip()
        if not role_id:
            continue
        entry = _approval_role_entry(role_id)
        if str(approval.status or "") == "pending":
            entry["pending_count"] += 1
            continue
        entry["decided_count"] += 1
        entry["_turnaround_total_hours"] += _safe_hours_between(approval.created_at, approval.decided_at)
        recommendation = recommendation_by_requirement.get(int(approval.requirement_id or 0), {})
        recommendation_action = str(recommendation.get("action") or "")
        if recommendation_action in {"approve", "revise"}:
            entry["_disagreement_checks"] += 1
            final_approved = str(approval.status or "") == "approved"
            if (recommendation_action == "approve" and not final_approved) or (
                recommendation_action == "revise" and final_approved
            ):
                entry["_disagreement_hits"] += 1

    approval_rows: list[dict[str, Any]] = []
    for role_id, entry in sorted(approval_role_stats.items(), key=lambda item: item[0]):
        decided_count = int(entry["decided_count"])
        assigned_count = int(entry["assigned_count"])
        disagreement_checks = int(entry["_disagreement_checks"])
        approval_rows.append(
            {
                "role_id": role_id,
                "assigned_count": assigned_count,
                "pending_count": int(entry["pending_count"]),
                "decided_count": decided_count,
                "average_turnaround_hours": round(
                    entry["_turnaround_total_hours"] / decided_count, 2
                ) if decided_count else 0.0,
                "disagreement_rate": round(
                    (entry["_disagreement_hits"] / disagreement_checks) * 100, 2
                ) if disagreement_checks else 0.0,
                "route_to_human_rate": round(
                    (entry["route_to_human_count"] / assigned_count) * 100, 2
                ) if assigned_count else 0.0,
                "approve_recommendation_count": int(entry["approve_recommendation_count"]),
                "revise_recommendation_count": int(entry["revise_recommendation_count"]),
                "route_to_human_count": int(entry["route_to_human_count"]),
            }
        )

    approval_pending_count = sum(row["pending_count"] for row in approval_rows)
    stale_cutoff = _to_utc(datetime.now(timezone.utc))
    approval_stale_count = 0
    if stale_cutoff is not None:
        for approval in approvals:
            if str(approval.status or "") != "pending":
                continue
            created_at = _to_utc(approval.created_at)
            if created_at is not None and (stale_cutoff - created_at).total_seconds() >= 24 * 3600:
                approval_stale_count += 1

    return {
        "roles": role_rows,
        "approval_roles": approval_rows,
        "summary": {
            "role_count": len(role_rows),
            "total_backlog_count": total_backlog_count,
            "overloaded_role_count": sum(1 for row in role_rows if row["backlog_count"] >= 3),
            "approval_pending_count": approval_pending_count,
            "approval_stale_count": approval_stale_count,
        },
    }
