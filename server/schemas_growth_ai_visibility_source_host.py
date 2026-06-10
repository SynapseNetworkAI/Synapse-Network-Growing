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


class GrowthAIVisibilitySourceHostSubmissionFieldOut(BaseModel):
    label: str
    value: str
    notes: str = ""


class GrowthAIVisibilitySourceHostActionOut(BaseModel):
    host: str
    surface: str
    observed_count: int = 0
    priority: str = "p2"
    draft_type: str = "contextual_source_host_review"
    rationale: str = ""


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
    submission_fields: list[GrowthAIVisibilitySourceHostSubmissionFieldOut] = Field(
        default_factory=list
    )
    submission_steps: list[str] = Field(default_factory=list)
    evidence_recording_steps: list[str] = Field(default_factory=list)
    live_listing_search_urls: list[str] = Field(default_factory=list)
    live_listing_validation_steps: list[str] = Field(default_factory=list)
    latest_live_evidence_status: str = ""
    latest_live_missing_terms: list[str] = Field(default_factory=list)
    latest_live_evidence_url: str = ""
    latest_live_validation_summary: str = ""
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


class GrowthAIVisibilitySourceHostLiveSpotCheckItemOut(BaseModel):
    host: str
    search_url: str
    status: str
    http_status: int = 0
    matched_terms: list[str] = Field(default_factory=list)
    missing_terms: list[str] = Field(default_factory=list)
    evidence_excerpt: str = ""
    next_action: str = ""


class GrowthAIVisibilitySourceHostLiveSpotCheckOut(BaseModel):
    module_key: str = "ai_visibility"
    check_type: str = "source_host_live_spot_check"
    generated_at: datetime
    feed_key: str
    run_group: str = ""
    execute: bool = False
    status: str
    items: list[GrowthAIVisibilitySourceHostLiveSpotCheckItemOut] = Field(
        default_factory=list
    )
    blockers: list[str] = Field(default_factory=list)
    commands: dict[str, str] = Field(default_factory=dict)
