type RequestFn = <T>(path: string, options?: RequestInit, timeoutMs?: number) => Promise<T>

export interface BugRecord {
  id: number
  bug_key: string
  source_key: string
  source_kind: string
  status: string
  title: string
  summary: string
  severity: string
  fingerprint: string
  project_key: string | null
  project_root_path: string | null
  source_ref: string | null
  environment: string | null
  occurrence_count: number
  evidence: Array<Record<string, unknown>>
  metadata: Record<string, unknown>
  scorecard: Record<string, unknown>
  converted_requirement_id: number | null
  materialized_requirement_id?: number | null
  discovery_status: string
  discovery_recommendation?: Record<string, unknown> | null
  first_seen_at: string | null
  last_seen_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface BugFixAttempt {
  id: number
  bug_id: number
  status: string
  agent_id: string
  branch_name: string | null
  commit_sha: string | null
  pr_url: string | null
  workflow_run_id: number | null
  requirement_id: number | null
  lease_expires_at: string | null
  verification_summary: string | null
  verification_commands: Array<Record<string, unknown>>
  verification_screenshots: Array<Record<string, unknown>>
  failure_reason: string | null
  created_at: string | null
  updated_at: string | null
  verified_at: string | null
}

export interface BugEvent {
  id: number
  bug_id: number
  event_type: string
  actor: string
  from_status: string | null
  to_status: string | null
  message: string
  metadata: Record<string, unknown>
  created_at: string | null
}

export interface BugAgentContext {
  bug_id: number
  bug_key: string
  project_key: string | null
  target_project_path: string | null
  title: string
  summary: string
  repro_steps: string[]
  expected_behavior: string | null
  actual_behavior: string | null
  evidence: Array<Record<string, unknown>>
  acceptance_checks: string[]
  linked_requirement_id: number | null
  allowed_next_actions: string[]
}

export interface BugList {
  items: BugRecord[]
  total: number
  limit: number
  offset: number
  status_counts: Record<string, number>
  severity_counts: Record<string, number>
}

export interface BugDetail {
  bug: BugRecord
  latest_fix_attempt: BugFixAttempt | null
  fix_attempts: BugFixAttempt[]
  events: BugEvent[]
  agent_context: BugAgentContext
}

export interface BugClaimResult {
  bug: BugRecord
  fix_attempt: BugFixAttempt
  agent_context: BugAgentContext
}

export function createBugsApi(request: RequestFn) {
  return {
    getBugs: (params?: {
      project_key?: string
      status?: string
      severity?: string
      source_key?: string
      q?: string
      limit?: number
      offset?: number
    }) => {
      const query = new URLSearchParams()
      Object.entries(params || {}).forEach(([key, value]) => {
        if (value !== undefined && value !== null && String(value).trim()) query.set(key, String(value))
      })
      return request<BugList>(`/bugs${query.toString() ? `?${query.toString()}` : ''}`)
    },
    getBugDetail: (id: number) => request<BugDetail>(`/bugs/${id}`),
    claimBug: (id: number, data?: { agent_id?: string; lease_minutes?: number }) =>
      request<BugDetail | BugClaimResult>(`/bugs/${id}/claim`, { method: 'POST', body: JSON.stringify(data || {}) }),
    materializeBugRequirement: (id: number) =>
      request<BugDetail>(`/bugs/${id}/materialize-requirement`, { method: 'POST', body: JSON.stringify({}) }),
    linkBugFix: (
      id: number,
      data: {
        agent_id?: string
        branch_name?: string
        commit_sha?: string
        pr_url?: string
        workflow_run_id?: number
        requirement_id?: number
      },
    ) => request<BugDetail>(`/bugs/${id}/link-fix`, { method: 'POST', body: JSON.stringify(data) }),
    addBugVerification: (
      id: number,
      data: {
        agent_id?: string
        status?: string
        summary: string
        commands?: Array<Record<string, unknown>>
        screenshots?: Array<Record<string, unknown>>
      },
    ) => request<BugDetail>(`/bugs/${id}/verification`, { method: 'POST', body: JSON.stringify(data) }),
    closeBug: (id: number, data?: { actor?: string; resolution?: string }) =>
      request<BugDetail>(`/bugs/${id}/close`, { method: 'POST', body: JSON.stringify(data || {}) }),
    reopenBug: (id: number, data: { actor?: string; reason: string }) =>
      request<BugDetail>(`/bugs/${id}/reopen`, { method: 'POST', body: JSON.stringify(data) }),
  }
}
