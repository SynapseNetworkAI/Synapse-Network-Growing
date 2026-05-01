"""Project policy defaults, constants, and normalization helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CAPABILITY_KEYS = (
    "shell_access",
    "git_read",
    "git_write",
    "git_push",
    "network_access",
    "publish",
)
INTERRUPT_CONFIRM_ACTIONS = ("shell_access", "git_write", "git_push", "network_access", "publish")
INTERRUPT_PAUSE_EVENTS = (
    "capability_denied",
    "policy_violation",
    "missing_required_checks",
    "session_resume_failure",
    "operator_confirmation_required",
)
INTERRUPT_ABORT_EVENTS = ("forbidden_write", "publish_without_gate")


def default_capability_matrix(*, release_mode: str = "manual") -> dict[str, bool]:
    """Return the baseline capability matrix for a release mode."""

    auto_release = release_mode == "auto"
    return {
        "shell_access": True,
        "git_read": True,
        "git_write": True,
        "git_push": auto_release,
        "network_access": False,
        "publish": auto_release,
    }


def default_interrupt_policy() -> dict[str, list[str]]:
    """Return the default interrupt policy for project-scoped execution."""

    return {
        "operator_confirmation_actions": ["git_push", "publish"],
        "auto_pause_on_events": ["capability_denied", "policy_violation", "missing_required_checks", "session_resume_failure"],
        "auto_abort_on_events": ["forbidden_write", "publish_without_gate"],
    }


def normalize_github_repo_full_name(value: str | None) -> str | None:
    """Normalize GitHub URL/SSH/slug input to owner/repo."""

    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.removeprefix("git+")
    patterns = (
        r"^git@github\.com:(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?$",
        r"^https?://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$",
        r"^github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$",
        r"^(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.match(pattern, raw)
        if not match:
            continue
        owner = match.group("owner").strip()
        repo = match.group("repo").strip().removesuffix(".git")
        if owner and repo:
            return f"{owner}/{repo}"
    return raw.removesuffix(".git")


DEFAULT_PROJECT_POLICIES: list[dict[str, Any]] = [
    {
        "project_key": "synapse-network-growing",
        "display_name": "Synapse-Network-Growing",
        "root_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
        "allowed_write_globs": ["**"],
        "forbidden_globs": [".git/**", "node_modules/**", ".venv/**", ".agent-browser/**", "runtime/**"],
        "required_checks": [
            "/Users/cliff/workspace/agent/.venv/bin/python -m pytest -q",
            "cd dashboard && npm test",
            "cd dashboard && npm run build",
        ],
        "release_mode": "manual",
        "requires_manual_approval": True,
        "autonomy_mode": "execute_autonomously",
        "allow_rebalance": True,
        "allow_preemption": True,
        "capability_matrix": {
            **default_capability_matrix(release_mode="manual"),
            "git_push": True,
            "network_access": True,
        },
        "interrupt_policy": default_interrupt_policy(),
        "scheduler_weight": 1.2,
        "max_parallel_requirements": 1,
        "portfolio_budget_points": 140,
        "repo_full_name": "SynapseNetworkAI/Synapse-Network-Growing",
        "notes": "Control plane repo. Allow code and docs updates, but keep release decisions manual.",
    },
    {
        "project_key": "synapse-network",
        "display_name": "Synapse-Network",
        "root_path": "/Users/cliff/workspace/agent/Synapse-Network",
        "allowed_write_globs": ["**"],
        "forbidden_globs": [".git/**", "node_modules/**", ".venv/**", "services/**/dist/**", "services/**/build/**"],
        "required_checks": ["npm test", "pytest"],
        "release_mode": "manual",
        "requires_manual_approval": True,
        "autonomy_mode": "execute_with_approval",
        "allow_rebalance": True,
        "allow_preemption": False,
        "capability_matrix": default_capability_matrix(release_mode="manual"),
        "interrupt_policy": default_interrupt_policy(),
        "scheduler_weight": 1.4,
        "max_parallel_requirements": 1,
        "portfolio_budget_points": 130,
        "repo_full_name": "SynapseNetworkAI/Synapse-Network",
        "deploy_repo_full_name": "SynapseNetworkAI/Synapse-Network",
        "deploy_strategy": "github_actions_gcp_cloudrun",
        "deploy_trigger_enabled": True,
        "staging_host_label": "cloud-run-staging",
        "production_host_label": "cloud-run-production",
        "staging_workflow_file": "deploy-staging.yml",
        "production_workflow_file": "deploy-production.yml",
        "notes": "Primary product repo. Workflow human gate required before publish or merge.",
    },
    {
        "project_key": "synapse-network-provider",
        "display_name": "Synapse-Network-Provider",
        "root_path": "/Users/cliff/workspace/agent/Synapse-Network-Provider",
        "allowed_write_globs": ["**"],
        "forbidden_globs": [".git/**", "node_modules/**", ".venv/**", "runtime/**"],
        "required_checks": ["pytest"],
        "release_mode": "manual",
        "requires_manual_approval": True,
        "autonomy_mode": "recommend",
        "allow_rebalance": True,
        "allow_preemption": False,
        "capability_matrix": default_capability_matrix(release_mode="manual"),
        "interrupt_policy": default_interrupt_policy(),
        "scheduler_weight": 1.0,
        "max_parallel_requirements": 1,
        "portfolio_budget_points": 100,
        "repo_full_name": "SynapseNetworkAI/Synapse-Network-Provider",
        "deploy_repo_full_name": "SynapseNetworkAI/Synapse-Network-Provider",
        "deploy_strategy": "github_actions_wif_cloudrun",
        "deploy_trigger_enabled": True,
        "staging_host_label": "cloud-run-staging",
        "production_host_label": "prod-vm",
        "staging_workflow_file": "deploy-staging.yml",
        "production_workflow_file": "deploy-production.yml",
        "notes": "Provider runtime repo. Keep operator in the loop for releases.",
    },
    {
        "project_key": "synapse-network-sdk",
        "display_name": "Synapse-Network-Sdk",
        "root_path": "/Users/cliff/workspace/agent/Synapse-Network-Sdk",
        "allowed_write_globs": ["**"],
        "forbidden_globs": [".git/**", "node_modules/**", ".venv/**", "python/dist/**", "typescript/dist/**"],
        "required_checks": ["cd python && pytest", "cd typescript && npm test"],
        "release_mode": "manual",
        "requires_manual_approval": True,
        "autonomy_mode": "execute_autonomously",
        "allow_rebalance": True,
        "allow_preemption": True,
        "capability_matrix": default_capability_matrix(release_mode="manual"),
        "interrupt_policy": default_interrupt_policy(),
        "scheduler_weight": 1.1,
        "max_parallel_requirements": 1,
        "portfolio_budget_points": 95,
        "repo_full_name": "SynapseNetworkAI/Synapse-Network-Sdk",
        "notes": "SDK repo. Require package-level verification before release.",
    },
    {
        "project_key": "synapse-network-mcp-server",
        "display_name": "Synapse-Network-MCP-Server",
        "root_path": "/Users/cliff/workspace/agent/Synapse-Network-MCP-Server",
        "allowed_write_globs": ["**"],
        "forbidden_globs": [".git/**", "node_modules/**", "dist/**", "coverage/**"],
        "required_checks": ["npm run verify:mcp"],
        "release_mode": "manual",
        "requires_manual_approval": True,
        "autonomy_mode": "execute_autonomously",
        "allow_rebalance": True,
        "allow_preemption": False,
        "capability_matrix": default_capability_matrix(release_mode="manual"),
        "interrupt_policy": default_interrupt_policy(),
        "scheduler_weight": 0.95,
        "max_parallel_requirements": 1,
        "portfolio_budget_points": 90,
        "repo_full_name": "SynapseNetworkAI/Synapse-Network-MCP-Server",
        "deploy_strategy": "disabled",
        "deploy_trigger_enabled": False,
        "notes": "MCP server repo. Keep code verification active; staging release shortcut is disabled in v1.",
    },
    {
        "project_key": "agents-memory",
        "display_name": "Agents-Memory",
        "root_path": "/Users/cliff/workspace/agent/Agents-Memory",
        "allowed_write_globs": ["**"],
        "forbidden_globs": [".git/**", "node_modules/**", ".venv/**"],
        "required_checks": ["python -m pytest -q"],
        "release_mode": "manual",
        "requires_manual_approval": True,
        "autonomy_mode": "recommend",
        "allow_rebalance": True,
        "allow_preemption": False,
        "capability_matrix": default_capability_matrix(release_mode="manual"),
        "interrupt_policy": default_interrupt_policy(),
        "scheduler_weight": 0.9,
        "max_parallel_requirements": 1,
        "portfolio_budget_points": 80,
        "repo_full_name": "haochencheng/Agents-Memory",
        "notes": "Memory and standards repo. Keep profile and standards changes auditable.",
    },
]

LEGACY_VALIDATION_PROJECT_KEYS = {
    "sng-validation",
    "sng-validation-next",
    "sng-validation-autochain",
    "sng-validation-autochain-2",
    "sng-validation-autochain-3",
}

LEGACY_VALIDATION_ROOT_PREFIXES = (
    "/private/tmp/sng-delivery-validation",
    "/private/tmp/sng-delivery-validation-next",
    "/private/tmp/sng-delivery-autochain",
    "/private/tmp/sng-delivery-autochain-2",
    "/private/tmp/sng-delivery-autochain-3",
)


def _json_dump_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def _json_dump_dict(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_load_list(raw: str | None, fallback: list[str] | None = None) -> list[str]:
    if not raw:
        return list(fallback or [])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return list(fallback or [])
    if not isinstance(data, list):
        return list(fallback or [])
    return [str(item).strip() for item in data if str(item).strip()]


def _json_load_dict(raw: str | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not raw:
        return dict(fallback or {})
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return dict(fallback or {})
    if not isinstance(data, dict):
        return dict(fallback or {})
    return dict(data)


def _normalize_globs(values: list[str] | None, *, default: list[str]) -> list[str]:
    normalized = [str(value).strip() for value in (values or []) if str(value).strip()]
    return normalized or list(default)


def _normalize_root_path(value: str) -> str:
    return str(Path(value.strip()).resolve()) if value.strip() else ""


def _is_legacy_validation_policy(project_key: str | None, root_path: str | None) -> bool:
    key = str(project_key or "").strip().lower()
    root = _normalize_root_path(str(root_path or "")) if root_path else ""
    if key in LEGACY_VALIDATION_PROJECT_KEYS:
        return True
    return any(root.startswith(prefix) for prefix in LEGACY_VALIDATION_ROOT_PREFIXES)


def _normalize_capability_matrix(value: dict[str, Any] | None, *, release_mode: str = "manual") -> dict[str, bool]:
    base = default_capability_matrix(release_mode=release_mode)
    raw = value or {}
    return {key: bool(raw.get(key, base[key])) for key in CAPABILITY_KEYS}


def _normalize_interrupt_policy(value: dict[str, Any] | None) -> dict[str, list[str]]:
    base = default_interrupt_policy()
    raw = value or {}

    def _normalize_list(key: str, allowed: tuple[str, ...], fallback: list[str]) -> list[str]:
        items = raw.get(key, fallback)
        if not isinstance(items, list):
            items = fallback
        result: list[str] = []
        for item in items:
            text = str(item).strip()
            if text and text in allowed and text not in result:
                result.append(text)
        return result

    return {
        "operator_confirmation_actions": _normalize_list(
            "operator_confirmation_actions",
            INTERRUPT_CONFIRM_ACTIONS,
            list(base["operator_confirmation_actions"]),
        ),
        "auto_pause_on_events": _normalize_list(
            "auto_pause_on_events",
            INTERRUPT_PAUSE_EVENTS,
            list(base["auto_pause_on_events"]),
        ),
        "auto_abort_on_events": _normalize_list(
            "auto_abort_on_events",
            INTERRUPT_ABORT_EVENTS,
            list(base["auto_abort_on_events"]),
        ),
    }


def _split_target_paths(target_project_path: str | None) -> list[str]:
    """Split a multi-path target field into normalized absolute paths."""

    if not target_project_path:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for raw in target_project_path.splitlines():
        candidate = _normalize_root_path(raw) if raw.strip() else ""
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


__all__ = [
    "CAPABILITY_KEYS",
    "INTERRUPT_CONFIRM_ACTIONS",
    "INTERRUPT_PAUSE_EVENTS",
    "INTERRUPT_ABORT_EVENTS",
    "DEFAULT_PROJECT_POLICIES",
    "LEGACY_VALIDATION_PROJECT_KEYS",
    "LEGACY_VALIDATION_ROOT_PREFIXES",
    "default_capability_matrix",
    "default_interrupt_policy",
    "_json_dump_list",
    "_json_dump_dict",
    "_json_load_list",
    "_json_load_dict",
    "_normalize_globs",
    "_normalize_root_path",
    "_is_legacy_validation_policy",
    "_normalize_capability_matrix",
    "_normalize_interrupt_policy",
    "_split_target_paths",
]
