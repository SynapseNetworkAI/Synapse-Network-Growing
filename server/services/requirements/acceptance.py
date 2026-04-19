from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from server.database import RequirementRow, WorkflowRunRow


DEFAULT_ACCEPTANCE_CONTRACT: dict[str, Any] = {
    "acceptance_owner_role": "tester",
    "review_owner_role": "reviewer",
    "acceptance_mode": "scheduled",
    "acceptance_trigger": "implementation_completed",
    "workflow_step_types": ["review", "test", "closeout"],
    "required_evidence_artifact_types": ["project_change_summary", "validation_plan"],
    "done_criteria": [],
    "verification_checks": [],
    "scope_constraints": [],
    "delivery_expectation": "",
    "risk_notes": [],
    "expected_evidence": [],
    "acceptance_index": {},
    "markdown": "",
}


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def normalize_acceptance_contract(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(DEFAULT_ACCEPTANCE_CONTRACT)
    if isinstance(raw, dict):
        for key in {
            "acceptance_owner_role",
            "review_owner_role",
            "acceptance_mode",
            "acceptance_trigger",
        }:
            value = str(raw.get(key) or "").strip()
            if value:
                payload[key] = value
        for key in {"workflow_step_types", "required_evidence_artifact_types"}:
            values = [str(item).strip() for item in raw.get(key) or [] if str(item).strip()]
            if values:
                payload[key] = values
        for key in {"done_criteria", "scope_constraints", "risk_notes", "expected_evidence"}:
            values = [str(item).strip() for item in raw.get(key) or [] if str(item).strip()]
            if values:
                payload[key] = values
        verification_checks: list[dict[str, Any]] = []
        for item in raw.get("verification_checks") or []:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            verification_checks.append(
                {
                    "label": label,
                    "command": str(item.get("command") or "").strip() or None,
                    "kind": str(item.get("kind") or "evidence").strip() or "evidence",
                }
            )
        if verification_checks:
            payload["verification_checks"] = verification_checks
        delivery_expectation = str(raw.get("delivery_expectation") or "").strip()
        if delivery_expectation:
            payload["delivery_expectation"] = delivery_expectation
        acceptance_index = raw.get("acceptance_index")
        if isinstance(acceptance_index, dict):
            payload["acceptance_index"] = acceptance_index
        markdown = str(raw.get("markdown") or "").strip()
        if markdown:
            payload["markdown"] = markdown
    payload["acceptance_index"] = {
        **dict(payload.get("acceptance_index") or {}),
        "done_criteria_count": len(payload.get("done_criteria") or []),
        "scope_constraints_count": len(payload.get("scope_constraints") or []),
        "expected_evidence_count": len(payload.get("expected_evidence") or []),
    }
    return payload


def acceptance_contract_for_requirement(requirement: RequirementRow) -> dict[str, Any]:
    return normalize_acceptance_contract(
        _json_loads(getattr(requirement, "acceptance_contract_json", None), {})
    )


def list_acceptance_dispatch_candidates(db: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    """Return declarative workflow runs that may need operator validation attention.

    The legacy fixed-step acceptance dispatcher has been retired; this helper now
    exposes high-level workflow candidates only, without creating or dispatching
    hidden task/step records.
    """

    candidates: list[dict[str, Any]] = []
    requirements = db.query(RequirementRow).filter(
        RequirementRow.active_workflow_run_id.isnot(None)
    ).order_by(RequirementRow.id.asc()).all()
    for requirement in requirements:
        run = db.query(WorkflowRunRow).filter(
            WorkflowRunRow.id == requirement.active_workflow_run_id
        ).first()
        if run is None or str(run.status or "") in {"succeeded", "failed", "cancelled"}:
            continue
        contract = acceptance_contract_for_requirement(requirement)
        candidates.append(
            {
                "requirement_id": int(requirement.id),
                "requirement_title": str(requirement.title or ""),
                "workflow_run_id": int(run.id),
                "current_state": str(run.current_state or ""),
                "workflow_status": str(run.status or ""),
                "acceptance_owner_role": str(contract.get("acceptance_owner_role") or "tester"),
                "acceptance_mode": str(contract.get("acceptance_mode") or "scheduled"),
                "acceptance_trigger": "declarative_workflow_observation",
                "required_evidence_artifact_types": list(contract.get("required_evidence_artifact_types") or []),
            }
        )
        if len(candidates) >= limit:
            break
    return candidates[:limit]
