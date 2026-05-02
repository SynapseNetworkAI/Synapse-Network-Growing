export interface SocialDistributionAccount {
  id: number
  platform: string
  channel_key: string
  display_name: string
  signup_url: string | null
  profile_url: string | null
  account_type: string
  priority: string
  status: string
  email_hint: string | null
  two_factor_status: string
  read_automation_mode: string
  human_publish_required: boolean
  publish_mode: string
  credential_ref_configured: boolean
  api_capability: string
  notes: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SocialDistributionTask {
  id: number
  asset_id: number
  account_id: number
  platform: string
  channel_key: string
  action: string
  account_display_name: string | null
  signup_url: string | null
  publish_mode: string
  api_capability: string
  credential_ref_configured: boolean
  status: string
  platform_title: string | null
  platform_body: string | null
  operator_checklist: string | null
  submission_url: string | null
  published_url: string | null
  external_post_id: string | null
  failure_summary: string | null
  manual_result_note: string | null
  metadata: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface SocialContentAsset {
  id: number
  asset_type: string
  source_type: string
  title: string
  body: string | null
  summary: string | null
  canonical_url: string | null
  source_signal_id: number | null
  goal_key: string | null
  policy_check: Record<string, unknown>
  agent_metadata: Record<string, unknown>
  status: string
  created_by: string
  task_count: number
  status_counts: Record<string, number>
  created_at: string | null
  updated_at: string | null
}

export interface SocialDistributionEvent {
  id: number
  asset_id: number
  task_id: number | null
  event_type: string
  actor: string
  summary: string | null
  payload: Record<string, unknown>
  created_at: string | null
}

export interface SocialContentAssetDetail extends SocialContentAsset {
  tasks: SocialDistributionTask[]
  events: SocialDistributionEvent[]
}

export interface SocialDistributionTaskGroup {
  asset: SocialContentAsset
  tasks: SocialDistributionTask[]
}

export interface SocialDistributionTaskList {
  groups: SocialDistributionTaskGroup[]
  flat: SocialDistributionTask[]
  total_assets: number
  total_tasks: number
  limit: number
  offset: number
}

export interface SocialDistributionGenerateTasksResult {
  asset: SocialContentAssetDetail
  results: Array<{
    account_id: number
    platform: string
    channel_key: string
    status: string
    task_id: number | null
    error: string | null
  }>
  generated_task_ids: number[]
  failed_task_ids: number[]
}

export interface SocialAssetPlannerRun {
  workflow_key: string
  local_date: string
  target_count: number
  active_count: number
  no_asset_created: boolean
  already_satisfied: boolean
  selected_asset_type: string | null
  selected_signal_count: number
  reason: string | null
  created_asset_id: number | null
  asset: SocialContentAssetDetail | null
  signals: Array<{
    signal_type: string
    source_ref: string
    title: string
    summary: string
    score: number
  }>
}

type RequestFn = <T>(path: string, options?: RequestInit, timeoutMs?: number) => Promise<T>

export function createSocialDistributionApi(request: RequestFn) {
  return {
    getDistributionAccounts: () => request<SocialDistributionAccount[]>('/social/distribution/accounts'),
    updateDistributionAccount: (
      id: number,
      data: {
        profile_url?: string | null
        status?: string | null
        email_hint?: string | null
        two_factor_status?: string | null
        publish_mode?: string | null
        credential_ref?: string | null
        api_capability?: string | null
        notes?: string | null
      },
    ) =>
      request<SocialDistributionAccount>(`/social/distribution/accounts/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    getSocialContentAssets: () => request<SocialContentAsset[]>('/social/distribution/assets'),
    getSocialContentAsset: (id: number) => request<SocialContentAssetDetail>(`/social/distribution/assets/${id}`),
    runSocialAssetPlanner: () =>
      request<SocialAssetPlannerRun>(
        '/social/distribution/assets/plan-next',
        { method: 'POST', body: JSON.stringify({}) },
        60_000,
      ),
    createSocialContentAsset: (data: {
      asset_type?: string
      source_type?: string
      title: string
      body?: string | null
      summary?: string | null
      canonical_url?: string | null
      source_signal_id?: number | null
      goal_key?: string | null
      status?: string
      created_by?: string
    }) =>
      request<SocialContentAssetDetail>('/social/distribution/assets', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    updateSocialContentAsset: (
      id: number,
      data: {
        title?: string | null
        body?: string | null
        summary?: string | null
        canonical_url?: string | null
        goal_key?: string | null
        status?: string | null
      },
    ) =>
      request<SocialContentAssetDetail>(`/social/distribution/assets/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    getSocialDistributionTasks: (filters?: {
      platform?: string | null
      channel_key?: string | null
      status?: string | null
      limit?: number
      offset?: number
    }) => {
      const params = new URLSearchParams()
      if (filters?.platform) params.set('platform', filters.platform)
      if (filters?.channel_key) params.set('channel_key', filters.channel_key)
      if (filters?.status && filters.status !== 'all') params.set('status', filters.status)
      if (filters?.limit) params.set('limit', String(filters.limit))
      if (filters?.offset) params.set('offset', String(filters.offset))
      const query = params.toString()
      return request<SocialDistributionTaskList>(`/social/distribution/tasks${query ? `?${query}` : ''}`)
    },
    generateSocialDistributionTasks: (assetId: number, data: { account_ids: number[]; action?: string; actor?: string }) =>
      request<SocialDistributionGenerateTasksResult>(
        `/social/distribution/assets/${assetId}/generate-tasks`,
        {
          method: 'POST',
          body: JSON.stringify(data),
        },
        90_000,
      ),
    approveAndGenerateSocialDistributionTasks: (
      assetId: number,
      data: { account_ids?: number[]; action?: string; actor?: string },
    ) =>
      request<SocialDistributionGenerateTasksResult>(
        `/social/distribution/assets/${assetId}/approve-and-generate-tasks`,
        {
          method: 'POST',
          body: JSON.stringify(data),
        },
        90_000,
      ),
    updateSocialDistributionTask: (
      id: number,
      data: {
        platform_title?: string | null
        platform_body?: string | null
        operator_checklist?: string | null
        submission_url?: string | null
        published_url?: string | null
        external_post_id?: string | null
        failure_summary?: string | null
        manual_result_note?: string | null
        status?: string | null
      },
    ) =>
      request<SocialDistributionTask>(`/social/distribution/tasks/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    markSocialDistributionTaskLive: (
      id: number,
      data: { published_url: string; manual_result_note?: string | null; actor?: string },
    ) =>
      request<SocialDistributionTask>(`/social/distribution/tasks/${id}/mark-live`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    markSocialDistributionTaskRemoved: (
      id: number,
      data: { manual_result_note: string; actor?: string },
    ) =>
      request<SocialDistributionTask>(`/social/distribution/tasks/${id}/mark-removed`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    publishSocialDistributionTaskToX: (id: number, data: { actor?: string }) =>
      request<SocialDistributionTask>(`/social/distribution/tasks/${id}/publish-x`, {
        method: 'POST',
        body: JSON.stringify(data),
      }, 60_000),
  }
}
