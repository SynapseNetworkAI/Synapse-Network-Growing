from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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
    feed_key: str = ""
    run_group: str = ""
    result_rank: int = 0
    evidence_url: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


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


class GrowthAIVisibilityComparisonOut(BaseModel):
    feed_key: str
    run_group: str
    previous_run_group: str = ""
    platforms: list[str] = Field(default_factory=list)
    external_platforms: list[str] = Field(default_factory=list)
    total_checks: int = 0
    external_checks_count: int = 0
    local_validation_count: int = 0
    mentioned_count: int = 0
    cited_count: int = 0
    previous_mentioned_count: int = 0
    previous_cited_count: int = 0
    mentioned_delta: int = 0
    cited_delta: int = 0
    comparison_status: str = "baseline"
    citation_quality_status: str = "unknown"
    feed_effective: bool = False
    missing_platforms: list[str] = Field(default_factory=list)
    top_competitors: list[str] = Field(default_factory=list)
    known_collision_competitors: list[str] = Field(default_factory=list)
    official_cited_urls: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    latest_run_at: Optional[datetime] = None


class GrowthAIVisibilityComparisonListOut(BaseModel):
    items: list[GrowthAIVisibilityComparisonOut] = Field(default_factory=list)
    total: int = 0


class GrowthAIVisibilityFeedReportOut(BaseModel):
    feed_key: str
    latest_run_group: str = ""
    comparison_status: str = "needs_external_probe"
    citation_quality_status: str = "unknown"
    feed_effective: bool = False
    external_platforms: list[str] = Field(default_factory=list)
    missing_platforms: list[str] = Field(default_factory=list)
    known_collision_competitors: list[str] = Field(default_factory=list)
    official_cited_urls: list[str] = Field(default_factory=list)
    mentioned_count: int = 0
    cited_count: int = 0
    mentioned_delta: int = 0
    cited_delta: int = 0
    latest_run_at: Optional[datetime] = None
    next_actions: list[str] = Field(default_factory=list)


class GrowthAIVisibilityWeeklyReportOut(BaseModel):
    module_key: str = "ai_visibility"
    generated_at: datetime
    goal_status: str
    goal_achieved: bool = False
    required_stable_runs: int = 3
    stable_positive_runs: int = 0
    target_platforms: list[str] = Field(default_factory=list)
    covered_platforms: list[str] = Field(default_factory=list)
    missing_platforms: list[str] = Field(default_factory=list)
    total_external_checks: int = 0
    total_mentioned_count: int = 0
    total_cited_count: int = 0
    latest_feed_key: str = ""
    latest_run_group: str = ""
    latest_comparison_status: str = "needs_external_probe"
    feed_reports: list[GrowthAIVisibilityFeedReportOut] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    recommended_feed_key: str = ""
    recommended_probe_template_command: str = ""


class GrowthAIVisibilityNextCycleOut(BaseModel):
    module_key: str = "ai_visibility"
    feed_key: str
    run_group: str
    output_path: str
    missing_platforms: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    feed_validation_command: str
    manual_probe_template_command: str
    api_readiness_command: str
    api_execute_command: str
    apply_command: str
    compare_command: str
    weekly_report_command: str


class GrowthAIVisibilityReleaseCommandGroupOut(BaseModel):
    key: str
    purpose: str
    commands: list[str] = Field(default_factory=list)
    service_key: str = ""
    environment: str = ""
    notes: list[str] = Field(default_factory=list)


class GrowthAIVisibilityReleaseUnblockPlanOut(BaseModel):
    module_key: str = "ai_visibility"
    feed_key: str = "mcp_paid_api_discovery"
    status: str
    generated_at: datetime
    official_homepage: str = "https://www.synapse-network.ai/"
    project_key: str = "synapse-network"
    services: list[str] = Field(default_factory=list)
    branch_name: str = "main"
    target_commit_sha: str
    actor: str
    source_pr: dict[str, object] = Field(default_factory=dict)
    source_prs: list[dict[str, object]] = Field(default_factory=list)
    predeploy_evidence: dict[str, object] = Field(default_factory=dict)
    deploy_readiness_status: str = "unknown"
    deployment_gaps: list[dict[str, object]] = Field(default_factory=list)
    confirmed_facts: list[str] = Field(default_factory=list)
    hard_boundaries: list[str] = Field(default_factory=list)
    known_blockers: list[str] = Field(default_factory=list)
    environment_defaults: dict[str, object] = Field(default_factory=dict)
    command_groups: list[GrowthAIVisibilityReleaseCommandGroupOut] = Field(
        default_factory=list
    )
    success_criteria: list[str] = Field(default_factory=list)


class GrowthAIVisibilityReleaseSnapshotOut(BaseModel):
    module_key: str = "ai_visibility"
    snapshot_type: str = "release_blocker"
    generated_at: datetime
    feed_key: str
    run_group: str
    target_commit_sha: str
    official_homepage: str = "https://www.synapse-network.ai/"
    status: str
    release_plan_status: str
    deploy_readiness_status: str
    confirmed_facts: list[str] = Field(default_factory=list)
    deployment_gaps: list[dict[str, object]] = Field(default_factory=list)
    live_readiness: dict[str, object] = Field(default_factory=dict)
    gcloud: dict[str, object] = Field(default_factory=dict)
    external_probe_keys: dict[str, object] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class GrowthAIVisibilityHandoffBundleOut(BaseModel):
    module_key: str = "ai_visibility"
    bundle_type: str = "operator_handoff"
    generated_at: datetime
    feed_key: str
    run_group: str
    target_commit_sha: str
    official_homepage: str = "https://www.synapse-network.ai/"
    status: str
    release_status: str
    live_readiness_status: str
    external_probe_gate_status: str
    ready_platforms: list[str] = Field(default_factory=list)
    missing_platforms: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)
    commands: dict[str, str] = Field(default_factory=dict)


class GrowthAIVisibilityFeedCycleOut(BaseModel):
    feed_key: str
    status: str
    objective: str = ""
    latest_run_group: str = ""
    latest_comparison_status: str = "needs_external_probe"
    feed_ready: bool = False
    external_probe_ready: bool = False
    feed_effective: bool = False
    external_platforms: list[str] = Field(default_factory=list)
    missing_platforms: list[str] = Field(default_factory=list)
    mentioned_count: int = 0
    cited_count: int = 0
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    publish_surfaces: list[str] = Field(default_factory=list)
    feed_validation_command: str
    manual_probe_template_command: str
    api_readiness_command: str
    api_execute_command: str
    compare_command: str
    latest_run_at: Optional[datetime] = None


class GrowthAIVisibilityFeedCycleListOut(BaseModel):
    module_key: str = "ai_visibility"
    generated_at: datetime
    target_platforms: list[str] = Field(default_factory=list)
    recommended_feed_key: str = ""
    items: list[GrowthAIVisibilityFeedCycleOut] = Field(default_factory=list)
    total: int = 0


class GrowthAIVisibilityLiveReadinessCheckOut(BaseModel):
    label: str
    url: str
    status: int = 0
    ok: bool = False
    final_url: str = ""
    error: str = ""
    contains_synapse: bool = False


class GrowthAIVisibilityLiveReadinessItemOut(BaseModel):
    feed_key: str
    status: str
    feed_ready: bool = False
    external_probe_ready: bool = False
    run_group: str
    platform: str
    query: str
    answer_summary: str = ""
    checked_urls: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    next_action: str = ""
    checks: list[GrowthAIVisibilityLiveReadinessCheckOut] = Field(default_factory=list)


class GrowthAIVisibilityLiveReadinessOut(BaseModel):
    module_key: str = "ai_visibility"
    generated_at: datetime
    run_group: str
    canonical_homepage: str = "https://www.synapse-network.ai/"
    status: str
    ready_count: int = 0
    blocked_count: int = 0
    validation_command: str
    apply_command: str
    items: list[GrowthAIVisibilityLiveReadinessItemOut] = Field(default_factory=list)
    total: int = 0


class GrowthAIVisibilityExternalProbeProviderOut(BaseModel):
    platform: str
    env_key: str
    configured: bool = False


class GrowthAIVisibilityExternalProbeGateOut(BaseModel):
    module_key: str = "ai_visibility"
    generated_at: datetime
    feed_key: str
    run_group: str
    status: str
    ready_to_execute: bool = False
    partial_ready_to_execute: bool = False
    manual_ready_to_execute: bool = False
    feed_ready: bool = False
    api_keys_ready: bool = False
    target_platforms: list[str] = Field(default_factory=list)
    ready_platforms: list[str] = Field(default_factory=list)
    missing_platforms: list[str] = Field(default_factory=list)
    provider_readiness: list[GrowthAIVisibilityExternalProbeProviderOut] = Field(
        default_factory=list
    )
    blockers: list[str] = Field(default_factory=list)
    feed_validation_command: str
    record_readiness_command: str
    manual_probe_template_command: str = ""
    api_readiness_command: str
    api_execute_command: str
    partial_api_readiness_command: str = ""
    partial_api_execute_command: str = ""
    record_probe_command: str
    compare_command: str


class GrowthAIVisibilityFeedScoreOut(BaseModel):
    feed_key: str
    rank: int = 0
    impact_score: int = 0
    status: str
    objective: str = ""
    latest_run_group: str = ""
    comparison_status: str = "needs_external_probe"
    citation_quality_status: str = "unknown"
    feed_ready: bool = False
    external_probe_ready: bool = False
    feed_effective: bool = False
    target_platforms: list[str] = Field(default_factory=list)
    covered_platforms: list[str] = Field(default_factory=list)
    missing_platforms: list[str] = Field(default_factory=list)
    external_checks_count: int = 0
    local_validation_count: int = 0
    mentioned_count: int = 0
    cited_count: int = 0
    known_collision_competitors: list[str] = Field(default_factory=list)
    official_cited_urls: list[str] = Field(default_factory=list)
    mentioned_delta: int = 0
    cited_delta: int = 0
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    recommended_action: str = ""
    feed_validation_command: str
    api_readiness_command: str
    api_execute_command: str
    compare_command: str


class GrowthAIVisibilityFeedScorecardOut(BaseModel):
    module_key: str = "ai_visibility"
    generated_at: datetime
    recommended_feed_key: str = ""
    ranking_basis: str = ""
    items: list[GrowthAIVisibilityFeedScoreOut] = Field(default_factory=list)
    total: int = 0


class GrowthAIVisibilityOptimizationBriefOut(BaseModel):
    module_key: str = "ai_visibility"
    title: str
    status: str
    generated_at: datetime
    official_homepage: str = "https://www.synapse-network.ai/"
    recommended_feed_key: str = ""
    target_platforms: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    artifact_path: str
    export_command: str
    markdown: str


class GrowthAIVisibilityQueryOut(BaseModel):
    query: str
    intent: str
    target_platforms: list[str] = Field(default_factory=list)
    success_signal: str


class GrowthAIVisibilityFeedExperimentOut(BaseModel):
    feed_key: str
    surfaces: list[str] = Field(default_factory=list)
    content_assets: list[str] = Field(default_factory=list)
    target_queries: list[str] = Field(default_factory=list)
    measurement_window_days: int = 14


class GrowthAIVisibilityFeedAssetOut(BaseModel):
    surface: str
    target: str
    purpose: str
    validation: str


class GrowthAIVisibilityPlatformStrategyOut(BaseModel):
    platform: str
    feed_focus: str
    preferred_surfaces: list[str] = Field(default_factory=list)
    probe_queries: list[str] = Field(default_factory=list)
    success_signal: str
    fallback_action: str


class GrowthAIVisibilityFeedPackageOut(BaseModel):
    feed_key: str
    objective: str
    canonical_domain: str = "https://www.synapse-network.ai/"
    surfaces: list[str] = Field(default_factory=list)
    content_assets: list[str] = Field(default_factory=list)
    target_queries: list[str] = Field(default_factory=list)
    publish_assets: list[GrowthAIVisibilityFeedAssetOut] = Field(default_factory=list)
    platform_strategies: list[GrowthAIVisibilityPlatformStrategyOut] = Field(
        default_factory=list
    )
    stitch_prompt: str = ""
    figma_handoff: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    probe_template_command: str
    success_metrics: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class GrowthAIVisibilityFeedPackageListOut(BaseModel):
    items: list[GrowthAIVisibilityFeedPackageOut] = Field(default_factory=list)
    total: int = 0


class GrowthAIVisibilityDocsPlanOut(BaseModel):
    canonical_domain: str = "https://www.synapse-network.ai/"
    docs_category: str
    pages: list[str] = Field(default_factory=list)
    required_blocks: list[str] = Field(default_factory=list)
    schema_types: list[str] = Field(default_factory=list)


class GrowthAIVisibilityDocsPageBlueprintOut(BaseModel):
    slug: str
    title: str
    canonical_url: str
    meta_description: str
    target_queries: list[str] = Field(default_factory=list)
    definition_block: str
    fact_table: list[dict[str, str]] = Field(default_factory=list)
    page_sections: list[str] = Field(default_factory=list)
    faq: list[dict[str, str]] = Field(default_factory=list)
    schema_types: list[str] = Field(default_factory=list)
    stitch_notes: list[str] = Field(default_factory=list)
    figma_components: list[str] = Field(default_factory=list)
    mdx_skeleton: str
    validation_commands: list[str] = Field(default_factory=list)


class GrowthAIVisibilityDocsBlueprintOut(BaseModel):
    category: str
    canonical_domain: str = "https://www.synapse-network.ai/"
    target_repo: str = "Synapse-Network"
    implementation_root: str = "services/docs-front/content/docs/ai-agent-payments"
    pages: list[GrowthAIVisibilityDocsPageBlueprintOut] = Field(default_factory=list)
    shared_components: list[str] = Field(default_factory=list)
    publishing_checklist: list[str] = Field(default_factory=list)


class GrowthAIVisibilityDesignFrameOut(BaseModel):
    name: str
    purpose: str
    source_page_slug: str
    layout_notes: list[str] = Field(default_factory=list)
    figma_components: list[str] = Field(default_factory=list)
    stitch_prompt: str


class GrowthAIVisibilityDesignHandoffOut(BaseModel):
    title: str
    canonical_domain: str = "https://www.synapse-network.ai/"
    source_tool: str = "Stitch"
    target_tool: str = "Figma"
    figma_file_name: str
    stitch_prompt: str
    frames: list[GrowthAIVisibilityDesignFrameOut] = Field(default_factory=list)
    component_specs: list[dict[str, str]] = Field(default_factory=list)
    design_tokens: dict[str, str] = Field(default_factory=dict)
    import_steps: list[str] = Field(default_factory=list)
    implementation_notes: list[str] = Field(default_factory=list)
    acceptance_checks: list[str] = Field(default_factory=list)


class GrowthAIVisibilityDesignPlanOut(BaseModel):
    stitch_prompt: str
    figma_handoff: list[str] = Field(default_factory=list)
    implementation_targets: list[str] = Field(default_factory=list)


class GrowthAIVisibilityOptimizationPlanOut(BaseModel):
    module_key: str = "ai_visibility"
    objective: str
    canonical_domain: str = "https://www.synapse-network.ai/"
    critical_fixes: list[str] = Field(default_factory=list)
    baseline_queries: list[GrowthAIVisibilityQueryOut] = Field(default_factory=list)
    feed_experiments: list[GrowthAIVisibilityFeedExperimentOut] = Field(
        default_factory=list
    )
    product_docs: GrowthAIVisibilityDocsPlanOut
    design_plan: GrowthAIVisibilityDesignPlanOut
    growing_workflows: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
