"""Formal Project center with 1:1 governance policy linkage."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.database import ProjectPolicyRow, ProjectRow, ReleaseRecordRow, RequirementRow
from server.services.projects.policy_defaults import (
    _json_dump_dict,
    _json_dump_list,
    _normalize_capability_matrix,
    _normalize_globs,
    _normalize_interrupt_policy,
    _normalize_root_path,
    default_capability_matrix,
    default_interrupt_policy,
    is_legacy_default_repo_full_name,
    normalize_github_repo_full_name,
    DEFAULT_PROJECT_POLICIES,
)
from server.services.projects.policy_registry import (
    ensure_default_project_policies,
    project_policy_to_dict,
    update_project_policy,
)


def _clean(value: str | None) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _clean_repo(value: str | None) -> str | None:
    return normalize_github_repo_full_name(value)


def _default_policy_for_key(project_key: str | None) -> dict[str, Any] | None:
    key = str(project_key or "").strip()
    for policy in DEFAULT_PROJECT_POLICIES:
        if str(policy.get("project_key") or "") == key:
            return policy
    return None


def _project_policy_row(project: ProjectRow) -> ProjectPolicyRow | None:
    return getattr(project, "_policy_row", None)


def _attach_policy(project: ProjectRow, policy: ProjectPolicyRow | None) -> ProjectRow:
    setattr(project, "_policy_row", policy)
    return project


def _find_project_policy(db: Session, project_id: int) -> ProjectPolicyRow | None:
    return (
        db.query(ProjectPolicyRow)
        .filter(ProjectPolicyRow.project_id == project_id, ProjectPolicyRow.status != "deleted")
        .order_by(ProjectPolicyRow.id.desc())
        .first()
    )


def serialize_project(row: ProjectRow, *, policy: ProjectPolicyRow | None = None) -> dict[str, Any]:
    current_policy = policy or _project_policy_row(row) or _find_project_policy_objectless(row)
    payload = {
        "id": int(row.id),
        "project_key": str(row.project_key or ""),
        "display_name": str(row.display_name or ""),
        "root_path": str(row.root_path or ""),
        "status": str(row.status or "active"),
        "repo_full_name": _clean_repo(getattr(row, "repo_full_name", None)),
        "default_branch": str(getattr(row, "default_branch", None) or "main"),
        "deploy_repo_full_name": _clean_repo(getattr(row, "deploy_repo_full_name", None)),
        "deploy_strategy": str(getattr(row, "deploy_strategy", None) or "disabled"),
        "deploy_trigger_enabled": bool(getattr(row, "deploy_trigger_enabled", False)),
        "staging_host_label": _clean(getattr(row, "staging_host_label", None)),
        "production_host_label": _clean(getattr(row, "production_host_label", None)),
        "staging_workflow_file": str(getattr(row, "staging_workflow_file", None) or "deploy-staging.yml"),
        "production_workflow_file": str(getattr(row, "production_workflow_file", None) or "deploy-production.yml"),
        "notes": _clean(getattr(row, "notes", None)),
        "policy_id": int(current_policy.id) if current_policy is not None else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    return payload


project_to_dict = serialize_project


def _find_project_for_root(db: Session, root_path: str | None) -> ProjectRow | None:
    normalized = _normalize_root_path(root_path or "")
    if not normalized:
        return None
    return db.query(ProjectRow).filter(ProjectRow.root_path == normalized, ProjectRow.status != "deleted").first()


def _find_project_for_key(db: Session, project_key: str | None) -> ProjectRow | None:
    cleaned = _clean(project_key)
    if cleaned is None:
        return None
    return db.query(ProjectRow).filter(ProjectRow.project_key == cleaned, ProjectRow.status != "deleted").first()


def resolve_project(db: Session, *, project_id: int | None = None, project_key: str | None = None, target_project_path: str | None = None) -> ProjectRow | None:
    if project_id is not None:
        row = db.query(ProjectRow).filter(ProjectRow.id == project_id, ProjectRow.status != "deleted").first()
        if row is not None:
            return _attach_policy(row, _find_project_policy(db, int(row.id)))
    row = _find_project_for_key(db, project_key)
    if row is not None:
        return _attach_policy(row, _find_project_policy(db, int(row.id)))
    row = _find_project_for_root(db, target_project_path)
    if row is not None:
        return _attach_policy(row, _find_project_policy(db, int(row.id)))
    return None


def _find_project_policy_objectless(project: ProjectRow) -> ProjectPolicyRow | None:
    return getattr(project, "_policy_row", None)


def ensure_projects_materialized(db: Session) -> None:
    ensure_default_project_policies(db)
    changed = False
    projects = db.query(ProjectRow).all()
    projects_by_key = {str(row.project_key or "").strip(): row for row in projects}
    projects_by_root = {str(row.root_path or "").strip(): row for row in projects}

    for policy in db.query(ProjectPolicyRow).filter(ProjectPolicyRow.status != "deleted").all():
        key = str(policy.project_key or "").strip()
        root = _normalize_root_path(str(policy.root_path or ""))
        default_policy = _default_policy_for_key(key)
        source_repo = _clean_repo(
            getattr(policy, "repo_full_name", None)
            or (default_policy or {}).get("repo_full_name")
            or getattr(policy, "deploy_repo_full_name", None)
        )
        deploy_repo = _clean_repo(getattr(policy, "deploy_repo_full_name", None))
        project = None
        if policy.project_id is not None:
            project = db.query(ProjectRow).filter(ProjectRow.id == int(policy.project_id)).first()
        if project is None:
            project = projects_by_key.get(key) or projects_by_root.get(root)
        if project is None:
            project = ProjectRow(
                project_key=key,
                display_name=str(policy.display_name or key),
                root_path=root,
                status="archived" if str(policy.status or "") == "disabled" else "active",
                repo_full_name=source_repo,
                default_branch="main",
                deploy_repo_full_name=deploy_repo,
                deploy_strategy=str(getattr(policy, "deploy_strategy", None) or "disabled"),
                deploy_trigger_enabled=bool(getattr(policy, "deploy_trigger_enabled", False)),
                staging_host_label=_clean(getattr(policy, "staging_host_label", None)),
                production_host_label=_clean(getattr(policy, "production_host_label", None)),
                staging_workflow_file=str(getattr(policy, "staging_workflow_file", None) or "deploy-staging.yml"),
                production_workflow_file=str(getattr(policy, "production_workflow_file", None) or "deploy-production.yml"),
                notes=_clean(getattr(policy, "notes", None)),
            )
            db.add(project)
            db.flush()
            projects_by_key[key] = project
            projects_by_root[root] = project
            changed = True
        else:
            project.project_key = key
            project.display_name = str(policy.display_name or key)
            project.root_path = root
            project.status = "archived" if str(policy.status or "") == "disabled" else "active"
            current_source_repo = _clean_repo(project.repo_full_name)
            project.repo_full_name = (
                source_repo
                if is_legacy_default_repo_full_name(current_source_repo, source_repo)
                else (current_source_repo or source_repo)
            )
            project.deploy_repo_full_name = deploy_repo
            project.deploy_strategy = str(getattr(policy, "deploy_strategy", None) or "disabled")
            project.deploy_trigger_enabled = bool(getattr(policy, "deploy_trigger_enabled", False))
            project.staging_host_label = _clean(getattr(policy, "staging_host_label", None))
            project.production_host_label = _clean(getattr(policy, "production_host_label", None))
            project.staging_workflow_file = str(getattr(policy, "staging_workflow_file", None) or "deploy-staging.yml")
            project.production_workflow_file = str(getattr(policy, "production_workflow_file", None) or "deploy-production.yml")
            project.notes = _clean(getattr(policy, "notes", None))
            changed = True
        if policy.project_id != project.id:
            policy.project_id = int(project.id)
            changed = True

    for requirement in db.query(RequirementRow).all():
        project = resolve_project(
            db,
            project_id=int(requirement.project_id) if getattr(requirement, "project_id", None) is not None else None,
            project_key=str(getattr(requirement, "project_key", "") or "") or None,
            target_project_path=str(getattr(requirement, "target_project_path", "") or "") or None,
        )
        if project is None:
            continue
        if requirement.project_id != project.id or requirement.project_key != project.project_key or requirement.project_display_name != project.display_name:
            requirement.project_id = int(project.id)
            requirement.project_key = str(project.project_key or "")
            requirement.project_display_name = str(project.display_name or "")
            if not str(requirement.target_project_path or "").strip():
                requirement.target_project_path = str(project.root_path or "")
            changed = True

    for release in db.query(ReleaseRecordRow).all():
        project = resolve_project(
            db,
            project_id=int(release.project_id) if getattr(release, "project_id", None) is not None else None,
            project_key=str(getattr(release, "project_key", "") or "") or None,
            target_project_path=str(getattr(release, "target_project_path", "") or "") or None,
        )
        if project is None:
            continue
        if release.project_id != project.id or release.project_key != project.project_key or release.project_display_name != project.display_name:
            release.project_id = int(project.id)
            release.project_key = str(project.project_key or "")
            release.project_display_name = str(project.display_name or "")
            if not str(release.target_project_path or "").strip():
                release.target_project_path = str(project.root_path or "")
            changed = True

    if changed:
        db.commit()


def list_projects(db: Session, *, status: str | None = None) -> list[ProjectRow]:
    ensure_projects_materialized(db)
    query = db.query(ProjectRow)
    if status:
        query = query.filter(ProjectRow.status == status)
    else:
        query = query.filter(ProjectRow.status != "deleted")
    rows = query.order_by(ProjectRow.display_name.asc(), ProjectRow.id.asc()).all()
    for row in rows:
        _attach_policy(row, _find_project_policy(db, int(row.id)))
    return rows


def get_project(db: Session, project_id: int) -> ProjectRow | None:
    ensure_projects_materialized(db)
    row = db.query(ProjectRow).filter(ProjectRow.id == project_id, ProjectRow.status != "deleted").first()
    if row is None:
        return None
    return _attach_policy(row, _find_project_policy(db, int(row.id)))


def create_project(
    db: Session,
    *,
    project_key: str,
    display_name: str,
    root_path: str,
    repo_full_name: str | None = None,
    default_branch: str = "main",
    deploy_repo_full_name: str | None = None,
    deploy_strategy: str = "disabled",
    deploy_trigger_enabled: bool = False,
    staging_host_label: str | None = None,
    production_host_label: str | None = None,
    staging_workflow_file: str = "deploy-staging.yml",
    production_workflow_file: str = "deploy-production.yml",
    notes: str | None = None,
) -> ProjectRow:
    ensure_projects_materialized(db)
    normalized_root = _normalize_root_path(root_path)
    cleaned_key = str(project_key or "").strip()
    cleaned_name = str(display_name or "").strip()
    if not cleaned_key or not cleaned_name or not normalized_root:
        raise ValueError("project_key, display_name, and root_path are required.")
    duplicate = db.query(ProjectRow).filter((ProjectRow.project_key == cleaned_key) | (ProjectRow.root_path == normalized_root)).first()
    if duplicate is not None:
        raise ValueError("Project already exists for this key or root path.")
    row = ProjectRow(
        project_key=cleaned_key,
        display_name=cleaned_name,
        root_path=normalized_root,
        status="active",
        repo_full_name=_clean_repo(repo_full_name),
        default_branch=str(default_branch or "main").strip() or "main",
        deploy_repo_full_name=_clean_repo(deploy_repo_full_name),
        deploy_strategy=str(deploy_strategy or "disabled").strip() or "disabled",
        deploy_trigger_enabled=bool(deploy_trigger_enabled),
        staging_host_label=_clean(staging_host_label),
        production_host_label=_clean(production_host_label),
        staging_workflow_file=str(staging_workflow_file or "deploy-staging.yml").strip() or "deploy-staging.yml",
        production_workflow_file=str(production_workflow_file or "deploy-production.yml").strip() or "deploy-production.yml",
        notes=_clean(notes),
    )
    db.add(row)
    db.flush()
    policy = ProjectPolicyRow(
        project_id=int(row.id),
        project_key=cleaned_key,
        display_name=cleaned_name,
        root_path=normalized_root,
        status="active",
        allowed_write_globs_json=_json_dump_list(_normalize_globs(["**"], default=["**"])),
        forbidden_globs_json=_json_dump_list([]),
        required_checks_json=_json_dump_list([]),
        release_mode="manual",
        requires_manual_approval=True,
        autonomy_mode="recommend",
        allow_rebalance=True,
        allow_preemption=False,
        capability_matrix_json=_json_dump_dict(_normalize_capability_matrix(default_capability_matrix(release_mode="manual"), release_mode="manual")),
        interrupt_policy_json=_json_dump_dict(_normalize_interrupt_policy(default_interrupt_policy())),
        scheduler_weight=1.0,
        max_parallel_requirements=1,
        portfolio_budget_points=100,
        deploy_repo_full_name=_clean_repo(deploy_repo_full_name),
        deploy_strategy=str(deploy_strategy or "disabled").strip() or "disabled",
        deploy_trigger_enabled=bool(deploy_trigger_enabled),
        staging_host_label=_clean(staging_host_label),
        production_host_label=_clean(production_host_label),
        staging_workflow_file=str(staging_workflow_file or "deploy-staging.yml").strip() or "deploy-staging.yml",
        production_workflow_file=str(production_workflow_file or "deploy-production.yml").strip() or "deploy-production.yml",
        notes=_clean(notes),
    )
    db.add(policy)
    db.commit()
    db.refresh(row)
    return _attach_policy(row, policy)


def update_project(
    db: Session,
    row: ProjectRow,
    *,
    project_key: str | None = None,
    display_name: str | None = None,
    root_path: str | None = None,
    status: str | None = None,
    repo_full_name: str | None = None,
    default_branch: str | None = None,
    deploy_repo_full_name: str | None = None,
    deploy_strategy: str | None = None,
    deploy_trigger_enabled: bool | None = None,
    staging_host_label: str | None = None,
    production_host_label: str | None = None,
    staging_workflow_file: str | None = None,
    production_workflow_file: str | None = None,
    notes: str | None = None,
) -> ProjectRow:
    if project_key is not None:
        cleaned_key = str(project_key or "").strip()
        duplicate = db.query(ProjectRow).filter(ProjectRow.id != row.id, ProjectRow.project_key == cleaned_key).first()
        if duplicate is not None:
            raise ValueError("Another project already uses this project_key.")
        row.project_key = cleaned_key
    if display_name is not None:
        row.display_name = str(display_name or "").strip()
    if root_path is not None:
        normalized_root = _normalize_root_path(root_path)
        duplicate = db.query(ProjectRow).filter(ProjectRow.id != row.id, ProjectRow.root_path == normalized_root).first()
        if duplicate is not None:
            raise ValueError("Another project already uses this root_path.")
        row.root_path = normalized_root
    if status is not None:
        row.status = str(status or "active").strip() or "active"
    if repo_full_name is not None:
        row.repo_full_name = _clean_repo(repo_full_name)
    if default_branch is not None:
        row.default_branch = str(default_branch or "main").strip() or "main"
    if deploy_repo_full_name is not None:
        row.deploy_repo_full_name = _clean_repo(deploy_repo_full_name)
    if deploy_strategy is not None:
        row.deploy_strategy = str(deploy_strategy or "disabled").strip() or "disabled"
    if deploy_trigger_enabled is not None:
        row.deploy_trigger_enabled = bool(deploy_trigger_enabled)
    if staging_host_label is not None:
        row.staging_host_label = _clean(staging_host_label)
    if production_host_label is not None:
        row.production_host_label = _clean(production_host_label)
    if staging_workflow_file is not None:
        row.staging_workflow_file = str(staging_workflow_file or "deploy-staging.yml").strip() or "deploy-staging.yml"
    if production_workflow_file is not None:
        row.production_workflow_file = str(production_workflow_file or "deploy-production.yml").strip() or "deploy-production.yml"
    if notes is not None:
        row.notes = _clean(notes)

    policy = _find_project_policy(db, int(row.id))
    if policy is not None:
        policy_patch: dict[str, Any] = {}
        for field in (
            "display_name",
            "root_path",
            "deploy_repo_full_name",
            "deploy_strategy",
            "deploy_trigger_enabled",
            "staging_host_label",
            "production_host_label",
            "staging_workflow_file",
            "production_workflow_file",
            "notes",
        ):
            if locals()[field] is not None:
                policy_patch[field] = locals()[field]
        if project_key is not None:
            policy.project_key = str(row.project_key or "")
        if status is not None:
            policy.status = "disabled" if row.status == "archived" else "active"
        if policy_patch:
            update_project_policy(db, policy, **policy_patch)
        else:
            db.commit()
    else:
        db.commit()

    db.refresh(row)
    return _attach_policy(row, _find_project_policy(db, int(row.id)))


def archive_project(db: Session, row: ProjectRow) -> ProjectRow:
    updated = update_project(db, row, status="archived")
    for requirement in db.query(RequirementRow).filter(RequirementRow.project_id == row.id).all():
        requirement.project_display_name = str(updated.display_name or "")
        requirement.project_key = str(updated.project_key or "")
    db.commit()
    return updated


def _project_requirement_count(db: Session, project_id: int) -> int:
    return int(db.query(RequirementRow).filter(RequirementRow.project_id == project_id).count())


def _project_release_count(db: Session, project_id: int) -> int:
    return int(db.query(ReleaseRecordRow).filter(ReleaseRecordRow.project_id == project_id).count())


def delete_project(db: Session, row: ProjectRow) -> None:
    if _project_requirement_count(db, int(row.id)) > 0:
        raise ValueError("Project cannot be deleted because requirements exist")
    if _project_release_count(db, int(row.id)) > 0:
        raise ValueError("Project cannot be deleted because releases exist")

    row.status = "deleted"
    policy = _find_project_policy(db, int(row.id))
    if policy is not None:
        policy.status = "deleted"
    db.commit()


def get_project_policy_for_project(db: Session, project_id: int) -> ProjectPolicyRow | None:
    ensure_projects_materialized(db)
    return _find_project_policy(db, project_id)


def update_project_policy_for_project(db: Session, project_id: int, **patch: Any) -> ProjectPolicyRow:
    policy = get_project_policy_for_project(db, project_id)
    if policy is None:
        raise ValueError("Project policy not found.")
    updated = update_project_policy(db, policy, **patch)
    project = db.query(ProjectRow).filter(ProjectRow.id == project_id).first()
    if project is not None:
        project.project_key = str(updated.project_key or "")
        project.display_name = str(updated.display_name or "")
        project.root_path = str(updated.root_path or "")
        project.status = "archived" if str(updated.status or "") == "disabled" else "active"
        project.deploy_repo_full_name = _clean_repo(getattr(updated, "deploy_repo_full_name", None))
        project.repo_full_name = _clean_repo(project.repo_full_name)
        project.deploy_strategy = str(getattr(updated, "deploy_strategy", None) or "disabled")
        project.deploy_trigger_enabled = bool(getattr(updated, "deploy_trigger_enabled", False))
        project.staging_host_label = _clean(getattr(updated, "staging_host_label", None))
        project.production_host_label = _clean(getattr(updated, "production_host_label", None))
        project.staging_workflow_file = str(getattr(updated, "staging_workflow_file", None) or "deploy-staging.yml")
        project.production_workflow_file = str(getattr(updated, "production_workflow_file", None) or "deploy-production.yml")
        project.notes = _clean(getattr(updated, "notes", None))
        db.commit()
    return updated


def serialize_project_with_policy(row: ProjectRow, *, policy: ProjectPolicyRow | None = None) -> dict[str, Any]:
    current_policy = policy or _project_policy_row(row) or _find_project_policy_objectless(row)
    payload = serialize_project(row, policy=current_policy)
    payload["policy"] = project_policy_to_dict(current_policy) if current_policy is not None else None
    return payload


project_with_policy_to_dict = serialize_project_with_policy
