export interface ScheduledCloudRunJob {
  job_name: string
  family: string
  job_type: string
  cadence: string
  command: string
  purpose: string
  scheduler_job: string | null
  freshness_required: boolean
  migration_execution_required: boolean
}

export interface ScheduledCloudRunJobStatus extends ScheduledCloudRunJob {
  publish_status: string
  scheduler_status: string
  health_status: string
  image_digest: string | null
  effective_image: string | null
  latest_execution: string | null
  last_published_at: string | null
  last_deployment_record_id: number | null
  external_url: string | null
  failure_summary: string | null
  diagnostic: string | null
  metadata: Record<string, unknown>
}

export interface ScheduledCloudRunJobsStatus {
  items: ScheduledCloudRunJobStatus[]
  diagnostics: string[]
  updated_at: string | null
}

export interface ScheduledCloudRunJobsPublishResult {
  deployment_record_id: number | null
  task_id: number | null
  family: string
  environment: string
  publish_mode: string
  job_name: string | null
  status: string
  external_url: string | null
  jobs: string[]
  message: string
}

export interface ScheduledCloudRunJobRecord {
  id: number
  deployment_record_id: number | null
  job_name: string | null
  jobs: string[]
  family: string
  job_type: string | null
  environment: string
  publish_mode: string
  source_ref_type: string
  source_ref: string | null
  status: string
  health_status: string
  actor: string | null
  created_by: string | null
  executed_by: string | null
  workflow_file: string | null
  external_run_id: string | null
  external_url: string | null
  failure_summary: string | null
  notes: string | null
  created_at: string | null
  updated_at: string | null
  started_at: string | null
  finished_at: string | null
  metadata: Record<string, unknown>
}

export interface ScheduledCloudRunJobRecordsResult {
  items: ScheduledCloudRunJobRecord[]
  total: number
  limit: number
  offset: number
}

export interface ScheduledCloudRunJobsSyncResult {
  processed_count: number
  succeeded_ids: number[]
  failed_ids: number[]
  running_ids: number[]
  pending_ids: number[]
  error_ids: number[]
}

type RequestFn = <T>(path: string, options?: RequestInit, timeoutMs?: number) => Promise<T>

export function createReleaseScheduledJobsApi(request: RequestFn) {
  return {
    getScheduledCloudRunJobsStatus: () => request<ScheduledCloudRunJobsStatus>('/releases/scheduled-jobs/status'),
    getScheduledCloudRunJobRecords: (filters?: {
      environment?: string
      job_name?: string
      family?: string
      status?: string
      limit?: number
      offset?: number
    }) => {
      const params = new URLSearchParams()
      if (filters?.environment) params.set('environment', filters.environment)
      if (filters?.job_name) params.set('job_name', filters.job_name)
      if (filters?.family) params.set('family', filters.family)
      if (filters?.status) params.set('status', filters.status)
      if (typeof filters?.limit === 'number') params.set('limit', String(filters.limit))
      if (typeof filters?.offset === 'number') params.set('offset', String(filters.offset))
      const query = params.toString()
      return request<ScheduledCloudRunJobRecordsResult>(`/releases/scheduled-jobs/tasks${query ? `?${query}` : ''}`)
    },
    createScheduledCloudRunJobTask: (data: {
      job_name?: string | null
      environment?: 'staging' | 'production'
      source_ref_type?: 'branch' | 'tag' | 'commit'
      source_ref?: string
      actor?: string
      note?: string | null
      run_smoke_jobs?: boolean
      run_migrations?: boolean
    }) => request<ScheduledCloudRunJobRecord>('/releases/scheduled-jobs/tasks', { method: 'POST', body: JSON.stringify(data) }),
    publishScheduledCloudRunJobTask: (taskId: number, data: { actor?: string }) =>
      request<ScheduledCloudRunJobsPublishResult>(`/releases/scheduled-jobs/tasks/${taskId}/publish`, { method: 'POST', body: JSON.stringify(data) }),
    cancelScheduledCloudRunJobTask: (taskId: number) =>
      request<ScheduledCloudRunJobRecord>(`/releases/scheduled-jobs/tasks/${taskId}/cancel`, { method: 'POST' }),
    syncScheduledCloudRunJobs: () =>
      request<ScheduledCloudRunJobsSyncResult>('/releases/scheduled-jobs/sync', { method: 'POST' }),
  }
}
