import { request, type ReleaseTask } from './api'

export interface DeploymentEvent {
  id: number
  deployment_record_id: number
  sequence: number
  event_type: 'stdout' | 'stderr' | 'step_started' | 'step_finished' | 'runner_status' | 'local_deploy_force_reset' | string
  step_key: string | null
  message: string
  created_at: string | null
}

export interface DeploymentEventsPage {
  items: DeploymentEvent[]
  next_sequence: number
  has_more: boolean
}

export interface ReleaseTaskPage {
  items: ReleaseTask[]
  total: number
  limit: number
  offset: number
}

export function getReleaseTasksPage(filters?: {
  project_key?: string
  environment?: string
  status?: string
  source_type?: string
  q?: string
  limit?: number
  offset?: number
}) {
  const params = new URLSearchParams()
  if (filters?.project_key) params.set('project_key', filters.project_key)
  if (filters?.environment) params.set('environment', filters.environment)
  if (filters?.status) params.set('status', filters.status)
  if (filters?.source_type) params.set('source_type', filters.source_type)
  if (filters?.q) params.set('q', filters.q)
  if (filters?.limit) params.set('limit', String(filters.limit))
  if (filters?.offset) params.set('offset', String(filters.offset))
  const q = params.toString() ? `?${params.toString()}` : ''
  return request<ReleaseTaskPage>(`/releases/tasks/query${q}`)
}

export function getReleaseTaskGateStatus(id: number) {
  return request<ReleaseTask['pr_gate']>(`/releases/tasks/${id}/gate-status`)
}

export function getDeploymentEvents(deploymentId: number, filters?: { after_sequence?: number; limit?: number }) {
  const params = new URLSearchParams()
  if (filters?.after_sequence !== undefined) params.set('after_sequence', String(filters.after_sequence))
  if (filters?.limit) params.set('limit', String(filters.limit))
  const q = params.toString() ? `?${params.toString()}` : ''
  return request<DeploymentEventsPage>(`/releases/deployments/${deploymentId}/events${q}`)
}

export function deployReleaseTask(id: number, data?: { actor?: string; note?: string | null; confirm_phrase?: string | null }) {
  return request<ReleaseTask>(`/releases/tasks/${id}/deploy`, { method: 'POST', body: JSON.stringify(data || {}) })
}

export function resetReleaseTaskRunning(
  id: number,
  data: { confirm_phrase: string; operator?: string; reason?: string | null },
) {
  return request<ReleaseTask>(`/releases/tasks/${id}/reset-running`, { method: 'POST', body: JSON.stringify(data) })
}

export function attachReleaseTaskPrebuiltImage(
  id: number,
  data: {
    service_key: string
    image_digest: string
    source_commit_sha: string
    image_source?: string
    build_evidence?: Record<string, unknown>
  },
) {
  return request<ReleaseTask>(`/releases/tasks/${id}/attach-prebuilt-image`, { method: 'POST', body: JSON.stringify(data) })
}
