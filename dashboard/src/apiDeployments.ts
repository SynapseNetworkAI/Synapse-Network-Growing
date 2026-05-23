import { request } from './api'

export interface DeploymentEvent {
  id: number
  deployment_record_id: number
  event_type: string
  actor: string | null
  status_from: string | null
  status_to: string | null
  summary: string | null
  payload: Record<string, unknown>
  created_at: string | null
}

export function getDeploymentEvents(recordId: number) {
  return request<DeploymentEvent[]>(`/deployments/${recordId}/events`)
}
