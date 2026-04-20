const BASE = '/api'
const REQUEST_TIMEOUT_MS = 17000

export interface ApiError extends Error {
  detail?: unknown
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
      signal: controller.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      const timeoutError = new Error(`Request timed out after ${REQUEST_TIMEOUT_MS / 1000}s`) as ApiError
      timeoutError.detail = { message: 'request_timeout', timeout_ms: REQUEST_TIMEOUT_MS }
      throw timeoutError
    }
    throw error
  } finally {
    window.clearTimeout(timeoutId)
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = body.detail
    const message = typeof detail === 'string'
      ? detail
      : detail?.message || body.message || `HTTP ${res.status}`
    const error = new Error(message) as ApiError
    error.detail = detail ?? body
    throw error
  }
  return res.json()
}

// Types
export interface Agent {
  id: string
  display_name: string
  goal: string
  group: string
  persona_path: string | null
  skills: string
  task_count: number
  completed_count: number
}

export interface RoleKPI {
  role_id: string
  display_name: string
  group: string
  mission: string
  task_count: number
  completed_count: number
  active_task_count: number
  pending_task_count: number
  failed_task_count: number
  backlog_count: number
  reopened_task_count: number
  human_gate_dependency_count: number
  completion_rate: number
  reopen_rate: number
  human_gate_dependency_rate: number
  average_token_cost: number
  average_budget_cost_points: number
  tokens_used_total: number
  budget_cost_points_total: number
  open_requirement_count: number
  status_mix: Record<string, number>
}

export interface HumanGateRoleKPI {
  role_id: string
  assigned_count: number
  pending_count: number
  decided_count: number
  average_turnaround_hours: number
  disagreement_rate: number
  route_to_human_rate: number
  approve_recommendation_count: number
  revise_recommendation_count: number
  route_to_human_count: number
}

export interface RoleWorkAllocationSummary {
  role_count: number
  total_backlog_count: number
  overloaded_role_count: number
  human_gate_pending_count: number
  human_gate_stale_count: number
}

export interface RoleKpiSnapshot {
  roles: RoleKPI[]
  human_gate_roles: HumanGateRoleKPI[]
  summary: RoleWorkAllocationSummary
}

// Agents-Memory types
export interface AgentsMemoryResult {
  type: 'error' | 'wiki'
  id: string
  title: string
  snippet: string
  score: number
}

export interface AgentsMemorySearchResponse {
  query: string
  results: AgentsMemoryResult[]
  total: number
}

const AGENTS_MEMORY_BASE = 'http://localhost:10100'

export const agentsMemoryApi = {
  search: (q: string, limit = 5): Promise<AgentsMemorySearchResponse> =>
    fetch(`${AGENTS_MEMORY_BASE}/api/search?q=${encodeURIComponent(q)}&mode=hybrid&limit=${limit}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r))),
  linkFor: (result: AgentsMemoryResult) =>
    result.type === 'wiki'
      ? `http://localhost:10000/wiki/${result.id}`
      : `http://localhost:10000/errors/${result.id}`,
}

export interface DashboardStats {
  agent_count: number
  requirement_total: number
  requirement_active: number
  workflow_total: number
  workflow_running: number
  workflow_succeeded: number
  workflow_failed: number
  human_gate_pending: number
}

export interface ProjectPolicy {
  id: number
  project_id: number | null
  project_key: string
  display_name: string
  root_path: string
  status: string
  allowed_write_globs: string[]
  forbidden_globs: string[]
  required_checks: string[]
  release_mode: string
  requires_manual_approval: boolean
  autonomy_mode: string
  allow_rebalance: boolean
  allow_preemption: boolean
  capability_matrix: {
    shell_access: boolean
    git_read: boolean
    git_write: boolean
    git_push: boolean
    network_access: boolean
    publish: boolean
  }
  interrupt_policy: {
    operator_confirmation_actions: string[]
    auto_pause_on_events: string[]
    auto_abort_on_events: string[]
  }
  scheduler_weight: number
  max_parallel_requirements: number
  portfolio_budget_points: number
  deploy_repo_full_name: string | null
  deploy_strategy: string
  deploy_trigger_enabled: boolean
  staging_host_label: string | null
  production_host_label: string | null
  staging_workflow_file: string
  production_workflow_file: string
  notes: string | null
  created_at: string | null
  updated_at: string | null
}

export interface Project {
  id: number
  project_key: string
  display_name: string
  root_path: string
  status: string
  repo_full_name: string | null
  default_branch: string
  deploy_repo_full_name: string | null
  deploy_strategy: string
  deploy_trigger_enabled: boolean
  staging_host_label: string | null
  production_host_label: string | null
  staging_workflow_file: string
  production_workflow_file: string
  notes: string | null
  policy_id: number | null
  created_at: string | null
  updated_at: string | null
}

export interface ProjectWithPolicy extends Project {
  policy: ProjectPolicy | null
}

export interface EnvironmentStatus {
  environment: 'staging' | 'production'
  project_key: string
  deploy_repo_full_name: string | null
  host_label: string | null
  deploy_strategy: string
  trigger_enabled: boolean
  current_commit_sha: string | null
  current_branch: string | null
  last_success_at: string | null
  health_status: string | null
  last_trigger_source: string | null
  last_external_url: string | null
  last_record_id: number | null
}

export interface DeploymentRecord {
  id: number
  requirement_id: number
  project_policy_id: number | null
  project_key: string
  environment: 'staging' | 'production'
  action: string
  status: string
  commit_sha: string | null
  branch_name: string | null
  workflow_file: string | null
  external_run_id: string | null
  external_url: string | null
  actor: string | null
  trigger_source: string
  rollback_target_sha: string | null
  health_status: string | null
  notes: string | null
  metadata: Record<string, unknown>
  started_at: string | null
  finished_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface DeploymentProjectOverview {
  project_policy_id: number
  project_key: string
  display_name: string
  deploy_repo_full_name: string | null
  deploy_strategy: string
  deploy_trigger_enabled: boolean
  staging_host_label: string | null
  production_host_label: string | null
  environment_statuses: EnvironmentStatus[]
  recent_records: DeploymentRecord[]
}

export interface DeploymentRequirementCandidate {
  requirement_id: number
  title: string
  status: string
  priority: string
  source: string
  source_ref: string | null
  project_key: string | null
  project_display_name: string | null
  target_project_path: string | null
  updated_at: string | null
  delivery_state: DeliveryState | null
  deployment_records: DeploymentRecord[]
}

export interface DeploymentOverview {
  project_overviews: DeploymentProjectOverview[]
  release_candidates: DeploymentRequirementCandidate[]
}

export interface ProjectReadinessItem {
  key: string
  label: string
  status: string
  message: string
  details: string[]
}

export interface ProjectOnboarding {
  id: number
  project_key: string
  display_name: string
  root_path: string
  docs_entrypoints: string[]
  validation_commands: string[]
  agents_memory_namespace: string | null
  policy_id: number | null
  readiness_status: string
  readiness_score: number
  readiness_items: ProjectReadinessItem[]
  missing_items: string[]
  notes: string | null
  created_at: string | null
  updated_at: string | null
}

export interface OptimizationSignal {
  id: number
  dedupe_key: string
  signal_type: string
  source_kind: string
  status: string
  title: string
  summary: string
  severity: string
  confidence: number
  project_key: string | null
  project_root_path: string | null
  routing_target_path: string | null
  evidence: Record<string, unknown>[]
  occurrence_count: number
  latest_evidence_at: string | null
  converted_requirement_id: number | null
  incident_family?: string | null
  incident_code?: string | null
  recovery_status?: string | null
  recovery_narrative?: string | null
  score_breakdown?: Record<string, number | string | boolean | null>
  recommended_priority?: string
  auto_intake_eligible?: boolean
  intake_recommendation?: string
  created_at: string | null
  updated_at: string | null
}

export interface OptimizationSignalAutoIntakeResult {
  created: Array<{
    signal_id: number
    requirement_id: number
    title: string
    score: number
  }>
  skipped: string[]
}

export interface SchedulerProjectState {
  project_key: string
  display_name: string
  root_path: string
  active_count: number
  queued_count: number
  max_parallel_requirements: number
  autonomy_mode: string
  allow_rebalance: boolean
  allow_preemption: boolean
  scheduler_weight: number
  portfolio_budget_points: number
  budget_used: number
  budget_remaining: number
  readiness_status: string
  readiness_score: number
}

export interface SchedulerDecision {
  candidate_type: string
  action: string
  requirement_id?: number | null
  signal_id?: number | null
  title: string
  project_key: string
  project_display_name: string
  score: number
  base_score: number
  scheduler_weight: number
  autonomy_mode: string
  budget_cost: number
  project_slot_available: boolean
  reason: string
  reasons: string[]
  template_key?: string | null
  source?: string | null
  preempt_requirement_id?: number | null
  human_gate_required: boolean
}

export interface SchedulerPlan {
  global_capacity: number
  active_count: number
  available_slots: number
  generated_at: string | null
  project_states: SchedulerProjectState[]
  decisions: SchedulerDecision[]
  started_ids: number[]
  created_requirement_ids: number[]
  preempted_ids: number[]
  rebalanced_ids: number[]
  skipped: string[]
}

export type QueueAdvanceResult = Omit<SchedulerPlan, 'skipped'> & {
  started?: number
  skipped_reasons?: string[]
  skipped?: string | string[]
}

export interface Requirement {
  id: number
  title: string
  description_markdown: string
  status: string
  priority: string
  source: string
  source_ref: string | null
  target_project_path: string | null
  blocked_by_count: number
  active_workflow_run_id: number | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
  routing_context: RequirementRoutingContext
  score_breakdown: RequirementScoreBreakdown
}

export interface ProjectScorecard {
  project_key: string
  display_name: string
  root_path: string
  policy_status: string
  release_mode: string
  requires_manual_approval: boolean
  readiness_status: string
  readiness_score: number
  automation_ready: boolean
  onboarding_present: boolean
  active_requirement_count: number
  completed_requirement_count: number
  total_requirement_count: number
  bug_report_count: number
  blocked_publish_count: number
  manual_override_count?: number
  validation_pass_rate: number
  automation_coverage: number
  notes: string | null
  agents_memory_namespace: string | null
}

export interface RequirementRoutingContext {
  routing_mode: string
  target_project_path: string | null
  summary: string | null
  automation_ready: boolean
  readiness_status: string
  routed_project_keys: string[]
  routed_display_names: string[]
  skipped_project_keys: string[]
  project_scorecards: ProjectScorecard[]
}

export interface RequirementScoreBreakdown {
  total: number
  priority: number
  aging: number
  status_adjustment: number
  blocker_penalty: number
  readiness_adjustment: number
  bug_pressure: number
  delivery_pressure: number
  manual_escalation_pressure?: number
  signal_impact?: number
  signal_risk?: number
  signal_confidence?: number
  signal_urgency?: number
  implementation_cost_adjustment?: number
  automation_gap: number
}

export interface RequirementDependency {
  id: number
  requirement_id: number
  depends_on_requirement_id: number
  depends_on_title: string
  depends_on_status: string
  dependency_type: string
}

export interface RequirementAcceptanceCheck {
  id: number
  requirement_id: number
  check_key: string
  description: string
  check_type: string
  owner_role: string
  status: string
  success_criteria_markdown: string | null
  verified_by_step_id: number | null
  evidence_artifact_id: number | null
  created_at: string | null
  updated_at: string | null
}

export interface DeliveryState {
  branch_name: string | null
  branch_strategy: string | null
  base_branch: string | null
  review_status: string
  publish_status: string
  release_mode: string | null
  requires_manual_approval: boolean
  required_checks: string[]
  confirmed_checks: string[]
  pending_checks: string[]
  publish_blockers: string[]
  review_surface_summary: string | null
  rollback_hint_markdown: string | null
  review_ready_at: string | null
  published_at: string | null
  publish_note: string | null
  vcs_status: string | null
  vcs_remote_name: string | null
  vcs_repositories: Record<string, unknown>[]
  compare_url: string | null
  pr_status: string | null
  pr_number: number | null
  pr_url: string | null
  head_branch: string | null
  latest_commit_sha: string | null
  latest_remote_sha: string | null
  review_bundle_generated_at: string | null
  last_pushed_at: string | null
  pr_metadata: Record<string, unknown> | null
  promotion_checklist: Record<string, unknown>[]
  staging_status: EnvironmentStatus | null
  production_status: EnvironmentStatus | null
  last_deployed_sha: string | null
  last_deployed_at: string | null
  deploy_readiness: Record<string, unknown> | null
}

export interface DeclarativeWorkflowRunSummary {
  id: number
  requirement_id: number
  requirement_title?: string
  requirement_candidate_id?: number | null
  requirement_source?: string | null
  workflow_key: string
  current_state: string
  status: string
  resolution: string | null
  risk_level: string
  goal_key?: string | null
  operating_manifest_id?: number | null
  pending_human_gate_count: number
  last_human_gate_decision?: string | null
  last_atom?: string | null
  artifact_count?: number
  atom_count?: number
  duration_ms?: number | null
  pr_url?: string | null
  release_status?: string | null
  delivery_pr_url?: string | null
  delivery_compare_url?: string | null
  delivery_branch?: string | null
  delivery_base_branch?: string | null
  delivery_status?: string | null
  delivery_is_simulated?: boolean
  changed_files_count?: number
  command_evidence_count?: number
  updated_at: string | null
  started_at: string | null
  completed_at: string | null
  archived_at?: string | null
  archived_by?: string | null
  archive_reason?: string | null
  outcome_label?: string
  is_truly_completed?: boolean
  completed_truthfully?: boolean
  needs_human?: boolean
  is_simulated?: boolean
  simulated_delivery?: boolean
  evidence_complete?: boolean
  acceptance_override?: boolean
  manual_review_prompt?: string
  business_outcome_status?: string | null
  business_outcome_confirmed_by?: string | null
  business_outcome_confirmed_at?: string | null
  business_outcome_note?: string | null
  awaiting_business_confirmation?: boolean
}

export interface DeclarativeWorkflowRunPage {
  items: DeclarativeWorkflowRunSummary[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface WorkflowRunsSummary {
  running: number
  needs_human: number
  pending_gate_count?: number
  failed: number
  failed_count?: number
  resume_failure_count?: number
  stale_awaiting_operator_count?: number
  completed: number
  completed_today: number
  pending_release: number
  average_duration_ms: number
  archived: number
  pending_candidate_count: number
  recent_candidates: Array<{
    id: number
    title: string
    status: string
    goal_key: string
    workflow_key: string
  }>
  blocker_items?: DeclarativeWorkflowRunSummary[]
}

export interface DeclarativeWorkflowDefinitionState {
  key: string
  atom_key: string | null
  atom_type: 'agent' | 'deterministic' | 'terminal' | string
  terminal: boolean
  resolution: string | null
  output_key: string | null
  risk_level: string | null
  transitions: Array<{
    condition: string
    goto: string
    increment?: unknown
  }>
}

export interface DeclarativeWorkflowDefinition {
  id: number
  workflow_key: string
  version: number
  title: string
  status: string
  description: string
  initial_state: string
  states: DeclarativeWorkflowDefinitionState[]
  limits: Record<string, unknown>
  risk_policy: Record<string, unknown>
  blackboard: Record<string, unknown>
  spec: Record<string, unknown>
}

type RawWorkflowDefinitionState = {
  atom?: string | null
  agent?: string | null
  terminal?: boolean
  resolution?: string | null
  output_key?: string | null
  risk_level?: string | null
  transitions?: Array<{
    if?: string
    condition?: string
    goto: string
    increment?: unknown
  }>
}

function normalizeWorkflowDefinition(raw: DeclarativeWorkflowDefinition): DeclarativeWorkflowDefinition {
  const spec = (raw.spec || {}) as Record<string, unknown>
  const specStates = spec.states as Record<string, RawWorkflowDefinitionState> | DeclarativeWorkflowDefinitionState[] | undefined
  const states = Array.isArray(raw.states)
    ? raw.states
    : Array.isArray(specStates)
      ? specStates
      : Object.entries(specStates || {}).map(([key, state]) => {
          const terminal = Boolean(state.terminal)
          const atomKey = state.agent || state.atom || null
          const atomType = terminal ? 'terminal' : state.agent ? 'agent' : 'deterministic'
          return {
            key,
            atom_key: atomKey,
            atom_type: atomType,
            terminal,
            resolution: state.resolution || null,
            output_key: state.output_key || null,
            risk_level: state.risk_level || null,
            transitions: (state.transitions || []).map((transition) => ({
              condition: transition.condition || transition.if || 'always',
              goto: transition.goto,
              increment: transition.increment,
            })),
          }
        })

  return {
    ...raw,
    description: raw.description || String(spec.description || ''),
    initial_state: raw.initial_state || String(spec.initial_state || ''),
    states,
    limits: raw.limits || (spec.limits as Record<string, unknown>) || {},
    risk_policy: raw.risk_policy || (spec.risk_policy as Record<string, unknown>) || {},
    blackboard: raw.blackboard || (spec.blackboard as Record<string, unknown>) || {},
  }
}

export interface WorkflowReadiness {
  requirement_id: number
  assets_status: string
  active_workflow_run_id: number | null
  active_workflow_run_summary: DeclarativeWorkflowRunSummary | null
  blocking_reason: string | null
  next_action: string
  can_start_workflow: boolean
  recommended_workflow_key: string | null
}

export interface DeclarativeWorkflowEvent {
  id: number
  event_type: string
  from_state: string | null
  to_state: string
  condition: string | null
  payload: Record<string, unknown>
  created_at: string | null
}

export interface DeclarativeWorkflowArtifact {
  id: number
  artifact_type: string
  state_key: string | null
  atom_key: string | null
  content_summary: string
  payload: Record<string, unknown>
  created_at: string | null
}

export interface DeclarativeAtomInvocation {
  id: number
  state_key: string
  atom_key: string
  atom_type: string
  status: string
  output_summary: string
  artifact_ids: number[]
  duration_ms: number
  error_excerpt: string | null
}

export interface DeclarativeHumanGate {
  id: number
  state_key: string
  gate_type: string
  risk_level: string
  status: string
  reason: string
  decision: string | null
  created_at: string | null
}

export interface DeclarativeTimelineArtifactPreview {
  id: number
  artifact_type: string
  summary: string
  payload: Record<string, unknown>
  raw_excerpt: string
}

export interface DeclarativeWorkflowTimelineItem {
  kind: string
  id: number
  created_at: string | null
  completed_at?: string | null
  state_key: string
  atom_key?: string | null
  atom_type?: string | null
  status: string
  title: string
  summary: string
  artifact_ids: number[]
  artifacts?: DeclarativeTimelineArtifactPreview[]
  artifact?: DeclarativeTimelineArtifactPreview
  from_state?: string | null
  to_state?: string | null
  condition?: string | null
  payload_ref?: Record<string, unknown>
  decision?: string | null
  decided_by?: string | null
}

export interface DeclarativeAgentOutput {
  state_key: string
  atom_key: string
  agent_name: string
  status: string
  summary: string
  input_summary: string
  parsed_writes: Record<string, unknown>
  raw_artifact_id: number | null
  raw_output: string
  created_at: string | null
}

export interface DeclarativeChangedFilesSummary {
  changed_files: string[]
  added_files: string[]
  modified_files: string[]
  deleted_files: string[]
  changed_files_count: number
  diff_summary: string
  patch_artifact_id?: number | null
  planned_change_only: boolean
}

export interface DeclarativeCommandResult {
  cwd?: string
  command: string
  purpose?: string
  exit_code: number
  duration_ms?: number
  stdout_excerpt?: string
  stderr_excerpt?: string
  log_artifact_id?: number | null
  timeout?: boolean
  simulated?: boolean
  state_key?: string | null
  atom_key?: string | null
}

export interface DeclarativeDeliverySummary {
  pr_created: boolean
  pr_url: string | null
  branch_name: string | null
  compare_url: string | null
  pr_status: string | null
  release_status: string | null
  sync_action: string | null
  simulated: boolean
  human_commits_detected?: boolean
  rebase_attempted?: boolean
  rebase_status?: string | null
  delivery_blocker_type?: string | null
}

export interface DeclarativeWorkflowRunDetail extends DeclarativeWorkflowRunSummary {
  blackboard: Record<string, unknown>
  retry_counters: Record<string, number>
  events: DeclarativeWorkflowEvent[]
  artifacts: DeclarativeWorkflowArtifact[]
  atom_invocations: DeclarativeAtomInvocation[]
  human_gates: DeclarativeHumanGate[]
  timeline?: DeclarativeWorkflowTimelineItem[]
  notifications?: NotificationDelivery[]
  outcome_label?: string
  is_truly_completed?: boolean
  completed_truthfully?: boolean
  needs_human?: boolean
  is_simulated?: boolean
  simulated_delivery?: boolean
  evidence_complete?: boolean
  observability_warnings?: string[]
  agent_outputs?: DeclarativeAgentOutput[]
  changed_files_summary?: DeclarativeChangedFilesSummary
  command_results?: DeclarativeCommandResult[]
  delivery_summary?: DeclarativeDeliverySummary
  resume_attempted?: boolean
  resume_status?: string
  workflow_status_after_resume?: string
  next_state?: string
  created_gate_id?: number | null
}

export interface AgentRequirement {
  id: number
  title: string
  description_markdown: string
  acceptance_criteria_markdown: string
  state: string
  attention_reason: string | null
  failure_reason?: string | null
  requirement_plan_summary?: string | null
  project: {
    project_id: number | null
    project_key: string | null
    project_display_name: string | null
    target_project_path: string | null
    target_project_path_override: string | null
  } | null
  current_attempt_id: number | null
  current_delivery_id: number | null
  status: string
  priority: string
  source: string
  source_ref: string | null
  linked_requirement_id?: number | null
  followup_requirement_id?: number | null
  resolution_path?: string | null
  operating_manifest_id?: number | null
  goal_key?: string | null
  requirement_candidate_id?: number | null
  project_id: number | null
  project_key: string | null
  project_display_name: string | null
  target_project_path: string | null
  target_project_path_override: string | null
  target_projects: string[]
  phase: string
  allowed_actions: string[]
  pending_operations: string[]
  recovery_status: string | null
  recovery_scope: string | null
  recovery_deadline_at: string | null
  recovery_timeout_status: string | null
  time_remaining_seconds: number | null
  assets_status: string
  assets_error_message: string | null
  created_at: string | null
  updated_at: string | null
  active_workflow_run_id: number | null
  active_workflow_run_summary: DeclarativeWorkflowRunSummary | null
  latest_release_status: string | null
  business_outcome_status?: string | null
  business_outcome_confirmed_by?: string | null
  business_outcome_confirmed_at?: string | null
  business_outcome_note?: string | null
}

export interface AcceptanceContractCheck {
  label: string
  command: string | null
  kind: string
}

export interface AcceptanceContract {
  acceptance_owner_role?: string
  review_owner_role?: string
  acceptance_mode?: string
  acceptance_trigger?: string
  workflow_step_types?: string[]
  required_evidence_artifact_types?: string[]
  done_criteria?: string[]
  verification_checks?: AcceptanceContractCheck[]
  scope_constraints?: string[]
  risk_notes?: string[]
  expected_evidence?: string[]
  execution_acceptance_steps?: AcceptanceExecutionStep[]
  acceptance_kind?: 'business' | 'system_dogfood' | string
  manual_review_prompt?: string
  acceptance_override?: boolean
  override_by?: string
  override_reason?: string
  override_at?: string
  acceptance_index?: Record<string, unknown>
  delivery_expectation?: string
  markdown?: string
}

export interface AcceptanceExecutionStep {
  step_key: string
  title: string
  expected_result: string
  required_commands?: string[]
  required_evidence_types?: string[]
  required_db_lineage?: string[]
  manual_review_prompt?: string
}

export interface ExecutionPlanStep {
  step_key: string
  title: string
  step_type?: string
  scope?: string
  done_when?: string
}

export interface ExecutionPlan {
  plan_kind?: string
  planning_mode?: string
  goal_summary?: string
  summary_markdown?: string
  target_files_or_areas?: string[]
  steps?: ExecutionPlanStep[]
  planned_checks?: string[]
  risks?: string[]
  delivery_intent?: string
  blocker_type?: string
  failed_gate_name?: string
  blocker_excerpt?: string
  repair_scope?: string[]
  success_criteria?: string[]
  verification_checks?: string[]
  attempt_index?: number
  attempt_budget?: number
  parent_plan_reference_summary?: string
  parent_plan_reference?: {
    summary_markdown?: string | null
    goal_summary?: string | null
  }
  repair_context?: {
    latest_blocker_excerpt?: string | null
    latest_blocker_raw_output?: string | null
    previous_attempt_summary?: {
      attempt_id?: number | null
      planner_summary?: string | null
      changed_files?: string[]
      commands_run?: string[]
      validation_status?: string | null
      failure_summary?: string | null
      failed_reasoning?: string | null
      raw_output_excerpt?: string | null
    }
    previous_failure_summary?: string | null
  }
}

export interface AgentRequirementDetail {
  requirement: AgentRequirement
  state: string
  attention_reason: string | null
  failure_reason?: string | null
  policy_summary_markdown: string
  project: Project | null
  active_workflow_run_id: number | null
  active_workflow_run_summary: DeclarativeWorkflowRunSummary | null
  latest_release_id: number | null
  latest_release: ReleaseRecord | null
  phase: string
  allowed_actions: string[]
  pending_operations: string[]
  recovery_status: string | null
  recovery_scope: string | null
  recovery_deadline_at: string | null
  recovery_timeout_status: string | null
  time_remaining_seconds: number | null
  assets_status: string
  assets_error_message: string | null
  acceptance_contract: AcceptanceContract
  execution_plan: ExecutionPlan
  workflow_readiness: WorkflowReadiness | null
  attachments: RequirementAttachment[]
  followup_requirement_id?: number | null
  resolution_path?: string | null
  business_outcome_status?: string | null
  business_outcome_confirmed_by?: string | null
  business_outcome_confirmed_at?: string | null
  business_outcome_note?: string | null
}

export interface ValidationCheckResult {
  label: string
  command: string | null
  project_path: string | null
  status: string
  output_excerpt: string | null
  exit_code?: number | null
  duration_ms?: number | null
  log_path?: string | null
  started_at?: string | null
  completed_at?: string | null
  timed_out?: boolean
  purpose?: string | null
}

export interface VerificationPlan {
  mode: string
  summary: string
  checks: string[]
  evidence_expectations: string[]
  why_no_verification: string | null
  markdown?: string
  required_commands?: Record<string, unknown>[]
  expected_artifacts?: string[]
  evidence_to_inspect?: string[]
  non_mutating_rules?: string[]
  verdict_rubric?: string[]
}

export interface WorkspaceBlocker {
  repo_path: string
  base_branch: string | null
  target_branch: string | null
  current_branch: string | null
  dirty_file_count: number
  dirty_files_preview: string[]
  has_untracked: boolean
  recommended_operator_action: string | null
  workspace_mode: string
}

export interface ValidationRecord {
  id: number
  requirement_id: number
  workflow_run_id: number | null
  profile: string
  status: string
  summary_markdown: string
  checks: ValidationCheckResult[]
  verification_plan: VerificationPlan | null
  verification_agent_id: string | null
  verification_agent_label: string | null
  evidence_used: string[]
  reasoning_markdown: string
  suggested_next_action: string | null
  resolution_recommendation?: string | null
  resolution_confidence?: number | null
  resolution_reason?: string | null
  resolution_path?: string | null
  followup_requirement_id?: number | null
  followup_requirement_payload?: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface ReleaseRecord {
  id: number
  requirement_id: number
  workflow_run_id: number | null
  state: string
  project_id: number | null
  project_key: string | null
  project_display_name: string | null
  target_project_path: string | null
  status: string
  branch_name: string | null
  planned_branch_name: string | null
  actual_branch_name: string | null
  branch_reuse_status: string | null
  base_branch: string | null
  commit_sha: string | null
  compare_url: string | null
  pr_url: string | null
  pr_number: number | null
  notes: string | null
  blocker_kind: string | null
  delivery_blocker_type: string | null
  failed_gate_name?: string | null
  delivery_failure_excerpt: string | null
  delivery_failure_raw_output: string | null
  repairable: boolean
  repairability: string | null
  repair_attempt_count: number
  next_action: string | null
  workspace_blocker: WorkspaceBlocker | null
  workspace_mode: string
  prepared_at: string | null
  delivered_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ReleaseCandidate {
  requirement: AgentRequirement
  validation: ValidationRecord
  release: ReleaseRecord | null
}

export interface ReleaseDetail {
  requirement: AgentRequirement
  validation: ValidationRecord | null
  release: ReleaseRecord | null
  deployments: DeploymentRecord[]
}

export interface NotificationDelivery {
  id: number
  channel: string
  event_type: string
  event_key: string
  object_type: string
  object_key: string
  service_name: string | null
  status: string
  payload: Record<string, unknown>
  event_id?: number | null
  fingerprint_key?: string | null
  fingerprint?: {
    status?: string
    occurrence_count?: number
    suppressed_count?: number
    last_sent_at?: string | null
    cooldown_until?: string | null
    severity?: string
    risk_level?: string
  }
  response_excerpt: string | null
  delivered_at: string | null
  created_at: string | null
}

export interface ErrorEvent {
  id: number
  fingerprint_key: string
  source_kind: string
  service_name: string
  project_key: string | null
  project_root_path: string | null
  incident_code: string | null
  severity: string
  summary: string
  message: string
  stack_trace: string | null
  source_ref: string | null
  environment: string | null
  metadata: Record<string, unknown>
  occurred_at: string | null
  created_at: string | null
}

export interface ErrorFingerprint {
  fingerprint_key: string
  source_kind: string
  service_name: string
  project_key: string | null
  project_root_path: string | null
  incident_code: string | null
  severity: string
  summary: string
  evidence_excerpt: string | null
  status: string
  occurrence_count: number
  first_seen_at: string | null
  latest_seen_at: string | null
  latest_error_event_id: number | null
  linked_requirement_id: number | null
  materialized_requirement_id?: number | null
  active_workflow_run_id?: number | null
  active_workflow_run_summary?: DeclarativeWorkflowRunSummary | null
  discovery_status?: string
  discovery_recommendation?: {
    discovery_action: string
    confidence: number
    reason: string
    target_project_key: string | null
    suggested_title: string | null
    suggested_priority: string | null
    auto_start_allowed: boolean
  } | null
  last_discovery_at?: string | null
}

export interface ErrorFingerprintDetail {
  fingerprint: ErrorFingerprint
  requirement: AgentRequirement | null
  release: ReleaseRecord | null
  events: ErrorEvent[]
  notifications: NotificationDelivery[]
}

export interface RequirementAttachment {
  id: number
  requirement_id: number
  file_name: string
  stored_path: string
  content_type: string
  attachment_kind: 'image' | 'file'
  source: string
  size_bytes: number
  created_at: string | null
}

export interface RequirementAttachmentInput {
  file_name: string
  content_type: string
  content_base64: string
  source?: string
}

export interface RequirementApprovalDecision {
  action: 'approve' | 'reject' | 'waive'
  reviewer?: string
  comment?: string | null
}

export interface OperatingReviewPortfolioSummary {
  active_requirements: number
  completed_requirements: number
  completion_rate: number
  open_signals: number
  human_gate_required_decisions: number
  rebalance_opportunities: number
  projects_over_budget: number
  blocked_publish_projects: number
  budget_spent_points: number
  tokens_used: number
  prompt_cache_saved_chars: number
  deduped_bindings: number
  escalations: number
  downgrades: number
  tier_mix: Record<string, number>
  human_gate_hotspots: number
  open_bug_pressure: number
  unresolved_critical_bugs: number
  bug_requirements_created: number
  recurring_bug_fingerprint_count: number
  cross_project_bug_recoveries: number
}

export interface OperatingReviewProjectHighlight {
  project_key: string
  display_name: string
  readiness_status: string
  readiness_score: number
  active_count: number
  queued_count: number
  bug_report_count: number
  blocked_publish_count: number
  scheduler_weight: number
  autonomy_mode: string
  budget_used: number
  budget_remaining: number
  completed_requirements: number
  budget_spent_points: number
  prompt_cache_saved_chars: number
  escalations: number
  downgrades: number
  tier_mix: Record<string, number>
  open_bug_count: number
  critical_bug_count: number
  converted_bug_count: number
  recurring_bug_count: number
}

export interface OperatingReviewBugFingerprint {
  bug_id: number
  bug_key: string
  title: string
  severity: string
  project_key?: string | null
  project_display_name?: string | null
  fingerprint: string
  occurrence_count: number
  score_total: number
  source_key: string
  converted_requirement_id?: number | null
  last_seen_at?: string | null
}

export interface OperatingReviewCrossProjectBugRecovery {
  item_key: string
  title: string
  severity: string
  summary: string
  project_key?: string | null
  project_display_name?: string | null
  recommendation?: string | null
  incident_family?: string | null
  incident_code?: string | null
  recovery_status?: string | null
  requirement_id?: number | null
  source_ref?: string | null
  affected_project_keys: string[]
  affected_project_display_names: string[]
  score_total: number
}

export interface OperatingReviewItem {
  item_key: string
  title: string
  severity: string
  summary: string
  project_key?: string | null
  project_display_name?: string | null
  recommendation?: string | null
  incident_family?: string | null
  incident_code?: string | null
  recovery_status?: string | null
  requirement_id?: number | null
  source_ref?: string | null
}

export interface OperatingReviewGateHotspot {
  gate_key: string
  title: string
  approval_type: string
  approval_scope?: string | null
  step_type?: string | null
  project_key?: string | null
  project_display_name?: string | null
  occurrence_count: number
  pending_count: number
  latest_status: string
  summary: string
  recommendation?: string | null
}

export interface OperatingReviewAutomationCandidate {
  candidate_key: string
  title: string
  gate_key: string
  project_key?: string | null
  project_display_name?: string | null
  automation_type: string
  priority: string
  rationale: string
  occurrence_count: number
}

export interface OperatingReviewRecommendation {
  candidate_type: string
  title: string
  project_key: string
  project_display_name: string
  action: string
  score: number
  budget_cost: number
  source_ref?: string | null
  rationale: string
  human_gate_required?: boolean
  requirement_id?: number | null
  signal_id?: number | null
  incident_family?: string | null
  incident_code?: string | null
  recovery_status?: string | null
}

export interface OperatingReviewBundleItem {
  bundle_item_key: string
  title: string
  candidate_type: string
  project_key: string
  project_display_name: string
  action: string
  materialization_mode: string
  priority: string
  score: number
  budget_cost: number
  source_ref?: string | null
  target_project_path?: string | null
  requirement_id?: number | null
  template_key?: string | null
  rationale: string
  description_markdown: string
  acceptance_checks: Record<string, unknown>[]
  human_gate_required: boolean
}

export interface OperatingReviewOperatorDecision {
  decision_key: string
  title: string
  decision_type: string
  severity: string
  summary: string
  owner_hint?: string | null
  related_bundle_item_key?: string | null
}

export interface OperatingReviewOperatorPackage {
  title: string
  summary_markdown: string
  checklist: string[]
  decisions: OperatingReviewOperatorDecision[]
  autonomous_decision_count: number
  recommended_bundle_item_keys: string[]
}

export interface OperatingReviewAutonomousCooPosture {
  mode: string
  operator_only_high_risk: boolean
  autonomous_workflow_keys: string[]
  high_risk_decision_count: number
  autonomous_decision_count: number
  operator_queue_count: number
  pending_human_gate_count: number
  auto_approved_requirement_count: number
  stale_approval_count: number
  stuck_requirement_count: number
  critical_incident_count: number
  requires_operator_attention: boolean
  autonomous_execution_rate: number
  summary_markdown: string
}

export interface CompanyOperatingReview {
  id: number
  cycle_label: string
  title: string
  summary_markdown: string
  portfolio_summary: OperatingReviewPortfolioSummary
  project_highlights: OperatingReviewProjectHighlight[]
  bottlenecks: OperatingReviewItem[]
  incidents: OperatingReviewItem[]
  recurring_bug_fingerprints: OperatingReviewBugFingerprint[]
  cross_project_bug_recoveries: OperatingReviewCrossProjectBugRecovery[]
  human_gate_hotspots: OperatingReviewGateHotspot[]
  automation_candidates: OperatingReviewAutomationCandidate[]
  next_cycle_recommendations: OperatingReviewRecommendation[]
  next_cycle_requirement_bundle: OperatingReviewBundleItem[]
  operator_review_package: OperatingReviewOperatorPackage
  autonomous_coo_posture: OperatingReviewAutonomousCooPosture
  source_snapshot: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface CompanyReviewBundleMaterializeResult {
  review_id: number
  created_requirement_ids: number[]
  reused_requirement_ids: number[]
  skipped_bundle_item_keys: string[]
  items: Array<{
    bundle_item_key: string
    status: string
    title: string
    action: string
    requirement_id?: number | null
    source_ref?: string | null
  }>
}

export interface RecurringWorkflow {
  id: number
  workflow_key: string
  display_name: string
  description: string
  status: string
  trigger_type: string
  owner_role: string
  schedule: Record<string, unknown>
  input_query: Record<string, unknown>
  output_action: Record<string, unknown>
  escalation_rule: Record<string, unknown>
  validation_signal: Record<string, unknown>
  is_builtin: boolean
  last_run_at: string | null
  next_run_at: string | null
  is_due: boolean
  health_status: string
  last_result: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface RecurringWorkflowRun {
  id: number
  workflow_key: string
  status: string
  triggered_by: string
  dry_run: boolean
  params: Record<string, unknown>
  result: Record<string, unknown>
  error_excerpt: string | null
  started_at: string | null
  completed_at: string | null
  duration_ms: number
}

export interface RecurringWorkflowRunResult {
  workflow_key: string
  status: string
  run_started_at: string | null
  run_id: number | null
  result: Record<string, unknown>
}

export interface RecurringWorkflowHealth {
  bug_log_scheduler: Record<string, unknown>
  goal_planner_scheduler?: Record<string, unknown>
  notification_dispatcher: Record<string, unknown>
  recurring_registry: Record<string, unknown>
}

export interface PlanningManifest {
  id: number
  manifest_key: string
  version_name: string
  cycle_label: string
  status: string
  revision: number
  payload: Record<string, unknown>
  goal_count: number
  active_goal_count: number
  dropped_goal_count: number
  achieved_goal_count: number
  review_summary: Record<string, unknown>
  change_log: Array<Record<string, unknown>>
  created_by: string
  created_at: string | null
  updated_at: string | null
  archived_at: string | null
}

export interface PlanningManifestHistory {
  items: PlanningManifest[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface PlanningGoalRollup {
  manifest_id: number
  goal_key: string
  goal: Record<string, unknown>
  candidate_status_counts: Record<string, number>
  requirement_status_counts: Record<string, number>
  workflow_status_counts: Record<string, number>
  release_status_counts: Record<string, number>
}

export interface GlobalSteering {
  focus_weights: Record<string, unknown>
  global_budget: Record<string, unknown>
  global_constraints: unknown[]
}

export interface PlanningGoal {
  id: number
  manifest_id: number
  goal_key: string
  title: string
  intent_markdown?: string | null
  intent_excerpt: string
  success_metric: string
  domain: string
  status: string
  workflow_key: string
  project_key?: string | null
  priority: string
  risk_level: string
  weight: number
  acceptance_kind: string
  execution_acceptance_steps: Array<Record<string, unknown>>
  metadata: Record<string, unknown>
  closed_at: string | null
  review_note: string | null
  drop_decision: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface PlanningGoalTraceDiagnostic {
  reason: string
  source: string
  timestamp: string | null
  sweep_id?: number | null
  goal_key?: string | null
}

export interface PlanningGoalTraceNode {
  kind: string
  status: 'ok' | 'warning' | 'blocked' | 'missing' | string
  title: string
  summary: string
  object_id: number | null
  deep_link: string | null
  diagnostic?: PlanningGoalTraceDiagnostic | null
  metadata: Record<string, unknown>
}

export interface PlanningGoalTrace {
  goal: Record<string, unknown>
  nodes: PlanningGoalTraceNode[]
  diagnostics: PlanningGoalTraceDiagnostic[]
  next_actions: Array<Record<string, unknown>>
  history: Array<Record<string, unknown>>
}

export interface RequirementCandidate {
  id: number
  manifest_id: number
  goal_key: string
  candidate_fingerprint: string
  title: string
  description_markdown: string
  project_id: number | null
  project_key: string | null
  workflow_key: string
  priority: string
  risk_level: string
  confidence: number
  rationale: string
  expected_evidence: unknown[]
  status: string
  suppression_reason: string | null
  reject_reason: string | null
  reject_comment: string | null
  approved_by: string | null
  materialized_requirement_id: number | null
  metadata: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
  approved_at: string | null
  rejected_at: string | null
}

export interface RequirementCandidatePage {
  items: RequirementCandidate[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface CandidateApproveRunResult {
  candidate: RequirementCandidate
  requirement_id: number
  workflow_run_id: number | null
  workflow_status: string
  workflow_current_state: string
  auto_run_status: string
  next_action: string
}

export interface PlannerSweep {
  id: number
  manifest_id: number
  status: string
  triggered_by: string
  dry_run: boolean
  input_snapshot: Record<string, unknown>
  parsed_output: Record<string, unknown>
  created_candidate_ids: number[]
  suppressed_items: Array<Record<string, unknown>>
  routing_results?: Array<Record<string, unknown>>
  auto_materialized_requirement_ids?: number[]
  auto_started_workflow_run_ids?: number[]
  routing_suppressed_items?: Array<Record<string, unknown>>
  validation_failed_candidate_ids?: number[]
  planner_validation_errors?: Array<Record<string, unknown>>
  error_excerpt: string | null
  started_at: string | null
  completed_at: string | null
  duration_ms: number
}

export interface DropGoalResult {
  manifest: PlanningManifest
  goal_key: string
  halt_summary: Record<string, unknown>
  decision: Record<string, unknown>
}

export interface GoalMissionLane {
  goal_key: string
  goal: PlanningGoal
  rollup: PlanningGoalRollup
  candidates: RequirementCandidate[]
}

export interface MissionControlHistoryPreview extends PlanningManifestHistory {}

export interface PlanningMissionControl {
  manifest: PlanningManifest
  global_steering: GlobalSteering
  goal_lanes: GoalMissionLane[]
  candidate_totals: Record<string, number>
  history_preview: MissionControlHistoryPreview
  last_sweep: PlannerSweep | null
}

// API functions
export const api = {
  // Agents
  getAgents: () => request<Agent[]>('/agents'),
  getAgent: (id: string) => request<Agent>(`/agents/${id}`),
  getRoleKpis: () => request<RoleKpiSnapshot>('/agents/role-kpis'),

  // Org tree
  getCompanyOperatingReview: () => request<CompanyOperatingReview>('/company-review'),
  materializeCompanyReviewBundle: (reviewId: number, data?: { bundle_item_keys?: string[]; auto_start?: boolean }) =>
    request<CompanyReviewBundleMaterializeResult>(`/company-review/${reviewId}/materialize-bundle`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),
  getRecurringWorkflows: () => request<RecurringWorkflow[]>('/recurring-workflows'),
  getRecurringWorkflowHealth: () => request<RecurringWorkflowHealth>('/recurring-workflows/health'),
  getRecurringWorkflowRuns: (workflowKey: string, limit = 50) =>
    request<RecurringWorkflowRun[]>(`/recurring-workflows/${workflowKey}/runs?limit=${encodeURIComponent(String(limit))}`),
  runRecurringWorkflow: (
    workflowKey: string,
    data?: {
      dry_run?: boolean
      auto_start?: boolean
      intake_min_score?: number
      intake_max_created?: number
      acceptance_limit?: number
      auto_dispatch_acceptance?: boolean
    },
  ) =>
    request<RecurringWorkflowRunResult>(`/recurring-workflows/${workflowKey}/run`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),

  // Planning lifecycle
  getPlanningMissionControl: () => request<PlanningMissionControl>('/planning/mission-control'),
  getActivePlanningManifest: () => request<PlanningManifest>('/planning/manifest/active'),
  saveActivePlanningManifest: (data: { version_name?: string; cycle_label?: string; payload: Record<string, unknown>; operator?: string }) =>
    request<PlanningManifest>('/planning/manifest/active', { method: 'PUT', body: JSON.stringify(data) }),
  getPlanningManifestHistory: (filters?: { page?: number; page_size?: number; status?: string; search?: string }) => {
    const params = new URLSearchParams()
    params.set('page', String(filters?.page ?? 1))
    params.set('page_size', String(filters?.page_size ?? 20))
    if (filters?.status) params.set('status', filters.status)
    if (filters?.search) params.set('search', filters.search)
    return request<PlanningManifestHistory>(`/planning/manifests/history?${params.toString()}`)
  },
  getPlanningGoal: (id: number) => request<PlanningGoal>(`/planning/goals/${id}`),
  getPlanningGoalTrace: (id: number) => request<PlanningGoalTrace>(`/planning/goals/${id}/trace`),
  createPlanningGoal: (data: Partial<PlanningGoal> & { goal_key: string; title: string }) =>
    request<PlanningGoal>('/planning/goals', { method: 'POST', body: JSON.stringify(data) }),
  updatePlanningGoal: (id: number, data: Partial<PlanningGoal> & { operator?: string }) =>
    request<PlanningGoal>(`/planning/goals/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  archiveAndStartPlanningCycle: (manifestId: number, data: { version_name: string; cycle_label: string; operator?: string; payload_patch?: Record<string, unknown> }) =>
    request<PlanningManifest>(`/planning/manifest/${manifestId}/archive-and-start-cycle`, { method: 'POST', body: JSON.stringify(data) }),
  dropPlanningGoal: (goalId: number, data: { reason: string; operator?: string; halt_mode?: string }) =>
    request<DropGoalResult>(`/planning/goals/${goalId}/drop`, { method: 'POST', body: JSON.stringify(data) }),
  getPlanningGoalRollup: (manifestId: number, goalKey: string) =>
    request<PlanningGoalRollup>(`/planning/manifest/${manifestId}/goals/${encodeURIComponent(goalKey)}/rollup`),
  runPlannerSweep: (data?: { dry_run?: boolean; triggered_by?: string }) =>
    request<PlannerSweep>('/planning/sweeps/run', { method: 'POST', body: JSON.stringify(data || {}) }),
  getRequirementCandidates: (filters?: { manifest_id?: number; status?: string; goal_key?: string; page?: number; page_size?: number }) => {
    const params = new URLSearchParams()
    params.set('page', String(filters?.page ?? 1))
    params.set('page_size', String(filters?.page_size ?? 30))
    if (filters?.manifest_id != null) params.set('manifest_id', String(filters.manifest_id))
    if (filters?.status) params.set('status', filters.status)
    if (filters?.goal_key) params.set('goal_key', filters.goal_key)
    return request<RequirementCandidatePage>(`/planning/candidates?${params.toString()}`)
  },
  approveRequirementCandidate: (id: number, data?: { operator?: string }) =>
    request<RequirementCandidate>(`/planning/candidates/${id}/approve`, { method: 'POST', body: JSON.stringify(data || {}) }),
  approveAndRunRequirementCandidate: (id: number, data?: { operator?: string }) =>
    request<CandidateApproveRunResult>(`/planning/candidates/${id}/approve-and-run`, { method: 'POST', body: JSON.stringify(data || {}) }),
  rejectRequirementCandidate: (id: number, data: { reason: string; operator?: string; comment?: string | null }) =>
    request<RequirementCandidate>(`/planning/candidates/${id}/reject`, { method: 'POST', body: JSON.stringify(data) }),
  materializeRequirementCandidate: (id: number, data?: { operator?: string }) =>
    request<{ candidate: RequirementCandidate; requirement_id: number }>(`/planning/candidates/${id}/materialize`, { method: 'POST', body: JSON.stringify(data || {}) }),

  // Dashboard
  getStats: () => request<DashboardStats>('/dashboard/stats'),

  // Project policies
  getProjects: (status?: string) => request<Project[]>(`/projects${status ? `?status=${encodeURIComponent(status)}` : ''}`),
  getProject: (id: number) => request<ProjectWithPolicy>(`/projects/${id}`),
  createProject: (data: {
    project_key: string
    display_name: string
    root_path: string
    status?: string
    repo_full_name?: string | null
    default_branch?: string
    deploy_repo_full_name?: string | null
    deploy_strategy?: string
    deploy_trigger_enabled?: boolean
    staging_host_label?: string | null
    production_host_label?: string | null
    staging_workflow_file?: string
    production_workflow_file?: string
    notes?: string | null
  }) => request<ProjectWithPolicy>('/projects', { method: 'POST', body: JSON.stringify(data) }),
  updateProject: (id: number, data: {
    project_key?: string
    display_name?: string
    root_path?: string
    status?: string
    repo_full_name?: string | null
    default_branch?: string
    deploy_repo_full_name?: string | null
    deploy_strategy?: string
    deploy_trigger_enabled?: boolean
    staging_host_label?: string | null
    production_host_label?: string | null
    staging_workflow_file?: string
    production_workflow_file?: string
    notes?: string | null
  }) => request<ProjectWithPolicy>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  archiveProject: (id: number) => request<ProjectWithPolicy>(`/projects/${id}`, { method: 'DELETE' }),
  getProjectPolicyForProject: (id: number) => request<ProjectPolicy>(`/projects/${id}/policy`),
  updateProjectPolicyForProject: (id: number, data: {
    display_name?: string
    root_path?: string
    status?: string
    allowed_write_globs?: string[]
    forbidden_globs?: string[]
    required_checks?: string[]
    release_mode?: string
    requires_manual_approval?: boolean
    autonomy_mode?: string
    allow_rebalance?: boolean
    allow_preemption?: boolean
    capability_matrix?: {
      shell_access?: boolean
      git_read?: boolean
      git_write?: boolean
      git_push?: boolean
      network_access?: boolean
      publish?: boolean
    }
    interrupt_policy?: {
      operator_confirmation_actions?: string[]
      auto_pause_on_events?: string[]
      auto_abort_on_events?: string[]
    }
    scheduler_weight?: number
    max_parallel_requirements?: number
    portfolio_budget_points?: number
    deploy_repo_full_name?: string | null
    deploy_strategy?: string
    deploy_trigger_enabled?: boolean
    staging_host_label?: string | null
    production_host_label?: string | null
    staging_workflow_file?: string
    production_workflow_file?: string
    notes?: string | null
  }) => request<ProjectPolicy>(`/projects/${id}/policy`, { method: 'PATCH', body: JSON.stringify(data) }),
  getProjectPolicies: () => request<ProjectPolicy[]>('/project-policies'),
  getDeploymentOverview: () => request<DeploymentOverview>('/deployments/overview'),
  getProjectPolicyEnvironmentStatus: (id: number) => request<EnvironmentStatus[]>(`/deployments/project-policies/${id}/environment-status`),
  getProjectOnboardings: () => request<ProjectOnboarding[]>('/project-onboarding'),
  createProjectOnboarding: (data: {
    project_key: string
    display_name: string
    root_path: string
    docs_entrypoints?: string[]
    validation_commands?: string[]
    agents_memory_namespace?: string | null
    auto_create_policy?: boolean
    allowed_write_globs?: string[]
    forbidden_globs?: string[]
    release_mode?: string
    requires_manual_approval?: boolean
    notes?: string | null
  }) => request<ProjectOnboarding>('/project-onboarding', { method: 'POST', body: JSON.stringify(data) }),
  createProjectPolicy: (data: {
    project_key: string
    display_name: string
    root_path: string
    status?: string
    allowed_write_globs?: string[]
    forbidden_globs?: string[]
    required_checks?: string[]
    release_mode?: string
    requires_manual_approval?: boolean
    autonomy_mode?: string
    allow_rebalance?: boolean
    allow_preemption?: boolean
    capability_matrix?: {
      shell_access?: boolean
      git_read?: boolean
      git_write?: boolean
      git_push?: boolean
      network_access?: boolean
      publish?: boolean
    }
    interrupt_policy?: {
      operator_confirmation_actions?: string[]
      auto_pause_on_events?: string[]
      auto_abort_on_events?: string[]
    }
    scheduler_weight?: number
    max_parallel_requirements?: number
    portfolio_budget_points?: number
    deploy_repo_full_name?: string | null
    deploy_strategy?: string
    deploy_trigger_enabled?: boolean
    staging_host_label?: string | null
    production_host_label?: string | null
    staging_workflow_file?: string
    production_workflow_file?: string
    notes?: string | null
  }) => request<ProjectPolicy>('/project-policies', { method: 'POST', body: JSON.stringify(data) }),
  updateProjectPolicy: (id: number, data: {
    display_name?: string
    root_path?: string
    status?: string
    allowed_write_globs?: string[]
    forbidden_globs?: string[]
    required_checks?: string[]
    release_mode?: string
    requires_manual_approval?: boolean
    autonomy_mode?: string
    allow_rebalance?: boolean
    allow_preemption?: boolean
    capability_matrix?: {
      shell_access?: boolean
      git_read?: boolean
      git_write?: boolean
      git_push?: boolean
      network_access?: boolean
      publish?: boolean
    }
    interrupt_policy?: {
      operator_confirmation_actions?: string[]
      auto_pause_on_events?: string[]
      auto_abort_on_events?: string[]
    }
    scheduler_weight?: number
    max_parallel_requirements?: number
    portfolio_budget_points?: number
    deploy_repo_full_name?: string | null
    deploy_strategy?: string
    deploy_trigger_enabled?: boolean
    staging_host_label?: string | null
    production_host_label?: string | null
    staging_workflow_file?: string
    production_workflow_file?: string
    notes?: string | null
  }) => request<ProjectPolicy>(`/project-policies/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteProjectPolicy: (id: number) => request<void>(`/project-policies/${id}`, { method: 'DELETE' }),
  getOptimizationSignals: (status?: string, refresh?: boolean) => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (refresh) params.set('refresh', 'true')
    const q = params.toString() ? `?${params.toString()}` : ''
    return request<OptimizationSignal[]>(`/optimization-signals${q}`)
  },
  refreshOptimizationSignals: () => request<OptimizationSignal[]>('/optimization-signals/refresh', { method: 'POST' }),
  autoIntakeOptimizationSignals: (data?: { min_score?: number; max_created?: number; auto_start?: boolean }) =>
    request<OptimizationSignalAutoIntakeResult>('/optimization-signals/auto-intake', { method: 'POST', body: JSON.stringify(data || {}) }),
  dismissOptimizationSignal: (id: number) => request<OptimizationSignal>(`/optimization-signals/${id}/dismiss`, { method: 'POST' }),
  createRequirementFromSignal: (id: number, data?: { title?: string; auto_start?: boolean }) =>
    request<AgentRequirementDetail>(`/optimization-signals/${id}/create-requirement`, { method: 'POST', body: JSON.stringify(data || {}) }),

  // Agent-first requirements / workflows / releases
  getRequirements: (status?: string, _sort?: string, search?: string) => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (search) params.set('search', search)
    const q = params.toString() ? `?${params.toString()}` : ''
    return request<AgentRequirement[]>(`/requirements${q}`)
  },
  getRequirement: (id: number) => request<AgentRequirementDetail>(`/requirements/${id}`),
  createRequirement: (data: {
    title: string
    description_markdown: string
    acceptance_criteria_markdown?: string
    priority?: string
    source?: string
    source_ref?: string | null
    project_id?: number
    target_project_path_override?: string | null
    target_project_path?: string
    attachments?: RequirementAttachmentInput[]
  }) =>
    request<AgentRequirementDetail>('/requirements', { method: 'POST', body: JSON.stringify(data) }),
  updateRequirement: (id: number, data: {
    title?: string
    description_markdown?: string
    acceptance_criteria_markdown?: string
    acceptance_contract?: AcceptanceContract
    execution_plan?: ExecutionPlan
    priority?: string
    project_id?: number
    target_project_path_override?: string | null
    target_project_path?: string
  }) => request<AgentRequirementDetail>(`/requirements/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  submitRequirement: (id: number) => request<AgentRequirementDetail>(`/requirements/${id}/submit`, { method: 'POST' }),
  regenerateRequirementAssets: (id: number) => request<AgentRequirementDetail>(`/requirements/${id}/regenerate-assets`, { method: 'POST' }),
  getRequirementWorkflowReadiness: (id: number) => request<WorkflowReadiness>(`/requirements/${id}/workflow-readiness`),
  generateRequirementWorkflow: (id: number) => request<AgentRequirementDetail>(`/requirements/${id}/workflow/generate`, { method: 'POST' }),
  startRequirementWorkflow: (
    id: number,
    data?: { workflow_key?: string | null; run_immediately?: boolean; triggered_by?: string },
  ) => request<DeclarativeWorkflowRunDetail>(`/requirements/${id}/workflow/start`, { method: 'POST', body: JSON.stringify(data || {}) }),
  reviseRequirement: (id: number, data: {
    title?: string
    description_markdown: string
    acceptance_criteria_markdown?: string
    source_ref?: string | null
    revision_note?: string | null
  }) => request<AgentRequirementDetail>(`/requirements/${id}/revise`, { method: 'POST', body: JSON.stringify(data) }),
  cancelRequirement: (id: number) => request<AgentRequirementDetail>(`/requirements/${id}/cancel`, { method: 'POST' }),
  deleteRequirement: (id: number) => request<AgentRequirementDetail>(`/requirements/${id}/delete`, { method: 'POST' }),

  getWorkflowDefinitions: () => request<DeclarativeWorkflowDefinition[]>('/workflows/definitions')
    .then((definitions) => definitions.map(normalizeWorkflowDefinition)),
  getWorkflowDefinition: (workflowKey: string) => request<DeclarativeWorkflowDefinition>(`/workflows/definitions/${encodeURIComponent(workflowKey)}`)
    .then(normalizeWorkflowDefinition),
  getWorkflowRunsSummary: () => request<WorkflowRunsSummary>('/workflows/runs/summary'),
  getWorkflowRuns: (filters?: {
    limit?: number
    page?: number
    page_size?: number
    tab?: string
    include_archived?: boolean
    status?: string
    workflow_key?: string
    goal_key?: string
    current_state?: string
    risk_level?: string
    pending_human_gate?: boolean
    requirement_id?: number
  }) => {
    const params = new URLSearchParams()
    params.set('limit', String(filters?.limit ?? 100))
    if (filters?.page != null) params.set('page', String(filters.page))
    if (filters?.page_size != null) params.set('page_size', String(filters.page_size))
    if (filters?.tab) params.set('tab', filters.tab)
    if (filters?.include_archived != null) params.set('include_archived', String(filters.include_archived))
    if (filters?.status) params.set('status', filters.status)
    if (filters?.workflow_key) params.set('workflow_key', filters.workflow_key)
    if (filters?.goal_key) params.set('goal_key', filters.goal_key)
    if (filters?.current_state) params.set('current_state', filters.current_state)
    if (filters?.risk_level) params.set('risk_level', filters.risk_level)
    if (filters?.pending_human_gate != null) params.set('pending_human_gate', String(filters.pending_human_gate))
    if (filters?.requirement_id != null) params.set('requirement_id', String(filters.requirement_id))
    return request<DeclarativeWorkflowRunSummary[]>(`/workflows/runs?${params.toString()}`)
  },
  getWorkflowRunsPage: (filters?: {
    page?: number
    page_size?: number
    tab?: string
    include_archived?: boolean
    status?: string
    workflow_key?: string
    goal_key?: string
    current_state?: string
    risk_level?: string
    pending_human_gate?: boolean
    requirement_id?: number
  }) => {
    const params = new URLSearchParams()
    params.set('page', String(filters?.page ?? 1))
    params.set('page_size', String(filters?.page_size ?? 50))
    if (filters?.tab) params.set('tab', filters.tab)
    if (filters?.include_archived != null) params.set('include_archived', String(filters.include_archived))
    if (filters?.status) params.set('status', filters.status)
    if (filters?.workflow_key) params.set('workflow_key', filters.workflow_key)
    if (filters?.goal_key) params.set('goal_key', filters.goal_key)
    if (filters?.current_state) params.set('current_state', filters.current_state)
    if (filters?.risk_level) params.set('risk_level', filters.risk_level)
    if (filters?.pending_human_gate != null) params.set('pending_human_gate', String(filters.pending_human_gate))
    if (filters?.requirement_id != null) params.set('requirement_id', String(filters.requirement_id))
    return request<DeclarativeWorkflowRunPage>(`/workflows/runs?${params.toString()}`)
  },
  getWorkflowRun: (id: number) => request<DeclarativeWorkflowRunDetail>(`/workflows/runs/${id}`),
  getWorkflowRunEvents: (id: number) => request<DeclarativeWorkflowEvent[]>(`/workflows/runs/${id}/events`),
  archiveWorkflowRun: (id: number, data?: { archived_by?: string; reason?: string }) =>
    request<DeclarativeWorkflowRunSummary>(`/workflows/runs/${id}/archive`, { method: 'POST', body: JSON.stringify(data || {}) }),
  createWorkflowFollowup: (id: number, data?: { title?: string; description_markdown?: string; operator?: string }) =>
    request<{ requirement_id: number; workflow_run_id: number }>(`/workflows/runs/${id}/create-followup`, { method: 'POST', body: JSON.stringify(data || {}) }),
  confirmWorkflowBusinessOutcome: (id: number, data?: { operator?: string; note?: string }) =>
    request<DeclarativeWorkflowRunDetail>(`/workflows/runs/${id}/business-outcome/confirm`, { method: 'POST', body: JSON.stringify(data || {}) }),
  rejectWorkflowBusinessOutcome: (id: number, data?: { operator?: string; note?: string }) =>
    request<DeclarativeWorkflowRunDetail>(`/workflows/runs/${id}/business-outcome/reject`, { method: 'POST', body: JSON.stringify(data || {}) }),
  requestWorkflowBusinessFollowup: (id: number, data?: { title?: string; description_markdown?: string; operator?: string; note?: string }) =>
    request<{ requirement_id: number; workflow_run_id: number; workflow: DeclarativeWorkflowRunDetail }>(`/workflows/runs/${id}/business-outcome/follow-up`, { method: 'POST', body: JSON.stringify(data || {}) }),
  decideWorkflowHumanGate: (
    workflowRunId: number,
    gateId: number,
    data: { decision: string; reviewer?: string; comment?: string },
  ) =>
    request<DeclarativeWorkflowRunDetail>(`/workflows/runs/${workflowRunId}/human-gates/${gateId}/decide`, {
      method: 'POST',
      body: JSON.stringify({
        decision: data.decision,
        reviewer: data.reviewer || 'operator',
        comment: data.comment || '',
      }),
    }),

  getReleaseCandidates: () => request<ReleaseCandidate[]>('/releases/candidates'),
  getReleaseDetail: (requirementId: number) => request<ReleaseDetail>(`/releases/${requirementId}`),
  prepareRelease: (requirementId: number, data?: { actor?: string; note?: string | null }) =>
    request<ReleaseDetail>(`/releases/${requirementId}/prepare`, { method: 'POST', body: JSON.stringify(data || {}) }),
  openReleasePr: (requirementId: number, data?: { actor?: string; note?: string | null }) =>
    request<ReleaseDetail>(`/releases/${requirementId}/open-pr`, { method: 'POST', body: JSON.stringify(data || {}) }),
  deployReleaseToStaging: (requirementId: number, data?: { actor?: string; note?: string | null }) =>
    request<ReleaseDetail>(`/releases/${requirementId}/deploy/staging`, { method: 'POST', body: JSON.stringify(data || {}) }),
  deployReleaseToProduction: (requirementId: number, data?: { actor?: string; note?: string | null }) =>
    request<ReleaseDetail>(`/releases/${requirementId}/deploy/production`, { method: 'POST', body: JSON.stringify(data || {}) }),
  rollbackRelease: (requirementId: number, data: { actor?: string; note?: string | null; rollback_target_sha: string }) =>
    request<ReleaseDetail>(`/releases/${requirementId}/rollback`, { method: 'POST', body: JSON.stringify(data) }),

  getErrors: () => request<ErrorFingerprint[]>('/errors'),
  getErrorDetail: (fingerprintKey: string) => request<ErrorFingerprintDetail>(`/errors/${encodeURIComponent(fingerprintKey)}`),

  // Skills
  getSkills: () => request<string[]>('/skills'),
}
