"""Project onboarding manifest + readiness assessment."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from server.database import ProjectOnboardingRow, ProjectPolicyRow
from server.services.project_policy import create_project_policy, list_project_policies, project_policy_to_dict


def _normalize_root_path(value: str) -> str:
    return str(Path(value.strip()).resolve()) if value.strip() else ""


def _json_dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _json_load_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def _json_load_items(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _find_exact_policy(db: Session, root_path: str) -> ProjectPolicyRow | None:
    normalized = _normalize_root_path(root_path)
    return db.query(ProjectPolicyRow).filter(ProjectPolicyRow.root_path == normalized).first()


def _readiness_item(
    key: str,
    label: str,
    ok: bool,
    success_message: str,
    failure_message: str,
    *,
    details: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": "ready" if ok else "missing",
        "message": success_message if ok else failure_message,
        "details": list(details or []),
    }


def _assess_manifest(
    *,
    root_path: str,
    docs_entrypoints: list[str],
    validation_commands: list[str],
    agents_memory_namespace: str | None,
    policy: ProjectPolicyRow | None,
) -> tuple[list[dict[str, Any]], list[str], int, str]:
    repo_root = Path(root_path)
    docs_files = [Path(item) for item in docs_entrypoints if str(item).strip()]
    existing_docs = [str(path) for path in docs_files if path.exists()]
    missing_docs = [str(path) for path in docs_files if not path.exists()]
    has_agents_or_llms = (repo_root / "AGENTS.md").exists() or (repo_root / "llms.txt").exists()
    memory_root = Path("/Users/cliff/workspace/agent/Agents-Memory")
    items = [
        _readiness_item(
            "repo_exists",
            "Repository Path",
            repo_root.is_dir(),
            "Repository path is reachable.",
            "Repository path does not exist or is not a directory.",
            details=[root_path],
        ),
        _readiness_item(
            "git_repo",
            "Git Repository",
            (repo_root / ".git").exists(),
            "Git metadata is present.",
            "`.git` directory is missing.",
        ),
        _readiness_item(
            "agent_context",
            "Agent Context",
            has_agents_or_llms,
            "AGENTS.md or llms.txt is present.",
            "Neither AGENTS.md nor llms.txt was found at the project root.",
        ),
        _readiness_item(
            "docs_entrypoints",
            "Docs Entrypoints",
            bool(docs_files) and not missing_docs,
            "All declared docs entrypoints exist.",
            "One or more declared docs entrypoints are missing.",
            details=existing_docs + missing_docs,
        ),
        _readiness_item(
            "validation_commands",
            "Validation Commands",
            bool(validation_commands),
            "Validation commands are declared.",
            "Validation commands are missing.",
            details=validation_commands,
        ),
        _readiness_item(
            "project_policy",
            "Project Policy",
            policy is not None,
            "Project policy is registered.",
            "Project policy is not registered yet.",
            details=[str(policy.id)] if policy is not None else [],
        ),
        _readiness_item(
            "agents_memory",
            "Agents-Memory Namespace",
            bool((agents_memory_namespace or "").strip()) and memory_root.exists(),
            "Agents-Memory namespace is declared.",
            "Agents-Memory namespace is missing or Agents-Memory repo is unavailable.",
            details=[agents_memory_namespace] if agents_memory_namespace else [],
        ),
    ]

    ready_count = sum(1 for item in items if item["status"] == "ready")
    score = int((ready_count / max(len(items), 1)) * 100)
    missing = [item["label"] for item in items if item["status"] != "ready"]
    if missing:
        status = "needs_setup"
    else:
        status = "ready"
    return items, missing, score, status


def project_onboarding_to_dict(row: ProjectOnboardingRow) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "project_key": str(row.project_key),
        "display_name": str(row.display_name),
        "root_path": str(row.root_path),
        "docs_entrypoints": _json_load_list(row.docs_entrypoints_json),
        "validation_commands": _json_load_list(row.validation_commands_json),
        "agents_memory_namespace": row.agents_memory_namespace,
        "policy_id": int(row.policy_id) if row.policy_id is not None else None,
        "readiness_status": str(row.readiness_status),
        "readiness_score": int(row.readiness_score),
        "readiness_items": _json_load_items(row.readiness_items_json),
        "missing_items": _json_load_list(row.missing_items_json),
        "notes": row.notes,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_project_onboardings(db: Session) -> list[ProjectOnboardingRow]:
    return db.query(ProjectOnboardingRow).order_by(ProjectOnboardingRow.updated_at.desc(), ProjectOnboardingRow.id.desc()).all()


def create_project_onboarding(
    db: Session,
    *,
    project_key: str,
    display_name: str,
    root_path: str,
    docs_entrypoints: list[str],
    validation_commands: list[str],
    agents_memory_namespace: str | None,
    auto_create_policy: bool,
    allowed_write_globs: list[str],
    forbidden_globs: list[str],
    release_mode: str,
    requires_manual_approval: bool,
    notes: str | None,
) -> ProjectOnboardingRow:
    normalized_root = _normalize_root_path(root_path)
    if not normalized_root:
        raise ValueError("root_path is required")

    policy = _find_exact_policy(db, normalized_root)
    if policy is None and auto_create_policy:
        policy = create_project_policy(
            db,
            project_key=project_key.strip(),
            display_name=display_name.strip(),
            root_path=normalized_root,
            status="active",
            allowed_write_globs=allowed_write_globs,
            forbidden_globs=forbidden_globs,
            required_checks=validation_commands,
            release_mode=release_mode,
            requires_manual_approval=requires_manual_approval,
            autonomy_mode="recommend",
            allow_rebalance=True,
            allow_preemption=False,
            scheduler_weight=1.0,
            max_parallel_requirements=1,
            portfolio_budget_points=100,
            notes=notes,
        )

    readiness_items, missing_items, readiness_score, readiness_status = _assess_manifest(
        root_path=normalized_root,
        docs_entrypoints=docs_entrypoints,
        validation_commands=validation_commands,
        agents_memory_namespace=agents_memory_namespace,
        policy=policy,
    )

    row = ProjectOnboardingRow(
        project_key=project_key.strip(),
        display_name=display_name.strip(),
        root_path=normalized_root,
        docs_entrypoints_json=_json_dump(docs_entrypoints),
        validation_commands_json=_json_dump(validation_commands),
        agents_memory_namespace=(agents_memory_namespace or "").strip() or None,
        policy_id=int(policy.id) if policy is not None else None,
        readiness_status=readiness_status,
        readiness_score=readiness_score,
        readiness_items_json=_json_dump(readiness_items),
        missing_items_json=_json_dump(missing_items),
        notes=(notes or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
