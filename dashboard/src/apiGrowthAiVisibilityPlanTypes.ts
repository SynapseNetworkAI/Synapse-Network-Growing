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
export interface GrowthAIVisibilityPresenceAction {
  host: string
  priority: number
  action_type: string
  ownership: string
  rationale: string
  target_surface: string
  asset: string
  copy_points: string[]
  validation_command: string
  probe_followup: string
  submit_url: string
  source_reference_url: string
  submission_payload: Record<string, unknown>
  operator_notes: string[]
}
export interface GrowthAIVisibilityPresencePlan {
  module_key: string
  generated_at: string
  feed_key: string
  run_group: string
  status: string
  source_hosts: string[]
  actions: GrowthAIVisibilityPresenceAction[]
  blockers: string[]
  validation_commands: string[]
  next_probe_command: string
  compare_command: string
}
export interface GrowthAIVisibilitySourceHostDraft {
  host: string
  priority: number
  draft_type: string
  status: string
  target_url: string
  submit_url: string
  title: string
  summary: string
  body_markdown: string
  source_reference_url: string
  submission_payload: Record<string, unknown>
  validation_command: string
  probe_followup: string
  operator_notes: string[]
}
export interface GrowthAIVisibilitySourceHostFeedPackage {
  module_key: string
  package_type: string
  generated_at: string
  feed_key: string
  run_group: string
  status: string
  source_hosts: string[]
  drafts: GrowthAIVisibilitySourceHostDraft[]
  blockers: string[]
  commands: Record<string, string>
}
export interface GrowthAIVisibilitySourceHostExecutionItem {
  key: string
  host: string
  priority: number
  draft_type: string
  execution_status: string
  target_url: string
  action_required: string
  required_evidence: string[]
  validation_command: string
  re_probe_command: string
  completion_gate: string
}
export interface GrowthAIVisibilitySourceHostExecutionChecklist {
  module_key: string
  checklist_type: string
  generated_at: string
  feed_key: string
  run_group: string
  status: string
  items: GrowthAIVisibilitySourceHostExecutionItem[]
  blockers: string[]
  commands: Record<string, string>
}
