from __future__ import annotations

"""Deterministic workspace recovery before retrying killed agent sessions."""

from pathlib import Path

from sqlalchemy.orm import Session

from server.database import (
    CodexSessionRow,
    RequirementRow,
    WorkflowRunRow,
    utcnow,
)
from server.services.runtime.workspace_recovery_models import (
    RECOVERY_STATUS_FAILED,
    RECOVERY_STATUS_HUMAN_REVIEW,
    RECOVERY_STATUS_NOT_REQUIRED,
    RECOVERY_STATUS_RECOVERED,
    WORKSPACE_TRUST_CLEAN,
    WORKSPACE_TRUST_DIRTY_AFTER_KILL,
    WORKSPACE_TRUST_RECOVERY_FAILED,
    WORKSPACE_TRUST_RECOVERY_REQUIRED,
    ActiveGitProcessChecker,
    WorkspaceRecoveryResult,
    WorkspaceRecoverySummary,
)
from server.services.runtime.workspace_recovery_utils import (
    clean_workspace,
    create_workflow_session,
    expected_branch,
    git_stdout,
    is_workflow_owned_workspace,
    json_dump,
    json_load,
    latest_session_for_workflow,
    merge_metadata,
    preflight_failure,
    record_recovery_event,
    requirement_project_root,
    repo_context,
    workflow_run_or_error,
    workspace_recovery_logs_from_session,
)


def workspace_recovery_summary_for_workflow(
    db: Session, workflow_run_id: int
) -> WorkspaceRecoverySummary:
    """Return the latest workspace trust projection for a workflow run."""

    session = latest_session_for_workflow(db, workflow_run_id)
    if session is None:
        return WorkspaceRecoverySummary(
            logs=["No Codex runtime session is registered for this workflow run."]
        )
    return WorkspaceRecoverySummary(
        workspace_trust_state=str(
            getattr(session, "workspace_trust_state", "") or WORKSPACE_TRUST_CLEAN
        ),
        requires_workspace_recovery=bool(
            getattr(session, "requires_workspace_recovery", False)
        ),
        recovery_status=(
            RECOVERY_STATUS_HUMAN_REVIEW
            if bool(getattr(session, "requires_workspace_recovery", False))
            else RECOVERY_STATUS_NOT_REQUIRED
        ),
        latest_session_id=int(session.id),
        killed_at=session.killed_at.isoformat()
        if getattr(session, "killed_at", None)
        else None,
        kill_signal=str(getattr(session, "kill_signal", "") or "") or None,
        repo_root=str(session.project_root or "") or None,
        logs=workspace_recovery_logs_from_session(session),
    )


def mark_workflow_workspace_killed(
    db: Session,
    workflow_run_id: int,
    *,
    kill_signal: str = "SIGKILL",
) -> WorkspaceRecoveryResult:
    """Mark a workflow-owned runtime workspace dirty after an operator/runner kill."""

    run = workflow_run_or_error(db, workflow_run_id)
    requirement = (
        db.query(RequirementRow)
        .filter(RequirementRow.id == int(run.requirement_id))
        .first()
    )
    project_root = requirement_project_root(requirement)
    session = latest_session_for_workflow(
        db, workflow_run_id
    ) or create_workflow_session(
        db, run=run, requirement=requirement, project_root=project_root
    )
    now = utcnow()
    session.status = "killed"
    session.workspace_trust_state = WORKSPACE_TRUST_DIRTY_AFTER_KILL
    session.requires_workspace_recovery = True
    session.killed_at = now
    session.kill_signal = str(kill_signal or "SIGKILL")
    session.metadata_json = json_dump(
        merge_metadata(
            json_load(session.metadata_json),
            {
                "workspace_trust_state": WORKSPACE_TRUST_DIRTY_AFTER_KILL,
                "requires_workspace_recovery": True,
                "killed_at": now.isoformat(),
                "kill_signal": session.kill_signal,
                "next_action": "Run workspace recovery before retrying agent.",
            },
        )
    )
    result = WorkspaceRecoveryResult(
        workspace_trust_state=WORKSPACE_TRUST_DIRTY_AFTER_KILL,
        requires_workspace_recovery=True,
        recovery_status=RECOVERY_STATUS_HUMAN_REVIEW,
        latest_session_id=int(session.id),
        killed_at=now.isoformat(),
        kill_signal=session.kill_signal,
        repo_root=str(session.project_root or "") or None,
        root_cause="dirty_after_kill",
        logs=["Kill recorded; workspace must be recovered before retrying the agent."],
    )
    result.event_payload = result.model_dump()
    record_recovery_event(
        db, run, event_type="workspace_marked_dirty_after_kill", result=result
    )
    db.flush()
    return result


def record_trusted_workspace_checkpoint(
    db: Session,
    *,
    workflow_run_id: int,
    project_root: str | Path,
    role_key: str = "workflow_runner",
    thread_id: str | None = None,
    artifact_snapshot_path: str | None = None,
) -> WorkspaceRecoveryResult:
    """Record a clean checkpoint before a deterministic runner starts an agent turn."""

    run = workflow_run_or_error(db, workflow_run_id)
    requirement = (
        db.query(RequirementRow)
        .filter(RequirementRow.id == int(run.requirement_id))
        .first()
    )
    root = Path(str(project_root)).expanduser().resolve()
    branch = git_stdout(["branch", "--show-current"], cwd=root)
    head_sha = git_stdout(["rev-parse", "HEAD"], cwd=root)
    status = git_stdout(["status", "--porcelain"], cwd=root)
    clean = not status.strip()
    session = create_workflow_session(
        db, run=run, requirement=requirement, project_root=root
    )
    checkpoint = {
        "branch": branch,
        "head_sha": head_sha,
        "clean": clean,
        "status_porcelain": status,
        "runtime_session_id": int(session.id) if getattr(session, "id", None) else None,
        "artifact_snapshot_path": str(artifact_snapshot_path or "").strip() or None,
        "created_at": utcnow().isoformat(),
    }
    session.thread_id = thread_id or session.thread_id
    session.status = "active"
    session.workspace_trust_state = (
        WORKSPACE_TRUST_CLEAN if clean else WORKSPACE_TRUST_RECOVERY_REQUIRED
    )
    session.requires_workspace_recovery = not clean
    session.trusted_checkpoint_json = json_dump(checkpoint)
    session.metadata_json = json_dump(
        merge_metadata(
            json_load(session.metadata_json),
            {
                "trusted_checkpoint": checkpoint,
                "workflow_owned_workspace": is_workflow_owned_workspace(
                    root, branch=branch, expected_branch_value=None
                ),
            },
        )
    )
    result = WorkspaceRecoveryResult(
        workspace_trust_state=str(session.workspace_trust_state),
        requires_workspace_recovery=bool(session.requires_workspace_recovery),
        recovery_status=RECOVERY_STATUS_NOT_REQUIRED
        if clean
        else RECOVERY_STATUS_HUMAN_REVIEW,
        latest_session_id=int(session.id) if getattr(session, "id", None) else None,
        repo_root=str(root),
        branch=branch or None,
        status_porcelain=status,
        logs=[
            "Trusted checkpoint recorded."
            if clean
            else "Checkpoint recorded but workspace is not clean."
        ],
    )
    result.event_payload = result.model_dump()
    record_recovery_event(
        db, run, event_type="workspace_checkpoint_recorded", result=result
    )
    db.flush()
    return result


def recover_workspace_before_retry(
    db: Session,
    workflow_run_id: int,
    *,
    active_git_process_checker: ActiveGitProcessChecker | None = None,
) -> WorkspaceRecoveryResult:
    """Run workspace recovery preflight and clean only workflow-owned workspaces."""

    run = workflow_run_or_error(db, workflow_run_id)
    session = latest_session_for_workflow(db, workflow_run_id)
    not_required = _recovery_not_required_result(db, run, session)
    if not_required is not None:
        return not_required

    metadata = json_load(session.metadata_json)
    expected_root = Path(str(session.project_root or "")).expanduser().resolve()
    expected = expected_branch(run, metadata)
    logs: list[str] = [f"Recovery requested for session #{int(session.id)}."]
    return _run_recovery_preflight(
        db,
        run,
        session,
        metadata=metadata,
        expected_root=expected_root,
        expected=expected,
        logs=logs,
        active_git_process_checker=active_git_process_checker,
    )


def _recovery_not_required_result(
    db: Session, run: WorkflowRunRow, session: CodexSessionRow | None
) -> WorkspaceRecoveryResult | None:
    if session is None:
        result = WorkspaceRecoveryResult(
            logs=["No Codex runtime session requires recovery."]
        )
    elif bool(getattr(session, "requires_workspace_recovery", False)):
        return None
    else:
        result = WorkspaceRecoveryResult(
            workspace_trust_state=str(
                session.workspace_trust_state or WORKSPACE_TRUST_CLEAN
            ),
            requires_workspace_recovery=False,
            recovery_status=RECOVERY_STATUS_NOT_REQUIRED,
            latest_session_id=int(session.id),
            repo_root=str(session.project_root or "") or None,
            logs=["Workspace recovery not required."],
        )
    result.event_payload = result.model_dump()
    record_recovery_event(
        db, run, event_type="workspace_recovery_not_required", result=result
    )
    return result


def _run_recovery_preflight(
    db: Session,
    run: WorkflowRunRow,
    session: CodexSessionRow,
    *,
    metadata: dict[str, object],
    expected_root: Path,
    expected: str | None,
    logs: list[str],
    active_git_process_checker: ActiveGitProcessChecker | None,
) -> WorkspaceRecoveryResult:
    try:
        repo_root, repo_git_dir, branch = repo_context(expected_root, logs)
        failure = preflight_failure(db, repo_root, expected_root, branch, expected)
        if failure:
            return _fail_recovery(
                db,
                run,
                session,
                root_cause=failure,
                logs=logs,
                status=RECOVERY_STATUS_HUMAN_REVIEW,
                repo_root=repo_root,
                branch=branch,
                expected_branch=expected,
            )
        cleaned_locks, status_after = clean_workspace(
            session,
            repo_root=repo_root,
            repo_git_dir=repo_git_dir,
            logs=logs,
            active_git_process_checker=active_git_process_checker,
        )
        if status_after == "git_process_still_running":
            return _fail_recovery(
                db,
                run,
                session,
                root_cause="git_process_still_running",
                logs=[
                    *logs,
                    "Git lock files exist and an active git process is still running.",
                ],
                status=RECOVERY_STATUS_FAILED,
                repo_root=repo_root,
                branch=branch,
                expected_branch=expected,
            )
        if status_after:
            return _fail_recovery(
                db,
                run,
                session,
                root_cause="workspace_not_clean_after_recovery",
                logs=[*logs, status_after[:1000]],
                status=RECOVERY_STATUS_FAILED,
                repo_root=repo_root,
                branch=branch,
                expected_branch=expected,
                status_porcelain=status_after,
                cleaned_locks=cleaned_locks,
            )
        return _mark_recovered(
            db,
            run,
            session,
            metadata=metadata,
            repo_root=repo_root,
            branch=branch,
            expected_branch_value=expected,
            cleaned_locks=cleaned_locks,
            logs=logs,
        )
    except Exception as exc:
        return _fail_recovery(
            db,
            run,
            session,
            root_cause="workspace_recovery_failed",
            logs=[*logs, str(exc)[:1000]],
            status=RECOVERY_STATUS_FAILED,
        )


def _mark_recovered(
    db: Session,
    run: WorkflowRunRow,
    session: CodexSessionRow,
    *,
    metadata: dict[str, object],
    repo_root: Path,
    branch: str,
    expected_branch_value: str | None,
    cleaned_locks: list[str],
    logs: list[str],
) -> WorkspaceRecoveryResult:
    session.workspace_trust_state = WORKSPACE_TRUST_CLEAN
    session.requires_workspace_recovery = False
    session.status = "resumable"
    session.metadata_json = json_dump(
        merge_metadata(
            metadata,
            {
                "workspace_trust_state": WORKSPACE_TRUST_CLEAN,
                "requires_workspace_recovery": False,
                "workspace_recovered_at": utcnow().isoformat(),
                "workspace_recovery_root": str(repo_root),
                "workspace_recovery_branch": branch,
            },
        )
    )
    result = WorkspaceRecoveryResult(
        workspace_trust_state=WORKSPACE_TRUST_CLEAN,
        requires_workspace_recovery=False,
        recovery_status=RECOVERY_STATUS_RECOVERED,
        latest_session_id=int(session.id),
        killed_at=session.killed_at.isoformat() if session.killed_at else None,
        kill_signal=str(session.kill_signal or "") or None,
        repo_root=str(repo_root),
        branch=branch or None,
        expected_branch=expected_branch_value,
        cleaned_locks=cleaned_locks,
        logs=[*logs, "Workspace recovered; safe to retry agent."],
    )
    result.event_payload = result.model_dump()
    record_recovery_event(db, run, event_type="workspace_recovered", result=result)
    db.flush()
    return result


def _fail_recovery(
    db: Session,
    run: WorkflowRunRow,
    session: CodexSessionRow,
    *,
    root_cause: str,
    logs: list[str],
    status: str,
    repo_root: Path | None = None,
    branch: str | None = None,
    expected_branch: str | None = None,
    status_porcelain: str = "",
    cleaned_locks: list[str] | None = None,
) -> WorkspaceRecoveryResult:
    session.workspace_trust_state = WORKSPACE_TRUST_RECOVERY_FAILED
    session.requires_workspace_recovery = True
    session.status = "recovery_failed"
    session.metadata_json = json_dump(
        merge_metadata(
            json_load(session.metadata_json),
            {
                "workspace_trust_state": WORKSPACE_TRUST_RECOVERY_FAILED,
                "requires_workspace_recovery": True,
                "workspace_recovery_failed_at": utcnow().isoformat(),
                "workspace_recovery_root_cause": root_cause,
            },
        )
    )
    result = WorkspaceRecoveryResult(
        workspace_trust_state=WORKSPACE_TRUST_RECOVERY_FAILED,
        requires_workspace_recovery=True,
        recovery_status=status,
        latest_session_id=int(session.id),
        killed_at=session.killed_at.isoformat() if session.killed_at else None,
        kill_signal=str(session.kill_signal or "") or None,
        repo_root=str(repo_root)
        if repo_root
        else str(session.project_root or "") or None,
        branch=branch or None,
        expected_branch=expected_branch,
        root_cause=root_cause,
        cleaned_locks=list(cleaned_locks or []),
        status_porcelain=status_porcelain,
        logs=logs,
    )
    result.event_payload = result.model_dump()
    record_recovery_event(
        db, run, event_type="workspace_recovery_failed", result=result
    )
    db.flush()
    return result
