"""Workflow and human-gate KPI aggregation for agent capability profiles."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import (
    AgentRow,
    HumanGateRequestRow,
)


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


def build_role_kpi_snapshot(db: Session) -> dict[str, Any]:
    """Aggregate workflow and human-gate KPI metrics by capability profile."""

    agents = db.query(AgentRow).order_by(AgentRow.group.asc(), AgentRow.display_name.asc()).all()
    human_gates = db.query(HumanGateRequestRow).all()

    role_rows: list[dict[str, Any]] = []
    total_backlog_count = 0
    for agent in agents:
        role_id = str(agent.id)
        status_mix: dict[str, int] = {}
        task_count = 0
        completed_count = 0
        active_task_count = 0
        pending_task_count = 0
        failed_task_count = 0
        backlog_count = 0
        reopened_task_count = 0
        human_gate_dependency_count = 0
        average_token_cost = 0.0
        average_budget_cost_points = 0.0
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
                "human_gate_dependency_count": human_gate_dependency_count,
                "completion_rate": round((completed_count / task_count) * 100, 2) if task_count else 0.0,
                "reopen_rate": round((reopened_task_count / task_count) * 100, 2) if task_count else 0.0,
                "human_gate_dependency_rate": round((human_gate_dependency_count / task_count) * 100, 2) if task_count else 0.0,
                "average_token_cost": average_token_cost,
                "average_budget_cost_points": average_budget_cost_points,
                "tokens_used_total": 0,
                "budget_cost_points_total": 0,
                "open_requirement_count": 0,
                "status_mix": status_mix,
            }
        )

    gate_role_stats: dict[str, dict[str, Any]] = {}

    def _gate_role_entry(role_id: str) -> dict[str, Any]:
        if role_id not in gate_role_stats:
            gate_role_stats[role_id] = {
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
        return gate_role_stats[role_id]

    for gate in human_gates:
        role_id = str(getattr(gate, "decided_by", "") or "operator").strip()
        entry = _gate_role_entry(role_id)
        entry["assigned_count"] += 1
        if str(gate.status or "") == "pending":
            entry["pending_count"] += 1
            continue
        entry["decided_count"] += 1
        entry["_turnaround_total_hours"] += _safe_hours_between(gate.created_at, gate.decided_at)

    approval_rows: list[dict[str, Any]] = []
    for role_id, entry in sorted(gate_role_stats.items(), key=lambda item: item[0]):
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

    gate_pending_count = sum(row["pending_count"] for row in approval_rows)
    stale_cutoff = _to_utc(datetime.now(timezone.utc))
    human_gate_stale_count = 0
    if stale_cutoff is not None:
        for gate in human_gates:
            if str(gate.status or "") != "pending":
                continue
            created_at = _to_utc(gate.created_at)
            if created_at is not None and (stale_cutoff - created_at).total_seconds() >= 24 * 3600:
                human_gate_stale_count += 1

    return {
        "roles": role_rows,
        "human_gate_roles": approval_rows,
        "summary": {
            "role_count": len(role_rows),
            "total_backlog_count": total_backlog_count,
            "overloaded_role_count": sum(1 for row in role_rows if row["backlog_count"] >= 3),
            "human_gate_pending_count": gate_pending_count,
            "human_gate_stale_count": human_gate_stale_count,
        },
    }
