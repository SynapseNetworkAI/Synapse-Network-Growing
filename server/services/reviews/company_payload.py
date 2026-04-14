"""Company review payload parsing and serialization helpers."""

from __future__ import annotations

import json
from typing import Any

from server.database import CompanyOperatingReviewRow

_DEFAULT_OPERATOR_REVIEW_PACKAGE = {
    "title": "Operator Review Package",
    "summary_markdown": "No operator package generated yet.",
    "checklist": [],
    "decisions": [],
    "autonomous_decision_count": 0,
    "recommended_bundle_item_keys": [],
}

_DEFAULT_AUTONOMOUS_COO_POSTURE = {
    "mode": "autonomous_coo",
    "operator_only_high_risk": True,
    "autonomous_workflow_keys": [],
    "high_risk_decision_count": 0,
    "autonomous_decision_count": 0,
    "operator_queue_count": 0,
    "pending_human_gate_count": 0,
    "auto_approved_requirement_count": 0,
    "stale_approval_count": 0,
    "stuck_requirement_count": 0,
    "critical_incident_count": 0,
    "requires_operator_attention": False,
    "autonomous_execution_rate": 0.0,
    "summary_markdown": "Autonomous COO posture has not been computed yet.",
}


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _review_payload(row: CompanyOperatingReviewRow) -> dict[str, Any]:
    """Decode the persisted payload JSON for a company review row."""

    payload = _json_loads(row.payload_json, {})
    return payload if isinstance(payload, dict) else {}


def company_review_to_dict(row: CompanyOperatingReviewRow) -> dict[str, Any]:
    """Serialize a company operating review row for API responses."""

    payload = _review_payload(row)
    return {
        "id": int(row.id),
        "cycle_label": str(row.cycle_label),
        "title": str(row.title),
        "summary_markdown": str(row.summary_markdown or ""),
        "portfolio_summary": dict(payload.get("portfolio_summary") or {}),
        "project_highlights": list(payload.get("project_highlights") or []),
        "bottlenecks": list(payload.get("bottlenecks") or []),
        "incidents": list(payload.get("incidents") or []),
        "recurring_bug_fingerprints": list(payload.get("recurring_bug_fingerprints") or []),
        "cross_project_bug_recoveries": list(payload.get("cross_project_bug_recoveries") or []),
        "human_gate_hotspots": list(payload.get("human_gate_hotspots") or []),
        "automation_candidates": list(payload.get("automation_candidates") or []),
        "next_cycle_recommendations": list(payload.get("next_cycle_recommendations") or []),
        "next_cycle_requirement_bundle": list(payload.get("next_cycle_requirement_bundle") or []),
        "operator_review_package": dict(payload.get("operator_review_package") or _DEFAULT_OPERATOR_REVIEW_PACKAGE),
        "autonomous_coo_posture": dict(payload.get("autonomous_coo_posture") or _DEFAULT_AUTONOMOUS_COO_POSTURE),
        "source_snapshot": dict(payload.get("source_snapshot") or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


__all__ = [
    "_review_payload",
    "company_review_to_dict",
]
