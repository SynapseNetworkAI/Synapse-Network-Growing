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
  status: 'planned' | 'building' | 'ready_to_publish' | 'publishing' | 'published' | 'failed' | 'cancelled' | string
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

export const sdkPackagesApi = {
  getSdkPackageReleases: (filters?: { release_train_version?: string; sdk_language?: string; status?: string }) => {
    const params = new URLSearchParams()
    if (filters?.release_train_version) params.set('release_train_version', filters.release_train_version)
    if (filters?.sdk_language) params.set('sdk_language', filters.sdk_language)
    if (filters?.status) params.set('status', filters.status)
    const q = params.toString() ? `?${params.toString()}` : ''
    return request<SdkPackageRelease[]>(`/releases/sdk-packages${q}`)
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
  publishSdkPackageRelease: (id: number, data?: { actor?: string; package_version?: string | null; channel?: string | null; note?: string | null }) =>
    request<SdkPackageRelease>(`/releases/sdk-packages/${id}/publish`, { method: 'POST', body: JSON.stringify(data || {}) }),
  retrySdkPackageRelease: (id: number, data?: { actor?: string; package_version?: string | null; channel?: string | null; note?: string | null }) =>
    request<SdkPackageRelease>(`/releases/sdk-packages/${id}/retry`, { method: 'POST', body: JSON.stringify(data || {}) }),
  syncSdkPackageReleaseStatuses: () =>
    request<SdkPackageReleaseSyncResult>('/releases/sdk-packages/sync-statuses', { method: 'POST' }),
}
