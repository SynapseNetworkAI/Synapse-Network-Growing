"""Project policy registry and enforcement helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from server.database import ProjectOnboardingRow, ProjectPolicyRow, RequirementRow

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
    return {
        "operator_confirmation_actions": ["git_push", "publish"],
        "auto_pause_on_events": ["capability_denied", "policy_violation", "missing_required_checks", "session_resume_failure"],
        "auto_abort_on_events": ["forbidden_write", "publish_without_gate"],
    }


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
            "network_access": True,
        },
        "interrupt_policy": default_interrupt_policy(),
        "scheduler_weight": 1.2,
        "max_parallel_requirements": 1,
        "portfolio_budget_points": 140,
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
        "deploy_repo_full_name": "cliff-personal/Synapse-Network",
        "deploy_strategy": "github_actions_ssh",
        "deploy_trigger_enabled": True,
        "staging_host_label": "staging-vm",
        "production_host_label": "prod-vm",
        "staging_workflow_file": "deploy-staging.yml",
        "production_workflow_file": "deploy-production.yml",
        "notes": "Primary product repo. Human approval required before publish or merge.",
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
        "deploy_repo_full_name": "cliff-personal/Synapse-Network-Provider",
        "deploy_strategy": "github_actions_ssh",
        "deploy_trigger_enabled": True,
        "staging_host_label": "staging-vm",
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
        "notes": "SDK repo. Require package-level verification before release.",
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
        "notes": "Memory and standards repo. Keep profile and standards changes auditable.",
    },
    {
        "project_key": "spec2flow",
        "display_name": "Spec2Flow",
        "root_path": "/Users/cliff/workspace/agent/Spec2Flow",
        "allowed_write_globs": ["**"],
        "forbidden_globs": [".git/**", "node_modules/**", ".venv/**", "packages/**/dist/**"],
        "required_checks": ["npm run test:unit", "npm run typecheck"],
        "release_mode": "manual",
        "requires_manual_approval": True,
        "autonomy_mode": "execute_with_approval",
        "allow_rebalance": True,
        "allow_preemption": False,
        "capability_matrix": default_capability_matrix(release_mode="manual"),
        "interrupt_policy": default_interrupt_policy(),
        "scheduler_weight": 1.0,
        "max_parallel_requirements": 1,
        "portfolio_budget_points": 90,
        "notes": "Workflow orchestrator repo. Changes should stay reviewable and reproducible.",
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


def aggregate_execution_controls(project_policies: list[dict[str, Any]]) -> dict[str, Any]:
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


def ensure_default_project_policies(db: Session) -> None:
    legacy_rows = (
        db.query(ProjectPolicyRow)
        .all()
    )
    legacy_changed = False
    for row in legacy_rows:
        if _is_legacy_validation_policy(getattr(row, "project_key", None), getattr(row, "root_path", None)):
            db.delete(row)
            legacy_changed = True
    if legacy_changed:
        db.flush()

    rows = db.execute(text("SELECT project_key, root_path FROM project_policies")).all()
    existing = {str(project_key) for project_key, _ in rows if project_key}
    existing_roots = {
        _normalize_root_path(str(root_path))
        for _, root_path in rows
        if root_path
    }
    changed = False
    for policy in DEFAULT_PROJECT_POLICIES:
        normalized_root = _normalize_root_path(policy["root_path"])
        if policy["project_key"] in existing or normalized_root in existing_roots:
            continue
        db.add(
            ProjectPolicyRow(
                project_key=policy["project_key"],
                display_name=policy["display_name"],
                root_path=normalized_root,
                status="active",
                allowed_write_globs_json=_json_dump_list(policy["allowed_write_globs"]),
                forbidden_globs_json=_json_dump_list(policy["forbidden_globs"]),
                required_checks_json=_json_dump_list(policy["required_checks"]),
                release_mode=policy["release_mode"],
                requires_manual_approval=policy["requires_manual_approval"],
                autonomy_mode=str(policy.get("autonomy_mode") or "recommend"),
                allow_rebalance=bool(policy.get("allow_rebalance", True)),
                allow_preemption=bool(policy.get("allow_preemption", False)),
                capability_matrix_json=_json_dump_dict(
                    _normalize_capability_matrix(policy.get("capability_matrix"), release_mode=str(policy.get("release_mode") or "manual"))
                ),
                interrupt_policy_json=_json_dump_dict(_normalize_interrupt_policy(policy.get("interrupt_policy"))),
                scheduler_weight=float(policy.get("scheduler_weight") or 1.0),
                max_parallel_requirements=int(policy.get("max_parallel_requirements") or 1),
                portfolio_budget_points=max(20, int(policy.get("portfolio_budget_points") or 100)),
                deploy_repo_full_name=str(policy.get("deploy_repo_full_name") or "").strip() or None,
                deploy_strategy=str(policy.get("deploy_strategy") or "github_actions_ssh").strip() or "github_actions_ssh",
                deploy_trigger_enabled=bool(policy.get("deploy_trigger_enabled", False)),
                staging_host_label=str(policy.get("staging_host_label") or "").strip() or None,
                production_host_label=str(policy.get("production_host_label") or "").strip() or None,
                staging_workflow_file=str(policy.get("staging_workflow_file") or "deploy-staging.yml").strip() or "deploy-staging.yml",
                production_workflow_file=str(policy.get("production_workflow_file") or "deploy-production.yml").strip() or "deploy-production.yml",
                notes=policy["notes"],
            )
        )
        changed = True
    if changed:
        db.commit()


def _visible_policy_query(db: Session):
    return db.query(ProjectPolicyRow).filter(ProjectPolicyRow.status != "deleted")


def project_policy_to_dict(row: ProjectPolicyRow) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "project_key": str(row.project_key),
        "display_name": str(row.display_name),
        "root_path": str(row.root_path),
        "status": str(row.status),
        "allowed_write_globs": _json_load_list(row.allowed_write_globs_json, ["**"]),
        "forbidden_globs": _json_load_list(row.forbidden_globs_json, []),
        "required_checks": _json_load_list(row.required_checks_json, []),
        "release_mode": str(row.release_mode),
        "requires_manual_approval": bool(row.requires_manual_approval),
        "autonomy_mode": str(getattr(row, "autonomy_mode", None) or "recommend"),
        "allow_rebalance": bool(getattr(row, "allow_rebalance", True)),
        "allow_preemption": bool(getattr(row, "allow_preemption", False)),
        "capability_matrix": _normalize_capability_matrix(
            _json_load_dict(getattr(row, "capability_matrix_json", None), {}),
            release_mode=str(row.release_mode or "manual"),
        ),
        "interrupt_policy": _normalize_interrupt_policy(
            _json_load_dict(getattr(row, "interrupt_policy_json", None), {})
        ),
        "scheduler_weight": float(row.scheduler_weight or 1.0),
        "max_parallel_requirements": int(row.max_parallel_requirements or 1),
        "portfolio_budget_points": max(20, int(getattr(row, "portfolio_budget_points", 100) or 100)),
        "deploy_repo_full_name": str(getattr(row, "deploy_repo_full_name", "") or "").strip() or None,
        "deploy_strategy": str(getattr(row, "deploy_strategy", None) or "github_actions_ssh"),
        "deploy_trigger_enabled": bool(getattr(row, "deploy_trigger_enabled", False)),
        "staging_host_label": str(getattr(row, "staging_host_label", "") or "").strip() or None,
        "production_host_label": str(getattr(row, "production_host_label", "") or "").strip() or None,
        "staging_workflow_file": str(getattr(row, "staging_workflow_file", None) or "deploy-staging.yml"),
        "production_workflow_file": str(getattr(row, "production_workflow_file", None) or "deploy-production.yml"),
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_project_policies(db: Session) -> list[ProjectPolicyRow]:
    ensure_default_project_policies(db)
    return _visible_policy_query(db).order_by(ProjectPolicyRow.display_name.asc()).all()


def get_project_policy(db: Session, policy_id: int) -> ProjectPolicyRow | None:
    ensure_default_project_policies(db)
    return _visible_policy_query(db).filter(ProjectPolicyRow.id == policy_id).first()


def create_project_policy(
    db: Session,
    *,
    project_key: str,
    display_name: str,
    root_path: str,
    status: str,
    allowed_write_globs: list[str],
    forbidden_globs: list[str],
    required_checks: list[str],
    release_mode: str,
    requires_manual_approval: bool,
    autonomy_mode: str,
    allow_rebalance: bool,
    allow_preemption: bool,
    capability_matrix: dict[str, Any] | None,
    interrupt_policy: dict[str, Any] | None,
    scheduler_weight: float,
    max_parallel_requirements: int,
    portfolio_budget_points: int,
    deploy_repo_full_name: str | None,
    deploy_strategy: str,
    deploy_trigger_enabled: bool,
    staging_host_label: str | None,
    production_host_label: str | None,
    staging_workflow_file: str,
    production_workflow_file: str,
    notes: str | None,
) -> ProjectPolicyRow:
    ensure_default_project_policies(db)
    normalized_root = _normalize_root_path(root_path)
    existing = db.query(ProjectPolicyRow).filter(
        (ProjectPolicyRow.project_key == project_key) | (ProjectPolicyRow.root_path == normalized_root)
    ).first()
    if existing is not None:
        raise ValueError("Project policy already exists for this project key or root path.")
    row = ProjectPolicyRow(
        project_key=project_key.strip(),
        display_name=display_name.strip(),
        root_path=normalized_root,
        status=status,
        allowed_write_globs_json=_json_dump_list(_normalize_globs(allowed_write_globs, default=["**"])),
        forbidden_globs_json=_json_dump_list(_normalize_globs(forbidden_globs, default=[])),
        required_checks_json=_json_dump_list(_normalize_globs(required_checks, default=[])),
        release_mode=release_mode,
        requires_manual_approval=requires_manual_approval,
        autonomy_mode=(autonomy_mode or "recommend").strip() or "recommend",
        allow_rebalance=bool(allow_rebalance),
        allow_preemption=bool(allow_preemption),
        capability_matrix_json=_json_dump_dict(
            _normalize_capability_matrix(capability_matrix, release_mode=release_mode)
        ),
        interrupt_policy_json=_json_dump_dict(_normalize_interrupt_policy(interrupt_policy)),
        scheduler_weight=max(0.2, float(scheduler_weight or 1.0)),
        max_parallel_requirements=max(1, int(max_parallel_requirements or 1)),
        portfolio_budget_points=max(20, int(portfolio_budget_points or 100)),
        deploy_repo_full_name=(deploy_repo_full_name or "").strip() or None,
        deploy_strategy=(deploy_strategy or "github_actions_ssh").strip() or "github_actions_ssh",
        deploy_trigger_enabled=bool(deploy_trigger_enabled),
        staging_host_label=(staging_host_label or "").strip() or None,
        production_host_label=(production_host_label or "").strip() or None,
        staging_workflow_file=(staging_workflow_file or "deploy-staging.yml").strip() or "deploy-staging.yml",
        production_workflow_file=(production_workflow_file or "deploy-production.yml").strip() or "deploy-production.yml",
        notes=(notes or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_project_policy(
    db: Session,
    row: ProjectPolicyRow,
    *,
    display_name: str | None = None,
    root_path: str | None = None,
    status: str | None = None,
    allowed_write_globs: list[str] | None = None,
    forbidden_globs: list[str] | None = None,
    required_checks: list[str] | None = None,
    release_mode: str | None = None,
    requires_manual_approval: bool | None = None,
    autonomy_mode: str | None = None,
    allow_rebalance: bool | None = None,
    allow_preemption: bool | None = None,
    capability_matrix: dict[str, Any] | None = None,
    interrupt_policy: dict[str, Any] | None = None,
    scheduler_weight: float | None = None,
    max_parallel_requirements: int | None = None,
    portfolio_budget_points: int | None = None,
    deploy_repo_full_name: str | None = None,
    deploy_strategy: str | None = None,
    deploy_trigger_enabled: bool | None = None,
    staging_host_label: str | None = None,
    production_host_label: str | None = None,
    staging_workflow_file: str | None = None,
    production_workflow_file: str | None = None,
    notes: str | None = None,
) -> ProjectPolicyRow:
    if display_name is not None:
        row.display_name = display_name.strip()
    if root_path is not None:
        normalized_root = _normalize_root_path(root_path)
        duplicate = db.query(ProjectPolicyRow).filter(
            ProjectPolicyRow.id != row.id,
            ProjectPolicyRow.root_path == normalized_root,
        ).first()
        if duplicate is not None:
            raise ValueError("Another project policy already uses this root path.")
        row.root_path = normalized_root
    if status is not None:
        row.status = status
    if allowed_write_globs is not None:
        row.allowed_write_globs_json = _json_dump_list(_normalize_globs(allowed_write_globs, default=["**"]))
    if forbidden_globs is not None:
        row.forbidden_globs_json = _json_dump_list(_normalize_globs(forbidden_globs, default=[]))
    if required_checks is not None:
        row.required_checks_json = _json_dump_list(_normalize_globs(required_checks, default=[]))
    if release_mode is not None:
        row.release_mode = release_mode
    if requires_manual_approval is not None:
        row.requires_manual_approval = requires_manual_approval
    if autonomy_mode is not None:
        row.autonomy_mode = autonomy_mode.strip() or "recommend"
    if allow_rebalance is not None:
        row.allow_rebalance = bool(allow_rebalance)
    if allow_preemption is not None:
        row.allow_preemption = bool(allow_preemption)
    if capability_matrix is not None:
        release_mode_for_matrix = release_mode if release_mode is not None else str(row.release_mode or "manual")
        row.capability_matrix_json = _json_dump_dict(
            _normalize_capability_matrix(capability_matrix, release_mode=release_mode_for_matrix)
        )
    if interrupt_policy is not None:
        row.interrupt_policy_json = _json_dump_dict(_normalize_interrupt_policy(interrupt_policy))
    if scheduler_weight is not None:
        row.scheduler_weight = max(0.2, float(scheduler_weight))
    if max_parallel_requirements is not None:
        row.max_parallel_requirements = max(1, int(max_parallel_requirements))
    if portfolio_budget_points is not None:
        row.portfolio_budget_points = max(20, int(portfolio_budget_points))
    if deploy_repo_full_name is not None:
        row.deploy_repo_full_name = deploy_repo_full_name.strip() or None
    if deploy_strategy is not None:
        row.deploy_strategy = deploy_strategy.strip() or "github_actions_ssh"
    if deploy_trigger_enabled is not None:
        row.deploy_trigger_enabled = bool(deploy_trigger_enabled)
    if staging_host_label is not None:
        row.staging_host_label = staging_host_label.strip() or None
    if production_host_label is not None:
        row.production_host_label = production_host_label.strip() or None
    if staging_workflow_file is not None:
        row.staging_workflow_file = staging_workflow_file.strip() or "deploy-staging.yml"
    if production_workflow_file is not None:
        row.production_workflow_file = production_workflow_file.strip() or "deploy-production.yml"
    if notes is not None:
        row.notes = notes.strip() or None
    db.commit()
    db.refresh(row)
    return row


def delete_project_policy(db: Session, row: ProjectPolicyRow) -> None:
    default_project_keys = {str(item.get("project_key") or "") for item in DEFAULT_PROJECT_POLICIES}
    normalized_root = _normalize_root_path(str(row.root_path or ""))
    active_requirements = [
        requirement
        for requirement in db.query(RequirementRow).all()
        if str(requirement.status or "") != "deleted"
        and normalized_root in _split_target_paths(getattr(requirement, "target_project_path", None))
    ]
    if active_requirements:
        requirement_titles = ", ".join(
            f"#{int(requirement.id)} {str(requirement.title or '').strip()}"
            for requirement in active_requirements[:3]
        )
        raise ValueError(
            "Project policy is still referenced by active requirements: "
            f"{requirement_titles or 'unknown requirements'}."
        )

    onboardings = db.query(ProjectOnboardingRow).filter(ProjectOnboardingRow.policy_id == row.id).all()
    for onboarding in onboardings:
        onboarding.policy_id = None

    if str(row.project_key or "") in default_project_keys:
        row.status = "deleted"
        db.commit()
        return

    db.delete(row)
    db.commit()


def _split_target_paths(target_project_path: str | None) -> list[str]:
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


def _match_policy_for_path(db: Session, target_path: str) -> ProjectPolicyRow | None:
    ensure_default_project_policies(db)
    normalized = _normalize_root_path(target_path)
    best: ProjectPolicyRow | None = None
    for row in _visible_policy_query(db).all():
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


def project_policy_summary_markdown(db: Session, target_project_path: str | None) -> str:
    policies = resolve_project_policies_for_target(db, target_project_path, require_active=False)
    if not policies:
        return ""

    lines = ["## Project Policies"]
    for policy in policies:
        data = project_policy_to_dict(policy)
        lines.append(
            f"- **{data['display_name']}** (`{data['root_path']}`): status={data['status']}, "
            f"release_mode={data['release_mode']}, manual_approval={'yes' if data['requires_manual_approval'] else 'no'}"
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
