"""Template library for optimization requirements."""
from __future__ import annotations

import json
from typing import Any

from server.schemas import RequirementCreate


_TEMPLATES: dict[str, dict[str, Any]] = {
    "defect_reduction": {
        "template_key": "defect_reduction",
        "category": "code_quality",
        "display_name": "Defect Reduction",
        "description": "Convert repeated failures into a root-cause fix with regression coverage.",
        "supported_signal_types": ["bug_report"],
        "acceptance_checks": [
            {
                "check_key": "root_cause_documented",
                "description": "Review confirms the defect root cause and remediation scope are documented.",
                "check_type": "manual_review",
                "owner_role": "reviewer",
                "success_criteria_markdown": "Review artifact explains root cause, affected surface, and chosen remediation.",
                "validation_step_key": "review",
                "verification_type": "manual",
            },
            {
                "check_key": "regression_guard_added",
                "description": "Validation confirms regression coverage was added for the repeated defect path.",
                "check_type": "content_assertion",
                "owner_role": "tester",
                "success_criteria_markdown": "Automated validation proves the failing path is covered by a repeatable regression guard.",
                "validation_step_key": "test",
                "verification_type": "automated",
            },
        ],
    },
    "release_bottleneck": {
        "template_key": "release_bottleneck",
        "category": "release_safety",
        "display_name": "Release Bottleneck",
        "description": "Remove a recurring release blocker while preserving required checks and rollback clarity.",
        "supported_signal_types": ["delivery_blocker"],
        "acceptance_checks": [
            {
                "check_key": "release_blocker_removed",
                "description": "Validation confirms the original release blocker no longer prevents promotion.",
                "check_type": "content_assertion",
                "owner_role": "tester",
                "success_criteria_markdown": "Delivery evidence shows the blocker is removed or explicitly automated away.",
                "validation_step_key": "test",
                "verification_type": "automated",
            },
            {
                "check_key": "rollback_path_documented",
                "description": "Review confirms the release path still has a safe rollback instruction.",
                "check_type": "manual_review",
                "owner_role": "reviewer",
                "success_criteria_markdown": "Review surface includes rollback guidance that matches the updated delivery path.",
                "validation_step_key": "review",
                "verification_type": "manual",
            },
        ],
    },
    "approval_automation": {
        "template_key": "approval_automation",
        "category": "process_quality",
        "display_name": "Approval Automation",
        "description": "Reduce repetitive manual approvals without losing escalation safety.",
        "supported_signal_types": ["manual_override"],
        "acceptance_checks": [
            {
                "check_key": "manual_override_reduced",
                "description": "Validation confirms the workflow removes or narrows the repeated manual touchpoint.",
                "check_type": "content_assertion",
                "owner_role": "tester",
                "success_criteria_markdown": "Validation evidence shows the same flow now executes with fewer manual approvals.",
                "validation_step_key": "test",
                "verification_type": "automated",
            },
            {
                "check_key": "escalation_policy_preserved",
                "description": "Review confirms high-risk escalation paths are still protected after automation.",
                "check_type": "manual_review",
                "owner_role": "reviewer",
                "success_criteria_markdown": "Reviewer confirms the automated path still preserves explicit escalation rules for risky cases.",
                "validation_step_key": "review",
                "verification_type": "manual",
            },
        ],
    },
    "onboarding_friction": {
        "template_key": "onboarding_friction",
        "category": "process_quality",
        "display_name": "Onboarding Friction",
        "description": "Standardize project onboarding gaps so a repo becomes automation-ready.",
        "supported_signal_types": [],
        "acceptance_checks": [
            {
                "check_key": "readiness_gap_closed",
                "description": "Validation confirms the targeted onboarding gap is closed.",
                "check_type": "content_assertion",
                "owner_role": "tester",
                "success_criteria_markdown": "Readiness evidence shows the project moved closer to automation-ready.",
                "validation_step_key": "test",
                "verification_type": "automated",
            },
            {
                "check_key": "onboarding_contract_documented",
                "description": "Review confirms onboarding docs and policy expectations are documented.",
                "check_type": "manual_review",
                "owner_role": "reviewer",
                "success_criteria_markdown": "Reviewer verifies the onboarding pack documents repo entrypoints, checks, and constraints.",
                "validation_step_key": "review",
                "verification_type": "manual",
            },
        ],
    },
    "docs_drift": {
        "template_key": "docs_drift",
        "category": "knowledge_quality",
        "display_name": "Docs Drift",
        "description": "Repair divergence between system behavior and operational documentation.",
        "supported_signal_types": [],
        "acceptance_checks": [
            {
                "check_key": "docs_alignment_verified",
                "description": "Review confirms the updated docs match the current implementation and workflow contract.",
                "check_type": "manual_review",
                "owner_role": "reviewer",
                "success_criteria_markdown": "Reviewer verifies docs are aligned with the delivered behavior and repo constraints.",
                "validation_step_key": "review",
                "verification_type": "manual",
            },
            {
                "check_key": "docs_examples_refreshed",
                "description": "Validation confirms examples or operator guidance reflect the new behavior.",
                "check_type": "content_assertion",
                "owner_role": "tester",
                "success_criteria_markdown": "Validation evidence shows examples and instructions are updated and usable.",
                "validation_step_key": "test",
                "verification_type": "automated",
            },
        ],
    },
}


_SIGNAL_TEMPLATE_MAP = {
    "bug_report": "defect_reduction",
    "delivery_blocker": "release_bottleneck",
    "manual_override": "approval_automation",
}


def list_optimization_requirement_templates() -> list[dict[str, Any]]:
    return [
        {
            "template_key": template["template_key"],
            "category": template["category"],
            "display_name": template["display_name"],
            "description": template["description"],
            "supported_signal_types": list(template.get("supported_signal_types") or []),
            "default_acceptance_checks": list(template.get("acceptance_checks") or []),
        }
        for template in _TEMPLATES.values()
    ]


def get_optimization_requirement_template(template_key: str) -> dict[str, Any]:
    template = _TEMPLATES.get(str(template_key))
    if template is None:
        raise ValueError("Optimization requirement template not found")
    return template


def template_key_for_signal(signal_type: str) -> str:
    return _SIGNAL_TEMPLATE_MAP.get(str(signal_type), "defect_reduction")


def _template_title(template: dict[str, Any], *, title: str, project_label: str) -> str:
    display_name = str(template.get("display_name") or "Optimization")
    return f"{display_name}: {project_label} - {title}".strip()


def _template_description_markdown(
    template: dict[str, Any],
    *,
    context_summary: str,
    evidence: list[dict[str, Any]],
    score_breakdown: dict[str, Any] | None,
) -> str:
    return (
        f"## Optimization Template\n\n"
        f"- Template: `{template['template_key']}`\n"
        f"- Category: `{template['category']}`\n"
        f"- Objective: {template['description']}\n\n"
        f"## Context\n\n{context_summary}\n\n"
        f"## Acceptance Focus\n\n"
        + "\n".join(
            f"- `{check['check_key']}`: {check['description']}"
            for check in template.get("acceptance_checks") or []
        )
        + (
            f"\n\n## Template Score Context\n\n```json\n{json.dumps(score_breakdown or {}, ensure_ascii=False, indent=2)}\n```"
            if score_breakdown else ""
        )
        + (
            f"\n\n## Evidence\n\n```json\n{json.dumps(evidence[:8], ensure_ascii=False, indent=2)}\n```"
            if evidence else ""
        )
    )


def build_template_instance(
    *,
    template_key: str,
    title: str,
    context_summary: str,
    target_project_path: str | None,
    priority: str,
    source: str,
    source_ref: str | None,
    evidence: list[dict[str, Any]] | None = None,
    score_breakdown: dict[str, Any] | None = None,
    template_payload_extra: dict[str, Any] | None = None,
    auto_start: bool = False,
) -> RequirementCreate:
    template = get_optimization_requirement_template(template_key)
    raw_project_label = str((template_payload_extra or {}).get("project_display_name") or "")
    project_label = (
        raw_project_label.rsplit("/", 1)[-1]
        if "/" in raw_project_label else raw_project_label
    ) or str(target_project_path or "Org Ops").rsplit("/", 1)[-1]
    requirement_title = _template_title(template, title=title, project_label=project_label)
    acceptance_checks = list(template.get("acceptance_checks") or [])
    template_payload = {
        "template_key": template["template_key"],
        "category": template["category"],
        "display_name": template["display_name"],
        "description": template["description"],
        "acceptance_checks": acceptance_checks,
        "score_breakdown": score_breakdown or {},
        **(template_payload_extra or {}),
    }
    return RequirementCreate(
        title=requirement_title,
        description_markdown=_template_description_markdown(
            template,
            context_summary=context_summary,
            evidence=evidence or [],
            score_breakdown=score_breakdown,
        ),
        priority=priority,
        source=source,
        source_ref=source_ref,
        target_project_path=target_project_path,
        auto_start=auto_start,
        template_key=template["template_key"],
        template_payload=template_payload,
        template_acceptance_checks=acceptance_checks,
    )
