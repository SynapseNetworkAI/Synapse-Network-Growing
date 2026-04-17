from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from server.database import RequirementRow, WorkflowRunRow, WorkflowStepDependencyRow, WorkflowStepRow


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


def _step_is_dispatchable(db: Session, step: WorkflowStepRow) -> bool:
    dependencies = db.query(WorkflowStepDependencyRow).filter(
        WorkflowStepDependencyRow.step_id == step.id,
        WorkflowStepDependencyRow.is_blocking == True,  # noqa: E712
    ).all()
    if not dependencies:
        return True
    prior_ids = [int(dep.depends_on_step_id) for dep in dependencies if dep.depends_on_step_id is not None]
    if not prior_ids:
        return True
    prior_steps = db.query(WorkflowStepRow).filter(WorkflowStepRow.id.in_(prior_ids)).all()
    return all(str(item.status or "") == "completed" for item in prior_steps)


def list_acceptance_dispatch_candidates(db: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    requirements = db.query(RequirementRow).filter(
        RequirementRow.active_workflow_run_id.isnot(None)
    ).order_by(RequirementRow.id.asc()).all()
    for requirement in requirements:
        run = db.query(WorkflowRunRow).filter(
            WorkflowRunRow.id == requirement.active_workflow_run_id
        ).first()
        if run is None or str(run.status or "") in {"completed", "failed"}:
            continue
        contract = acceptance_contract_for_requirement(requirement)
        step_types = {
            str(item).strip()
            for item in contract.get("workflow_step_types") or []
            if str(item).strip()
        }
        steps = db.query(WorkflowStepRow).filter(
            WorkflowStepRow.workflow_run_id == run.id
        ).order_by(WorkflowStepRow.sequence_no.asc(), WorkflowStepRow.id.asc()).all()
        for step in steps:
            if str(step.status or "") != "pending":
                continue
            if str(step.step_type or "") not in step_types:
                continue
            if not _step_is_dispatchable(db, step):
                continue
            candidates.append(
                {
                    "requirement_id": int(requirement.id),
                    "requirement_title": str(requirement.title or ""),
                    "workflow_run_id": int(run.id),
                    "step_id": int(step.id),
                    "step_key": str(step.step_key or ""),
                    "step_type": str(step.step_type or ""),
                    "step_title": str(step.title or ""),
                    "acceptance_owner_role": (
                        str(contract.get("review_owner_role") or "reviewer")
                        if str(step.step_type or "") == "review"
                        else str(contract.get("acceptance_owner_role") or "tester")
                    ),
                    "acceptance_mode": str(contract.get("acceptance_mode") or "scheduled"),
                    "acceptance_trigger": str(contract.get("acceptance_trigger") or "implementation_completed"),
                    "required_evidence_artifact_types": list(contract.get("required_evidence_artifact_types") or []),
                }
            )
            break
        if len(candidates) >= limit:
            break
    return candidates[:limit]
