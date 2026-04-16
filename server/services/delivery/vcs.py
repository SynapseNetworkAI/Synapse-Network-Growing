from __future__ import annotations

"""Deterministic VCS delivery executor for requirement closeout."""

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server import config


def _trim_excerpt(value: str | None, limit: int = 1200) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:limit]


def _gate_name_from_message(message: str) -> str | None:
    lowered = message.lower()
    if any(
        token in lowered
        for token in (
            "[ci:docs]",
            "docs_checks.sh",
            "documentation validation failed",
            "missing required anchor",
            "missing '- status:'",
            "documentation inventory",
            "last verified against code",
            "unsupported lifecycle status",
            "links to retired path",
        )
    ):
        return "docs_checks"
    if "[ci:pr]" in lowered or "pr_checks.sh" in lowered or "running pr quality gates" in lowered:
        return "pr_checks"
    if "typecheck" in lowered:
        return "typecheck"
    if "lint" in lowered:
        return "lint"
    if "pytest" in lowered or "unit test" in lowered:
        return "test"
    return None


def _classify_delivery_failure(message: str) -> dict[str, Any]:
    raw = str(message or "").strip()
    lowered = raw.lower()
    blocker_type = "unknown_delivery_failure"
    repairable = False
    failed_gate_name = _gate_name_from_message(raw)
    if "dirty worktree" in lowered or "automatic execution branch preparation" in lowered:
        blocker_type = "workspace_blocked"
    elif any(token in lowered for token in ("authentication failed", "permission denied (publickey)", "could not read from remote repository", "access denied", "repository not found")):
        blocker_type = "git_auth_failed"
    elif any(token in lowered for token in ("non-fast-forward", "fetch first", "protected branch hook declined", "pre-receive hook declined", "remote rejected", "branch protection")):
        blocker_type = "remote_rejected"
    elif any(token in lowered for token in ("unable to access", "failed to connect", "network is unreachable", "connection timed out", "could not resolve host")):
        blocker_type = "network_failed"
    elif any(token in lowered for token in ("docs validation failed", "[ci:docs]", "[ci:pr]", "pr_checks.sh", "docs_checks.sh", "lint", "typecheck", "pytest", "unit test", "inventory", "missing required anchor", "unsupported lifecycle status", "links to retired path", "missing '- status:'", "last verified against code")):
        blocker_type = "repo_gate_failed"
        repairable = True
        if any(
            token in lowered
            for token in (
                "[ci:docs]",
                "docs_checks.sh",
                "documentation validation failed",
                "missing required anchor",
                "missing '- status:'",
                "documentation inventory",
                "last verified against code",
                "unsupported lifecycle status",
                "links to retired path",
            )
        ):
            failed_gate_name = "docs_checks"
        elif "[ci:pr]" in lowered or "pr_checks.sh" in lowered:
            failed_gate_name = "pr_checks"
        elif "typecheck" in lowered:
            failed_gate_name = "typecheck"
        elif "lint" in lowered:
            failed_gate_name = "lint"
        elif "pytest" in lowered or "unit test" in lowered:
            failed_gate_name = "test"
    elif "branch push required but git_push is disabled by project policy" in lowered:
        blocker_type = "remote_rejected"
    return {
        "delivery_blocker_type": blocker_type,
        "delivery_failure_excerpt": _trim_excerpt(raw),
        "delivery_failure_raw_output": raw or None,
        "repairable": repairable,
        "failed_gate_name": failed_gate_name,
    }


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
        output_parts = [part.strip() for part in (completed.stdout, completed.stderr) if str(part or "").strip()]
        output = "\n".join(output_parts).strip()
        raise RuntimeError(f"{command} failed in {repo_path}: {output or 'unknown git error'}")
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


def _sync_base_branch(repo_path: str, base_branch: str, remote_name: str) -> dict[str, Any]:
    current = _current_branch(repo_path)
    dirty = _working_tree_dirty(repo_path)
    if dirty:
        raise RuntimeError(f"dirty worktree on `{current}` blocks automatic execution branch preparation")

    remotes = _list_remotes(repo_path)
    if remote_name in remotes:
        _run_git(repo_path, "fetch", remote_name)

    local_base_exists = _local_branch_exists(repo_path, base_branch)
    remote_base_exists = remote_name in remotes and _remote_branch_exists(repo_path, remote_name, base_branch)
    if current != base_branch:
        if local_base_exists:
            _run_git(repo_path, "checkout", base_branch)
        elif remote_base_exists:
            _run_git(repo_path, "checkout", "-b", base_branch, f"{remote_name}/{base_branch}")

    if remote_base_exists:
        _run_git(repo_path, "pull", "--ff-only", remote_name, base_branch)

    return {
        "base_branch_synced": True,
        "base_branch_before_sync": current,
        "base_branch_after_sync": _current_branch(repo_path),
    }


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


def _is_ancestor(repo_path: str, ancestor_ref: str, descendant_ref: str) -> bool:
    return _run_git(repo_path, "merge-base", "--is-ancestor", ancestor_ref, descendant_ref, check=False).returncode == 0


def _replacement_branch_name(repo_path: str, branch_name: str, remote_name: str) -> str:
    for index in range(2, 100):
        candidate = f"{branch_name}-r{index}"
        if not _local_branch_exists(repo_path, candidate) and not _remote_branch_exists(repo_path, remote_name, candidate):
            return candidate
    raise RuntimeError(f"no replacement branch name available for `{branch_name}`")


def _ensure_delivery_branch(repo_path: str, branch_name: str, base_branch: str, remote_name: str) -> dict[str, Any]:
    current = _current_branch(repo_path)
    dirty = _working_tree_dirty(repo_path)
    exists = _local_branch_exists(repo_path, branch_name)

    if current == branch_name:
        return {
            "current_branch_before": current,
            "planned_branch_name": branch_name,
            "actual_branch_name": branch_name,
            "branch_reuse_status": "reused",
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
            "planned_branch_name": branch_name,
            "actual_branch_name": branch_name,
            "branch_reuse_status": "created",
            "branch_switched": True,
            "branch_created": True,
            "dirty_before_branch_switch": True,
        }

    if exists:
        actual_branch = branch_name
        reuse_status = "reused"
        base_ref = _branch_base_ref(repo_path, base_branch, remote_name)
        if base_ref and not _is_ancestor(repo_path, base_ref, branch_name):
            actual_branch = _replacement_branch_name(repo_path, branch_name, remote_name)
            _run_git(repo_path, "checkout", "-b", actual_branch, base_ref)
            reuse_status = "replacement_created"
        else:
            _run_git(repo_path, "checkout", branch_name)
        return {
            "current_branch_before": current,
            "planned_branch_name": branch_name,
            "actual_branch_name": actual_branch,
            "branch_reuse_status": reuse_status,
            "branch_switched": True,
            "branch_created": reuse_status == "replacement_created",
            "dirty_before_branch_switch": False,
        }

    base_ref = _branch_base_ref(repo_path, base_branch, remote_name)
    if base_ref:
        _run_git(repo_path, "checkout", "-b", branch_name, base_ref)
    else:
        _run_git(repo_path, "checkout", "-b", branch_name)
    return {
        "current_branch_before": current,
        "planned_branch_name": branch_name,
        "actual_branch_name": branch_name,
        "branch_reuse_status": "created",
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
    fallback_raw = str(fallback_target_path or "")
    for candidate in fallback_raw.splitlines():
        normalized = candidate.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
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
            "planned_branch_name": branch_name or None,
            "actual_branch_name": None,
            "branch_reuse_status": "blocked",
            "base_branch": base_branch,
            "remote_name": remote_name,
            "blockers": blockers,
            "repositories": [],
        }

    for repo_path in repo_paths:
        repo_result: dict[str, Any] = {
            "repo_path": repo_path,
            "branch_name": branch_name,
            "planned_branch_name": branch_name,
            "actual_branch_name": None,
            "branch_reuse_status": "blocked",
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
            actual_branch_name = str(repo_result.get("actual_branch_name") or branch_name).strip() or branch_name
            repo_result["branch_name"] = actual_branch_name
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
                remote_sha = _push_branch(repo_path, remote_name, actual_branch_name)
                repo_result["remote_sha"] = remote_sha
                repo_result["pushed"] = True
                repo_result["last_pushed_at"] = _utcnow_iso()
            repo_result["status"] = "delivered"
        except Exception as exc:  # noqa: BLE001
            classified = _classify_delivery_failure(str(exc))
            repo_result["blockers"].append(str(exc))
            repo_result.update(classified)
            blockers.append(f"{repo_path}: {exc}")
        repo_results.append(repo_result)

    latest_commit_sha = next((str(item.get("commit_sha") or "").strip() for item in repo_results if str(item.get("commit_sha") or "").strip()), None)
    latest_remote_sha = next((str(item.get("remote_sha") or "").strip() for item in repo_results if str(item.get("remote_sha") or "").strip()), None)
    last_pushed_at = next((str(item.get("last_pushed_at") or "").strip() for item in repo_results if str(item.get("last_pushed_at") or "").strip()), None)
    first_repo = next((item for item in repo_results if isinstance(item, dict)), {})
    actual_branch_name = (
        str(first_repo.get("actual_branch_name") or "").strip()
        if blockers and isinstance(first_repo, dict) and str(first_repo.get("branch_reuse_status") or "") == "blocked"
        else (str(first_repo.get("actual_branch_name") or first_repo.get("branch_name") or branch_name).strip() if isinstance(first_repo, dict) else branch_name)
    )
    branch_reuse_status = str(first_repo.get("branch_reuse_status") or ("blocked" if blockers else "created")).strip() if isinstance(first_repo, dict) else ("blocked" if blockers else "created")
    blocker_context = {}
    if blockers:
        blocked_repo = next((item for item in repo_results if item.get("status") != "delivered"), None)
        if isinstance(blocked_repo, dict):
            blocker_context = {
                "delivery_blocker_type": blocked_repo.get("delivery_blocker_type"),
                "delivery_failure_excerpt": blocked_repo.get("delivery_failure_excerpt"),
                "delivery_failure_raw_output": blocked_repo.get("delivery_failure_raw_output"),
                "repairable": bool(blocked_repo.get("repairable")),
                "failed_gate_name": blocked_repo.get("failed_gate_name"),
            }
        if not blocker_context:
            blocker_context = _classify_delivery_failure(blockers[0])
    return {
        "status": "delivered" if not blockers else "blocked",
        "branch_name": actual_branch_name or branch_name,
        "planned_branch_name": branch_name,
        "actual_branch_name": actual_branch_name or None,
        "branch_reuse_status": branch_reuse_status or None,
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
        **blocker_context,
    }


def prepare_requirement_delivery_branch(
    *,
    delivery_contract: dict[str, Any],
    fallback_target_path: str | None = None,
) -> dict[str, Any]:
    branch_name = str(delivery_contract.get("branch_name") or "").strip()
    base_branch = str(delivery_contract.get("base_branch") or "main").strip() or "main"
    remote_name = str(delivery_contract.get("remote_name") or config.DELIVERY_VCS_REMOTE_NAME).strip() or "origin"
    capability_matrix = dict(delivery_contract.get("capability_matrix") or {})
    repo_paths = _normalize_repo_paths(delivery_contract, fallback_target_path)
    blockers: list[str] = []
    repo_results: list[dict[str, Any]] = []

    if not branch_name:
        blockers.append("delivery contract is missing branch_name")
    if not repo_paths:
        blockers.append("no target repositories resolved for branch preparation")
    if not bool(capability_matrix.get("git_write", True)):
        blockers.append("branch preparation requires git_write but project policy disables it")
    if blockers:
        return {
            "status": "blocked",
            "branch_name": branch_name or None,
            "planned_branch_name": branch_name or None,
            "actual_branch_name": None,
            "branch_reuse_status": "blocked",
            "base_branch": base_branch,
            "remote_name": remote_name,
            "blockers": blockers,
            "repositories": [],
        }

    for repo_path in repo_paths:
        repo_result: dict[str, Any] = {
            "repo_path": repo_path,
            "branch_name": branch_name,
            "planned_branch_name": branch_name,
            "actual_branch_name": None,
            "branch_reuse_status": "blocked",
            "base_branch": base_branch,
            "remote_name": remote_name,
            "remote_url": None,
            "status": "blocked",
            "blockers": [],
            "current_branch_after": None,
        }
        try:
            if not os.path.isdir(repo_path):
                raise RuntimeError("repository path does not exist")
            if not _is_git_repo(repo_path):
                raise RuntimeError("target path is not a git repository")
            repo_result["remote_url"] = _remote_url(repo_path, remote_name)
            repo_result.update(_sync_base_branch(repo_path, base_branch, remote_name))
            repo_result.update(_ensure_delivery_branch(repo_path, branch_name, base_branch, remote_name))
            actual_branch_name = str(repo_result.get("actual_branch_name") or branch_name).strip() or branch_name
            repo_result["branch_name"] = actual_branch_name
            repo_result["current_branch_after"] = _current_branch(repo_path)
            repo_result["status"] = "ready"
        except Exception as exc:  # noqa: BLE001
            classified = _classify_delivery_failure(str(exc))
            repo_result["blockers"].append(str(exc))
            repo_result.update(classified)
            blockers.append(f"{repo_path}: {exc}")
        repo_results.append(repo_result)

    blocker_context = {}
    if blockers:
        blocked_repo = next((item for item in repo_results if item.get("status") != "ready"), None)
        if isinstance(blocked_repo, dict):
            blocker_context = {
                "delivery_blocker_type": blocked_repo.get("delivery_blocker_type"),
                "delivery_failure_excerpt": blocked_repo.get("delivery_failure_excerpt"),
                "delivery_failure_raw_output": blocked_repo.get("delivery_failure_raw_output"),
                "repairable": bool(blocked_repo.get("repairable")),
                "failed_gate_name": blocked_repo.get("failed_gate_name"),
            }
        if not blocker_context:
            blocker_context = _classify_delivery_failure(blockers[0])

    first_repo = next((item for item in repo_results if isinstance(item, dict)), {})
    actual_branch_name = (
        str(first_repo.get("actual_branch_name") or "").strip()
        if blockers and isinstance(first_repo, dict) and str(first_repo.get("branch_reuse_status") or "") == "blocked"
        else (str(first_repo.get("actual_branch_name") or first_repo.get("branch_name") or branch_name).strip() if isinstance(first_repo, dict) else branch_name)
    )
    branch_reuse_status = str(first_repo.get("branch_reuse_status") or ("blocked" if blockers else "created")).strip() if isinstance(first_repo, dict) else ("blocked" if blockers else "created")
    return {
        "status": "ready" if not blockers else "blocked",
        "branch_name": actual_branch_name or branch_name,
        "planned_branch_name": branch_name,
        "actual_branch_name": actual_branch_name or None,
        "branch_reuse_status": branch_reuse_status or None,
        "base_branch": base_branch,
        "remote_name": remote_name,
        "blockers": blockers,
        "repositories": repo_results,
        **blocker_context,
    }
