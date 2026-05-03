from __future__ import annotations

"""Small deterministic helpers for workspace recovery."""

import json
import os
import subprocess  # nosec B404 - recovery runner invokes fixed git/ps commands without shell.
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from server import config
from server.database import (
    CodexSessionRow,
    ProjectPolicyRow,
    RequirementRow,
    WorkflowRunRow,
    WorkflowStateEventRow,
)
from server.services.runtime.codex_session_registry import build_session_key
from server.services.runtime.workspace_recovery_models import WorkspaceRecoveryResult
from server.services.runtime.workspace_recovery_models import ActiveGitProcessChecker


def workflow_run_or_error(db: Session, workflow_run_id: int) -> WorkflowRunRow:
    run = (
        db.query(WorkflowRunRow)
        .filter(WorkflowRunRow.id == int(workflow_run_id))
        .first()
    )
    if run is None:
        raise ValueError(f"workflow run not found: {workflow_run_id}")
    return run


def latest_session_for_workflow(
    db: Session, workflow_run_id: int
) -> CodexSessionRow | None:
    return (
        db.query(CodexSessionRow)
        .filter(CodexSessionRow.workflow_run_id == int(workflow_run_id))
        .order_by(CodexSessionRow.updated_at.desc(), CodexSessionRow.id.desc())
        .first()
    )


def create_workflow_session(
    db: Session,
    *,
    run: WorkflowRunRow,
    requirement: RequirementRow | None,
    project_root: Path,
) -> CodexSessionRow:
    role_key = "workflow_runner"
    session_key = build_session_key(
        role_key=role_key,
        project_root=str(project_root),
        requirement_id=int(run.requirement_id),
    )
    row = (
        db.query(CodexSessionRow)
        .filter(CodexSessionRow.session_key == session_key)
        .first()
    )
    if row is None:
        row = CodexSessionRow(
            session_key=session_key,
            role_key=role_key,
            project_root=str(project_root),
            requirement_id=int(run.requirement_id),
            workflow_run_id=int(run.id),
        )
        db.add(row)
    row.workflow_run_id = int(run.id)
    if requirement is not None:
        row.project_root = str(project_root)
    db.flush()
    return row


def requirement_project_root(requirement: RequirementRow | None) -> Path:
    raw = str(getattr(requirement, "target_project_path", "") or "").strip()
    if not raw:
        raw = str(config.PROJECT_ROOT)
    return Path(raw).expanduser().resolve()


def expected_branch(run: WorkflowRunRow, metadata: dict[str, Any]) -> str | None:
    trusted_checkpoint = metadata.get("trusted_checkpoint")
    checkpoint_branch = (
        trusted_checkpoint.get("branch")
        if isinstance(trusted_checkpoint, dict)
        else None
    )
    candidates = (
        getattr(run, "delivery_branch", None),
        metadata.get("workflow_branch"),
        metadata.get("branch"),
        metadata.get("delivery_branch"),
        checkpoint_branch,
    )
    for item in candidates:
        value = str(item or "").strip()
        if value:
            return value
    return None


def is_registered_project_scope(db: Session, repo_root: Path) -> bool:
    policies = (
        db.query(ProjectPolicyRow).filter(ProjectPolicyRow.status == "active").all()
    )
    for policy in policies:
        root_raw = str(policy.root_path or "").strip()
        if not root_raw:
            continue
        try:
            policy_root = Path(root_raw).expanduser().resolve()
        except Exception:  # nosec B112 - malformed operator policy paths are skipped.
            continue
        if repo_root == policy_root or policy_root in repo_root.parents:
            return True
    return False


def is_workflow_owned_workspace(
    repo_root: Path, *, branch: str | None, expected_branch_value: str | None
) -> bool:
    normalized = str(repo_root)
    if f"{os.sep}.runtime{os.sep}worktrees{os.sep}workflow-" in normalized:
        return True
    branch_value = str(branch or "").strip()
    if (
        branch_value
        and branch_value == str(expected_branch_value or "").strip()
        and branch_value.startswith(("ops/", "codex/"))
    ):
        return True
    return False


def git_dir(repo_root: Path) -> Path:
    raw = git_stdout(["rev-parse", "--git-dir"], cwd=repo_root)
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def existing_git_lock_paths(git_dir_path: Path) -> list[Path]:
    candidates = [git_dir_path / "index.lock", git_dir_path / "shallow.lock"]
    refs_dir = git_dir_path / "refs"
    if refs_dir.exists():
        candidates.extend(ref for ref in refs_dir.rglob("*.lock") if ref.is_file())
    return [path for path in candidates if path.exists()]


def trusted_snapshot_path(session: CodexSessionRow) -> str | None:
    checkpoint = _json_load(session.trusted_checkpoint_json)
    value = str(checkpoint.get("artifact_snapshot_path") or "").strip()
    return value or None


def has_active_git_process(repo_root: Path) -> bool:
    try:
        completed = subprocess.run(  # nosec B603 B607 - fixed local ps invocation.
            ["ps", "-axo", "pid=,command="],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return False
    root_text = str(repo_root)
    return any(
        "git" in line and root_text in line for line in completed.stdout.splitlines()
    )


def git_stdout(args: list[str], *, cwd: Path, allow_failure: bool = False) -> str:
    completed = subprocess.run(  # nosec B603 B607 - constrained git subcommands.
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    if int(completed.returncode) != 0 and not allow_failure:
        message = completed.stderr or completed.stdout or f"git {' '.join(args)} failed"
        raise RuntimeError(str(message)[:1000])
    return str(completed.stdout or "").strip()


def run_git_checked(args: list[str], *, cwd: Path) -> None:
    completed = subprocess.run(  # nosec B603 B607 - constrained git subcommands.
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if int(completed.returncode) != 0:
        message = completed.stderr or completed.stdout or f"git {' '.join(args)} failed"
        raise RuntimeError(str(message)[:1000])


def workspace_recovery_logs_from_session(session: CodexSessionRow) -> list[str]:
    metadata = _json_load(session.metadata_json)
    logs = metadata.get("workspace_recovery_logs")
    if isinstance(logs, list):
        return [str(item) for item in logs[:10]]
    if bool(getattr(session, "requires_workspace_recovery", False)):
        return ["Run workspace recovery before retrying agent."]
    return ["Workspace is trusted."]


def repo_context(expected_root: Path, logs: list[str]) -> tuple[Path, Path, str]:
    repo_root = (
        Path(git_stdout(["rev-parse", "--show-toplevel"], cwd=expected_root))
        .expanduser()
        .resolve()
    )
    branch = git_stdout(["branch", "--show-current"], cwd=repo_root)
    remote = git_stdout(
        ["remote", "get-url", "origin"], cwd=repo_root, allow_failure=True
    )
    logs.extend(
        [
            f"repo_root={repo_root}",
            f"branch={branch or '(detached)'}",
            f"remote={remote or '(none)'}",
        ]
    )
    return repo_root, git_dir(repo_root), branch


def preflight_failure(
    db: Session, repo_root: Path, expected_root: Path, branch: str, expected: str | None
) -> str | None:
    if repo_root != expected_root:
        return "repo_root_mismatch"
    if not is_registered_project_scope(db, repo_root):
        return "project_policy_missing"
    if not is_workflow_owned_workspace(
        repo_root, branch=branch, expected_branch_value=expected
    ):
        return "workspace_not_workflow_owned"
    if expected and branch and branch != expected:
        return "branch_mismatch"
    return None


def clean_workspace(
    session: CodexSessionRow,
    *,
    repo_root: Path,
    repo_git_dir: Path,
    logs: list[str],
    active_git_process_checker: ActiveGitProcessChecker | None,
) -> tuple[list[str], str]:
    lock_paths = existing_git_lock_paths(repo_git_dir)
    checker = active_git_process_checker or has_active_git_process
    if lock_paths and checker(repo_root):
        return [], "git_process_still_running"
    cleaned_locks = remove_lock_paths(lock_paths)
    if cleaned_locks:
        logs.append(f"Removed {len(cleaned_locks)} stale git lock file(s).")
    snapshot_path = trusted_snapshot_path(session)
    if snapshot_path:
        logs.append(
            f"Trusted snapshot restore is configured but not implemented in v1: {snapshot_path}; using reset/clean."
        )
    run_git_checked(["reset", "--hard", "HEAD"], cwd=repo_root)
    run_git_checked(["clean", "-fd"], cwd=repo_root)
    return cleaned_locks, git_stdout(["status", "--porcelain"], cwd=repo_root)


def remove_lock_paths(lock_paths: list[Path]) -> list[str]:
    cleaned_locks: list[str] = []
    for path in lock_paths:
        path.unlink(missing_ok=True)
        cleaned_locks.append(str(path))
    return cleaned_locks


def record_recovery_event(
    db: Session,
    run: WorkflowRunRow,
    *,
    event_type: str,
    result: WorkspaceRecoveryResult,
) -> None:
    db.add(
        WorkflowStateEventRow(
            workflow_run_id=int(run.id),
            event_type=event_type,
            from_state=str(run.current_state or ""),
            to_state=str(run.current_state or "awaiting_operator"),
            condition=result.recovery_status,
            payload_json=json_dump(result.model_dump()),
        )
    )


def _json_load(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        data = json.loads(payload)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def json_dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=json_default)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _merge_metadata(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    payload = dict(existing or {})
    payload.update(patch or {})
    logs = list(payload.get("workspace_recovery_logs") or [])
    if patch.get("workspace_recovery_root_cause"):
        logs.append(str(patch.get("workspace_recovery_root_cause")))
    if logs:
        payload["workspace_recovery_logs"] = logs[-10:]
    return payload


json_load = _json_load
json_default = _json_default
merge_metadata = _merge_metadata
