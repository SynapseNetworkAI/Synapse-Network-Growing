"""Schemas for local CI runner APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LocalCiRunCreateRequest(BaseModel):
    repo_path: str
    branch_name: str
    commit_sha: str
    base_ref: str = "origin/main"
    scope: str = "auto"
    actor: str = "operator"
    metadata: dict[str, object] = Field(default_factory=dict)


class LocalCiRunResetRequest(BaseModel):
    confirm_phrase: str
    actor: str = "operator"
    reason: str | None = None


class LocalCiRunOut(BaseModel):
    id: int
    repo_path: str
    branch_name: str
    commit_sha: str
    base_ref: str = "origin/main"
    scope: str = "auto"
    status: str = "requested"
    actor: str = "operator"
    exit_code: int | None = None
    summary: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LocalCiRunsPageOut(BaseModel):
    items: list[LocalCiRunOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class LocalCiEventOut(BaseModel):
    id: int
    ci_run_id: int
    sequence: int
    event_type: str
    step_key: str | None = None
    message: str = ""
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class LocalCiEventsPageOut(BaseModel):
    items: list[LocalCiEventOut] = Field(default_factory=list)
    next_sequence: int = 0
    has_more: bool = False
