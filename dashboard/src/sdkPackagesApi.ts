import { request } from './api'

export interface SdkPackageRelease {
  id: number
  release_train_version: string
  sdk_language: string
  package_name: string
  registry: string
  channel: 'preview' | 'latest' | 'beta' | 'next' | string
  package_version: string
  git_tag: string | null
  status: 'planned' | 'dry_running' | 'building' | 'ready_to_publish' | 'publishing' | 'published' | 'failed' | 'cancelled' | string
  package_url: string | null
  workflow_run_url: string | null
  failure_summary: string | null
  release_notes: string | null
  metadata: Record<string, unknown>
  published_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SdkPackageReleaseEvent {
  id: number
  sdk_package_release_id: number
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

export interface SdkPackageReleasePage {
  items: SdkPackageRelease[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface SdkReleaseTrain {
  release_train_version: string
  channel: string
  package_count: number
  status_counts: Record<string, number>
  packages: SdkPackageRelease[]
  created_at: string | null
  updated_at: string | null
}

export interface SdkPackageReleaseSyncResult {
  processed_count: number
  publishing_ids: number[]
  ready_ids: number[]
  published_ids: number[]
  failed_ids: number[]
  error_ids: number[]
}

export interface SdkPackagePlatform {
  platform_key: string
  sdk_language: string
  registry: string
  package_name: string
  registry_url: string
  package_url_template: string
  credential_env_var: string
  enabled: boolean
  configured: boolean
  credential_present: boolean
  dry_run_template: string
  publish_template: string
  verify_template: string
  install_command: string
  notes: string | null
  metadata: Record<string, unknown>
  updated_at: string | null
}

export const sdkPackagesApi = {
  getSdkPackagePlatforms: () => request<SdkPackagePlatform[]>('/releases/sdk-packages/platforms'),
  updateSdkPackagePlatform: (platformKey: string, data: Partial<Pick<SdkPackagePlatform, 'enabled' | 'registry_url' | 'package_name' | 'package_url_template' | 'credential_env_var' | 'notes'>>) =>
    request<SdkPackagePlatform>(`/releases/sdk-packages/platforms/${encodeURIComponent(platformKey)}`, { method: 'PATCH', body: JSON.stringify(data) }),
  getSdkPackageReleases: (filters?: { release_train_version?: string; sdk_language?: string; registry?: string; status?: string; search?: string; page?: number; page_size?: number }) => {
    const params = new URLSearchParams()
    if (filters?.release_train_version) params.set('release_train_version', filters.release_train_version)
    if (filters?.sdk_language) params.set('sdk_language', filters.sdk_language)
    if (filters?.registry) params.set('registry', filters.registry)
    if (filters?.status) params.set('status', filters.status)
    if (filters?.search) params.set('search', filters.search)
    if (filters?.page) params.set('page', String(filters.page))
    if (filters?.page_size) params.set('page_size', String(filters.page_size))
    const q = params.toString() ? `?${params.toString()}` : ''
    return request<SdkPackageReleasePage>(`/releases/sdk-packages${q}`)
  },
  getSdkPackageRelease: (id: number) => request<SdkPackageRelease>(`/releases/sdk-packages/${id}`),
  getSdkPackageReleaseEvents: (id: number) => request<SdkPackageReleaseEvent[]>(`/releases/sdk-packages/${id}/events`),
  getSdkReleaseTrains: () => request<SdkReleaseTrain[]>('/releases/sdk-trains'),
  getSdkReleaseTrain: (version: string) => request<SdkReleaseTrain>(`/releases/sdk-trains/${encodeURIComponent(version)}`),
  initializeSdkReleaseTrain: (data: {
    release_train_version: string
    channel: string
    release_notes?: string | null
    packages?: string[]
  }) => request<SdkPackageRelease[]>('/releases/sdk-packages/initialize-train', { method: 'POST', body: JSON.stringify(data) }),
  dryRunSdkPackageRelease: (id: number, data?: { actor?: string; package_version?: string | null; channel?: string | null; note?: string | null }) =>
    request<SdkPackageRelease>(`/releases/sdk-packages/${id}/dry-run`, { method: 'POST', body: JSON.stringify(data || {}) }),
  publishSdkPackageRelease: (id: number, data?: { actor?: string; package_version?: string | null; channel?: string | null; note?: string | null; confirm_phrase?: string | null }) =>
    request<SdkPackageRelease>(`/releases/sdk-packages/${id}/publish`, { method: 'POST', body: JSON.stringify(data || {}) }),
  retrySdkPackageRelease: (id: number, data?: { actor?: string; package_version?: string | null; channel?: string | null; note?: string | null }) =>
    request<SdkPackageRelease>(`/releases/sdk-packages/${id}/retry`, { method: 'POST', body: JSON.stringify(data || {}) }),
  syncSdkPackageReleaseStatuses: () =>
    request<SdkPackageReleaseSyncResult>('/releases/sdk-packages/sync-statuses', { method: 'POST' }),
}
