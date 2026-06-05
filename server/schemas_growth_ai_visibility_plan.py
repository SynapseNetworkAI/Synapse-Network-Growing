from __future__ import annotations

from pydantic import BaseModel, Field


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
