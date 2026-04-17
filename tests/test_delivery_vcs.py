from __future__ import annotations

import subprocess
from pathlib import Path

from server.services.delivery.vcs import execute_requirement_delivery_vcs, prepare_requirement_delivery_branch


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout or "git failed")
    return completed


def _init_repo(repo_path: Path, remote_path: Path) -> None:
    _git(repo_path, "init")
    _git(repo_path, "config", "user.name", "Test User")
    _git(repo_path, "config", "user.email", "test@example.com")
    _git(repo_path, "checkout", "-b", "main")
    (repo_path / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo_path, "add", "README.md")
    _git(repo_path, "commit", "-m", "initial")
    _git(repo_path, "remote", "add", "origin", str(remote_path))
    _git(repo_path, "push", "-u", "origin", "main")


def test_execute_requirement_delivery_vcs_commits_and_pushes(tmp_path):
    remote_path = tmp_path / "remote.git"
    repo_path = tmp_path / "repo"
    remote_path.mkdir()
    repo_path.mkdir()
    _git(remote_path, "init", "--bare")
    _init_repo(repo_path, remote_path)

    (repo_path / "README.md").write_text("base\nchange\n", encoding="utf-8")

    result = execute_requirement_delivery_vcs(
        requirement_id=17,
        requirement_title="Incident recovery",
        delivery_contract={
            "branch_name": "ops/req-17-incident-recovery",
            "base_branch": "main",
            "commit_required": True,
            "push_required": True,
            "capability_matrix": {"git_write": True, "git_push": True},
            "changed_target_project_paths": [str(repo_path)],
        },
    )

    assert result["status"] == "delivered"
    assert result["planned_branch_name"] == "ops/req-17-incident-recovery"
    assert result["actual_branch_name"] == "ops/req-17-incident-recovery"
    assert result["branch_reuse_status"] == "created"
    assert result["blockers"] == []
    assert result["delivered_repository_count"] == 1
    repo_result = result["repositories"][0]
    assert repo_result["status"] == "delivered"
    assert repo_result["committed"] is True
    assert repo_result["pushed"] is True
    assert repo_result["commit_sha"]
    assert repo_result["remote_sha"]
    assert _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "ops/req-17-incident-recovery"
    remote_head = _git(repo_path, "ls-remote", "--heads", "origin", "ops/req-17-incident-recovery").stdout.strip()
    assert repo_result["remote_sha"] in remote_head


def test_execute_requirement_delivery_vcs_blocks_when_push_capability_disabled(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    _git(repo_path, "init")
    _git(repo_path, "config", "user.name", "Test User")
    _git(repo_path, "config", "user.email", "test@example.com")
    _git(repo_path, "checkout", "-b", "main")

    result = execute_requirement_delivery_vcs(
        requirement_id=9,
        requirement_title="Blocked push",
        delivery_contract={
            "branch_name": "ops/req-9-blocked",
            "base_branch": "main",
            "commit_required": True,
            "push_required": True,
            "capability_matrix": {"git_write": True, "git_push": False},
            "changed_target_project_paths": [str(repo_path)],
        },
    )

    assert result["status"] == "blocked"
    assert "branch push required but git_push is disabled by project policy" in result["blockers"]
    assert result["repositories"] == []


def test_execute_requirement_delivery_vcs_supports_multiline_fallback_target_paths(tmp_path):
    remote_a = tmp_path / "remote-a.git"
    remote_b = tmp_path / "remote-b.git"
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    remote_a.mkdir()
    remote_b.mkdir()
    repo_a.mkdir()
    repo_b.mkdir()
    _git(remote_a, "init", "--bare")
    _git(remote_b, "init", "--bare")
    _init_repo(repo_a, remote_a)
    _init_repo(repo_b, remote_b)
    (repo_a / "README.md").write_text("base\nchange-a\n", encoding="utf-8")
    (repo_b / "README.md").write_text("base\nchange-b\n", encoding="utf-8")

    result = execute_requirement_delivery_vcs(
        requirement_id=43,
        requirement_title="Validation clone multiline fallback",
        delivery_contract={
            "branch_name": "ops/req-43-validation",
            "base_branch": "main",
            "commit_required": True,
            "push_required": False,
            "capability_matrix": {"git_write": True, "git_push": False},
            "changed_target_project_paths": [],
        },
        fallback_target_path=f"{repo_a}\n{repo_b}",
    )

    assert result["status"] == "delivered"
    assert result["blockers"] == []
    assert result["delivered_repository_count"] == 2
    repo_paths = [item["repo_path"] for item in result["repositories"]]
    assert sorted(repo_paths) == sorted([str(repo_a), str(repo_b)])
    assert all(item["status"] == "delivered" for item in result["repositories"])
    assert all(item["committed"] for item in result["repositories"])


def test_execute_requirement_delivery_vcs_classifies_local_repo_gate_push_failure(tmp_path):
    remote_path = tmp_path / "remote.git"
    repo_path = tmp_path / "repo"
    remote_path.mkdir()
    repo_path.mkdir()
    _git(remote_path, "init", "--bare")
    _init_repo(repo_path, remote_path)
    hooks_dir = repo_path / ".git" / "hooks"
    hook_path = hooks_dir / "pre-push"
    hook_path.write_text(
        "#!/bin/sh\n"
        "echo '[ci:docs] validating documentation constraints'\n"
        "echo '[ci:docs] documentation validation failed'\n"
        "echo ''\n"
        "echo '- llms.txt is missing required anchor: docs/Harness_engineering.md'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    hook_path.chmod(0o755)
    (repo_path / "README.md").write_text("base\nchange\n", encoding="utf-8")

    result = execute_requirement_delivery_vcs(
        requirement_id=18,
        requirement_title="Docs gate blocked push",
        delivery_contract={
            "branch_name": "ops/req-18-docs-gate",
            "base_branch": "main",
            "commit_required": True,
            "push_required": True,
            "capability_matrix": {"git_write": True, "git_push": True},
            "changed_target_project_paths": [str(repo_path)],
        },
    )

    assert result["status"] == "blocked"
    assert result["delivery_blocker_type"] == "repo_gate_failed"
    assert result["repairable"] is True
    assert result["failed_gate_name"] == "docs_checks"
    assert "documentation validation failed" in str(result["delivery_failure_excerpt"])


def test_execute_requirement_delivery_vcs_pushes_precommitted_branch_when_local_base_moved(tmp_path):
    remote_path = tmp_path / "remote.git"
    repo_path = tmp_path / "repo"
    remote_path.mkdir()
    repo_path.mkdir()
    _git(remote_path, "init", "--bare")
    _init_repo(repo_path, remote_path)
    _git(repo_path, "checkout", "-b", "ops/req-19-precommitted")
    (repo_path / "README.md").write_text("base\nagent committed change\n", encoding="utf-8")
    _git(repo_path, "add", "README.md")
    _git(repo_path, "commit", "-m", "agent committed change")
    head_sha = _git(repo_path, "rev-parse", "HEAD").stdout.strip()
    _git(repo_path, "branch", "-f", "main", "HEAD")

    result = execute_requirement_delivery_vcs(
        requirement_id=19,
        requirement_title="Precommitted branch delivery",
        delivery_contract={
            "branch_name": "ops/req-19-precommitted",
            "base_branch": "main",
            "commit_required": True,
            "push_required": True,
            "capability_matrix": {"git_write": True, "git_push": True},
            "changed_target_project_paths": [str(repo_path)],
        },
    )

    assert result["status"] == "delivered"
    assert result["latest_commit_sha"] == head_sha
    repo_result = result["repositories"][0]
    assert repo_result["committed"] is False
    assert repo_result["preexisting_commit"] is True
    assert repo_result["commit_sha"] == head_sha
    assert repo_result["ahead_of_base"] == 1
    assert repo_result["pushed"] is True
    remote_head = _git(repo_path, "ls-remote", "--heads", "origin", "ops/req-19-precommitted").stdout.strip()
    assert head_sha in remote_head


def test_prepare_requirement_delivery_branch_classifies_dirty_workspace_blocker(tmp_path):
    remote_path = tmp_path / "remote.git"
    repo_path = tmp_path / "repo"
    remote_path.mkdir()
    repo_path.mkdir()
    _git(remote_path, "init", "--bare")
    _init_repo(repo_path, remote_path)
    _git(repo_path, "checkout", "-b", "ops/req-1-use-attachment-context-during-execution")
    (repo_path / "README.md").write_text("base\nleftover dirty change\n", encoding="utf-8")

    result = prepare_requirement_delivery_branch(
        delivery_contract={
            "branch_name": "ops/req-3-requirement",
            "base_branch": "main",
            "remote_name": "origin",
            "capability_matrix": {"git_write": True},
            "changed_target_project_paths": [str(repo_path)],
        },
    )

    assert result["status"] == "blocked"
    assert result["branch_name"] == "ops/req-3-requirement"
    assert result["planned_branch_name"] == "ops/req-3-requirement"
    assert result["actual_branch_name"] is None
    assert result["branch_reuse_status"] == "blocked"
    assert result["base_branch"] == "main"
    assert result["delivery_blocker_type"] == "workspace_blocked"
    assert result["repairable"] is False
    assert "ops/req-1-use-attachment-context-during-execution" in result["delivery_failure_excerpt"]
    assert "dirty worktree" in result["blockers"][0]


def test_prepare_requirement_delivery_branch_reuses_existing_clean_branch(tmp_path):
    remote_path = tmp_path / "remote.git"
    repo_path = tmp_path / "repo"
    remote_path.mkdir()
    repo_path.mkdir()
    _git(remote_path, "init", "--bare")
    _init_repo(repo_path, remote_path)
    _git(repo_path, "checkout", "-b", "ops/req-3-requirement")
    _git(repo_path, "checkout", "main")

    result = prepare_requirement_delivery_branch(
        delivery_contract={
            "branch_name": "ops/req-3-requirement",
            "base_branch": "main",
            "remote_name": "origin",
            "capability_matrix": {"git_write": True},
            "changed_target_project_paths": [str(repo_path)],
        },
    )

    assert result["status"] == "ready"
    assert result["planned_branch_name"] == "ops/req-3-requirement"
    assert result["actual_branch_name"] == "ops/req-3-requirement"
    assert result["branch_reuse_status"] == "reused"
    assert _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "ops/req-3-requirement"


def test_prepare_requirement_delivery_branch_creates_replacement_for_unsafe_existing_branch(tmp_path):
    remote_path = tmp_path / "remote.git"
    repo_path = tmp_path / "repo"
    remote_path.mkdir()
    repo_path.mkdir()
    _git(remote_path, "init", "--bare")
    _init_repo(repo_path, remote_path)
    _git(repo_path, "checkout", "--orphan", "ops/req-3-requirement")
    _git(repo_path, "rm", "-rf", ".")
    (repo_path / "README.md").write_text("orphan branch\n", encoding="utf-8")
    _git(repo_path, "add", "README.md")
    _git(repo_path, "commit", "-m", "orphan branch")
    _git(repo_path, "checkout", "main")

    result = prepare_requirement_delivery_branch(
        delivery_contract={
            "branch_name": "ops/req-3-requirement",
            "base_branch": "main",
            "remote_name": "origin",
            "capability_matrix": {"git_write": True},
            "changed_target_project_paths": [str(repo_path)],
        },
    )

    assert result["status"] == "ready"
    assert result["planned_branch_name"] == "ops/req-3-requirement"
    assert result["actual_branch_name"] == "ops/req-3-requirement-r2"
    assert result["branch_reuse_status"] == "replacement_created"
    assert _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "ops/req-3-requirement-r2"
