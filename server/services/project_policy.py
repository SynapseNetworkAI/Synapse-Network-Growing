"""Project policy registry and enforcement helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from server.database import ProjectPolicyRow


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
        "scheduler_weight": 1.4,
        "max_parallel_requirements": 1,
        "portfolio_budget_points": 130,
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
        "scheduler_weight": 1.0,
        "max_parallel_requirements": 1,
        "portfolio_budget_points": 100,
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
        "scheduler_weight": 1.0,
        "max_parallel_requirements": 1,
        "portfolio_budget_points": 90,
        "notes": "Workflow orchestrator repo. Changes should stay reviewable and reproducible.",
    },
]


def _json_dump_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


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


def _normalize_globs(values: list[str] | None, *, default: list[str]) -> list[str]:
    normalized = [str(value).strip() for value in (values or []) if str(value).strip()]
    return normalized or list(default)


def _normalize_root_path(value: str) -> str:
    return str(Path(value.strip()).resolve()) if value.strip() else ""


def ensure_default_project_policies(db: Session) -> None:
    rows = db.query(ProjectPolicyRow).all()
    existing = {str(row.project_key) for row in rows}
    existing_roots = {_normalize_root_path(str(row.root_path)) for row in rows}
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
                scheduler_weight=float(policy.get("scheduler_weight") or 1.0),
                max_parallel_requirements=int(policy.get("max_parallel_requirements") or 1),
                portfolio_budget_points=max(20, int(policy.get("portfolio_budget_points") or 100)),
                notes=policy["notes"],
            )
        )
        changed = True
    if changed:
        db.commit()


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
        "scheduler_weight": float(row.scheduler_weight or 1.0),
        "max_parallel_requirements": int(row.max_parallel_requirements or 1),
        "portfolio_budget_points": max(20, int(getattr(row, "portfolio_budget_points", 100) or 100)),
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_project_policies(db: Session) -> list[ProjectPolicyRow]:
    ensure_default_project_policies(db)
    return db.query(ProjectPolicyRow).order_by(ProjectPolicyRow.display_name.asc()).all()


def get_project_policy(db: Session, policy_id: int) -> ProjectPolicyRow | None:
    ensure_default_project_policies(db)
    return db.query(ProjectPolicyRow).filter(ProjectPolicyRow.id == policy_id).first()


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
    scheduler_weight: float,
    max_parallel_requirements: int,
    portfolio_budget_points: int,
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
        scheduler_weight=max(0.2, float(scheduler_weight or 1.0)),
        max_parallel_requirements=max(1, int(max_parallel_requirements or 1)),
        portfolio_budget_points=max(20, int(portfolio_budget_points or 100)),
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
    scheduler_weight: float | None = None,
    max_parallel_requirements: int | None = None,
    portfolio_budget_points: int | None = None,
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
    if scheduler_weight is not None:
        row.scheduler_weight = max(0.2, float(scheduler_weight))
    if max_parallel_requirements is not None:
        row.max_parallel_requirements = max(1, int(max_parallel_requirements))
    if portfolio_budget_points is not None:
        row.portfolio_budget_points = max(20, int(portfolio_budget_points))
    if notes is not None:
        row.notes = notes.strip() or None
    db.commit()
    db.refresh(row)
    return row


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
    for row in db.query(ProjectPolicyRow).all():
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
    return "\n".join(lines)
