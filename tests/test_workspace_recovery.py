from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from server.database import (
    CodexSessionRow,
    ProjectPolicyRow,
    RequirementRow,
    WorkflowRunRow,
)
from server.services.runtime.workspace_recovery import (
    WORKSPACE_TRUST_CLEAN,
    WORKSPACE_TRUST_DIRTY_AFTER_KILL,
    WORKSPACE_TRUST_RECOVERY_FAILED,
    mark_workflow_workspace_killed,
    record_trusted_workspace_checkpoint,
    recover_workspace_before_retry,
)
from server.services.runtime.codex_session_registry import build_session_key


def _git_env() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }


def _git(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=_git_env(),
        text=True,
        capture_output=True,
        check=True,
    )
    return str(completed.stdout or "").strip()


def _init_git_repo(path: Path, *, branch: str = "ops/req-1-agent-work") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-b", branch], cwd=path)
    _git(["config", "user.email", "test@example.com"], cwd=path)
    _git(["config", "user.name", "Test Operator"], cwd=path)
    (path / "README.md").write_text("trusted\n", encoding="utf-8")
    _git(["add", "README.md"], cwd=path)
    _git(["commit", "-m", "initial"], cwd=path)
    return path


def _create_run_with_session(
    db_session, repo_root: Path, *, branch: str = "ops/req-1-agent-work"
):
    policy_root = repo_root
    if ".runtime" in repo_root.parts:
        parts = list(repo_root.parts)
        policy_root = Path(*parts[: parts.index(".runtime")])
    policy = ProjectPolicyRow(
        project_key=f"test-policy-{abs(hash(str(policy_root))) % 100000}",
        display_name="Test Project",
        root_path=str(policy_root),
        status="active",
    )
    requirement = RequirementRow(
        title="Recover workspace before retry",
        description_markdown="Verify recovery preflight.",
        status="blocked",
        target_project_path=str(repo_root),
        acceptance_contract_json="{}",
    )
    db_session.add_all([policy, requirement])
    db_session.flush()
    run = WorkflowRunRow(
        requirement_id=int(requirement.id),
        workflow_key="agent_self_repair",
        current_state="awaiting_operator",
        status="awaiting_operator",
        delivery_branch=branch,
    )
    db_session.add(run)
    db_session.flush()
    session = CodexSessionRow(
        session_key=build_session_key(
            role_key="workflow_runner",
            project_root=str(repo_root),
            requirement_id=int(requirement.id),
        ),
        role_key="workflow_runner",
        project_root=str(repo_root),
        requirement_id=int(requirement.id),
        workflow_run_id=int(run.id),
        status="killed",
        workspace_trust_state=WORKSPACE_TRUST_DIRTY_AFTER_KILL,
        requires_workspace_recovery=True,
        kill_signal="SIGKILL",
        metadata_json=json.dumps(
            {"workflow_branch": branch, "workflow_owned_workspace": True}
        ),
    )
    db_session.add(session)
    db_session.commit()
    return run, session


def test_mark_killed_sets_dirty_workspace_state(db_session, tmp_path):
    repo = _init_git_repo(
        tmp_path / "project" / ".runtime" / "worktrees" / "workflow-1"
    )
    run, session = _create_run_with_session(db_session, repo)
    session.requires_workspace_recovery = False
    session.workspace_trust_state = WORKSPACE_TRUST_CLEAN
    db_session.commit()

    result = mark_workflow_workspace_killed(
        db_session, int(run.id), kill_signal="SIGTERM"
    )
    db_session.commit()
    db_session.refresh(session)

    assert result.workspace_trust_state == WORKSPACE_TRUST_DIRTY_AFTER_KILL
    assert result.requires_workspace_recovery is True
    assert session.workspace_trust_state == WORKSPACE_TRUST_DIRTY_AFTER_KILL
    assert session.requires_workspace_recovery is True
    assert session.kill_signal == "SIGTERM"


def test_recovery_cleans_workflow_owned_worktree(db_session, tmp_path):
    repo = _init_git_repo(
        tmp_path / "project" / ".runtime" / "worktrees" / "workflow-2"
    )
    run, session = _create_run_with_session(db_session, repo)
    (repo / "README.md").write_text("half-written\n", encoding="utf-8")
    (repo / "scratch.tmp").write_text("orphan\n", encoding="utf-8")
    git_dir = Path(_git(["rev-parse", "--git-dir"], cwd=repo))
    if not git_dir.is_absolute():
        git_dir = repo / git_dir
    (git_dir / "index.lock").write_text("stale", encoding="utf-8")

    result = recover_workspace_before_retry(
        db_session, int(run.id), active_git_process_checker=lambda _: False
    )
    db_session.commit()
    db_session.refresh(session)

    assert result.recovery_status == "recovered"
    assert result.workspace_trust_state == WORKSPACE_TRUST_CLEAN
    assert session.requires_workspace_recovery is False
    assert not (repo / "scratch.tmp").exists()
    assert not (git_dir / "index.lock").exists()
    assert _git(["status", "--porcelain"], cwd=repo) == ""
    assert (repo / "README.md").read_text(encoding="utf-8") == "trusted\n"


def test_recovery_refuses_user_main_workspace_with_dirty_files(db_session, tmp_path):
    repo = _init_git_repo(tmp_path / "project", branch="main")
    run, session = _create_run_with_session(db_session, repo, branch="main")
    (repo / "scratch.tmp").write_text("human work\n", encoding="utf-8")

    result = recover_workspace_before_retry(
        db_session, int(run.id), active_git_process_checker=lambda _: False
    )
    db_session.commit()
    db_session.refresh(session)

    assert result.recovery_status == "human_review"
    assert result.root_cause == "workspace_not_workflow_owned"
    assert session.workspace_trust_state == WORKSPACE_TRUST_RECOVERY_FAILED
    assert (repo / "scratch.tmp").exists()


def test_recovery_does_not_delete_lock_while_git_process_active(db_session, tmp_path):
    repo = _init_git_repo(
        tmp_path / "project" / ".runtime" / "worktrees" / "workflow-3"
    )
    run, session = _create_run_with_session(db_session, repo)
    git_dir = Path(_git(["rev-parse", "--git-dir"], cwd=repo))
    if not git_dir.is_absolute():
        git_dir = repo / git_dir
    lock_path = git_dir / "index.lock"
    lock_path.write_text("active", encoding="utf-8")

    result = recover_workspace_before_retry(
        db_session, int(run.id), active_git_process_checker=lambda _: True
    )
    db_session.commit()
    db_session.refresh(session)

    assert result.recovery_status == "failed"
    assert result.root_cause == "git_process_still_running"
    assert lock_path.exists()


def test_record_trusted_workspace_checkpoint_marks_clean_workspace(
    db_session, tmp_path
):
    repo = _init_git_repo(
        tmp_path / "project" / ".runtime" / "worktrees" / "workflow-4"
    )
    run, session = _create_run_with_session(db_session, repo)

    result = record_trusted_workspace_checkpoint(
        db_session,
        workflow_run_id=int(run.id),
        project_root=repo,
        thread_id="thread-checkpoint",
        artifact_snapshot_path="runtime/snapshots/checkpoint.tar",
    )
    db_session.commit()
    db_session.refresh(session)

    assert result.recovery_status == "not_required"
    assert result.workspace_trust_state == WORKSPACE_TRUST_CLEAN
    assert result.status_porcelain == ""
    assert session.thread_id == "thread-checkpoint"
    assert session.requires_workspace_recovery is False


def test_recovery_without_registered_session_is_noop(db_session, tmp_path):
    repo = _init_git_repo(
        tmp_path / "project" / ".runtime" / "worktrees" / "workflow-5"
    )
    policy = ProjectPolicyRow(
        project_key="no-session-project",
        display_name="No Session Project",
        root_path=str(repo),
        status="active",
    )
    requirement = RequirementRow(
        title="No session recovery",
        description_markdown="No runtime session exists yet.",
        target_project_path=str(repo),
        status="blocked",
    )
    db_session.add_all([policy, requirement])
    db_session.flush()
    run = WorkflowRunRow(
        requirement_id=int(requirement.id),
        workflow_key="agent_self_repair",
        current_state="awaiting_operator",
        status="awaiting_operator",
        delivery_branch="ops/req-1-agent-work",
    )
    db_session.add(run)
    db_session.commit()

    result = recover_workspace_before_retry(db_session, int(run.id))

    assert result.recovery_status == "not_required"
    assert result.logs == ["No Codex runtime session requires recovery."]
