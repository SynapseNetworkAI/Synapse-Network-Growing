"""Execution profile helpers for workflow planning."""

from __future__ import annotations

from typing import Any

_TIER_BUDGETS: dict[str, dict[str, int]] = {
    "mini": {
        "max_input_tokens": 6000,
        "max_output_tokens": 1500,
        "max_attempts": 2,
        "max_runtime_seconds": 600,
    },
    "standard": {
        "max_input_tokens": 14000,
        "max_output_tokens": 4000,
        "max_attempts": 3,
        "max_runtime_seconds": 1800,
    },
    "max": {
        "max_input_tokens": 24000,
        "max_output_tokens": 8000,
        "max_attempts": 4,
        "max_runtime_seconds": 3600,
    },
}


def _default_budget_cap(tier: str) -> dict[str, int]:
    """Return the default budget cap for a complexity tier."""

    return dict(_TIER_BUDGETS.get(tier, _TIER_BUDGETS["standard"]))


def _normalize_complexity_tier(value: str | None) -> str:
    """Normalize planner complexity tiers to the supported set."""

    normalized = str(value or "").strip().lower()
    if normalized in {"mini", "standard", "max"}:
        return normalized
    return ""


def _default_complexity_tier(*, step_type: str, scope: str = "", target_paths: list[str] | None = None) -> str:
    """Choose a default complexity tier from the step type, scope, and targets."""

    target_paths = target_paths or []
    if step_type == "closeout":
        return "mini"
    if step_type in {"implementation", "bugfix", "validate"}:
        if len(target_paths) > 1 and step_type in {"implementation", "bugfix", "validate"}:
            return "max"
        if scope == "docs" and len(target_paths) <= 1:
            return "mini"
        return "standard"
    if step_type == "research":
        return "mini" if len(target_paths) <= 1 else "standard"
    return "standard"


def _default_escalation_rule(tier: str, *, allow_escalation: bool) -> dict[str, Any]:
    """Return the default escalation contract for a planner tier."""

    if not allow_escalation:
        return {
            "next_tier": "stay",
            "when": [],
            "max_escalations": 0,
        }
    next_tier = "standard" if tier == "mini" else "max"
    return {
        "next_tier": next_tier,
        "when": [
            "step_failed_twice",
            "changed_files_over_threshold",
            "multi_project_change_detected",
            "validation_blocker",
        ],
        "changed_files_threshold": 8,
        "max_escalations": 1,
    }


def _build_execution_profile(
    *,
    step_type: str,
    scope: str = "",
    target_paths: list[str] | None = None,
    complexity_tier: str | None = None,
    budget_cap: dict[str, Any] | None = None,
    allow_escalation: bool | None = None,
    escalation_rule: dict[str, Any] | None = None,
    expected_outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the execution profile attached to a planner step."""

    tier = _normalize_complexity_tier(complexity_tier) or _default_complexity_tier(
        step_type=step_type,
        scope=scope,
        target_paths=target_paths,
    )
    escalation_allowed = True if allow_escalation is None else bool(allow_escalation)
    if tier == "max" and allow_escalation is None:
        escalation_allowed = False
    return {
        "complexity_tier": tier,
        "budget_cap": dict(budget_cap or _default_budget_cap(tier)),
        "allow_escalation": escalation_allowed,
        "escalation_rule": dict(escalation_rule or _default_escalation_rule(tier, allow_escalation=escalation_allowed)),
        "expected_outputs": list(expected_outputs or []),
    }


__all__ = [
    "_build_execution_profile",
    "_default_budget_cap",
    "_default_complexity_tier",
    "_default_escalation_rule",
    "_normalize_complexity_tier",
]
