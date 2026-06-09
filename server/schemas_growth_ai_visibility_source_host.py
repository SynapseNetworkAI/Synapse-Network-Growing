from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GrowthAIVisibilitySourceHostDraftOut(BaseModel):
    host: str
    priority: int = 0
    draft_type: str
    status: str
    target_url: str
    submit_url: str = ""
    title: str
    summary: str
    body_markdown: str
    source_reference_url: str = ""
    submission_payload: dict[str, Any] = Field(default_factory=dict)
    validation_command: str
    probe_followup: str
    operator_notes: list[str] = Field(default_factory=list)


class GrowthAIVisibilitySourceHostFeedPackageOut(BaseModel):
    module_key: str = "ai_visibility"
    package_type: str = "source_host_feed"
    generated_at: datetime
    feed_key: str
    run_group: str = ""
    status: str
    source_hosts: list[str] = Field(default_factory=list)
    drafts: list[GrowthAIVisibilitySourceHostDraftOut] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    commands: dict[str, str] = Field(default_factory=dict)


class GrowthAIVisibilitySourceHostExecutionItemOut(BaseModel):
    key: str
    host: str
    priority: int = 0
    draft_type: str
    execution_status: str
    target_url: str
    design_handoff_frame: str = ""
    action_required: str
    required_evidence: list[str] = Field(default_factory=list)
    submission_confirmation_command: str = ""
    validation_command: str
    re_probe_command: str
    completion_gate: str


class GrowthAIVisibilitySourceHostExecutionChecklistOut(BaseModel):
    module_key: str = "ai_visibility"
    checklist_type: str = "source_host_feed_execution"
    generated_at: datetime
    feed_key: str
    run_group: str = ""
    status: str
    items: list[GrowthAIVisibilitySourceHostExecutionItemOut] = Field(
        default_factory=list
    )
    blockers: list[str] = Field(default_factory=list)
    commands: dict[str, str] = Field(default_factory=dict)
