from __future__ import annotations

import subprocess
from pathlib import Path

from server.services.delivery_vcs import execute_requirement_delivery_vcs


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
