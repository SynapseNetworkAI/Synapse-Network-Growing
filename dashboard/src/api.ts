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
  approval_dependency_count: number
  completion_rate: number
  reopen_rate: number
  approval_dependency_rate: number
  average_token_cost: number
  average_budget_cost_points: number
  tokens_used_total: number
  budget_cost_points_total: number
  open_requirement_count: number
  status_mix: Record<string, number>
}

export interface ApprovalRoleKPI {
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
  approval_pending_count: number
  approval_stale_count: number
}

export interface RoleKpiSnapshot {
  roles: RoleKPI[]
  approval_roles: ApprovalRoleKPI[]
  summary: RoleWorkAllocationSummary
}

export interface Task {
  id: number
  description: string
  agent_id: string
  status: string
  requires_approval: boolean
  priority: string
  project_id: string | null
  project_label: string | null
  agent_group: string | null
  skill_name: string | null
  context_files: string | null
  retry_of_task_id: number | null
  attempt_no: number
  last_error_message: string | null
  runtime_backend: string | null
  runtime_provider: string | null
  runtime_model: string | null
  runtime_session_id: string | null
  runtime_selected_agent: string | null
  output_path: string | null
  output_content: string | null
  execution_time_ms: number | null
  tokens_used: number
  budget_cost_points: number
  requirement_id: number | null
  requirement_title: string | null
  workflow_step_type: string | null
  workflow_step_title: string | null
  output_files: string[] | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface Approval {
  id: number
  task_id: number
  status: string
  reviewer: string | null
  comment: string | null
  created_at: string
  decided_at: string | null
  task: Task | null
}

export interface TaskLog {
  id: number
  task_id: number
  event_type: string
  detail: string | null
  created_at: string
}

export interface TaskHistoryItem {
  task_id: number
  retry_of_task_id: number | null
  attempt_no: number
  status: string
  project_id: string | null
  agent_group: string | null
  agent_id: string
  skill_name: string | null
  last_error_message: string | null
  runtime_backend: string | null
  runtime_provider: string | null
  runtime_model: string | null
  tokens_used: number
  budget_cost_points: number
  created_at: string | null
  started_at: string | null
  completed_at: string | null
}

export interface FileChange {
  filename: string
  additions: number
  deletions: number
  patch: string
}

export interface TaskFileChanges {
  changed_files: FileChange[]
  target_project_path: string | null
  source: 'snapshot' | 'live'
  captured_at: string | null
  error?: string
}

export interface TaskOutputFile {
  file_name: string
  content: string
  size_bytes: number
  truncated: boolean
  content_type: string
}

export interface RequirementTaskOutput {
  task_id: number
  step_id: number | null
  step_key: string
  step_type: string
  step_title: string
  task_status: string
  output_files: string[]
  changed_files: FileChange[]
  target_project_paths: string[]
  source: string
  captured_at: string | null
  legacy_snapshot: boolean
  change_warning: string | null
}

export interface RequirementMergedOutputFile {
  file_name: string
  task_ids: number[]
  step_keys: string[]
  step_types: string[]
  step_titles: string[]
}

export interface TaskPage {
  items: Task[]
  total: number
  page: number
  page_size: number
  total_pages: number
  status_counts: Record<string, number>
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

export interface TaskBulkRetryRequest {
  task_ids: number[]
  mode?: 'run_now' | 'edit_first'
}

export interface TaskExecutionCandidate {
  agent_id: string
  display_name: string
  agent_group: string
  skill_name: string
  confidence: number
  reason: string
}

export interface TaskExecutionSuggestion {
  agent_id: string | null
  skill_name: string | null
  confidence: number
  reason: string
  requires_confirmation: boolean
  candidates: TaskExecutionCandidate[]
}

export interface DashboardStats {
  agent_count: number
  task_total: number
  task_pending: number
  task_running: number
  task_completed: number
  task_failed: number
  approval_pending: number
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
  approval_required: boolean
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
  approval_status: string
  approval_contract: Record<string, unknown>
  approval_requested_at: string | null
  approved_at: string | null
  current_plan_version: number
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

export interface WorkflowStep {
  id: number
  workflow_run_id: number
  requirement_id: number
  step_key: string
  step_type: string
  title: string
  status: string
  sequence_no: number
  assigned_agent_id: string | null
  assigned_workflow_role: string | null
  branch_from_step_id: number | null
  compatibility_task_id: number | null
  retry_count: number
  handoff_summary_markdown: string | null
  done_when_markdown: string
  context_policy_json: string | null
  execution_profile_json: string | null
  runtime_backend: string | null
  runtime_provider: string | null
  runtime_model: string | null
  runtime_session_id: string | null
  runtime_selected_agent: string | null
  execution_time_ms: number | null
  tokens_used: number
  started_at: string | null
  completed_at: string | null
}

export interface RequirementPlanPatch {
  human_readable_body: string
}

export interface WorkflowStepPatch {
  title?: string
  done_when_markdown?: string
  handoff_summary_markdown?: string
}

export interface WorkflowRun {
  id: number
  requirement_id: number
  plan_version: number
  step_model_version: string
  status: string
  triggered_by: string
  planner_artifact_id: number | null
  started_at: string | null
  completed_at: string | null
  created_at: string | null
  updated_at: string | null
  steps: WorkflowStep[]
}

export interface Artifact {
  id: number
  requirement_id: number
  workflow_run_id: number | null
  step_id: number | null
  producer_step_id: number | null
  artifact_type: string
  path: string | null
  content_summary: string | null
  human_readable_body: string | null
  machine_readable_payload: string | null
  created_at: string | null
}

export interface RequirementDetail {
  requirement: Requirement
  workflow_run: WorkflowRun | null
  dependencies: RequirementDependency[]
  acceptance_checks: RequirementAcceptanceCheck[]
  artifacts: Artifact[]
  delivery_state: DeliveryState | null
  deployment_records: DeploymentRecord[]
  task_outputs: RequirementTaskOutput[]
  merged_output_files: RequirementMergedOutputFile[]
  incidents: Array<{
    incident_key: string
    requirement_id: number
    workflow_run_id: number | null
    step_id: number | null
    source_artifact_id: number
    source_artifact_type: string
    incident_family: string
    incident_code: string
    severity: string
    recovery_status: string
    title: string
    summary: string
    recommended_action: string
    project_root_path: string | null
    project_display_name: string | null
    evidence: Record<string, unknown>[]
    occurred_at: string | null
  }>
  attachments: RequirementAttachment[]
}

export interface AgentRequirement {
  id: number
  title: string
  description_markdown: string
  acceptance_criteria_markdown: string
  status: string
  priority: string
  source: string
  source_ref: string | null
  project_id: number | null
  project_key: string | null
  project_display_name: string | null
  target_project_path: string | null
  target_project_path_override: string | null
  target_projects: string[]
  approval_required: boolean
  approval_status: string
  phase: string
  allowed_actions: string[]
  pending_operations: string[]
  recovery_status: string | null
  assets_status: string
  assets_error_message: string | null
  created_at: string | null
  updated_at: string | null
  active_execution_run_id: number | null
  latest_execution_run_id: number | null
  latest_release_status: string | null
}

export interface AgentRequirementApproval {
  approval_decision: string
  approval_status: string
  approval_reason: string | null
  approval_source: string | null
  required_approver_roles: string[]
  risk_flags: string[]
  pending_execution_start: boolean
  auto_started: boolean
  execution_run_id: number | null
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
  delivery_expectation?: string
  markdown?: string
}

export interface ExecutionPlanStep {
  step_key: string
  title: string
  step_type?: string
  scope?: string
  done_when?: string
}

export interface ExecutionPlan {
  planning_mode?: string
  goal_summary?: string
  summary_markdown?: string
  target_files_or_areas?: string[]
  steps?: ExecutionPlanStep[]
  planned_checks?: string[]
  risks?: string[]
  delivery_intent?: string
}

export interface AgentRequirementDetail {
  requirement: AgentRequirement
  policy_summary_markdown: string
  project: Project | null
  latest_execution_id: number | null
  latest_release_id: number | null
  latest_release: ReleaseRecord | null
  approval: AgentRequirementApproval
  phase: string
  allowed_actions: string[]
  pending_operations: string[]
  recovery_status: string | null
  assets_status: string
  assets_error_message: string | null
  acceptance_contract: AcceptanceContract
  execution_plan: ExecutionPlan
  attachments: RequirementAttachment[]
}

export interface ExecutionNode {
  id: number
  execution_run_id: number
  requirement_id: number
  node_key: string
  node_type: string
  title: string
  status: string
  sequence_no: number
  task_id: number | null
  task_status: string | null
  agent_id: string | null
  agent_label: string | null
  runtime_backend: string | null
  runtime_provider: string | null
  runtime_model: string | null
  tokens_used: number | null
  elapsed_ms: number | null
  summary_markdown: string | null
  started_at: string | null
  completed_at: string | null
}

export interface ValidationCheckResult {
  label: string
  command: string | null
  project_path: string | null
  status: string
  output_excerpt: string | null
}

export interface VerificationPlan {
  mode: string
  summary: string
  checks: string[]
  evidence_expectations: string[]
  why_no_verification: string | null
}

export interface ValidationRecord {
  id: number
  requirement_id: number
  execution_run_id: number
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
  created_at: string | null
  updated_at: string | null
}

export interface ExecutionRun {
  id: number
  requirement_id: number
  execution_mode: string
  complexity: string
  status: string
  phase: string
  is_current_execution: boolean
  allowed_actions: string[]
  pending_operations: string[]
  recovery_status: string | null
  queue_reason: string | null
  blocking_reason_code: string | null
  blocking_reason_message: string | null
  validation_profile: string
  delivery_intent: string
  approval_required: boolean
  planner_summary: string | null
  target_projects: string[]
  latest_task_id: number | null
  agent_id: string | null
  agent_label: string | null
  runtime_backend: string | null
  runtime_provider: string | null
  runtime_model: string | null
  runtime_session_id: string | null
  resume_count: number | null
  last_heartbeat_at: string | null
  tokens_used_total: number | null
  elapsed_ms: number | null
  current_branch: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ExecutionChangedFile {
  path: string
  change_type: string
  additions: number
  deletions: number
  preview_available: boolean
}

export interface ExecutionFilePreview {
  path: string
  diff_patch: string | null
  current_content: string | null
  truncated: boolean
}

export interface ExecutionRuntimeSummary {
  tokens_used_total: number | null
  elapsed_ms: number | null
  agent_id: string | null
  agent_label: string | null
  runtime_backend: string | null
  runtime_provider: string | null
  runtime_model: string | null
  current_branch: string | null
}

export interface ExecutionActivityEvent {
  ts: string | null
  event: string
  status: string | null
  message: string
}

export interface ExecutionDetail {
  execution: ExecutionRun
  requirement: AgentRequirement
  phase: string
  is_current_execution: boolean
  allowed_actions: string[]
  pending_operations: string[]
  recovery_status: string | null
  queue_reason: string | null
  blocking_reason_code: string | null
  blocking_reason_message: string | null
  nodes: ExecutionNode[]
  validation: ValidationRecord | null
  verification_result: ValidationRecord | null
  verification_plan: VerificationPlan | null
  changed_files: ExecutionChangedFile[]
  runtime_summary: ExecutionRuntimeSummary | null
  delivery_summary: ReleaseRecord | null
  activity_stream: ExecutionActivityEvent[]
  incidents: Array<Record<string, unknown>>
  plan_summary: ExecutionPlan
  raw_task_output: string | null
  raw_task_output_truncated: boolean
}

export interface ReleaseRecord {
  id: number
  requirement_id: number
  execution_run_id: number | null
  project_id: number | null
  project_key: string | null
  project_display_name: string | null
  target_project_path: string | null
  status: string
  branch_name: string | null
  base_branch: string | null
  commit_sha: string | null
  compare_url: string | null
  pr_url: string | null
  pr_number: number | null
  notes: string | null
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
  latest_execution_run_id: number | null
}

export interface ErrorFingerprintDetail {
  fingerprint: ErrorFingerprint
  requirement: AgentRequirement | null
  latest_execution: ExecutionRun | null
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
  approval_required_decisions: number
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
  approval_required?: boolean
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
  approval_required: boolean
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
  last_result: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface RecurringWorkflowRunResult {
  workflow_key: string
  status: string
  run_started_at: string | null
  result: Record<string, unknown>
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

  // Tasks
  getTasks: (params?: { status?: string; agent_id?: string; agent_group?: string; project_id?: string; requirement_id?: number; only_anomalies?: boolean; search?: string; page?: number; page_size?: number }) => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set('status', params.status)
    if (params?.agent_id) qs.set('agent_id', params.agent_id)
    if (params?.agent_group) qs.set('agent_group', params.agent_group)
    if (params?.project_id) qs.set('project_id', params.project_id)
    if (params?.requirement_id != null) qs.set('requirement_id', String(params.requirement_id))
    if (params?.only_anomalies) qs.set('only_anomalies', 'true')
    if (params?.search) qs.set('search', params.search)
    if (params?.page != null) qs.set('page', String(params.page))
    if (params?.page_size != null) qs.set('page_size', String(params.page_size))
    const q = qs.toString()
    return request<TaskPage>(`/tasks${q ? '?' + q : ''}`)
  },
  createTask: (data: { description: string; agent_id?: string; requires_approval?: boolean; priority?: string; skill_name?: string; confirm_auto_selection?: boolean }) =>
    request<Task>('/tasks', { method: 'POST', body: JSON.stringify(data) }),
  suggestTaskExecution: (data: { description: string; agent_id?: string; skill_name?: string; limit?: number }) =>
    request<TaskExecutionSuggestion>('/tasks/suggest-execution', { method: 'POST', body: JSON.stringify(data) }),
  runTask: (id: number, skill?: string) => {
    const qs = skill ? `?skill=${encodeURIComponent(skill)}` : ''
    return request<Task>(`/tasks/${id}/run${qs}`, { method: 'POST' })
  },
  retryTask: (id: number, mode: 'run_now' | 'edit_first' = 'run_now') =>
    request<Task>(`/tasks/${id}/retry?mode=${encodeURIComponent(mode)}`, { method: 'POST' }),
  bulkRetryTasks: (data: TaskBulkRetryRequest) =>
    request<Task[]>('/tasks/bulk-retry', { method: 'POST', body: JSON.stringify(data) }),
  pauseTask: (id: number) =>
    request<Task>(`/tasks/${id}/pause`, { method: 'POST' }),
  updateTask: (id: number, data: { description?: string; priority?: string }) =>
    request<Task>(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  getTaskLogs: (id: number) => request<TaskLog[]>(`/tasks/${id}/logs`),
  getTaskHistory: (id: number) => request<TaskHistoryItem[]>(`/tasks/${id}/history`),
  getTaskFileChanges: (id: number) => request<TaskFileChanges>(`/tasks/${id}/file-changes`),
  getTaskOutputFile: (id: number, fileName: string) =>
    request<TaskOutputFile>(`/tasks/${id}/output-files/${encodeURIComponent(fileName)}`),

  // Approvals
  getApprovals: (status?: string) => {
    const q = status ? `?status=${status}` : ''
    return request<Approval[]>(`/approvals${q}`)
  },
  decideApproval: (id: number, data: { action: string; comment?: string; reviewer?: string }) =>
    request<Approval>(`/approvals/${id}/decide`, { method: 'POST', body: JSON.stringify(data) }),
  bulkDecideApprovals: (data: { approval_ids: number[]; action: string; comment?: string; reviewer?: string }) =>
    request<Approval[]>('/approvals/bulk-decide', { method: 'POST', body: JSON.stringify(data) }),

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

  // Agent-first requirements / executions / releases
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
  approveRequirement: (id: number, data?: { reviewer?: string; comment?: string | null }) =>
    request<AgentRequirementDetail>(`/requirements/${id}/approve`, { method: 'POST', body: JSON.stringify({ action: 'approve', reviewer: data?.reviewer || 'operator', comment: data?.comment || '' }) }),
  rejectRequirement: (id: number, data?: { reviewer?: string; comment?: string | null }) =>
    request<AgentRequirementDetail>(`/requirements/${id}/reject`, { method: 'POST', body: JSON.stringify({ action: 'reject', reviewer: data?.reviewer || 'operator', comment: data?.comment || '' }) }),
  reviseRequirement: (id: number, data: {
    title?: string
    description_markdown: string
    acceptance_criteria_markdown?: string
    source_ref?: string | null
    revision_note?: string | null
  }) => request<AgentRequirementDetail>(`/requirements/${id}/revise`, { method: 'POST', body: JSON.stringify(data) }),
  cancelRequirement: (id: number) => request<AgentRequirementDetail>(`/requirements/${id}/cancel`, { method: 'POST' }),
  deleteRequirement: (id: number) => request<AgentRequirementDetail>(`/requirements/${id}/delete`, { method: 'POST' }),

  getExecutions: () => request<ExecutionRun[]>('/executions'),
  createExecution: (data: { requirement_id: number }) =>
    request<ExecutionDetail>('/executions', { method: 'POST', body: JSON.stringify(data) }),
  getExecution: (id: number) => request<ExecutionDetail>(`/executions/${id}`),
  getExecutionFilePreview: (id: number, filePath: string) =>
    request<ExecutionFilePreview>(`/executions/${id}/files/${encodeURIComponent(filePath)}`),
  startExecution: (id: number) => request<ExecutionDetail>(`/executions/${id}/start`, { method: 'POST' }),
  pauseExecution: (id: number) => request<ExecutionDetail>(`/executions/${id}/pause`, { method: 'POST' }),
  resumeExecution: (id: number) => request<ExecutionDetail>(`/executions/${id}/resume`, { method: 'POST' }),
  retryExecution: (id: number) => request<ExecutionDetail>(`/executions/${id}/retry`, { method: 'POST' }),
  validateExecution: (id: number) => request<ExecutionDetail>(`/executions/${id}/validate`, { method: 'POST' }),

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
