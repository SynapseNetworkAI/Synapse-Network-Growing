const BASE = '/api'

export interface ApiError extends Error {
  detail?: unknown
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
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
  runtime_session_id: string | null
  runtime_selected_agent: string | null
  output_path: string | null
  output_content: string | null
  execution_time_ms: number | null
  requirement_id: number | null
  requirement_title: string | null
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
  project_key: string
  display_name: string
  root_path: string
  status: string
  allowed_write_globs: string[]
  forbidden_globs: string[]
  required_checks: string[]
  release_mode: string
  requires_manual_approval: boolean
  notes: string | null
  created_at: string | null
  updated_at: string | null
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

export interface Requirement {
  id: number
  title: string
  description_markdown: string
  status: string
  priority: string
  source: string
  source_ref: string | null
  target_project_path: string | null
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
  started_at: string | null
  completed_at: string | null
}

export interface WorkflowRun {
  id: number
  requirement_id: number
  plan_version: number
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
}

export interface OrgNode {
  id: string
  display_name: string
  type: 'org' | 'group' | 'agent'
  goal: string
  icon?: string
  color?: string
  project?: string
  skills?: string[]
  children?: OrgNode[]
}

export interface OrgTree {
  root: OrgNode
}

// API functions
export const api = {
  // Agents
  getAgents: () => request<Agent[]>('/agents'),
  getAgent: (id: string) => request<Agent>(`/agents/${id}`),
  syncAgents: () => request<Agent[]>('/agents/sync', { method: 'POST' }),

  // Org tree
  getOrgTree: () => request<OrgTree>('/org'),

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
  getProjectPolicies: () => request<ProjectPolicy[]>('/project-policies'),
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
    notes?: string | null
  }) => request<ProjectPolicy>(`/project-policies/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
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
    request<RequirementDetail>(`/optimization-signals/${id}/create-requirement`, { method: 'POST', body: JSON.stringify(data || {}) }),

  // Requirements
  getRequirements: (status?: string, sort?: string) => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (sort) params.set('sort', sort)
    const q = params.toString() ? `?${params.toString()}` : ''
    return request<Requirement[]>(`/requirements${q}`)
  },
  getRequirement: (id: number) => request<RequirementDetail>(`/requirements/${id}`),
  createRequirement: (data: {
    title: string
    description_markdown: string
    priority?: string
    source?: string
    source_ref?: string | null
    target_project_path?: string
    depends_on_requirement_ids?: number[]
    auto_start?: boolean
  }) =>
    request<RequirementDetail>('/requirements', { method: 'POST', body: JSON.stringify(data) }),
  planRequirement: (id: number) => request<RequirementDetail>(`/requirements/${id}/plan`, { method: 'POST' }),
  startRequirement: (id: number) => request<RequirementDetail>(`/requirements/${id}/start`, { method: 'POST' }),
  pauseRequirement: (id: number) => request<RequirementDetail>(`/requirements/${id}/pause`, { method: 'POST' }),
  publishRequirement: (id: number, data: { completed_checks?: string[]; note?: string | null }) =>
    request<RequirementDetail>(`/requirements/${id}/publish`, { method: 'POST', body: JSON.stringify(data) }),
  deleteRequirement: (id: number) => request<RequirementDetail>(`/requirements/${id}`, { method: 'DELETE' }),
  updateRequirement: (id: number, data: { title?: string; description_markdown?: string; priority?: string; target_project_path?: string }) =>
    request<RequirementDetail>(`/requirements/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  advanceQueue: () => request<{ started?: number; skipped?: string }>('/requirements/queue/advance', { method: 'POST' }),
  reviseRequirement: (id: number, data: {
    title?: string
    description_markdown: string
    source_ref?: string | null
    revision_note?: string | null
    depends_on_requirement_ids?: number[]
  }) => request<RequirementDetail>(`/requirements/${id}/revise`, { method: 'POST', body: JSON.stringify(data) }),
  updateRequirementDependencies: (id: number, depends_on_requirement_ids: number[]) =>
    request<RequirementDetail>(`/requirements/${id}/dependencies`, {
      method: 'PUT',
      body: JSON.stringify({ depends_on_requirement_ids }),
    }),

  // Skills
  getSkills: () => request<string[]>('/skills'),
}
