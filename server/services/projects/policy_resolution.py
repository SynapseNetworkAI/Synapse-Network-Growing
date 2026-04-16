"""Project policy resolution, scope application, and capability aggregation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from server.database import ProjectPolicyRow
from server.services.projects.policy_defaults import (
    CAPABILITY_KEYS,
    _normalize_capability_matrix,
    _normalize_interrupt_policy,
    _normalize_root_path,
    _split_target_paths,
    default_capability_matrix,
    default_interrupt_policy,
)
from server.services.projects.policy_registry import ensure_default_project_policies, project_policy_to_dict


def aggregate_execution_controls(project_policies: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the effective capability and interrupt policy across projects."""

    capability_matrix = {key: True for key in CAPABILITY_KEYS}
    interrupt_policy = default_interrupt_policy()
    policy_summaries: list[dict[str, Any]] = []
    if not project_policies:
        return {
            "capability_matrix": default_capability_matrix(),
            "interrupt_policy": interrupt_policy,
            "policy_summaries": policy_summaries,
        }
    for policy in project_policies:
        normalized_capabilities = _normalize_capability_matrix(
            policy.get("capability_matrix") if isinstance(policy, dict) else None,
            release_mode=str(policy.get("release_mode") or "manual"),
        )
        normalized_interrupt = _normalize_interrupt_policy(
            policy.get("interrupt_policy") if isinstance(policy, dict) else None
        )
        capability_matrix = {
            key: bool(capability_matrix.get(key, True) and normalized_capabilities.get(key, False))
            for key in CAPABILITY_KEYS
        }
        for field in ("operator_confirmation_actions", "auto_pause_on_events", "auto_abort_on_events"):
            merged: list[str] = []
            for item in list(interrupt_policy.get(field) or []) + list(normalized_interrupt.get(field) or []):
                text = str(item).strip()
                if text and text not in merged:
                    merged.append(text)
            interrupt_policy[field] = merged
        policy_summaries.append(
            {
                "project_key": str(policy.get("project_key") or ""),
                "display_name": str(policy.get("display_name") or ""),
                "capability_matrix": normalized_capabilities,
                "interrupt_policy": normalized_interrupt,
            }
        )
    return {
        "capability_matrix": capability_matrix,
        "interrupt_policy": interrupt_policy,
        "policy_summaries": policy_summaries,
    }


def _match_policy_for_path(db: Session, target_path: str) -> ProjectPolicyRow | None:
    ensure_default_project_policies(db)
    normalized = _normalize_root_path(target_path)
    best: ProjectPolicyRow | None = None
    for row in db.query(ProjectPolicyRow).filter(ProjectPolicyRow.status != "deleted").all():
        root = _normalize_root_path(str(row.root_path))
        try:
            Path(normalized).relative_to(root)
        except ValueError:
            continue
        if best is None or len(root) > len(str(best.root_path)):
            best = row
    return best


def resolve_project_policies_for_target(
    db: Session,
    target_project_path: str | None,
    *,
    require_active: bool = False,
) -> list[ProjectPolicyRow]:
    """Resolve all matching project policies for a multi-root target path field."""

    paths = _split_target_paths(target_project_path)
    policies: list[ProjectPolicyRow] = []
    for path in paths:
        row = _match_policy_for_path(db, path)
        if row is None:
            if require_active:
                raise ValueError(f"No project policy registered for target path: {path}")
            continue
        if require_active and str(row.status) != "active":
            raise ValueError(f"Project policy is not active for target path: {path}")
        if all(existing.id != row.id for existing in policies):
            policies.append(row)
    return policies


def _absolute_globs(root_path: str, globs: list[str], *, fallback: str | None = None) -> list[str]:
    result: list[str] = []
    for item in globs:
        normalized = item.strip()
        if not normalized:
            continue
        if normalized.startswith("/"):
            result.append(normalized)
        elif normalized == "**" and fallback:
            result.append(fallback)
        else:
            result.append(f"{root_path}/{normalized}")
    return result


def apply_project_policies_to_scope(
    db: Session,
    file_scope: dict[str, Any],
    target_project_path: str | None,
    *,
    write: bool,
) -> dict[str, Any]:
    """Overlay project policy constraints onto a planner-generated file scope."""

    policies = resolve_project_policies_for_target(db, target_project_path, require_active=False)
    if not policies:
        return file_scope

    scope = {
        "allowed_read_globs": list(file_scope.get("allowed_read_globs") or []),
        "allowed_write_globs": list(file_scope.get("allowed_write_globs") or []),
        "blocked_globs": list(file_scope.get("blocked_globs") or []),
    }
    for policy in policies:
        data = project_policy_to_dict(policy)
        root_path = str(data["root_path"])
        read_glob = f"{root_path}/**"
        if read_glob not in scope["allowed_read_globs"]:
            scope["allowed_read_globs"].append(read_glob)
        if write:
            for pattern in _absolute_globs(root_path, list(data["allowed_write_globs"]), fallback=read_glob):
                if pattern not in scope["allowed_write_globs"]:
                    scope["allowed_write_globs"].append(pattern)
        for blocked in _absolute_globs(root_path, list(data["forbidden_globs"])):
            if blocked not in scope["blocked_globs"]:
                scope["blocked_globs"].append(blocked)
    return scope


def project_policy_summary_markdown(db: Session, target_project_path: str | None = None) -> str:
    """Render matching project policies as a concise Markdown block."""

    policies = resolve_project_policies_for_target(db, target_project_path, require_active=False)
    if not policies:
        return ""

    lines = ["## Project Policies"]
    for policy in policies:
        data = project_policy_to_dict(policy)
        approval_preference = "manual_review_preferred" if data["requires_manual_approval"] else "agent_first_preferred"
        lines.append(
            f"- **{data['display_name']}** (`{data['root_path']}`): status={data['status']}, "
            f"release_mode={data['release_mode']}, approval_preference={approval_preference}"
        )
        if data["required_checks"]:
            lines.append(f"  Required checks: {', '.join(data['required_checks'])}")
        if data["allowed_write_globs"]:
            lines.append(f"  Allowed write globs: {', '.join(data['allowed_write_globs'])}")
        if data["forbidden_globs"]:
            lines.append(f"  Forbidden globs: {', '.join(data['forbidden_globs'])}")
        capability_matrix = data.get("capability_matrix") or {}
        capability_summary = ", ".join(
            f"{key}={'yes' if capability_matrix.get(key) else 'no'}"
            for key in CAPABILITY_KEYS
        )
        lines.append(f"  Capability matrix: {capability_summary}")
        interrupt_policy = data.get("interrupt_policy") or {}
        confirmation = ", ".join(interrupt_policy.get("operator_confirmation_actions") or []) or "none"
        pause_events = ", ".join(interrupt_policy.get("auto_pause_on_events") or []) or "none"
        abort_events = ", ".join(interrupt_policy.get("auto_abort_on_events") or []) or "none"
        lines.append(f"  Interrupt policy: confirm={confirmation}; pause={pause_events}; abort={abort_events}")
    return "\n".join(lines)


__all__ = [
    "aggregate_execution_controls",
    "resolve_project_policies_for_target",
    "apply_project_policies_to_scope",
    "project_policy_summary_markdown",
]
