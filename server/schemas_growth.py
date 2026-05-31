from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GrowthLeadCreate(BaseModel):
    lead_type: str
    project_key: str = "growing"
    name: str
    organization: str = ""
    role_title: str = ""
    public_profile_urls: list[str] = Field(default_factory=list)
    contact_channels: list[dict[str, object]] = Field(default_factory=list)
    source_kind: str = "manual"
    source_url: str = ""
    status: str = "new"
    fit_score: int = 0
    confidence_score: int = 0
    risk_flags: list[str] = Field(default_factory=list)
    evidence: list[dict[str, object]] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    next_action: str = ""


class GrowthLeadOut(GrowthLeadCreate):
    id: int
    last_contacted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GrowthLeadListOut(BaseModel):
    items: list[GrowthLeadOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    lead_type_counts: dict[str, int] = Field(default_factory=dict)


class GrowthLeadImportRequest(BaseModel):
    leads: list[GrowthLeadCreate] = Field(default_factory=list)


class GrowthLeadImportOut(BaseModel):
    created: int = 0
    reused: int = 0
    items: list[GrowthLeadOut] = Field(default_factory=list)


class GrowthSourceConfigCreate(BaseModel):
    config_key: str = ""
    name: str
    config_type: str
    status: str = "enabled"
    description: str = ""
    query: dict[str, object] = Field(default_factory=dict)
    cadence: dict[str, object] = Field(default_factory=dict)
    thresholds: dict[str, object] = Field(default_factory=dict)


class GrowthSourceConfigPatch(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    query: Optional[dict[str, object]] = None
    cadence: Optional[dict[str, object]] = None
    thresholds: Optional[dict[str, object]] = None


class GrowthSourceConfigOut(GrowthSourceConfigCreate):
    id: int
    last_run_at: Optional[datetime] = None
    last_result: dict[str, object] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GrowthSourceConfigListOut(BaseModel):
    items: list[GrowthSourceConfigOut] = Field(default_factory=list)
    total: int = 0


class GrowthSourceRunRequest(BaseModel):
    dry_run: bool = True
    max_results: Optional[int] = None
    create_drafts: bool = True
    actor: str = "operator"


class GrowthResearchRunOut(BaseModel):
    id: int
    source_config_id: int
    status: str
    dry_run: bool = False
    params: dict[str, object] = Field(default_factory=dict)
    candidate_count: int = 0
    created_count: int = 0
    reused_count: int = 0
    drafted_count: int = 0
    error_summary: str = ""
    result: dict[str, object] = Field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GrowthResearchRunListOut(BaseModel):
    items: list[GrowthResearchRunOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class GrowthOutreachMessageOut(BaseModel):
    id: int
    lead_id: int
    campaign_id: Optional[int] = None
    channel: str
    subject: str
    body: str
    personalization_evidence: list[dict[str, object]] = Field(default_factory=list)
    status: str
    approved_by: Optional[str] = None
    sent_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GrowthOutreachEventOut(BaseModel):
    id: int
    lead_id: Optional[int] = None
    message_id: Optional[int] = None
    event_type: str
    actor: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    summary: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class GrowthLeadDetailOut(BaseModel):
    lead: GrowthLeadOut
    messages: list[GrowthOutreachMessageOut] = Field(default_factory=list)
    events: list[GrowthOutreachEventOut] = Field(default_factory=list)


class GrowthDraftMessageRequest(BaseModel):
    campaign_id: Optional[int] = None
    channel: str = "email"
    actor: str = "agent"
    notes: str = ""


class GrowthMessageActionRequest(BaseModel):
    actor: str = "operator"
    summary: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


class GrowthReplyRequest(GrowthMessageActionRequest):
    reply_summary: str
    interested: bool = False


class GrowthAIVisibilityCheckCreate(BaseModel):
    query: str
    platform: str
    answer_summary: str = ""
    synapse_mentioned: bool = False
    synapse_cited: bool = False
    cited_urls: list[str] = Field(default_factory=list)
    competitor_mentions: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    next_action: str = ""


class GrowthAIVisibilityCheckOut(GrowthAIVisibilityCheckCreate):
    id: int
    run_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GrowthAIVisibilityCheckListOut(BaseModel):
    items: list[GrowthAIVisibilityCheckOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class GrowthDiscoveryListingCreate(BaseModel):
    surface: str
    target_repo: str = ""
    package_name: str = ""
    listing_url: str = ""
    status: str = "candidate"
    submission_evidence: dict[str, object] = Field(default_factory=dict)
    verification_evidence: dict[str, object] = Field(default_factory=dict)
    failure_reason: str = ""


class GrowthDiscoveryListingPatch(BaseModel):
    status: Optional[str] = None
    listing_url: Optional[str] = None
    submission_evidence: Optional[dict[str, object]] = None
    verification_evidence: Optional[dict[str, object]] = None
    failure_reason: Optional[str] = None


class GrowthDiscoveryListingOut(GrowthDiscoveryListingCreate):
    id: int
    last_checked_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GrowthDiscoveryListingListOut(BaseModel):
    items: list[GrowthDiscoveryListingOut] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class GrowthOverviewOut(BaseModel):
    lead_counts: dict[str, int] = Field(default_factory=dict)
    message_counts: dict[str, int] = Field(default_factory=dict)
    ai_visibility: dict[str, int] = Field(default_factory=dict)
    discovery_counts: dict[str, int] = Field(default_factory=dict)
