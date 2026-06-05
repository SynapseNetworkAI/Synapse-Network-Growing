export interface GrowthAIVisibilityQuery {
  query: string
  intent: string
  target_platforms: string[]
  success_signal: string
}
export interface GrowthAIVisibilityFeedExperiment {
  feed_key: string
  surfaces: string[]
  content_assets: string[]
  target_queries: string[]
  measurement_window_days: number
}
export interface GrowthAIVisibilityPlatformStrategy {
  platform: string
  feed_focus: string
  preferred_surfaces: string[]
  probe_queries: string[]
  success_signal: string
  fallback_action: string
}
export interface GrowthAIVisibilityFeedAsset {
  surface: string
  target: string
  purpose: string
  validation: string
}
export interface GrowthAIVisibilityFeedPackage {
  feed_key: string
  objective: string
  canonical_domain: string
  surfaces: string[]
  content_assets: string[]
  target_queries: string[]
  publish_assets: GrowthAIVisibilityFeedAsset[]
  platform_strategies: GrowthAIVisibilityPlatformStrategy[]
  stitch_prompt: string
  figma_handoff: string[]
  validation_commands: string[]
  probe_template_command: string
  success_metrics: string[]
  next_actions: string[]
}
export interface GrowthAIVisibilityDocsPlan {
  canonical_domain: string
  docs_category: string
  pages: string[]
  required_blocks: string[]
  schema_types: string[]
}
export interface GrowthAIVisibilityDocsPageBlueprint {
  slug: string
  title: string
  canonical_url: string
  meta_description: string
  target_queries: string[]
  definition_block: string
  fact_table: Array<Record<string, string>>
  page_sections: string[]
  faq: Array<Record<string, string>>
  schema_types: string[]
  stitch_notes: string[]
  figma_components: string[]
  mdx_skeleton: string
  validation_commands: string[]
}
export interface GrowthAIVisibilityDocsBlueprint {
  category: string
  canonical_domain: string
  target_repo: string
  implementation_root: string
  pages: GrowthAIVisibilityDocsPageBlueprint[]
  shared_components: string[]
  publishing_checklist: string[]
}
export interface GrowthAIVisibilityDesignFrame {
  name: string
  purpose: string
  source_page_slug: string
  layout_notes: string[]
  figma_components: string[]
  stitch_prompt: string
}
export interface GrowthAIVisibilityDesignHandoff {
  title: string
  canonical_domain: string
  source_tool: string
  target_tool: string
  figma_file_name: string
  stitch_prompt: string
  frames: GrowthAIVisibilityDesignFrame[]
  component_specs: Array<Record<string, string>>
  design_tokens: Record<string, string>
  import_steps: string[]
  implementation_notes: string[]
  acceptance_checks: string[]
}
export interface GrowthAIVisibilityDesignPlan {
  stitch_prompt: string
  figma_handoff: string[]
  implementation_targets: string[]
}
export interface GrowthAIVisibilityOptimizationPlan {
  module_key: string
  objective: string
  canonical_domain: string
  critical_fixes: string[]
  baseline_queries: GrowthAIVisibilityQuery[]
  feed_experiments: GrowthAIVisibilityFeedExperiment[]
  product_docs: GrowthAIVisibilityDocsPlan
  design_plan: GrowthAIVisibilityDesignPlan
  growing_workflows: string[]
  success_criteria: string[]
}
