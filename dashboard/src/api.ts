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
  getTasks: (params?: { status?: string; agent_id?: string; agent_group?: string; project_id?: string; requirement_id?: number; only_anomalies?: boolean }) => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set('status', params.status)
    if (params?.agent_id) qs.set('agent_id', params.agent_id)
    if (params?.agent_group) qs.set('agent_group', params.agent_group)
    if (params?.project_id) qs.set('project_id', params.project_id)
    if (params?.requirement_id != null) qs.set('requirement_id', String(params.requirement_id))
    if (params?.only_anomalies) qs.set('only_anomalies', 'true')
    const q = qs.toString()
    return request<Task[]>(`/tasks${q ? '?' + q : ''}`)
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
  getTaskLogs: (id: number) => request<TaskLog[]>(`/tasks/${id}/logs`),
  getTaskHistory: (id: number) => request<TaskHistoryItem[]>(`/tasks/${id}/history`),

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

  // Requirements
  getRequirements: (status?: string) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : ''
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
