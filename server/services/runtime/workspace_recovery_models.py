from __future__ import annotations

"""Typed state contracts for deterministic workspace recovery."""

from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field


WORKSPACE_TRUST_CLEAN = "clean"
WORKSPACE_TRUST_DIRTY_AFTER_KILL = "dirty_after_kill"
WORKSPACE_TRUST_RECOVERY_REQUIRED = "recovery_required"
WORKSPACE_TRUST_RECOVERY_FAILED = "recovery_failed"

RECOVERY_STATUS_NOT_REQUIRED = "not_required"
RECOVERY_STATUS_RECOVERED = "recovered"
RECOVERY_STATUS_FAILED = "failed"
RECOVERY_STATUS_HUMAN_REVIEW = "human_review"

ActiveGitProcessChecker = Callable[[Path], bool]


class WorkspaceRecoverySummary(BaseModel):
    workspace_trust_state: str = WORKSPACE_TRUST_CLEAN
    requires_workspace_recovery: bool = False
    recovery_status: str = RECOVERY_STATUS_NOT_REQUIRED
    root_cause: str | None = None
    latest_session_id: int | None = None
    killed_at: str | None = None
    kill_signal: str | None = None
    repo_root: str | None = None
    branch: str | None = None
    expected_branch: str | None = None
    logs: list[str] = Field(default_factory=list)


class WorkspaceRecoveryResult(WorkspaceRecoverySummary):
    cleaned_locks: list[str] = Field(default_factory=list)
    status_porcelain: str = ""
    event_payload: dict[str, object] = Field(default_factory=dict)
