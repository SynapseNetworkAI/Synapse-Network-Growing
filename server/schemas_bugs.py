from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from server.schemas import BugRecordOut


class BugFixAttemptOut(BaseModel):
    id: int
    bug_id: int
    status: str
    agent_id: str
    branch_name: Optional[str] = None
    commit_sha: Optional[str] = None
    pr_url: Optional[str] = None
    workflow_run_id: Optional[int] = None
    requirement_id: Optional[int] = None
    lease_expires_at: Optional[datetime] = None
    verification_summary: Optional[str] = None
    verification_commands: list[dict[str, object]] = Field(default_factory=list)
    verification_screenshots: list[dict[str, object]] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None


class BugEventOut(BaseModel):
    id: int
    bug_id: int
    event_type: str
    actor: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    message: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class BugAgentContextOut(BaseModel):
    bug_id: int
    bug_key: str
    project_key: Optional[str] = None
    target_project_path: Optional[str] = None
    title: str
    summary: str
    repro_steps: list[str] = Field(default_factory=list)
    expected_behavior: Optional[str] = None
    actual_behavior: Optional[str] = None
    evidence: list[dict[str, object]] = Field(default_factory=list)
    acceptance_checks: list[str] = Field(default_factory=list)
    linked_requirement_id: Optional[int] = None
    allowed_next_actions: list[str] = Field(default_factory=list)


class BugListOut(BaseModel):
    items: list[BugRecordOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    severity_counts: dict[str, int] = Field(default_factory=dict)


class BugDetailOut(BaseModel):
    bug: BugRecordOut
    latest_fix_attempt: Optional[BugFixAttemptOut] = None
    fix_attempts: list[BugFixAttemptOut] = Field(default_factory=list)
    events: list[BugEventOut] = Field(default_factory=list)
    agent_context: BugAgentContextOut


class BugAgentQueueOut(BaseModel):
    items: list[BugDetailOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0


class BugClaimRequest(BaseModel):
    agent_id: str = "agent"
    lease_minutes: int = 120


class BugClaimResultOut(BaseModel):
    bug: BugRecordOut
    fix_attempt: BugFixAttemptOut
    agent_context: BugAgentContextOut


class BugLinkFixRequest(BaseModel):
    agent_id: str = "agent"
    branch_name: Optional[str] = None
    commit_sha: Optional[str] = None
    pr_url: Optional[str] = None
    workflow_run_id: Optional[int] = None
    requirement_id: Optional[int] = None


class BugVerificationRequest(BaseModel):
    agent_id: str = "agent"
    status: str = "fixed_pending_verification"
    summary: str
    commands: list[dict[str, object]] = Field(default_factory=list)
    screenshots: list[dict[str, object]] = Field(default_factory=list)


class BugCloseRequest(BaseModel):
    actor: str = "agent"
    resolution: str = "verified"


class BugReopenRequest(BaseModel):
    actor: str = "agent"
    reason: str
