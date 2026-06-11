"""Pydantic result contracts for AI visibility feed diagnosis."""

from __future__ import annotations

from pydantic import BaseModel, Field

TARGET_PLATFORMS = ["chatgpt", "claude", "grok", "gemini"]
BRAND_COLLISIONS = {
    "azure synapse analytics",
    "mcpsynapse.dev",
    "project synapse",
    "sage bionetworks",
    "sage bionetworks synapse",
    "synapse protocol",
}
API_MONETIZATION_COMPETITORS = {
    "amberflo",
    "lago",
    "moesif",
    "rapidapi",
    "stripe",
    "x402",
    "zuplo",
}


class SourceHostExecution(BaseModel):
    surface: str
    draft_type: str
    priority: str
    target_platforms: list[str]
    target_queries: list[str]
    rationale: str
    content_brief: str
    validation_command: str
    next_probe_command: str
    evidence_role: str = "source_host_intent_not_external_citation"


class FeedDiagnosisIssue(BaseModel):
    issue_key: str
    severity: str
    summary: str
    terms: list[str] = Field(default_factory=list)


class FeedDiagnosisCommands(BaseModel):
    record_probe: str
    summarize_cycle: str
    rerun_api_probe: str


class FeedDiagnosisScope(BaseModel):
    feed_keys: list[str]
    run_groups: list[str]
    feed_key: str
    run_group: str


class CompetitorMap(BaseModel):
    by_name: dict[str, list[str]]


class FeedDiagnosis(BaseModel):
    module_key: str = "ai_visibility_feed_diagnosis"
    status: str
    generated_at: str
    source_path: str
    feed_key: str
    run_group: str
    feed_keys: list[str]
    run_groups: list[str]
    record_count: int
    external_probe_count: int
    api_probe_blocker_count: int
    provider_failure_count: int = 0
    external_mentioned_count: int
    external_cited_count: int
    target_platforms: list[str]
    covered_platforms: list[str]
    competitors: list[str]
    issues: list[FeedDiagnosisIssue]
    recommended_source_host_executions: list[SourceHostExecution]
    commands: FeedDiagnosisCommands
