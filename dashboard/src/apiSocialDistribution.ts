import type {
  SocialDistributionAccountAuthStatusList,
  SocialDistributionDocument,
} from './apiSocialDistributionTypes'

export type {
  SocialDistributionAccountAuthStatus,
  SocialDistributionAccountAuthStatusList,
  SocialDistributionDocument,
} from './apiSocialDistributionTypes'

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

export interface SocialDistributionXAuthStatus {
  status: string
  can_publish: boolean
  account_id: number | null
  account_handle: string | null
  auth_message: string | null
  requires_authorization: boolean
  refresh_token_rotated: boolean
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

export interface SocialReplyItem {
  id: number
  platform: string
  external_reply_id: string
  source_candidate_id: number | null
  source_post_id: string | null
  source_author_handle: string | null
  source_text: string | null
  author_handle: string | null
  incoming_text: string
  intent: string
  suggested_reply: string | null
  generation_reason: string | null
  risk_level: string
  status: string
  source_url: string | null
  published_external_post_id: string | null
  reviewed_by: string | null
  failure_summary: string | null
  metadata: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface SocialContentAssetDetail extends SocialContentAsset {
  tasks: SocialDistributionTask[]
  events: SocialDistributionEvent[]
  documents: SocialDistributionDocument[]
  reply_items: SocialReplyItem[]
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

export interface SocialDistributionBoardCard {
  id: string
  asset: SocialContentAsset
  column_key: string
  task_kind_code: string
  task_kind_label: string
  task_kind_action: string
  task_count: number
  document_count: number
  platform_count: number
  failed_count: number
  ready_to_publish_count: number
  live_count: number
  visibility_issue_count: number
  status_counts: Record<string, number>
  document_status_counts: Record<string, number>
  next_action: string
  updated_at: string | null
}

export interface SocialDistributionBoardColumn {
  key: string
  title: string
  description: string
  count: number
  cards: SocialDistributionBoardCard[]
}

export interface SocialDistributionBoard {
  columns: SocialDistributionBoardColumn[]
  summary: Record<string, number>
  generated_at: string | null
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

export interface SocialXReplyBlockGenerateResult {
  asset: SocialContentAssetDetail
  reply_ids: number[]
  failed_reply_ids: number[]
  source_candidate_ids: number[]
  processed_source_count: number
  auto_publish: boolean
  agent_review: boolean
  publish_mode: string
  approval_ref_configured: boolean
  timed_out: boolean
  blocked_reason: string | null
}

export interface SocialXArticlePackGenerateResult { asset: SocialContentAssetDetail; article_task_id: number; teaser_task_id: number; article_document_id: number; cover_image_path: string | null }

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

export interface SocialDistributionCampaignTemplateResult {
  campaign_key: string
  created_count: number
  existing_count: number
  assets: SocialContentAssetDetail[]
}

type RequestFn = <T>(path: string, options?: RequestInit, timeoutMs?: number) => Promise<T>

export function createSocialDistributionApi(request: RequestFn) {
  return {
    getSocialDistributionBoard: () => request<SocialDistributionBoard>('/social/distribution/board'),
    getDistributionAccounts: () => request<SocialDistributionAccount[]>('/social/distribution/accounts'),
    getDistributionAccountAuthStatuses: (filters?: { platform?: string | null; account_id?: number | null }) => {
      const params = new URLSearchParams()
      if (filters?.platform) params.set('platform', filters.platform)
      if (filters?.account_id) params.set('account_id', String(filters.account_id))
      const query = params.toString()
      return request<SocialDistributionAccountAuthStatusList>(
        `/social/distribution/accounts/auth-status${query ? `?${query}` : ''}`,
        undefined,
        60_000,
      )
    },
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
    createSocialContentTask: (data: {
      title: string
      task_type?: string | null
      source_material?: string | null
      target_audience?: string | null
      target_platforms?: string[]
      canonical_url?: string | null
      source_doc_path?: string | null
      goal_key?: string | null
      campaign_key?: string | null
      post_intent?: string | null
      planned_publish_at?: string | null
      created_by?: string
    }) =>
      request<SocialContentAssetDetail>('/social/distribution/content-tasks', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    createXBrandWeekCampaignTemplate: () =>
      request<SocialDistributionCampaignTemplateResult>(
        '/social/distribution/campaign-templates/x-brand-week-technical-builders',
        { method: 'POST', body: JSON.stringify({}) },
      ),
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
    generateSocialDistributionXArticlePack: (
      assetId: number,
      data: { actor?: string; article_url?: string | null; teaser_include_article_url?: boolean } = {},
    ) =>
      request<SocialXArticlePackGenerateResult>(
        `/social/distribution/assets/${assetId}/generate-x-article-pack`,
        {
          method: 'POST',
          body: JSON.stringify(data),
        },
        120_000,
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
    generateSocialDistributionContentPlan: (assetId: number, data: { actor?: string } = {}) =>
      request<SocialContentAssetDetail>(
        `/social/distribution/assets/${assetId}/generate-content-plan`,
        {
          method: 'POST',
          body: JSON.stringify(data),
        },
        60_000,
      ),
    expandSocialDistributionCanonicalArticle: (assetId: number, data: { actor?: string } = {}) =>
      request<SocialContentAssetDetail>(
        `/social/distribution/assets/${assetId}/expand-canonical-article`,
        {
          method: 'POST',
          body: JSON.stringify(data),
        },
        120_000,
      ),
    approveSocialDistributionCanonicalArticle: (
      assetId: number,
      data: { actor?: string; document_id?: number | null } = {},
    ) =>
      request<SocialContentAssetDetail>(
        `/social/distribution/assets/${assetId}/approve-canonical-article`,
        {
          method: 'POST',
          body: JSON.stringify(data),
        },
        60_000,
      ),
    generateSocialXReplyBlock: (
      assetId: number,
      data: {
        actor?: string
        target_count?: number
        agent_review?: boolean
        auto_publish?: boolean
        max_seconds?: number
        per_reply_timeout_seconds?: number
        source_posts?: Array<{
          source_url: string
          author_handle?: string | null
          source_text: string
          rationale?: string | null
          opt_in_evidence?: string | null
        }>
        force_regenerate?: boolean
      } = {},
    ) =>
      request<SocialXReplyBlockGenerateResult>(
        `/social/distribution/assets/${assetId}/generate-x-reply-block`,
        {
          method: 'POST',
          body: JSON.stringify(data),
        },
        120_000,
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
    auditSocialDistributionPublishedPage: (
      id: number,
      data: {
        visibility_status: string
        layout_status?: string
        audit_note?: string | null
        actor?: string
      },
    ) =>
      request<SocialDistributionTask>(`/social/distribution/tasks/${id}/audit-published-page`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    publishSocialDistributionTaskToX: (id: number, data: { actor?: string }) =>
      request<SocialDistributionTask>(`/social/distribution/tasks/${id}/publish-x`, {
        method: 'POST',
        body: JSON.stringify(data),
      }, 60_000),
    getSocialDistributionTaskXAuthStatus: (id: number) =>
      request<SocialDistributionXAuthStatus>(
        `/social/distribution/tasks/${id}/x-auth-status`,
        undefined,
        60_000,
      ),
  }
}
