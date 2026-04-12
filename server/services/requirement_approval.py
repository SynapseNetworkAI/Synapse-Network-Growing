from __future__ import annotations

import json
from typing import Any

from server.database import RequirementRow, WorkflowRunRow, WorkflowStepRow

DEFAULT_REQUIREMENT_APPROVAL_CONTRACT: dict[str, Any] = {
    "approval_mode": "auto_or_human",
    "required_approver_roles": ["request_owner", "reviewer", "tester"],
    "fallback_reviewer": "operator",
    "auto_approve": {
        "enabled": True,
        "max_priority": "normal",
        "max_complexity_tier": "standard",
        "single_project_only": True,
        "allow_incident_recovery": False,
    },
}

_PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2}
_TIER_RANK = {"mini": 0, "standard": 1, "max": 2}
_APPROVAL_STATUSES = {"pending_approval", "approved", "rejected", "waived"}


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def normalize_requirement_approval_contract(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = json.loads(json.dumps(DEFAULT_REQUIREMENT_APPROVAL_CONTRACT))
    if isinstance(raw, dict):
        mode = str(raw.get("approval_mode") or "").strip()
        if mode in {"auto_or_human", "manual_required", "waived"}:
            payload["approval_mode"] = mode
        roles = [str(item).strip() for item in raw.get("required_approver_roles") or [] if str(item).strip()]
        if roles:
            payload["required_approver_roles"] = roles
        fallback = str(raw.get("fallback_reviewer") or "").strip()
        if fallback:
            payload["fallback_reviewer"] = fallback
        auto = raw.get("auto_approve") or {}
        if isinstance(auto, dict):
            auto_payload = dict(payload["auto_approve"])
            auto_payload["enabled"] = bool(auto.get("enabled", auto_payload["enabled"]))
            priority = str(auto.get("max_priority") or "").strip()
            if priority in _PRIORITY_RANK:
                auto_payload["max_priority"] = priority
            tier = str(auto.get("max_complexity_tier") or "").strip()
            if tier in _TIER_RANK:
                auto_payload["max_complexity_tier"] = tier
            if "single_project_only" in auto:
                auto_payload["single_project_only"] = bool(auto.get("single_project_only"))
            if "allow_incident_recovery" in auto:
                auto_payload["allow_incident_recovery"] = bool(auto.get("allow_incident_recovery"))
            payload["auto_approve"] = auto_payload
    if str(payload.get("approval_mode") or "") == "manual_required":
        payload["auto_approve"]["enabled"] = False
    return payload


def requirement_approval_contract_for_requirement(requirement: RequirementRow) -> dict[str, Any]:
    return normalize_requirement_approval_contract(
        _json_loads(getattr(requirement, "approval_contract_json", None), {})
    )


def normalize_requirement_approval_status(value: str | None) -> str:
    status = str(value or "").strip()
    return status if status in _APPROVAL_STATUSES else "pending_approval"


def approval_request_reviewer(requirement: RequirementRow, contract: dict[str, Any]) -> str:
    intake = _json_loads(getattr(requirement, "intake_metadata_json", None), {})
    if isinstance(intake, dict):
        requested_by = str(intake.get("requested_by") or intake.get("request_owner") or "").strip()
        if requested_by:
            return requested_by
    return str(contract.get("fallback_reviewer") or "operator")


def _split_target_paths(target_project_path: str | None) -> list[str]:
    return [item.strip() for item in str(target_project_path or "").splitlines() if item.strip()]


def _workflow_steps_from_sources(
    *,
    planner_output: dict[str, Any] | None = None,
    workflow_run: WorkflowRunRow | None = None,
) -> list[dict[str, Any]]:
    if isinstance(planner_output, dict):
        steps = planner_output.get("workflow_steps") or []
        if isinstance(steps, list):
            return [dict(step) for step in steps if isinstance(step, dict)]
    if workflow_run is None:
        return []
    packets: list[dict[str, Any]] = []
    for step in workflow_run.steps or []:
        if not isinstance(step, WorkflowStepRow):
            continue
        execution_profile = _json_loads(getattr(step, "execution_profile_json", None), {})
        packets.append(
            {
                "step_type": str(getattr(step, "step_type", "") or ""),
                "complexity_tier": str((execution_profile or {}).get("complexity_tier") or ""),
            }
        )
    return packets


def build_requirement_approval_context(
    requirement: RequirementRow,
    *,
    planner_output: dict[str, Any] | None = None,
    workflow_run: WorkflowRunRow | None = None,
) -> dict[str, Any]:
    target_paths = _split_target_paths(getattr(requirement, "target_project_path", None))
    workflow_steps = _workflow_steps_from_sources(planner_output=planner_output, workflow_run=workflow_run)
    max_tier = "mini"
    for step in workflow_steps:
        tier = str(step.get("complexity_tier") or "standard").strip()
        if _TIER_RANK.get(tier, 1) > _TIER_RANK.get(max_tier, 0):
            max_tier = tier
    source = str(getattr(requirement, "source", "") or "")
    source_ref = str(getattr(requirement, "source_ref", "") or "")
    is_incident = source == "incident_followup" or "incident" in source_ref.lower() or "incident" in str(getattr(requirement, "title", "")).lower()
    return {
        "priority": str(getattr(requirement, "priority", "") or "normal"),
        "target_project_count": len(target_paths),
        "target_paths": target_paths,
        "max_complexity_tier": max_tier,
        "workflow_step_count": len(workflow_steps),
        "is_incident_recovery": is_incident,
    }


def evaluate_requirement_execution_approval(
    requirement: RequirementRow,
    *,
    planner_output: dict[str, Any] | None = None,
    workflow_run: WorkflowRunRow | None = None,
) -> dict[str, Any]:
    contract = requirement_approval_contract_for_requirement(requirement)
    mode = str(contract.get("approval_mode") or "auto_or_human")
    context = build_requirement_approval_context(requirement, planner_output=planner_output, workflow_run=workflow_run)
    if mode == "waived":
        return {"approval_status": "waived", "auto_approved": True, "reason": "approval waived by contract", "context": context}
    if mode == "manual_required":
        return {"approval_status": "pending_approval", "auto_approved": False, "reason": "manual approval required by contract", "context": context}
    auto = dict(contract.get("auto_approve") or {})
    if not bool(auto.get("enabled", True)):
        return {"approval_status": "pending_approval", "auto_approved": False, "reason": "auto approval disabled by contract", "context": context}
    reasons: list[str] = []
    if _PRIORITY_RANK.get(str(context["priority"]), 1) > _PRIORITY_RANK.get(str(auto.get("max_priority") or "normal"), 1):
        reasons.append(f"priority `{context['priority']}` exceeds auto-approve ceiling `{auto.get('max_priority')}`")
    if _TIER_RANK.get(str(context["max_complexity_tier"]), 1) > _TIER_RANK.get(str(auto.get("max_complexity_tier") or "standard"), 1):
        reasons.append(f"planner tier `{context['max_complexity_tier']}` exceeds auto-approve ceiling `{auto.get('max_complexity_tier')}`")
    if bool(auto.get("single_project_only", True)) and int(context["target_project_count"] or 0) > 1:
        reasons.append("requirement spans multiple target projects")
    if not bool(auto.get("allow_incident_recovery", False)) and bool(context["is_incident_recovery"]):
        reasons.append("incident recovery work requires human approval")
    if reasons:
        return {"approval_status": "pending_approval", "auto_approved": False, "reason": "; ".join(reasons), "context": context}
    return {"approval_status": "approved", "auto_approved": True, "reason": "requirement passed auto-approval policy", "context": context}
