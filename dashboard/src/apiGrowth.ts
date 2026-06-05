import { createGrowthAiVisibilityApi } from './apiGrowthAiVisibility'

type RequestFn = <T>(path: string, options?: RequestInit, timeoutMs?: number) => Promise<T>

export interface GrowthLead {
  id: number
  lead_type: 'investor' | 'provider' | string
  project_key: string
  name: string
  organization: string
  role_title: string
  public_profile_urls: string[]
  contact_channels: Array<Record<string, unknown>>
  source_kind: string
  source_url: string
  status: string
  fit_score: number
  confidence_score: number
  risk_flags: string[]
  evidence: Array<Record<string, unknown>>
  metadata: Record<string, unknown>
  next_action: string
  last_contacted_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface GrowthLeadList {
  items: GrowthLead[]
  total: number
  limit: number
  offset: number
  status_counts: Record<string, number>
  lead_type_counts: Record<string, number>
}

export interface GrowthProviderProfile {
  id: number
  lead_id: number
  organization: string
  website_url: string
  company_description: string
  contact_email: string
  contact_source_url: string
  source_url: string
  latest_message_id: number | null
  latest_message_subject: string
  latest_message_status: string
  last_contacted_at: string | null
  profile_status: string
  evidence: Array<Record<string, unknown>>
  metadata: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface GrowthProviderProfileList {
  items: GrowthProviderProfile[]
  total: number
  limit: number
  offset: number
}

export interface GrowthProviderReply {
  id: number
  lead_id: number
  message_id: number
  provider_profile_id: number | null
  mailbox_message_id: string
  thread_id: string
  from_email: string
  from_name: string
  subject: string
  snippet: string
  body_excerpt: string
  received_at: string | null
  classification: string
  confidence_score: number
  suggested_reply_message_id: number | null
  suggested_reply_subject: string
  suggested_reply_body: string
  suggested_reply_status: string
  status: string
  evidence: Array<Record<string, unknown>>
  metadata: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface GrowthProviderReplyList {
  items: GrowthProviderReply[]
  total: number
  limit: number
  offset: number
}

export interface GrowthOutreachMessage {
  id: number
  lead_id: number
  campaign_id: number | null
  channel: string
  subject: string
  body: string
  personalization_evidence: Array<Record<string, unknown>>
  status: string
  approved_by: string | null
  sent_at: string | null
  failure_reason: string | null
  metadata: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface GrowthOutreachEvent {
  id: number
  lead_id: number | null
  message_id: number | null
  event_type: string
  actor: string
  from_status: string | null
  to_status: string | null
  summary: string
  metadata: Record<string, unknown>
  created_at: string | null
}

export interface GrowthLeadDetail {
  lead: GrowthLead
  messages: GrowthOutreachMessage[]
  events: GrowthOutreachEvent[]
}

export interface GrowthSourceConfig {
  id: number
  config_key: string
  name: string
  config_type: string
  status: string
  description: string
  query: Record<string, unknown>
  cadence: Record<string, unknown>
  thresholds: Record<string, unknown>
  last_run_at: string | null
  last_result: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface GrowthResearchRun {
  id: number
  source_config_id: number
  status: string
  dry_run: boolean
  params: Record<string, unknown>
  candidate_count: number
  created_count: number
  reused_count: number
  drafted_count: number
  error_summary: string
  result: Record<string, unknown>
  started_at: string | null
  completed_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface GrowthDiscoveryListing {
  id: number
  surface: string
  target_repo: string
  package_name: string
  listing_url: string
  status: string
  submission_evidence: Record<string, unknown>
  verification_evidence: Record<string, unknown>
  failure_reason: string
  last_checked_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface GrowthOverview {
  lead_counts: Record<string, number>
  message_counts: Record<string, number>
  ai_visibility: Record<string, number>
  discovery_counts: Record<string, number>
}

export function createGrowthApi(request: RequestFn) {
  return {
    getGrowthOverview: () => request<GrowthOverview>('/growth/overview'),
    getGrowthLeads: (params?: {
      lead_type?: string
      status?: string
      q?: string
      limit?: number
      offset?: number
    }) => request<GrowthLeadList>(`/growth/leads${query(params)}`),
    createGrowthLead: (data: Partial<GrowthLead>) =>
      request<GrowthLead>('/growth/leads', { method: 'POST', body: JSON.stringify(data) }),
    getGrowthProviderProfiles: (params?: { q?: string; limit?: number; offset?: number }) =>
      request<GrowthProviderProfileList>(`/growth/provider-profiles${query(params)}`),
    getGrowthProviderReplies: (params?: { q?: string; status?: string; limit?: number; offset?: number }) =>
      request<GrowthProviderReplyList>(`/growth/provider-replies${query(params)}`),
    getGrowthSourceConfigs: () => request<{ items: GrowthSourceConfig[]; total: number }>('/growth/source-configs'),
    createGrowthSourceConfig: (data: Partial<GrowthSourceConfig>) =>
      request<GrowthSourceConfig>('/growth/source-configs', { method: 'POST', body: JSON.stringify(data) }),
    patchGrowthSourceConfig: (id: number, data: Partial<GrowthSourceConfig>) =>
      request<GrowthSourceConfig>(`/growth/source-configs/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    ensureDefaultGrowthProviderSource: () =>
      request<GrowthSourceConfig>('/growth/source-configs/default-provider', { method: 'POST', body: JSON.stringify({}) }),
    runGrowthSourceConfig: (id: number, data: { dry_run: boolean; max_results?: number; create_drafts?: boolean; actor?: string }) =>
      request<GrowthResearchRun>(
        `/growth/source-configs/${id}/run`,
        { method: 'POST', body: JSON.stringify(data) },
        120_000,
      ),
    getGrowthSourceRuns: (id: number, params?: { limit?: number; offset?: number }) =>
      request<{ items: GrowthResearchRun[]; total: number; limit: number; offset: number }>(
        `/growth/source-configs/${id}/runs${query(params)}`,
      ),
    getGrowthLead: (id: number) => request<GrowthLeadDetail>(`/growth/leads/${id}`),
    draftGrowthMessage: (id: number, data?: { channel?: string; actor?: string; notes?: string }) =>
      request<GrowthOutreachMessage>(
        `/growth/leads/${id}/draft-message`,
        { method: 'POST', body: JSON.stringify(data || {}) },
        120_000,
      ),
    approveGrowthMessage: (id: number, data?: { actor?: string; metadata?: Record<string, unknown> }) =>
      request<GrowthOutreachMessage>(`/growth/messages/${id}/approve`, { method: 'POST', body: JSON.stringify(data || {}) }),
    queueGrowthMessage: (id: number, data?: { actor?: string; metadata?: Record<string, unknown> }) =>
      request<GrowthOutreachMessage>(`/growth/messages/${id}/queue`, { method: 'POST', body: JSON.stringify(data || {}) }),
    createGrowthGmailDraft: (id: number, data?: { actor?: string; metadata?: Record<string, unknown> }) =>
      request<GrowthOutreachMessage>(`/growth/messages/${id}/create-gmail-draft`, { method: 'POST', body: JSON.stringify(data || {}) }),
    markGrowthMessageSent: (id: number, data?: { actor?: string; metadata?: Record<string, unknown> }) =>
      request<GrowthOutreachMessage>(`/growth/messages/${id}/mark-sent`, { method: 'POST', body: JSON.stringify(data || {}) }),
    recordGrowthReply: (id: number, data: { actor?: string; reply_summary: string; interested?: boolean }) =>
      request<GrowthOutreachMessage>(`/growth/messages/${id}/reply`, { method: 'POST', body: JSON.stringify(data) }),
    doNotContactGrowthLead: (id: number, data?: { actor?: string; summary?: string }) =>
      request<GrowthLead>(`/growth/leads/${id}/do-not-contact`, { method: 'POST', body: JSON.stringify(data || {}) }),
    ...createGrowthAiVisibilityApi(request),
    getGrowthDiscoveryListings: (params?: { surface?: string; status?: string; limit?: number; offset?: number }) =>
      request<{ items: GrowthDiscoveryListing[]; total: number; limit: number; offset: number }>(
        `/growth/discovery-listings${query(params)}`,
      ),
    createGrowthDiscoveryListing: (data: Partial<GrowthDiscoveryListing>) =>
      request<GrowthDiscoveryListing>('/growth/discovery-listings', { method: 'POST', body: JSON.stringify(data) }),
    patchGrowthDiscoveryListing: (id: number, data: Partial<GrowthDiscoveryListing>) =>
      request<GrowthDiscoveryListing>(`/growth/discovery-listings/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  }
}

function query(params?: Record<string, unknown>) {
  const search = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim()) search.set(key, String(value))
  })
  return search.toString() ? `?${search.toString()}` : ''
}
