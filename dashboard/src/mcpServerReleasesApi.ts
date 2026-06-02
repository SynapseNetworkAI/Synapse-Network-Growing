import { request } from './api'

export interface McpServerSurface {
  id: number
  mcp_server_release_id: number
  surface_key: string
  surface_label: string
  category: string
  status: string
  listing_url: string | null
  submission_url: string | null
  failure_reason: string | null
  operator_note: string | null
  evidence: Record<string, unknown>
  last_checked_at: string | null
  updated_at: string | null
}

export interface McpDiscoverySurface {
  id: number
  surface_key: string
  surface_label: string
  category: string
  requires_npm: boolean
  requires_remote_http: boolean
  supports_auto_submit: boolean
  submission_url: string | null
  docs_url: string | null
  priority: number
  status: string
  updated_at: string | null
}

export interface McpSurfaceConfig {
  id: number
  surface_key: string
  submission_mode: string
  auth_mode: string
  credential_ref: string | null
  required_env_vars: string[]
  docs_url: string | null
  submission_url: string | null
  is_enabled: boolean
  verification_status: string
  verification_summary: string | null
  last_verified_at: string | null
  metadata: Record<string, unknown>
  updated_at: string | null
}

export interface McpSurfaceConfigVerifyResult {
  surface_key: string
  verification_status: string
  verification_summary: string
  missing_env_vars: string[]
  required_tools: string[]
  checked_at: string
}

export interface McpSubmissionReadinessItem {
  surface_key: string
  surface_label: string
  category: string
  surface_status: string
  config_status: string
  readiness_status: string
  reason: string | null
  required_env_vars: string[]
  missing_env_vars: string[]
  submission_mode: string
  credential_ref: string | null
}

export interface McpSubmissionReadiness {
  server_id: number
  release_id: number | null
  items: McpSubmissionReadinessItem[]
}

export interface McpSurfaceLiveCheck {
  release_id: number
  surface_key: string
  status: string
  summary: string
  evidence: Record<string, unknown>
  checked_at: string
}

export interface McpServerRelease {
  id: number
  mcp_server_id: number | null
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

export interface McpServer {
  id: number
  server_key: string
  server_name: string
  repo_full_name: string
  repo_url: string
  local_repo_path: string | null
  package_name: string
  package_registry: string
  registry_name: string
  transport_kind: string
  remote_endpoint_url: string | null
  install_command: string
  tools: string[]
  security_boundary: string | null
  status: string
  metadata: Record<string, unknown>
  latest_release: McpServerRelease | null
  surface_summary: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface McpServerPage {
  items: McpServer[]
  total: number
  page: number
  page_size: number
  total_pages: number
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
  listCatalog: (filters?: { search?: string; transport_kind?: string; status?: string; surface_category?: string; page?: number; page_size?: number }) => {
    const params = new URLSearchParams()
    if (filters?.search) params.set('search', filters.search)
    if (filters?.transport_kind) params.set('transport_kind', filters.transport_kind)
    if (filters?.status) params.set('status', filters.status)
    if (filters?.surface_category) params.set('surface_category', filters.surface_category)
    if (filters?.page) params.set('page', String(filters.page))
    if (filters?.page_size) params.set('page_size', String(filters.page_size))
    const q = params.toString() ? `?${params.toString()}` : ''
    return request<McpServerPage>(`/releases/mcp-servers/catalog${q}`)
  },
  createServer: (data: {
    server_key: string
    server_name: string
    repo_full_name: string
    repo_url: string
    local_repo_path?: string | null
    package_name: string
    package_registry?: string
    registry_name: string
    transport_kind: string
    remote_endpoint_url?: string | null
    install_command: string
    tools?: string[]
    security_boundary?: string | null
  }) => request<McpServer>('/releases/mcp-servers/catalog', { method: 'POST', body: JSON.stringify(data) }),
  getServer: (id: number) => request<McpServer>(`/releases/mcp-servers/catalog/${id}`),
  createReleaseForServer: (serverId: number, data: { package_version: string; release_notes?: string | null }) =>
    request<McpServerRelease>(`/releases/mcp-servers/catalog/${serverId}/releases`, { method: 'POST', body: JSON.stringify(data) }),
  listSurfaces: () => request<McpDiscoverySurface[]>('/releases/mcp-surfaces'),
  getSurfaceConfig: (surfaceKey: string) =>
    request<McpSurfaceConfig>(`/releases/mcp-surfaces/${encodeURIComponent(surfaceKey)}/config`),
  patchSurfaceConfig: (surfaceKey: string, data: Partial<Pick<McpSurfaceConfig, 'submission_mode' | 'auth_mode' | 'credential_ref' | 'required_env_vars' | 'docs_url' | 'submission_url' | 'is_enabled' | 'metadata'>>) =>
    request<McpSurfaceConfig>(`/releases/mcp-surfaces/${encodeURIComponent(surfaceKey)}/config`, { method: 'PATCH', body: JSON.stringify(data) }),
  verifySurfaceConfig: (surfaceKey: string) =>
    request<McpSurfaceConfigVerifyResult>(`/releases/mcp-surfaces/${encodeURIComponent(surfaceKey)}/config/verify`, { method: 'POST' }),
  getSubmissionReadiness: (serverId: number) =>
    request<McpSubmissionReadiness>(`/releases/mcp-servers/${serverId}/submission-readiness`),
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
  deployRemoteProd: (id: number, data?: { actor?: string; note?: string | null; confirm_phrase?: string | null }) =>
    request<McpServerRelease>(`/releases/mcp-servers/${id}/deploy-remote-prod`, { method: 'POST', body: JSON.stringify(data || {}) }),
  complete: (id: number, data?: { actor?: string; note?: string | null }) =>
    request<McpServerRelease>(`/releases/mcp-servers/${id}/complete`, { method: 'POST', body: JSON.stringify(data || {}) }),
  patchSurface: (id: number, surfaceKey: string, data: Partial<Pick<McpServerSurface, 'status' | 'listing_url' | 'failure_reason' | 'evidence'>>) =>
    request<McpServerSurface>(`/releases/mcp-servers/${id}/surfaces/${encodeURIComponent(surfaceKey)}`, { method: 'PATCH', body: JSON.stringify(data) }),
  syncSurfaces: (id: number) =>
    request<McpServerRelease>(`/releases/mcp-servers/${id}/surface-sync`, { method: 'POST' }),
  liveCheckSurface: (id: number, data: { surface_key: string; actor?: string; note?: string | null }) =>
    request<McpSurfaceLiveCheck>(`/releases/mcp-servers/${id}/surface-live-check`, { method: 'POST', body: JSON.stringify(data) }),
  submitSurface: (id: number, data: { surface_key: string; actor?: string; note?: string | null }) =>
    request<McpServerSurface>(`/releases/mcp-servers/${id}/submit-surface`, { method: 'POST', body: JSON.stringify(data) }),
  submitDirectory: (id: number, data: { surface_key: string; actor?: string; note?: string | null }) =>
    request<McpServerSurface>(`/releases/mcp-servers/${id}/submit-directory`, { method: 'POST', body: JSON.stringify(data) }),
  syncStatuses: () => request<McpServerReleaseSyncResult>('/releases/mcp-servers/sync-statuses', { method: 'POST' }),
}
