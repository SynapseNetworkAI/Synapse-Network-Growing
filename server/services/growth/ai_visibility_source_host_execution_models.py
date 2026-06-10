"""Pydantic contracts for AI visibility source-host execution evidence."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceHostExecutionEvidence(BaseModel):
    module_key: str = "ai_visibility_source_host_execution"
    status: str
    evidence_type: str = "live_source_host"
    feed_key: str
    run_group: str
    surface: str
    source_url: str
    checked_at: str
    required_terms: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)
    missing_terms: list[str] = Field(default_factory=list)
    content_sha256: str = ""
    content_bytes: int = 0
    target_platforms: list[str] = Field(default_factory=list)
    target_queries: list[str] = Field(default_factory=list)
    evidence_role: str = "source_host_live_evidence_not_external_citation"
    design_handoff_frame: str = ""
    submitted_payload_summary: str = ""
    screenshot_url: str = ""
    validation_summary: str
    next_probe_command: str
