"""Schemas for human-gated multi-channel distribution workflows."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from server.schemas import SocialReplyItemOut


class SocialDistributionAccountOut(BaseModel):
    id: int
    platform: str
    channel_key: str
    display_name: str
    signup_url: str | None = None
    profile_url: str | None = None
    account_type: str = "operator"
    priority: str = "P1"
    status: str = "planned"
    email_hint: str | None = None
    two_factor_status: str = "unknown"
    read_automation_mode: str = "manual_only"
    human_publish_required: bool = True
    publish_mode: str = "manual_only"
    credential_ref_configured: bool = False
    api_capability: str = "none"
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class SocialDistributionAccountAuthStatusOut(BaseModel):
    account_id: int
    platform: str
    channel_key: str
    display_name: str
    login_url: str | None = None
    publish_path: str
    api_status: str
    browser_status: str
    api_supported: bool = False
    can_publish_via_api: bool = False
    can_use_browser_assist: bool = False
    private_web_adapter_enabled: bool = False
    blockers: list[str] = Field(default_factory=list)
    next_action: str
    oauth_status: str | None = None
    requires_authorization: bool = False
    auth_message: str | None = None
    last_checked_at: datetime | None = None


class SocialDistributionAccountAuthStatusListOut(BaseModel):
    items: list[SocialDistributionAccountAuthStatusOut] = Field(default_factory=list)
    generated_at: datetime | None = None


class SocialDistributionAccountPatchRequest(BaseModel):
    profile_url: str | None = None
    status: str | None = None
    email_hint: str | None = None
    two_factor_status: str | None = None
    publish_mode: str | None = None
    credential_ref: str | None = None
    api_capability: str | None = None
    notes: str | None = None


class SocialContentAssetCreateRequest(BaseModel):
    asset_type: str = "article"
    source_type: str = "manual"
    title: str
    body: str | None = None
    summary: str | None = None
    canonical_url: str | None = None
    source_signal_id: int | None = None
    goal_key: str | None = None
    status: str = "draft"
    created_by: str = "operator"


class SocialContentTaskCreateRequest(BaseModel):
    title: str
    source_material: str | None = None
    target_audience: str | None = None
    target_platforms: list[str] = Field(default_factory=list)
    canonical_url: str | None = None
    source_doc_path: str | None = None
    goal_key: str | None = None
    campaign_key: str | None = None
    post_intent: str | None = None
    planned_publish_at: datetime | None = None
    created_by: str = "operator"


class SocialContentAssetPatchRequest(BaseModel):
    title: str | None = None
    body: str | None = None
    summary: str | None = None
    canonical_url: str | None = None
    goal_key: str | None = None
    status: str | None = None


class SocialDistributionEventOut(BaseModel):
    id: int
    asset_id: int
    task_id: int | None = None
    event_type: str
    actor: str
    summary: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime | None = None


class SocialDistributionTaskOut(BaseModel):
    id: int
    asset_id: int
    account_id: int
    platform: str
    channel_key: str
    action: str = "post"
    account_display_name: str | None = None
    signup_url: str | None = None
    publish_mode: str = "manual_only"
    api_capability: str = "none"
    credential_ref_configured: bool = False
    status: str = "planned"
    platform_title: str | None = None
    platform_body: str | None = None
    operator_checklist: str | None = None
    submission_url: str | None = None
    published_url: str | None = None
    external_post_id: str | None = None
    failure_summary: str | None = None
    manual_result_note: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SocialDistributionAuditPublishedPageRequest(BaseModel):
    visibility_status: str
    layout_status: str = "unknown"
    audit_note: str | None = None
    actor: str = "operator"


class SocialDistributionDocumentOut(BaseModel):
    id: int
    asset_id: int
    task_id: int | None = None
    document_kind: str
    platform: str | None = None
    channel_key: str | None = None
    title: str
    body_markdown: str
    status: str = "generated"
    version: int = 1
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SocialContentAssetOut(BaseModel):
    id: int
    asset_type: str
    source_type: str
    title: str
    body: str | None = None
    summary: str | None = None
    canonical_url: str | None = None
    source_signal_id: int | None = None
    goal_key: str | None = None
    policy_check: dict[str, object] = Field(default_factory=dict)
    agent_metadata: dict[str, object] = Field(default_factory=dict)
    status: str = "draft"
    created_by: str = "operator"
    task_count: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SocialContentAssetDetailOut(SocialContentAssetOut):
    tasks: list[SocialDistributionTaskOut] = Field(default_factory=list)
    events: list[SocialDistributionEventOut] = Field(default_factory=list)
    documents: list[SocialDistributionDocumentOut] = Field(default_factory=list)
    reply_items: list[SocialReplyItemOut] = Field(default_factory=list)


class SocialDistributionTaskGroupOut(BaseModel):
    asset: SocialContentAssetOut
    tasks: list[SocialDistributionTaskOut] = Field(default_factory=list)


class SocialDistributionTaskListOut(BaseModel):
    groups: list[SocialDistributionTaskGroupOut] = Field(default_factory=list)
    flat: list[SocialDistributionTaskOut] = Field(default_factory=list)
    total_assets: int = 0
    total_tasks: int = 0
    limit: int = 100
    offset: int = 0


class SocialDistributionBoardCardOut(BaseModel):
    id: str
    asset: SocialContentAssetOut
    column_key: str
    task_kind_code: str = "content_distribution"
    task_kind_label: str = "内容分发"
    task_kind_action: str = "approve_and_generate_platform_docs"
    task_count: int = 0
    document_count: int = 0
    platform_count: int = 0
    failed_count: int = 0
    ready_to_publish_count: int = 0
    live_count: int = 0
    visibility_issue_count: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    document_status_counts: dict[str, int] = Field(default_factory=dict)
    next_action: str
    updated_at: datetime | None = None


class SocialDistributionBoardColumnOut(BaseModel):
    key: str
    title: str
    description: str
    count: int = 0
    cards: list[SocialDistributionBoardCardOut] = Field(default_factory=list)


class SocialDistributionBoardOut(BaseModel):
    columns: list[SocialDistributionBoardColumnOut] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    generated_at: datetime | None = None


class SocialDistributionGenerateContentPlanRequest(BaseModel):
    actor: str = "operator"


class SocialDistributionExpandCanonicalArticleRequest(BaseModel):
    actor: str = "operator"


class SocialDistributionApproveCanonicalArticleRequest(BaseModel):
    actor: str = "operator"
    document_id: int | None = None


class SocialDistributionGenerateTasksRequest(BaseModel):
    account_ids: list[int] = Field(default_factory=list)
    action: str = "post"
    actor: str = "operator"


class SocialDistributionPlatformGenerationOut(BaseModel):
    account_id: int
    platform: str
    channel_key: str
    status: str
    task_id: int | None = None
    error: str | None = None


class SocialDistributionGenerateTasksOut(BaseModel):
    asset: SocialContentAssetDetailOut
    results: list[SocialDistributionPlatformGenerationOut] = Field(default_factory=list)
    generated_task_ids: list[int] = Field(default_factory=list)
    failed_task_ids: list[int] = Field(default_factory=list)


class SocialDistributionApproveGenerateRequest(SocialDistributionGenerateTasksRequest):
    pass


class SocialDistributionGenerateXArticlePackRequest(BaseModel):
    actor: str = "operator"
    article_url: str | None = None
    teaser_include_article_url: bool = False


class SocialDistributionGenerateXArticlePackOut(BaseModel):
    asset: SocialContentAssetDetailOut
    article_task_id: int
    teaser_task_id: int
    article_document_id: int
    cover_image_path: str | None = None


class SocialXReplySourcePostIn(BaseModel):
    source_url: str
    author_handle: str | None = None
    source_text: str
    rationale: str | None = None
    opt_in_evidence: str | None = None


class SocialXReplyBlockGenerateRequest(BaseModel):
    actor: str = "agent"
    target_count: int = 5
    agent_review: bool = True
    max_seconds: int | None = None
    per_reply_timeout_seconds: int | None = None
    auto_publish: bool = False
    force_regenerate: bool = False
    source_posts: list[SocialXReplySourcePostIn] = Field(default_factory=list)


class SocialXReplyBlockGenerateOut(BaseModel):
    asset: SocialContentAssetDetailOut
    reply_ids: list[int] = Field(default_factory=list)
    failed_reply_ids: list[int] = Field(default_factory=list)
    source_candidate_ids: list[int] = Field(default_factory=list)
    processed_source_count: int = 0
    auto_publish: bool = False
    timed_out: bool = False
    blocked_reason: str | None = None
    agent_review: bool = True
    publish_mode: str = "agent_approved_needs_manual_publish"
    approval_ref_configured: bool = False


class SocialAssetPlannerSignalOut(BaseModel):
    signal_type: str
    source_ref: str
    title: str
    summary: str
    score: float = 0.0


class SocialAssetPlannerRunOut(BaseModel):
    workflow_key: str = "social_asset_planner_sweep"
    local_date: str
    target_count: int = 3
    active_count: int = 0
    no_asset_created: bool = False
    already_satisfied: bool = False
    selected_asset_type: str | None = None
    selected_signal_count: int = 0
    reason: str | None = None
    created_asset_id: int | None = None
    asset: SocialContentAssetDetailOut | None = None
    signals: list[SocialAssetPlannerSignalOut] = Field(default_factory=list)


class SocialDistributionCampaignTemplateOut(BaseModel):
    campaign_key: str
    created_count: int = 0
    existing_count: int = 0
    assets: list[SocialContentAssetDetailOut] = Field(default_factory=list)


class SocialDistributionTaskPatchRequest(BaseModel):
    platform_title: str | None = None
    platform_body: str | None = None
    operator_checklist: str | None = None
    submission_url: str | None = None
    published_url: str | None = None
    external_post_id: str | None = None
    failure_summary: str | None = None
    manual_result_note: str | None = None
    status: str | None = None


class SocialDistributionMarkLiveRequest(BaseModel):
    published_url: str
    manual_result_note: str | None = None
    actor: str = "operator"


class SocialDistributionMarkRemovedRequest(BaseModel):
    manual_result_note: str
    actor: str = "operator"


class SocialDistributionPublishXRequest(BaseModel):
    actor: str = "operator"


class SocialDistributionXAuthStatusOut(BaseModel):
    status: str
    can_publish: bool
    account_id: int | None = None
    account_handle: str | None = None
    auth_message: str | None = None
    requires_authorization: bool = False
    refresh_token_rotated: bool = False
