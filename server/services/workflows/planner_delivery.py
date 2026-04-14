"""Delivery contract helpers for workflow planning."""

from __future__ import annotations

import re
from typing import Any

from server.database import RequirementRow

_RELEASE_MODE_RANK = {"disabled": 0, "manual": 1, "auto": 2}


def _slugify_branch_fragment(value: str) -> str:
    """Convert a requirement title fragment into a branch-safe slug."""

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "requirement"


def _merge_release_mode(project_policies: list[dict[str, Any]]) -> str:
    """Return the most restrictive merged release mode across project policies."""

    if not project_policies:
        return "manual"
    return min(
        (str(item.get("release_mode") or "manual") for item in project_policies),
        key=lambda mode: _RELEASE_MODE_RANK.get(mode, 1),
    )


def _build_delivery_contract(
    requirement: RequirementRow,
    target_path: str | None,
    project_policies: list[dict[str, Any]],
    execution_controls: dict[str, Any],
) -> dict[str, Any]:
    """Build the delivery contract attached to a planned requirement."""

    required_checks: list[str] = []
    for policy in project_policies:
        for check in policy.get("required_checks") or []:
            if check not in required_checks:
                required_checks.append(str(check))

    release_mode = _merge_release_mode(project_policies)
    requires_manual_approval = any(bool(policy.get("requires_manual_approval")) for policy in project_policies)
    capability_matrix = dict(execution_controls.get("capability_matrix") or {})
    interrupt_policy = dict(execution_controls.get("interrupt_policy") or {})
    branch_name = f"ops/req-{getattr(requirement, 'id', 'x')}-{_slugify_branch_fragment(requirement.title)[:40]}"
    base_branch = "main"
    root_target = target_path or (project_policies[0]["root_path"] if project_policies else None)

    rollback_hint = (
        f"If publish must be rolled back, revert the promoted change from `{base_branch}` and archive `{branch_name}`. "
        f"Until publish happens, keep review work isolated on `{branch_name}`."
    )
    if root_target:
        rollback_hint += f"\n\nPrimary repo: `{root_target}`"

    return {
        "branch_strategy": "requirement_branch",
        "branch_name": branch_name,
        "base_branch": base_branch,
        "commit_required": True,
        "push_required": True,
        "review_surface": "delivery_state_artifact",
        "release_mode": release_mode,
        "requires_manual_approval": requires_manual_approval,
        "required_checks": required_checks,
        "required_capabilities": ["git_write", "git_push", "publish"],
        "capability_matrix": capability_matrix,
        "interrupt_policy": interrupt_policy,
        "auto_publish_allowed": (
            release_mode == "auto"
            and not requires_manual_approval
            and not required_checks
            and bool(capability_matrix.get("git_push"))
            and bool(capability_matrix.get("publish"))
            and "publish" not in set(interrupt_policy.get("operator_confirmation_actions") or [])
        ),
        "managed_projects": [
            {
                "project_key": policy["project_key"],
                "display_name": policy["display_name"],
                "root_path": policy["root_path"],
                "release_mode": policy["release_mode"],
                "capability_matrix": policy.get("capability_matrix") or {},
                "interrupt_policy": policy.get("interrupt_policy") or {},
            }
            for policy in project_policies
        ],
        "rollback_hint_markdown": rollback_hint,
        "summary_markdown": (
            f"Ship through branch `{branch_name}`, commit the branch changes, push the branch for review, "
            f"validate before promotion, surface a review-ready bundle, "
            f"and only publish when release mode `{release_mode}` allows it. "
            f"Capability gate: git_push={'yes' if capability_matrix.get('git_push') else 'no'}, "
            f"publish={'yes' if capability_matrix.get('publish') else 'no'}."
        ),
    }


__all__ = ["_build_delivery_contract", "_merge_release_mode", "_slugify_branch_fragment"]
