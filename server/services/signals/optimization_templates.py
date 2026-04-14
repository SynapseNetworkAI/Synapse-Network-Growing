"""Template library for optimization requirements."""
from __future__ import annotations

from typing import Any

from server.schemas import RequirementCreate


def _manual_check(
    check_key: str,
    description: str,
    success_criteria_markdown: str,
    *,
    owner_role: str = "reviewer",
) -> dict[str, Any]:
    return {
        "check_key": check_key,
        "description": description,
        "check_type": "manual_review",
        "owner_role": owner_role,
        "success_criteria_markdown": success_criteria_markdown,
        "validation_step_key": "validate",
        "verification_type": "manual",
    }


def _automated_check(
    check_key: str,
    description: str,
    success_criteria_markdown: str,
    *,
    owner_role: str = "tester",
    check_type: str = "content_assertion",
) -> dict[str, Any]:
    return {
        "check_key": check_key,
        "description": description,
        "check_type": check_type,
        "owner_role": owner_role,
        "success_criteria_markdown": success_criteria_markdown,
        "validation_step_key": "validate",
        "verification_type": "automated",
    }


_TEMPLATES: dict[str, dict[str, Any]] = {
    "defect_reduction": {
        "template_key": "defect_reduction",
        "category": "code_quality",
        "display_name": "Defect Reduction",
        "description": "Convert repeated failures into a root-cause fix with regression coverage.",
        "supported_signal_types": ["bug_report"],
        "default_step_policy": "engineering_fix",
        "validation_mode": "single_gate",
        "objective_markdown": "Convert a repeated defect into a scoped fix with root-cause clarity and regression protection.",
        "acceptance_markdown": (
            "- Document the root cause and remediation scope.\n"
            "- Prove a regression guard or equivalent repeatable validation exists."
        ),
        "escalation_markdown": "Escalate if the bug spans multiple repos or requires a risky runtime rollback.",
        "acceptance_checks": [
            _manual_check(
                "root_cause_documented",
                "Review confirms the defect root cause and remediation scope are documented.",
                "Review artifact explains root cause, affected surface, and chosen remediation.",
            ),
            _automated_check(
                "regression_guard_added",
                "Validation confirms regression coverage was added for the repeated defect path.",
                "Automated validation proves the failing path is covered by a repeatable regression guard.",
            ),
        ],
    },
    "release_bottleneck": {
        "template_key": "release_bottleneck",
        "category": "release_safety",
        "display_name": "Release Bottleneck",
        "description": "Remove a recurring release blocker while preserving required checks and rollback clarity.",
        "supported_signal_types": ["delivery_blocker"],
        "default_step_policy": "delivery_fix",
        "validation_mode": "single_gate",
        "objective_markdown": "Remove a recurring release blocker while keeping rollback and delivery gates explicit.",
        "acceptance_markdown": (
            "- Show the original blocker is removed or automated away.\n"
            "- Preserve rollback instructions and release visibility."
        ),
        "escalation_markdown": "Escalate if release mode is disabled or publish would bypass required checks.",
        "acceptance_checks": [
            _automated_check(
                "release_blocker_removed",
                "Validation confirms the original release blocker no longer prevents promotion.",
                "Delivery evidence shows the blocker is removed or explicitly automated away.",
            ),
            _manual_check(
                "rollback_path_documented",
                "Review confirms the release path still has a safe rollback instruction.",
                "Review surface includes rollback guidance that matches the updated delivery path.",
            ),
        ],
    },
    "approval_automation": {
        "template_key": "approval_automation",
        "category": "process_quality",
        "display_name": "Approval Automation",
        "description": "Reduce repetitive manual approvals without losing escalation safety.",
        "supported_signal_types": ["manual_override"],
        "default_step_policy": "workflow_automation",
        "validation_mode": "single_gate",
        "objective_markdown": "Reduce repetitive manual approval work without weakening high-risk escalation paths.",
        "acceptance_markdown": (
            "- Show the repeated manual touchpoint is removed or narrowed.\n"
            "- Preserve explicit escalation for risky cases."
        ),
        "escalation_markdown": "Escalate if automation changes would bypass expensive branches, publish gates, or high-risk approval review.",
        "acceptance_checks": [
            _automated_check(
                "manual_override_reduced",
                "Validation confirms the workflow removes or narrows the repeated manual touchpoint.",
                "Validation evidence shows the same flow now executes with fewer manual approvals.",
            ),
            _manual_check(
                "escalation_policy_preserved",
                "Review confirms high-risk escalation paths are still protected after automation.",
                "Reviewer confirms the automated path still preserves explicit escalation rules for risky cases.",
            ),
        ],
    },
    "incident_recovery": {
        "template_key": "incident_recovery",
        "category": "runtime_reliability",
        "display_name": "Incident Recovery",
        "description": "Stabilize a workflow/runtime incident and add recovery guards so the same failure path can close cleanly next time.",
        "supported_signal_types": ["workflow_incident"],
        "default_step_policy": "runtime_fix",
        "validation_mode": "single_gate",
        "objective_markdown": "Stabilize a runtime incident and prove the recovery path now closes safely.",
        "acceptance_markdown": (
            "- Document the incident root cause and recovery choice.\n"
            "- Prove the same incident path is now bounded, recoverable, or explicitly escalated."
        ),
        "escalation_markdown": "Escalate if the recovery path spans multiple projects or requires manual operator intervention to stay safe.",
        "acceptance_checks": [
            _manual_check(
                "incident_root_cause_documented",
                "Review confirms the incident root cause and recovery path are documented.",
                "Review artifact explains why the incident happened, which guardrail failed, and what recovery path was chosen.",
            ),
            _automated_check(
                "recovery_guard_verified",
                "Validation confirms the same runtime/recovery path now closes without repeating the incident.",
                "Validation evidence proves the incident path is now recoverable, bounded, or explicitly escalated.",
            ),
        ],
    },
    "onboarding_friction": {
        "template_key": "onboarding_friction",
        "category": "process_quality",
        "display_name": "Onboarding Friction",
        "description": "Standardize project onboarding gaps so a repo becomes automation-ready.",
        "supported_signal_types": [],
        "default_step_policy": "docs_or_setup",
        "validation_mode": "single_gate",
        "objective_markdown": "Close readiness gaps so the repository is easier to automate safely.",
        "acceptance_markdown": (
            "- Show the targeted readiness gap is closed.\n"
            "- Keep onboarding expectations and constraints documented."
        ),
        "escalation_markdown": "Escalate if the gap requires secrets, production access, or cross-team coordination.",
        "acceptance_checks": [
            _automated_check(
                "readiness_gap_closed",
                "Validation confirms the targeted onboarding gap is closed.",
                "Readiness evidence shows the project moved closer to automation-ready.",
            ),
            _manual_check(
                "onboarding_contract_documented",
                "Review confirms onboarding docs and policy expectations are documented.",
                "Reviewer verifies the onboarding pack documents repo entrypoints, checks, and constraints.",
            ),
        ],
    },
    "docs_drift": {
        "template_key": "docs_drift",
        "category": "knowledge_quality",
        "display_name": "Docs Drift",
        "description": "Repair divergence between system behavior and operational documentation.",
        "supported_signal_types": [],
        "default_step_policy": "docs_fix",
        "validation_mode": "single_gate",
        "objective_markdown": "Repair divergence between current behavior and operational documentation.",
        "acceptance_markdown": (
            "- Confirm docs match current implementation and workflow contract.\n"
            "- Refresh examples and operator guidance so they are usable."
        ),
        "escalation_markdown": "Escalate if behavior is still ambiguous or undocumented after the docs update.",
        "acceptance_checks": [
            _manual_check(
                "docs_alignment_verified",
                "Review confirms the updated docs match the current implementation and workflow contract.",
                "Reviewer verifies docs are aligned with the delivered behavior and repo constraints.",
            ),
            _automated_check(
                "docs_examples_refreshed",
                "Validation confirms examples or operator guidance reflect the new behavior.",
                "Validation evidence shows examples and instructions are updated and usable.",
            ),
        ],
    },
}


_SIGNAL_TEMPLATE_MAP = {
    "bug_report": "defect_reduction",
    "delivery_blocker": "release_bottleneck",
    "manual_override": "approval_automation",
    "workflow_incident": "incident_recovery",
}


def list_optimization_requirement_templates() -> list[dict[str, Any]]:
    return [
        {
            "template_key": template["template_key"],
            "category": template["category"],
            "display_name": template["display_name"],
            "description": template["description"],
            "supported_signal_types": list(template.get("supported_signal_types") or []),
            "default_step_policy": str(template.get("default_step_policy") or "engineering_fix"),
            "validation_mode": str(template.get("validation_mode") or "single_gate"),
            "objective_markdown": str(template.get("objective_markdown") or template.get("description") or ""),
            "acceptance_markdown": str(template.get("acceptance_markdown") or ""),
            "escalation_markdown": str(template.get("escalation_markdown") or ""),
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
    objective_markdown = str(template.get("objective_markdown") or template.get("description") or "").strip()
    acceptance_markdown = str(template.get("acceptance_markdown") or "").strip()
    escalation_markdown = str(template.get("escalation_markdown") or "").strip()
    evidence_lines = [
        f"- {str(item.get('summary') or item.get('message') or item.get('source_ref') or item)}"
        for item in (evidence or [])[:8]
        if str(item).strip()
    ]
    score_lines = [
        f"- {key}: {value}"
        for key, value in (score_breakdown or {}).items()
    ]
    return (
        f"## Optimization Template\n\n"
        f"- Template: `{template['template_key']}`\n"
        f"- Category: `{template['category']}`\n"
        f"- Objective: {objective_markdown}\n\n"
        f"## Context\n\n{context_summary}\n\n"
        f"## Acceptance Focus\n\n{acceptance_markdown or '- Validation proves the goal is met and escalation safety is preserved.'}"
        + (
            f"\n\n## Escalation Policy\n\n{escalation_markdown}"
            if escalation_markdown
            else ""
        )
        + (
            f"\n\n## Template Score Context\n\n" + "\n".join(score_lines)
            if score_lines else ""
        )
        + (
            f"\n\n## Evidence\n\n" + "\n".join(evidence_lines)
            if evidence_lines else ""
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
        "default_step_policy": template.get("default_step_policy"),
        "validation_mode": template.get("validation_mode"),
        "objective_markdown": template.get("objective_markdown"),
        "acceptance_markdown": template.get("acceptance_markdown"),
        "escalation_markdown": template.get("escalation_markdown"),
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
