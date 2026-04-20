from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from server.database import RequirementRow, WorkflowRunRow


class AcceptanceValidationError(ValueError):
    """Raised when a requirement cannot safely enter execution."""


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
    "execution_acceptance_steps": [],
    "acceptance_kind": "business",
    "manual_review_prompt": "",
    "acceptance_override": False,
    "override_by": "",
    "override_reason": "",
    "override_at": "",
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
        acceptance_kind = str(raw.get("acceptance_kind") or "").strip()
        if acceptance_kind in {"business", "system_dogfood"}:
            payload["acceptance_kind"] = acceptance_kind
        for key in {"manual_review_prompt", "override_by", "override_reason", "override_at"}:
            value = str(raw.get(key) or "").strip()
            if value:
                payload[key] = value
        if "acceptance_override" in raw:
            payload["acceptance_override"] = bool(raw.get("acceptance_override"))
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
        steps: list[dict[str, Any]] = []
        for item in raw.get("execution_acceptance_steps") or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            expected_result = str(item.get("expected_result") or "").strip()
            if not title or not expected_result:
                continue
            step = dict(item)
            step["step_key"] = str(step.get("step_key") or title).strip()
            step["title"] = title
            step["expected_result"] = expected_result
            for list_key in {"required_commands", "required_evidence_types", "required_db_lineage"}:
                step[list_key] = [str(value).strip() for value in step.get(list_key) or [] if str(value).strip()]
            step["manual_review_prompt"] = str(step.get("manual_review_prompt") or "").strip()
            steps.append(step)
        if steps:
            payload["execution_acceptance_steps"] = steps
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
        "execution_acceptance_step_count": len(payload.get("execution_acceptance_steps") or []),
    }
    return payload


def validate_acceptance_contract_for_execution(
    contract: dict[str, Any] | None,
    *,
    source: str,
    goal_key: str | None = None,
) -> dict[str, Any]:
    """Fail closed unless execution acceptance is evidence-bound.

    Human Override is a deliberate operator shortcut for manual requirements
    only; it still requires business confirmation after technical completion.
    """

    payload = normalize_acceptance_contract(contract or {})
    normalized_source = str(source or "").strip().lower()
    if bool(payload.get("acceptance_override")):
        prompt = str(payload.get("manual_review_prompt") or "").strip()
        if normalized_source not in {"manual", "operator", "human"}:
            raise AcceptanceValidationError("Human Override is only allowed for manually created requirements.")
        if not prompt:
            raise AcceptanceValidationError("Human Override requires manual_review_prompt.")
        return payload

    steps = payload.get("execution_acceptance_steps") or []
    if not isinstance(steps, list) or not steps:
        raise AcceptanceValidationError("execution_acceptance_steps must be non-empty.")
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise AcceptanceValidationError(f"execution_acceptance_steps[{index}] must be an object.")
        title = str(step.get("title") or "").strip()
        expected_result = str(step.get("expected_result") or "").strip()
        has_evidence = any(
            step.get(key)
            for key in ("required_commands", "required_evidence_types", "required_db_lineage")
        )
        if not title or not expected_result:
            raise AcceptanceValidationError(f"execution_acceptance_steps[{index}] requires title and expected_result.")
        if not has_evidence:
            raise AcceptanceValidationError(
                f"execution_acceptance_steps[{index}] requires required_commands, required_evidence_types, or required_db_lineage."
            )
    if str(payload.get("acceptance_kind") or "business") == "system_dogfood":
        normalized_goal = str(goal_key or "").strip().lower()
        if normalized_goal != "goalb":
            raise AcceptanceValidationError("system_dogfood acceptance is only allowed for goalb.")
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
