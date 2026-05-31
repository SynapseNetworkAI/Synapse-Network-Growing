import { request } from './api'

export interface McpServerSurface {
  id: number
  mcp_server_release_id: number
  surface_key: string
  surface_label: string
  status: string
  listing_url: string | null
  failure_reason: string | null
  evidence: Record<string, unknown>
  updated_at: string | null
}

export interface McpServerRelease {
  id: number
  server_key: string
  server_name: string
  package_name: string
  package_registry: string
  package_version: string
  registry_name: string
  git_tag: string | null
  install_command: string
  status: string
  package_url: string | null
  registry_url: string | null
  workflow_run_url: string | null
  failure_summary: string | null
  release_notes: string | null
  smoke_evidence: Record<string, unknown>
  metadata: Record<string, unknown>
  surfaces: McpServerSurface[]
  published_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface McpServerReleaseEvent {
  id: number
  mcp_server_release_id: number
  action: string
  from_status: string | null
  to_status: string | null
  actor: string | null
  note: string | null
  workflow_run_url: string | null
  error_summary: string | null
  metadata: Record<string, unknown>
  created_at: string | null
}

export interface McpServerReleasePage {
  items: McpServerRelease[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface McpServerReleaseSyncResult {
  processed_count: number
  ready_ids: number[]
  package_published_ids: number[]
  registry_listed_ids: number[]
  smoke_passed_ids: number[]
  error_ids: number[]
}

export const mcpServerReleasesApi = {
  list: (filters?: { status?: string; search?: string; page?: number; page_size?: number }) => {
    const params = new URLSearchParams()
    if (filters?.status) params.set('status', filters.status)
    if (filters?.search) params.set('search', filters.search)
    if (filters?.page) params.set('page', String(filters.page))
    if (filters?.page_size) params.set('page_size', String(filters.page_size))
    const q = params.toString() ? `?${params.toString()}` : ''
    return request<McpServerReleasePage>(`/releases/mcp-servers${q}`)
  },
  create: (data: { package_version: string; release_notes?: string | null; server_key?: string }) =>
    request<McpServerRelease>('/releases/mcp-servers', { method: 'POST', body: JSON.stringify(data) }),
  get: (id: number) => request<McpServerRelease>(`/releases/mcp-servers/${id}`),
  events: (id: number) => request<McpServerReleaseEvent[]>(`/releases/mcp-servers/${id}/events`),
  runReadiness: (id: number, data?: { actor?: string; note?: string | null }) =>
    request<McpServerRelease>(`/releases/mcp-servers/${id}/readiness`, { method: 'POST', body: JSON.stringify(data || {}) }),
  publishNpm: (id: number, data?: { actor?: string; note?: string | null; confirm_phrase?: string | null }) =>
    request<McpServerRelease>(`/releases/mcp-servers/${id}/publish-npm`, { method: 'POST', body: JSON.stringify(data || {}) }),
  submitRegistry: (id: number, data?: { actor?: string; note?: string | null }) =>
    request<McpServerRelease>(`/releases/mcp-servers/${id}/submit-registry`, { method: 'POST', body: JSON.stringify(data || {}) }),
  runProdSmoke: (id: number, data?: { actor?: string; note?: string | null }) =>
    request<McpServerRelease>(`/releases/mcp-servers/${id}/prod-smoke`, { method: 'POST', body: JSON.stringify(data || {}) }),
  complete: (id: number, data?: { actor?: string; note?: string | null }) =>
    request<McpServerRelease>(`/releases/mcp-servers/${id}/complete`, { method: 'POST', body: JSON.stringify(data || {}) }),
  patchSurface: (id: number, surfaceKey: string, data: Partial<Pick<McpServerSurface, 'status' | 'listing_url' | 'failure_reason' | 'evidence'>>) =>
    request<McpServerSurface>(`/releases/mcp-servers/${id}/surfaces/${encodeURIComponent(surfaceKey)}`, { method: 'PATCH', body: JSON.stringify(data) }),
  syncStatuses: () => request<McpServerReleaseSyncResult>('/releases/mcp-servers/sync-statuses', { method: 'POST' }),
}
