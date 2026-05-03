"""Project policy registry CRUD and default-seeding helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from server.database import ProjectOnboardingRow, ProjectPolicyRow, RequirementRow
from server.services.projects.policy_defaults import (
    DEFAULT_PROJECT_POLICIES,
    _is_legacy_validation_policy,
    _json_dump_dict,
    _json_dump_list,
    _json_load_dict,
    _json_load_list,
    _normalize_capability_matrix,
    _normalize_globs,
    _normalize_interrupt_policy,
    _normalize_root_path,
    is_legacy_default_repo_full_name,
    normalize_github_repo_full_name,
)


LEGACY_DEPLOY_STRATEGIES = {"github_actions_ssh", "github_actions_ssh_gce"}


def _default_policy_by_key(project_key: str | None) -> dict[str, Any] | None:
    key = str(project_key or "").strip()
    for policy in DEFAULT_PROJECT_POLICIES:
        if str(policy.get("project_key") or "") == key:
            return policy
    return None


def _default_deploy_strategy(policy: dict[str, Any]) -> str:
    return str(policy.get("deploy_strategy") or "disabled").strip() or "disabled"


def _sync_default_deploy_fields(row: ProjectPolicyRow) -> bool:
    policy = _default_policy_by_key(getattr(row, "project_key", None))
    if policy is None:
        normalized = normalize_github_repo_full_name(getattr(row, "deploy_repo_full_name", None))
        if normalized != (str(getattr(row, "deploy_repo_full_name", "") or "").strip() or None):
            row.deploy_repo_full_name = normalized
            return True
        return False

    changed = False
    expected_repo = normalize_github_repo_full_name(policy.get("deploy_repo_full_name"))
    current_repo = normalize_github_repo_full_name(getattr(row, "deploy_repo_full_name", None))
    if expected_repo and (not current_repo or is_legacy_default_repo_full_name(current_repo, expected_repo)):
        row.deploy_repo_full_name = expected_repo
        changed = True
    elif current_repo != (str(getattr(row, "deploy_repo_full_name", "") or "").strip() or None):
        row.deploy_repo_full_name = current_repo
        changed = True

    expected_strategy = _default_deploy_strategy(policy)
    current_strategy = str(getattr(row, "deploy_strategy", None) or "").strip()
    if not current_strategy or current_strategy in LEGACY_DEPLOY_STRATEGIES:
        row.deploy_strategy = expected_strategy
        changed = True

    if "deploy_trigger_enabled" in policy and current_strategy in LEGACY_DEPLOY_STRATEGIES:
        row.deploy_trigger_enabled = bool(policy.get("deploy_trigger_enabled", False))
        changed = True
    return changed


def ensure_default_project_policies(db: Session) -> None:
    """Seed built-in project policies and purge legacy validation clones."""

    legacy_rows = db.query(ProjectPolicyRow).all()
    legacy_changed = False
    for row in legacy_rows:
        if _is_legacy_validation_policy(getattr(row, "project_key", None), getattr(row, "root_path", None)):
            db.delete(row)
            legacy_changed = True
    if legacy_changed:
        db.flush()

    for row in db.query(ProjectPolicyRow).filter(ProjectPolicyRow.status != "deleted").all():
        if _sync_default_deploy_fields(row):
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
                    _normalize_capability_matrix(
                        policy.get("capability_matrix"),
                        release_mode=str(policy.get("release_mode") or "manual"),
                    )
                ),
                interrupt_policy_json=_json_dump_dict(_normalize_interrupt_policy(policy.get("interrupt_policy"))),
                scheduler_weight=float(policy.get("scheduler_weight") or 1.0),
                max_parallel_requirements=int(policy.get("max_parallel_requirements") or 1),
                portfolio_budget_points=max(20, int(policy.get("portfolio_budget_points") or 100)),
                deploy_repo_full_name=normalize_github_repo_full_name(policy.get("deploy_repo_full_name")),
                deploy_strategy=_default_deploy_strategy(policy),
                deploy_trigger_enabled=bool(policy.get("deploy_trigger_enabled", False)),
                staging_host_label=str(policy.get("staging_host_label") or "").strip() or None,
                production_host_label=str(policy.get("production_host_label") or "").strip() or None,
                staging_workflow_file=str(policy.get("staging_workflow_file") or "deploy-staging.yml").strip() or "deploy-staging.yml",
                production_workflow_file=str(policy.get("production_workflow_file") or "deploy-production.yml").strip() or "deploy-production.yml",
                notes=policy["notes"],
            )
        )
        changed = True
    if changed or legacy_changed:
        db.commit()


def _visible_policy_query(db: Session):
    return db.query(ProjectPolicyRow).filter(ProjectPolicyRow.status != "deleted")


def serialize_project_policy(row: ProjectPolicyRow) -> dict[str, Any]:
    """Serialize a project policy row into the public API shape."""

    return {
        "id": int(row.id),
        "project_id": int(getattr(row, "project_id", 0)) if getattr(row, "project_id", None) is not None else None,
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


project_policy_to_dict = serialize_project_policy


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
    """Create a new persisted project policy."""

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
        deploy_repo_full_name=normalize_github_repo_full_name(deploy_repo_full_name),
        deploy_strategy=(deploy_strategy or "disabled").strip() or "disabled",
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
    """Update a persisted project policy in place."""

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
        row.deploy_repo_full_name = normalize_github_repo_full_name(deploy_repo_full_name)
    if deploy_strategy is not None:
        row.deploy_strategy = deploy_strategy.strip() or "disabled"
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
    """Delete or tombstone a project policy when it is no longer referenced."""

    default_project_keys = {str(item.get("project_key") or "") for item in DEFAULT_PROJECT_POLICIES}
    normalized_root = _normalize_root_path(str(row.root_path or ""))
    from server.services.projects.policy_defaults import _split_target_paths

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


__all__ = [
    "ensure_default_project_policies",
    "project_policy_to_dict",
    "list_project_policies",
    "get_project_policy",
    "create_project_policy",
    "update_project_policy",
    "delete_project_policy",
]
