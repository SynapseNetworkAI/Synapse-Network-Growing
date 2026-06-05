type RequestFn = <T>(path: string, options?: RequestInit, timeoutMs?: number) => Promise<T>

export interface GrowthAIVisibilityCheck {
  id: number
  query: string
  platform: string
  answer_summary: string
  synapse_mentioned: boolean
  synapse_cited: boolean
  cited_urls: string[]
  competitor_mentions: string[]
  missing_facts: string[]
  next_action: string
  feed_key: string
  run_group: string
  result_rank: number
  evidence_url: string
  metadata: Record<string, unknown>
  run_at: string | null
  created_at: string | null
  updated_at: string | null
}
export interface GrowthAIVisibilityComparison {
  feed_key: string
  run_group: string
  previous_run_group: string
  platforms: string[]
  external_platforms: string[]
  total_checks: number
  external_checks_count: number
  local_validation_count: number
  mentioned_count: number
  cited_count: number
  previous_mentioned_count: number
  previous_cited_count: number
  mentioned_delta: number
  cited_delta: number
  comparison_status: string
  citation_quality_status?: string
  feed_effective: boolean
  missing_platforms: string[]
  top_competitors: string[]
  known_collision_competitors?: string[]
  official_cited_urls?: string[]
  next_actions: string[]
  evidence_urls: string[]
  latest_run_at: string | null
}
export interface GrowthAIVisibilityFeedReport {
  feed_key: string
  latest_run_group: string
  comparison_status: string
  citation_quality_status?: string
  feed_effective: boolean
  external_platforms: string[]
  missing_platforms: string[]
  known_collision_competitors?: string[]
  official_cited_urls?: string[]
  mentioned_count: number
  cited_count: number
  mentioned_delta: number
  cited_delta: number
  latest_run_at: string | null
  next_actions: string[]
}
export interface GrowthAIVisibilityWeeklyReport {
  module_key: string
  generated_at: string
  goal_status: string
  goal_achieved: boolean
  required_stable_runs: number
  stable_positive_runs: number
  target_platforms: string[]
  covered_platforms: string[]
  missing_platforms: string[]
  total_external_checks: number
  total_mentioned_count: number
  total_cited_count: number
  latest_feed_key: string
  latest_run_group: string
  latest_comparison_status: string
  feed_reports: GrowthAIVisibilityFeedReport[]
  blockers: string[]
  next_actions: string[]
  recommended_feed_key: string
  recommended_probe_template_command: string
}
export interface GrowthAIVisibilityNextCycle {
  module_key: string
  feed_key: string
  run_group: string
  output_path: string
  missing_platforms: string[]
  blockers: string[]
  next_actions: string[]
  validation_commands: string[]
  feed_validation_command: string
  manual_probe_template_command: string
  api_readiness_command: string
  api_execute_command: string
  apply_command: string
  compare_command: string
  weekly_report_command: string
}
export interface GrowthAIVisibilityReleaseCommandGroup {
  key: string
  purpose: string
  commands: string[]
  service_key: string
  environment: string
  notes: string[]
}
export interface GrowthAIVisibilityReleaseUnblockPlan {
  module_key: string
  feed_key: string
  status: string
  generated_at: string
  official_homepage: string
  project_key: string
  services: string[]
  branch_name: string
  target_commit_sha: string
  actor: string
  source_pr: Record<string, unknown>
  source_prs: Record<string, unknown>[]
  predeploy_evidence: Record<string, unknown>
  deploy_readiness_status: string
  deployment_gaps: Record<string, unknown>[]
  confirmed_facts: string[]
  hard_boundaries: string[]
  known_blockers: string[]
  environment_defaults: Record<string, unknown>
  command_groups: GrowthAIVisibilityReleaseCommandGroup[]
  success_criteria: string[]
}
export interface GrowthAIVisibilityReleaseSnapshot {
  module_key: string
  snapshot_type: string
  generated_at: string
  feed_key: string
  run_group: string
  target_commit_sha: string
  official_homepage: string
  status: string
  release_plan_status: string
  deploy_readiness_status: string
  confirmed_facts: string[]
  deployment_gaps: Record<string, unknown>[]
  live_readiness: Record<string, unknown>
  gcloud: Record<string, Record<string, unknown>>
  external_probe_keys: Record<string, Record<string, unknown>>
  blockers: string[]
  next_actions: string[]
}
export interface GrowthAIVisibilityHandoffBundle {
  module_key: string
  bundle_type: string
  generated_at: string
  feed_key: string
  run_group: string
  target_commit_sha: string
  official_homepage: string
  status: string
  release_status: string
  live_readiness_status: string
  external_probe_gate_status: string
  ready_platforms: string[]
  missing_platforms: string[]
  blockers: string[]
  next_actions: string[]
  files: Record<string, string>
  commands: Record<string, string>
}
export interface GrowthAIVisibilityFeedCycle {
  feed_key: string
  status: string
  objective: string
  latest_run_group: string
  latest_comparison_status: string
  feed_ready: boolean
  external_probe_ready: boolean
  feed_effective: boolean
  external_platforms: string[]
  missing_platforms: string[]
  mentioned_count: number
  cited_count: number
  blockers: string[]
  next_actions: string[]
  publish_surfaces: string[]
  feed_validation_command: string
  manual_probe_template_command: string
  api_readiness_command: string
  api_execute_command: string
  compare_command: string
  latest_run_at: string | null
}
export interface GrowthAIVisibilityFeedCycleList {
  module_key: string
  generated_at: string
  target_platforms: string[]
  recommended_feed_key: string
  items: GrowthAIVisibilityFeedCycle[]
  total: number
}
export interface GrowthAIVisibilityFeedScore {
  feed_key: string
  rank: number
  impact_score: number
  status: string
  objective: string
  latest_run_group: string
  comparison_status: string
  citation_quality_status?: string
  feed_ready: boolean
  external_probe_ready: boolean
  feed_effective: boolean
  target_platforms: string[]
  covered_platforms: string[]
  missing_platforms: string[]
  external_checks_count: number
  local_validation_count: number
  mentioned_count: number
  cited_count: number
  known_collision_competitors?: string[]
  official_cited_urls?: string[]
  mentioned_delta: number
  cited_delta: number
  blockers: string[]
  next_actions: string[]
  recommended_action: string
  feed_validation_command: string
  api_readiness_command: string
  api_execute_command: string
  compare_command: string
}
export interface GrowthAIVisibilityFeedScorecard {
  module_key: string
  generated_at: string
  recommended_feed_key: string
  ranking_basis: string
  items: GrowthAIVisibilityFeedScore[]
  total: number
}
export interface GrowthAIVisibilityOptimizationBrief {
  module_key: string
  title: string
  status: string
  generated_at: string
  official_homepage: string
  recommended_feed_key: string
  target_platforms: string[]
  blockers: string[]
  next_actions: string[]
  artifact_path: string
  export_command: string
  markdown: string
}
export interface GrowthAIVisibilityLiveReadinessCheck {
  label: string
  url: string
  status: number
  ok: boolean
  final_url: string
  error: string
  contains_synapse: boolean
}
export interface GrowthAIVisibilityLiveReadinessItem {
  feed_key: string
  status: string
  feed_ready: boolean
  external_probe_ready: boolean
  run_group: string
  platform: string
  query: string
  answer_summary: string
  checked_urls: string[]
  missing_facts: string[]
  next_action: string
  checks: GrowthAIVisibilityLiveReadinessCheck[]
}
export interface GrowthAIVisibilityLiveReadiness {
  module_key: string
  generated_at: string
  run_group: string
  canonical_homepage: string
  status: string
  ready_count: number
  blocked_count: number
  validation_command: string
  apply_command: string
  items: GrowthAIVisibilityLiveReadinessItem[]
  total: number
}
export interface GrowthAIVisibilityExternalProbeProvider {
  platform: string
  env_key: string
  configured: boolean
}
export interface GrowthAIVisibilityExternalProbeGate {
  module_key: string
  generated_at: string
  feed_key: string
  run_group: string
  status: string
  ready_to_execute: boolean
  partial_ready_to_execute: boolean
  manual_ready_to_execute: boolean
  feed_ready: boolean
  api_keys_ready: boolean
  target_platforms: string[]
  ready_platforms: string[]
  missing_platforms: string[]
  provider_readiness: GrowthAIVisibilityExternalProbeProvider[]
  blockers: string[]
  feed_validation_command: string
  record_readiness_command: string
  manual_probe_template_command: string
  api_readiness_command: string
  api_execute_command: string
  partial_api_readiness_command: string
  partial_api_execute_command: string
  record_probe_command: string
  compare_command: string
}
export interface GrowthAIVisibilityOfficialSource {
  surface_key: string
  surface: string
  canonical_url: string
  citation_role: string
  feed_keys: string[]
  required_for_success: boolean
  validation_command: string
  acceptance_signal: string
}
export interface GrowthAIVisibilityOfficialSourceList {
  module_key: string
  generated_at: string
  official_citation_prefixes: string[]
  items: GrowthAIVisibilityOfficialSource[]
  total: number
}
export interface GrowthAIVisibilityProbeMatrixRow {
  feed_key: string
  platform: string
  status: string
  run_group: string
  queries: string[]
  official_source_urls: string[]
  success_decision_rule: string
  manual_probe_template_command: string
  record_probe_command: string
  compare_command: string
  evidence_directory: string
  blockers: string[]
  next_actions: string[]
}
export interface GrowthAIVisibilityProbeMatrix {
  module_key: string
  generated_at: string
  target_platforms: string[]
  recommended_feed_key: string
  rows: GrowthAIVisibilityProbeMatrixRow[]
  total: number
}
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

export function createGrowthAiVisibilityApi(request: RequestFn) {
  return {
    getGrowthAIVisibilityChecks: (params?: { q?: string; platform?: string; limit?: number; offset?: number }) =>
      request<{ items: GrowthAIVisibilityCheck[]; total: number; limit: number; offset: number }>(
        `/growth/ai-visibility/checks${query(params)}`,
      ),
    getGrowthAIVisibilityComparisons: (params?: { feed_key?: string; run_group?: string; limit?: number }) =>
      request<{ items: GrowthAIVisibilityComparison[]; total: number }>(
        `/growth/ai-visibility/comparisons${query(params)}`,
      ),
    getGrowthAIVisibilityOptimizationPlan: () =>
      request<GrowthAIVisibilityOptimizationPlan>('/growth/ai-visibility/optimization-plan'),
    getGrowthAIVisibilityFeedPackage: (params?: { feed_key?: string }) =>
      request<{ items: GrowthAIVisibilityFeedPackage[]; total: number }>(
        `/growth/ai-visibility/feed-package${query(params)}`,
      ),
    getGrowthAIVisibilityDocsBlueprint: () =>
      request<GrowthAIVisibilityDocsBlueprint>('/growth/ai-visibility/docs-blueprint'),
    getGrowthAIVisibilityDesignHandoff: () =>
      request<GrowthAIVisibilityDesignHandoff>('/growth/ai-visibility/design-handoff'),
    getGrowthAIVisibilityWeeklyReport: () =>
      request<GrowthAIVisibilityWeeklyReport>('/growth/ai-visibility/weekly-report'),
    getGrowthAIVisibilityNextCycle: () =>
      request<GrowthAIVisibilityNextCycle>('/growth/ai-visibility/next-cycle'),
    getGrowthAIVisibilityReleaseUnblockPlan: () =>
      request<GrowthAIVisibilityReleaseUnblockPlan>('/growth/ai-visibility/release-unblock-plan'),
    getGrowthAIVisibilityReleaseSnapshot: () =>
      request<GrowthAIVisibilityReleaseSnapshot>('/growth/ai-visibility/release-snapshot'),
    getGrowthAIVisibilityHandoffBundle: () =>
      request<GrowthAIVisibilityHandoffBundle>('/growth/ai-visibility/handoff-bundle'),
    getGrowthAIVisibilityFeedCycles: () =>
      request<GrowthAIVisibilityFeedCycleList>('/growth/ai-visibility/feed-cycles'),
    getGrowthAIVisibilityFeedScorecard: () =>
      request<GrowthAIVisibilityFeedScorecard>('/growth/ai-visibility/feed-scorecard'),
    getGrowthAIVisibilityOptimizationBrief: () =>
      request<GrowthAIVisibilityOptimizationBrief>('/growth/ai-visibility/optimization-brief'),
    getGrowthAIVisibilityLiveReadiness: () =>
      request<GrowthAIVisibilityLiveReadiness>('/growth/ai-visibility/live-readiness'),
    getGrowthAIVisibilityExternalProbeGate: () =>
      request<GrowthAIVisibilityExternalProbeGate>('/growth/ai-visibility/external-probe-gate'),
    getGrowthAIVisibilityOfficialSources: () =>
      request<GrowthAIVisibilityOfficialSourceList>('/growth/ai-visibility/official-sources'),
    getGrowthAIVisibilityProbeMatrix: () =>
      request<GrowthAIVisibilityProbeMatrix>('/growth/ai-visibility/probe-matrix'),
    createGrowthAIVisibilityCheck: (data: Partial<GrowthAIVisibilityCheck>) =>
      request<GrowthAIVisibilityCheck>('/growth/ai-visibility/checks', { method: 'POST', body: JSON.stringify(data) }),
  }
}

function query(params?: Record<string, unknown>) {
  const search = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim()) search.set(key, String(value))
  })
  return search.toString() ? `?${search.toString()}` : ''
}
