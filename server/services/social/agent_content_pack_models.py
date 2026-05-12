"""Typed outputs for agent-generated content packs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CanonicalCodeBlock(BaseModel):
    language: str = ""
    title: str = ""
    code: str = ""


class CanonicalAssetPack(BaseModel):
    title: str
    summary: str
    body: str
    asset_type: str
    source_type: str = "asset_planner"
    goal_key: str | None = None
    key_facts: list[str] = Field(default_factory=list)
    code_blocks: list[CanonicalCodeBlock] = Field(default_factory=list)
    recommended_channels: list[str] = Field(default_factory=list)
    source_signal_refs: list[str] = Field(default_factory=list)
    generation_reason: str = ""
    context_refs: list[str] = Field(default_factory=list)
    context_sources: list[str] = Field(default_factory=list)
    generation_metadata: dict[str, object] = Field(default_factory=dict)


class AgentDistributionDraft(BaseModel):
    title: str
    body: str
    checklist: str
    risk_level: str = "normal"
    rationale: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


class CanonicalArticleExpansion(BaseModel):
    title: str
    summary: str
    body_markdown: str
    key_facts: list[str] = Field(default_factory=list)
    generation_reason: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


class AgentContentGenerationError(ValueError):
    code = "agent_content_generation_failed"
