from __future__ import annotations

"""Deterministic VCS delivery executor for requirement closeout."""

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server import config


def _run_git(repo_path: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=max(1, config.DELIVERY_VCS_TIMEOUT_SECONDS),
    )
    if check and completed.returncode != 0:
        command = " ".join(["git", *args])
        stderr = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"{command} failed in {repo_path}: {stderr or 'unknown git error'}")
    return completed


def _list_remotes(repo_path: str) -> list[str]:
    completed = _run_git(repo_path, "remote", check=False)
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _remote_url(repo_path: str, remote_name: str) -> str | None:
    if remote_name not in _list_remotes(repo_path):
        return None
    completed = _run_git(repo_path, "remote", "get-url", remote_name, check=False)
    if completed.returncode != 0:
        return None
    value = (completed.stdout or "").strip()
    return value or None


def _is_git_repo(repo_path: str) -> bool:
    completed = _run_git(repo_path, "rev-parse", "--show-toplevel", check=False)
    return completed.returncode == 0


def _current_branch(repo_path: str) -> str:
    return (_run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD").stdout or "").strip()


def _local_branch_exists(repo_path: str, branch_name: str) -> bool:
    return _run_git(repo_path, "show-ref", "--verify", f"refs/heads/{branch_name}", check=False).returncode == 0


def _remote_branch_exists(repo_path: str, remote_name: str, branch_name: str) -> bool:
    if remote_name not in _list_remotes(repo_path):
        return False
    return _run_git(
        repo_path,
        "ls-remote",
        "--exit-code",
        "--heads",
        remote_name,
        branch_name,
        check=False,
    ).returncode == 0


def _working_tree_dirty(repo_path: str) -> bool:
    completed = _run_git(repo_path, "status", "--porcelain", check=False)
    return bool((completed.stdout or "").strip())


def _commit_message(requirement_id: int, requirement_title: str, repo_path: str) -> str:
    repo_name = Path(repo_path).name
    title = " ".join(str(requirement_title or "").split()).strip()
    subject = f"ops(req-{requirement_id}): {title or repo_name}"
    return subject[:72]


def _branch_base_ref(repo_path: str, base_branch: str, remote_name: str) -> str | None:
    if _local_branch_exists(repo_path, base_branch):
        return base_branch
    remote_ref = f"{remote_name}/{base_branch}"
    if _remote_branch_exists(repo_path, remote_name, base_branch):
        return remote_ref
    return None


def _ahead_of_base_count(repo_path: str, base_branch: str, remote_name: str) -> int:
    base_ref = _branch_base_ref(repo_path, base_branch, remote_name)
    if not base_ref:
        return 0
    completed = _run_git(repo_path, "rev-list", "--count", f"{base_ref}..HEAD", check=False)
    if completed.returncode != 0:
        return 0
    try:
        return int((completed.stdout or "0").strip() or "0")
    except ValueError:
        return 0


def _ensure_delivery_branch(repo_path: str, branch_name: str, base_branch: str, remote_name: str) -> dict[str, Any]:
    current = _current_branch(repo_path)
    dirty = _working_tree_dirty(repo_path)
    exists = _local_branch_exists(repo_path, branch_name)

    if current == branch_name:
        return {
            "current_branch_before": current,
            "branch_switched": False,
            "branch_created": False,
            "dirty_before_branch_switch": dirty,
        }

    if dirty and exists:
        raise RuntimeError(
            f"dirty worktree on `{current}` cannot deterministically switch to existing branch `{branch_name}`"
        )

    if dirty:
        _run_git(repo_path, "checkout", "-b", branch_name)
        return {
            "current_branch_before": current,
            "branch_switched": True,
            "branch_created": True,
            "dirty_before_branch_switch": True,
        }

    if exists:
        _run_git(repo_path, "checkout", branch_name)
        return {
            "current_branch_before": current,
            "branch_switched": True,
            "branch_created": False,
            "dirty_before_branch_switch": False,
        }

    base_ref = _branch_base_ref(repo_path, base_branch, remote_name)
    if base_ref:
        _run_git(repo_path, "checkout", "-b", branch_name, base_ref)
    else:
        _run_git(repo_path, "checkout", "-b", branch_name)
    return {
        "current_branch_before": current,
        "branch_switched": True,
        "branch_created": True,
        "dirty_before_branch_switch": False,
    }


def _commit_all_changes(repo_path: str, message: str) -> str | None:
    if not _working_tree_dirty(repo_path):
        return None
    _run_git(repo_path, "add", "-A")
    _run_git(repo_path, "commit", "-m", message)
    return (_run_git(repo_path, "rev-parse", "HEAD").stdout or "").strip() or None


def _push_branch(repo_path: str, remote_name: str, branch_name: str) -> str | None:
    _run_git(repo_path, "push", "-u", remote_name, branch_name)
    completed = _run_git(repo_path, "ls-remote", "--heads", remote_name, branch_name, check=False)
    if completed.returncode != 0:
        return None
    line = (completed.stdout or "").strip().splitlines()
    if not line:
        return None
    return line[0].split()[0]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_repo_paths(contract: dict[str, Any], fallback_target_path: str | None) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in contract.get("changed_target_project_paths") or []:
        value = str(candidate or "").strip()
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    if not ordered:
        for item in contract.get("affected_projects") or []:
            if not isinstance(item, dict):
                continue
            value = str(item.get("root_path") or "").strip()
            if value and value not in seen:
                seen.add(value)
                ordered.append(value)
    if not ordered:
        for item in contract.get("managed_projects") or []:
            if not isinstance(item, dict):
                continue
            value = str(item.get("root_path") or "").strip()
            if value and value not in seen:
                seen.add(value)
                ordered.append(value)
    fallback = str(fallback_target_path or "").strip()
    if fallback and fallback not in seen:
        ordered.append(fallback)
    return ordered


def execute_requirement_delivery_vcs(
    *,
    requirement_id: int,
    requirement_title: str,
    delivery_contract: dict[str, Any],
    fallback_target_path: str | None = None,
) -> dict[str, Any]:
    branch_name = str(delivery_contract.get("branch_name") or "").strip()
    base_branch = str(delivery_contract.get("base_branch") or "main").strip() or "main"
    remote_name = str(delivery_contract.get("remote_name") or config.DELIVERY_VCS_REMOTE_NAME).strip() or "origin"
    commit_required = bool(delivery_contract.get("commit_required"))
    push_required = bool(delivery_contract.get("push_required"))
    capability_matrix = dict(delivery_contract.get("capability_matrix") or {})
    repo_paths = _normalize_repo_paths(delivery_contract, fallback_target_path)
    blockers: list[str] = []
    repo_results: list[dict[str, Any]] = []

    if not branch_name:
        blockers.append("delivery contract is missing branch_name")
    if not repo_paths:
        blockers.append("no target repositories resolved for delivery")
    if commit_required and not bool(capability_matrix.get("git_write", True)):
        blockers.append("branch commit required but git_write is disabled by project policy")
    if push_required and not bool(capability_matrix.get("git_push")):
        blockers.append("branch push required but git_push is disabled by project policy")
    if blockers:
        return {
            "status": "blocked",
            "branch_name": branch_name or None,
            "base_branch": base_branch,
            "remote_name": remote_name,
            "blockers": blockers,
            "repositories": [],
        }

    for repo_path in repo_paths:
        repo_result: dict[str, Any] = {
            "repo_path": repo_path,
            "branch_name": branch_name,
            "base_branch": base_branch,
            "remote_name": remote_name,
            "remote_url": None,
            "status": "blocked",
            "blockers": [],
            "committed": False,
            "pushed": False,
            "commit_sha": None,
            "remote_sha": None,
            "ahead_of_base": 0,
        }
        try:
            if not os.path.isdir(repo_path):
                raise RuntimeError("repository path does not exist")
            if not _is_git_repo(repo_path):
                raise RuntimeError("target path is not a git repository")
            repo_result["remote_url"] = _remote_url(repo_path, remote_name)
            repo_result.update(_ensure_delivery_branch(repo_path, branch_name, base_branch, remote_name))
            dirty_before_commit = _working_tree_dirty(repo_path)
            repo_result["dirty_before_commit"] = dirty_before_commit
            commit_message = _commit_message(requirement_id, requirement_title, repo_path)
            repo_result["commit_message"] = commit_message
            commit_sha = _commit_all_changes(repo_path, commit_message)
            repo_result["commit_sha"] = commit_sha
            repo_result["committed"] = bool(commit_sha)
            ahead_of_base = _ahead_of_base_count(repo_path, base_branch, remote_name)
            repo_result["ahead_of_base"] = ahead_of_base
            if commit_required and not commit_sha and ahead_of_base <= 0:
                raise RuntimeError("no repository changes detected to commit for delivery")
            if push_required:
                if remote_name not in _list_remotes(repo_path):
                    raise RuntimeError(f"remote `{remote_name}` is not configured")
                remote_sha = _push_branch(repo_path, remote_name, branch_name)
                repo_result["remote_sha"] = remote_sha
                repo_result["pushed"] = True
                repo_result["last_pushed_at"] = _utcnow_iso()
            repo_result["status"] = "delivered"
        except Exception as exc:  # noqa: BLE001
            repo_result["blockers"].append(str(exc))
            blockers.append(f"{repo_path}: {exc}")
        repo_results.append(repo_result)

    latest_commit_sha = next((str(item.get("commit_sha") or "").strip() for item in repo_results if str(item.get("commit_sha") or "").strip()), None)
    latest_remote_sha = next((str(item.get("remote_sha") or "").strip() for item in repo_results if str(item.get("remote_sha") or "").strip()), None)
    last_pushed_at = next((str(item.get("last_pushed_at") or "").strip() for item in repo_results if str(item.get("last_pushed_at") or "").strip()), None)
    return {
        "status": "delivered" if not blockers else "blocked",
        "branch_name": branch_name,
        "base_branch": base_branch,
        "remote_name": remote_name,
        "commit_required": commit_required,
        "push_required": push_required,
        "blockers": blockers,
        "repositories": repo_results,
        "delivered_repository_count": sum(1 for item in repo_results if item.get("status") == "delivered"),
        "latest_commit_sha": latest_commit_sha,
        "latest_remote_sha": latest_remote_sha,
        "last_pushed_at": last_pushed_at,
    }
