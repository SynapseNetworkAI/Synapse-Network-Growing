from __future__ import annotations

import json
import re
from typing import Any

from server.database import RequirementRow, WorkflowRunRow

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
    "agent_review": {
        "enabled": True,
        "approval_role": "reviewer",
        "minimum_confidence": 0.72,
        "route_to_human_on_low_confidence": True,
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
        agent_review = raw.get("agent_review") or {}
        if isinstance(agent_review, dict):
            agent_payload = dict(payload["agent_review"])
            if "enabled" in agent_review:
                agent_payload["enabled"] = bool(agent_review.get("enabled"))
            approval_role = str(agent_review.get("approval_role") or "").strip()
            if approval_role:
                agent_payload["approval_role"] = approval_role
            minimum_confidence = agent_review.get("minimum_confidence")
            try:
                if minimum_confidence is not None:
                    agent_payload["minimum_confidence"] = max(0.0, min(1.0, float(minimum_confidence)))
            except (TypeError, ValueError):
                pass
            if "route_to_human_on_low_confidence" in agent_review:
                agent_payload["route_to_human_on_low_confidence"] = bool(
                    agent_review.get("route_to_human_on_low_confidence")
                )
            payload["agent_review"] = agent_payload
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


def _plan_items_from_sources(
    *,
    planner_output: dict[str, Any] | None = None,
    workflow_run: WorkflowRunRow | None = None,
) -> list[dict[str, Any]]:
    if isinstance(planner_output, dict):
        items = planner_output.get("plan_items") or []
        if isinstance(items, list):
            return [dict(item) for item in items if isinstance(item, dict)]
    if workflow_run is None:
        return []
    blackboard = _json_loads(getattr(workflow_run, "blackboard_json", None), {})
    workflow_key = str(getattr(workflow_run, "workflow_key", "") or "")
    if workflow_key:
        return [
            {
                "item_type": workflow_key,
                "complexity_tier": str((blackboard or {}).get("complexity_tier") or "standard"),
            }
        ]
    return []


def build_requirement_approval_context(
    requirement: RequirementRow,
    *,
    planner_output: dict[str, Any] | None = None,
    workflow_run: WorkflowRunRow | None = None,
) -> dict[str, Any]:
    target_paths = _split_target_paths(getattr(requirement, "target_project_path", None))
    plan_items = _plan_items_from_sources(planner_output=planner_output, workflow_run=workflow_run)
    max_tier = "mini"
    estimated_budget_points = 0
    for item in plan_items:
        tier = str(item.get("complexity_tier") or "standard").strip()
        if _TIER_RANK.get(tier, 1) > _TIER_RANK.get(max_tier, 0):
            max_tier = tier
        try:
            estimated_budget_points = max(
                estimated_budget_points,
                int((item.get("budget_cap") or {}).get("max_cost_points") or 0),
            )
        except (AttributeError, TypeError, ValueError):
            continue
    source = str(getattr(requirement, "source", "") or "")
    source_ref = str(getattr(requirement, "source_ref", "") or "")
    intake = _json_loads(getattr(requirement, "intake_metadata_json", None), {})
    title = str(getattr(requirement, "title", "") or "")
    description = str(getattr(requirement, "description_markdown", "") or "")
    is_incident = source == "incident_followup" or "incident" in source_ref.lower() or "incident" in str(getattr(requirement, "title", "")).lower()
    is_bug_recovery = source == "bug_intake" or source_ref.startswith("bug-intake:")
    cross_project_bug_recovery = bool((intake or {}).get("cross_project_recovery"))
    publish_impact = any(token in f"{title}\n{description}".lower() for token in ("publish", "release", "production"))
    description_complete = len(re.sub(r"\s+", " ", description).strip()) >= 48 if isinstance(description, str) else False
    return {
        "priority": str(getattr(requirement, "priority", "") or "normal"),
        "source": source or "manual",
        "source_ref": source_ref,
        "target_project_count": len(target_paths),
        "target_paths": target_paths,
        "max_complexity_tier": max_tier,
        "plan_item_count": len(plan_items),
        "is_incident_recovery": is_incident,
        "is_bug_recovery": is_bug_recovery,
        "cross_project_bug_recovery": cross_project_bug_recovery,
        "publish_impact": publish_impact,
        "estimated_budget_points": estimated_budget_points,
        "description_complete": description_complete,
    }


def _approval_role_for_requirement(requirement: RequirementRow, contract: dict[str, Any]) -> str:
    agent_review = dict(contract.get("agent_review") or {})
    approval_role = str(agent_review.get("approval_role") or "").strip()
    if approval_role:
        return approval_role
    intake = _json_loads(getattr(requirement, "intake_metadata_json", None), {})
    if isinstance(intake, dict):
        for key in ("approval_role", "review_owner_role", "acceptance_owner_role"):
            value = str(intake.get(key) or "").strip()
            if value:
                return value
    return "reviewer"


def build_requirement_approval_router(
    requirement: RequirementRow,
    *,
    planner_output: dict[str, Any] | None = None,
    workflow_run: WorkflowRunRow | None = None,
) -> dict[str, Any]:
    contract = requirement_approval_contract_for_requirement(requirement)
    mode = str(contract.get("approval_mode") or "auto_or_human")
    context = build_requirement_approval_context(requirement, planner_output=planner_output, workflow_run=workflow_run)
    auto = dict(contract.get("auto_approve") or {})
    hard_rule_hits: list[str] = []
    soft_rule_hits: list[str] = []

    if bool(context.get("cross_project_bug_recovery")):
        hard_rule_hits.append("cross_project_bug_recovery")
    if bool(context.get("publish_impact")):
        hard_rule_hits.append("publish_or_delivery_impact")
    if bool(context.get("is_incident_recovery")) and _PRIORITY_RANK.get(str(context.get("priority")), 1) >= _PRIORITY_RANK["high"]:
        hard_rule_hits.append("critical_incident_recovery")
    if _TIER_RANK.get(str(context.get("max_complexity_tier") or "standard"), 1) >= _TIER_RANK["max"]:
        hard_rule_hits.append("max_tier_execution")
    if int(context.get("estimated_budget_points") or 0) >= 60:
        hard_rule_hits.append("over_budget_execution")
    if int(context.get("target_project_count") or 0) > 1 and _TIER_RANK.get(str(context.get("max_complexity_tier") or "standard"), 1) >= _TIER_RANK["standard"]:
        hard_rule_hits.append("multi_project_high_risk_work")

    if _PRIORITY_RANK.get(str(context["priority"]), 1) > _PRIORITY_RANK.get(str(auto.get("max_priority") or "normal"), 1):
        soft_rule_hits.append(f"priority `{context['priority']}` exceeds auto-approve ceiling `{auto.get('max_priority')}`")
    if _TIER_RANK.get(str(context["max_complexity_tier"]), 1) > _TIER_RANK.get(str(auto.get("max_complexity_tier") or "standard"), 1):
        soft_rule_hits.append(
            f"planner tier `{context['max_complexity_tier']}` exceeds auto-approve ceiling `{auto.get('max_complexity_tier')}`"
        )
    if bool(auto.get("single_project_only", True)) and int(context["target_project_count"] or 0) > 1:
        soft_rule_hits.append("requirement spans multiple target projects")
    if not bool(auto.get("allow_incident_recovery", False)) and bool(context["is_incident_recovery"]):
        soft_rule_hits.append("incident recovery work requires human approval")
    if int(context.get("estimated_budget_points") or 0) >= 30:
        soft_rule_hits.append("estimated budget exceeds low-risk threshold")

    approval_source = "agent"
    needs_human_gate = False
    route_reason = "agent review required"
    if mode == "waived":
        approval_source = "waived"
        route_reason = "approval waived by contract"
    elif mode == "manual_required":
        approval_source = "human"
        needs_human_gate = True
        route_reason = "manual approval required by contract"
    elif hard_rule_hits:
        approval_source = "human"
        needs_human_gate = True
        route_reason = "; ".join(hard_rule_hits)
    elif not bool(auto.get("enabled", True)):
        approval_source = "agent"
        route_reason = "auto approval disabled; route through approval recommendation"
    elif not soft_rule_hits:
        approval_source = "auto"
        route_reason = "requirement passed deterministic auto-approval policy"

    return {
        "approval_source": approval_source,
        "needs_human_gate": needs_human_gate,
        "required_approver_roles": list(contract.get("required_approver_roles") or []),
        "approval_role": _approval_role_for_requirement(requirement, contract),
        "hard_rule_hits": hard_rule_hits,
        "soft_rule_hits": soft_rule_hits,
        "reason": route_reason,
        "context": context,
    }


def build_requirement_approval_recommendation(
    requirement: RequirementRow,
    *,
    planner_output: dict[str, Any] | None = None,
    workflow_run: WorkflowRunRow | None = None,
) -> dict[str, Any]:
    contract = requirement_approval_contract_for_requirement(requirement)
    router = build_requirement_approval_router(requirement, planner_output=planner_output, workflow_run=workflow_run)
    context = dict(router.get("context") or {})
    approval_role = str(router.get("approval_role") or "reviewer")
    if str(router.get("approval_source")) == "waived":
        return {
            "action": "approve",
            "role": approval_role,
            "confidence": 1.0,
            "reason": "approval waived by contract",
        }
    if str(router.get("approval_source")) == "auto":
        return {
            "action": "approve",
            "role": approval_role,
            "confidence": 0.99,
            "reason": str(router.get("reason") or "deterministic auto-approval"),
        }
    if str(router.get("approval_source")) == "human":
        return {
            "action": "route_to_human",
            "role": approval_role,
            "confidence": 0.98,
            "reason": str(router.get("reason") or "human review required"),
        }

    completeness_gaps: list[str] = []
    if not bool(context.get("description_complete")):
        completeness_gaps.append("description is too short")
    plan_payload = _json_loads(getattr(requirement, "execution_plan_json", None), {})
    has_plan_brief = isinstance(plan_payload, dict) and bool(str(plan_payload.get("summary_markdown") or "").strip())
    has_active_plan = (
        bool(getattr(requirement, "active_workflow_run_id", None))
        or int(getattr(requirement, "current_plan_version", 0) or 0) > 0
        or has_plan_brief
    )
    if has_active_plan and not has_plan_brief and int(context.get("plan_item_count") or 0) == 0:
        completeness_gaps.append("workflow selection is missing")
    if int(context.get("target_project_count") or 0) == 0:
        completeness_gaps.append("target project is missing")
    if completeness_gaps:
        return {
            "action": "revise",
            "role": approval_role,
            "confidence": 0.91,
            "reason": "; ".join(completeness_gaps),
        }

    risk_hits = list(router.get("soft_rule_hits") or [])
    confidence = 0.82
    if bool(context.get("is_bug_recovery")):
        confidence -= 0.04
    if int(context.get("estimated_budget_points") or 0) >= 20:
        confidence -= 0.06
    if risk_hits:
        confidence -= min(0.18, 0.06 * len(risk_hits))

    agent_review = dict(contract.get("agent_review") or {})
    min_confidence = float(agent_review.get("minimum_confidence") or 0.72)
    route_to_human_on_low_confidence = bool(agent_review.get("route_to_human_on_low_confidence", True))

    if confidence >= min_confidence and not risk_hits:
        return {
            "action": "approve",
            "role": approval_role,
            "confidence": round(confidence, 2),
            "reason": "requirement is complete and low risk enough for autonomous execution",
        }
    only_priority_ceiling = bool(risk_hits) and all("exceeds auto-approve ceiling" in str(hit) for hit in risk_hits)
    if (
        str(router.get("approval_source") or "") == "agent"
        and bool(context.get("is_bug_recovery"))
        and not bool(context.get("cross_project_bug_recovery"))
        and not bool(context.get("publish_impact"))
        and only_priority_ceiling
        and confidence >= max(min_confidence - 0.08, 0.68)
    ):
        return {
            "action": "approve",
            "role": approval_role,
            "confidence": round(confidence, 2),
            "reason": "single-project bug recovery exceeded the deterministic auto ceiling but passed agent review",
        }
    if confidence < min_confidence and route_to_human_on_low_confidence:
        return {
            "action": "route_to_human",
            "role": approval_role,
            "confidence": round(max(confidence, 0.51), 2),
            "reason": str(router.get("reason") or "approval confidence below threshold"),
        }
    return {
        "action": "revise",
        "role": approval_role,
        "confidence": round(max(confidence, 0.55), 2),
        "reason": "requirement needs clarification before autonomous execution",
    }


def evaluate_requirement_execution_approval(
    requirement: RequirementRow,
    *,
    planner_output: dict[str, Any] | None = None,
    workflow_run: WorkflowRunRow | None = None,
) -> dict[str, Any]:
    contract = requirement_approval_contract_for_requirement(requirement)
    router = build_requirement_approval_router(requirement, planner_output=planner_output, workflow_run=workflow_run)
    recommendation = build_requirement_approval_recommendation(requirement, planner_output=planner_output, workflow_run=workflow_run)
    approval_source = str(router.get("approval_source") or "human")
    action = str(recommendation.get("action") or "route_to_human")
    reason = str(recommendation.get("reason") or router.get("reason") or "")
    reviewer = approval_request_reviewer(requirement, contract)
    if action == "revise":
        reviewer = "request_owner"
    elif action == "route_to_human" and str(router.get("approval_role") or "").strip():
        reviewer = str(router.get("approval_role") or reviewer)

    approval_status = "pending_approval"
    auto_approved = False
    if approval_source == "waived":
        approval_status = "waived"
        auto_approved = True
    elif action == "approve" and approval_source in {"auto", "agent"}:
        approval_status = "approved"
        auto_approved = True

    return {
        "approval_status": approval_status,
        "auto_approved": auto_approved,
        "reason": reason,
        "context": dict(router.get("context") or {}),
        "approval_source": approval_source,
        "approval_router": router,
        "approval_recommendation": recommendation,
        "needs_human_gate": bool(router.get("needs_human_gate")),
        "required_approver_roles": list(router.get("required_approver_roles") or []),
        "reviewer": reviewer,
    }
