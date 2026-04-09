const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
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
  output_path: string | null
  output_content: string | null
  execution_time_ms: number | null
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
  created_at: string | null
  started_at: string | null
  completed_at: string | null
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

export interface OrgNode {
  id: string
  display_name: string
  type: 'cto' | 'domain' | 'team' | 'service' | 'agent'
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
  getTasks: (params?: { status?: string; agent_id?: string; agent_group?: string; project_id?: string; only_anomalies?: boolean }) => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set('status', params.status)
    if (params?.agent_id) qs.set('agent_id', params.agent_id)
    if (params?.agent_group) qs.set('agent_group', params.agent_group)
    if (params?.project_id) qs.set('project_id', params.project_id)
    if (params?.only_anomalies) qs.set('only_anomalies', 'true')
    const q = qs.toString()
    return request<Task[]>(`/tasks${q ? '?' + q : ''}`)
  },
  createTask: (data: { description: string; agent_id: string; requires_approval?: boolean; priority?: string; skill_name?: string }) =>
    request<Task>('/tasks', { method: 'POST', body: JSON.stringify(data) }),
  runTask: (id: number, skill?: string) => {
    const qs = skill ? `?skill=${encodeURIComponent(skill)}` : ''
    return request<Task>(`/tasks/${id}/run${qs}`, { method: 'POST' })
  },
  retryTask: (id: number, mode: 'run_now' | 'edit_first' = 'run_now') =>
    request<Task>(`/tasks/${id}/retry?mode=${encodeURIComponent(mode)}`, { method: 'POST' }),
  getTaskLogs: (id: number) => request<TaskLog[]>(`/tasks/${id}/logs`),
  getTaskHistory: (id: number) => request<TaskHistoryItem[]>(`/tasks/${id}/history`),

  // Approvals
  getApprovals: (status?: string) => {
    const q = status ? `?status=${status}` : ''
    return request<Approval[]>(`/approvals${q}`)
  },
  decideApproval: (id: number, data: { action: string; comment?: string; reviewer?: string }) =>
    request<Approval>(`/approvals/${id}/decide`, { method: 'POST', body: JSON.stringify(data) }),

  // Dashboard
  getStats: () => request<DashboardStats>('/dashboard/stats'),

  // Skills
  getSkills: () => request<string[]>('/skills'),
}
