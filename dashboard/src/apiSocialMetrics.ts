import type { SocialPostMetricSummary, SocialPostMetricTopPost } from './types/socialOps'

export interface SocialPostMetric {
  id: number
  post_id: number | null
  external_post_id: string | null
  impressions: number
  likes: number
  replies: number
  reposts: number
  follows: number
  link_clicks: number
  profile_visits: number
  bookmarks: number
  format_kind: string | null
  posted_at: string | null
  summary: string | null
  content_type: string | null
  post_intent: string | null
  source_strategy: string | null
  hook_text: string | null
  topic_tags: string[]
  has_media: boolean
  has_thread: boolean
  has_url: boolean
  human_link_reason: string | null
  negative_feedback_count: number
  subscription_conversions: number
  metric_source: string | null
  diagnostic: string | null
  observed_at: string | null
}

export interface SocialPostMetricDetail extends SocialPostMetric {
  post_title: string | null
  post_body_excerpt: string | null
  post_status: string | null
  published_at: string | null
  x_url: string | null
  created_at: string | null
}

export interface SocialPostMetricQueryResult {
  items: SocialPostMetricDetail[]
  total: number
  limit: number
  offset: number
}

type SocialPostMetricAggregateFields = Pick<
  SocialPostMetricSummary,
  | 'observed_post_count'
  | 'metric_row_count'
  | 'total_impressions'
  | 'total_likes'
  | 'total_replies'
  | 'total_reposts'
  | 'total_link_clicks'
  | 'total_profile_visits'
  | 'total_bookmarks'
  | 'total_negative_feedback'
  | 'total_subscription_conversions'
  | 'average_engagement'
>

export interface SocialPostMetricDaily extends SocialPostMetricAggregateFields {
  local_date: string
  top_post: SocialPostMetricTopPost | null
  last_observed_at: string | null
}

export interface SocialPostMetricDailyResult {
  items: SocialPostMetricDaily[]
  total: number
  limit: number
  offset: number
  date_from: string | null
  date_to: string | null
}

export interface SocialAccountSnapshot {
  id: number
  platform: string
  account_handle: string
  followers: number
  following: number
  followers_delta: number
  profile_url: string | null
  summary: string | null
  observed_at: string | null
}

export interface SocialAccountSnapshotResult {
  items: SocialAccountSnapshot[]
  total: number
  limit: number
  offset: number
}

export interface SocialWeeklyReview {
  id: number
  platform: string
  week_start: string
  week_end: string
  status: string
  summary: string | null
  best_topics: Array<Record<string, unknown>>
  best_hooks: Array<Record<string, unknown>>
  low_performing_patterns: Array<Record<string, unknown>>
  recommendations: Array<Record<string, unknown>>
  content_generation_guidance: Record<string, unknown>
  source_metric_ids: number[]
  error_excerpt: string | null
  created_at: string | null
}

export interface SocialWeeklyReviewResult {
  items: SocialWeeklyReview[]
  total: number
  limit: number
  offset: number
}

function queryString(filters: Record<string, string | number | null | undefined>) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  return params.toString() ? `?${params.toString()}` : ''
}

type RequestFn = <T>(path: string, options?: RequestInit, timeoutMs?: number) => Promise<T>

export function createSocialMetricApi(request: RequestFn) {
  return {
    getSocialPostMetrics: () => request<SocialPostMetric[]>('/social/post-metrics'),
    getSocialPostMetricSummary: () => request<SocialPostMetricSummary>('/social/post-metrics/summary'),
    getSocialPostMetricsDaily: (filters?: { date_from?: string; date_to?: string; limit?: number; offset?: number }) =>
      request<SocialPostMetricDailyResult>(`/social/post-metrics/daily${queryString(filters ?? {})}`),
    querySocialPostMetrics: (filters?: {
      date_from?: string
      date_to?: string
      post_id?: number
      external_post_id?: string
      limit?: number
      offset?: number
    }) => request<SocialPostMetricQueryResult>(`/social/post-metrics/query${queryString(filters ?? {})}`),
    getSocialPostMetric: (id: number) => request<SocialPostMetricDetail>(`/social/post-metrics/${id}`),
    createManualSocialPostMetric: (data: {
      external_post_id?: string | null
      impressions?: number
      likes?: number
      replies?: number
      reposts?: number
      follows?: number
      link_clicks?: number
      profile_visits?: number
      bookmarks?: number
      negative_feedback_count?: number
      subscription_conversions?: number
      format_kind?: string | null
      posted_at?: string | null
      summary?: string | null
      content_type?: string | null
      post_intent?: string | null
      source_strategy?: string | null
      hook_text?: string | null
      topic_tags?: string[]
      has_media?: boolean
      has_thread?: boolean
      has_url?: boolean
      human_link_reason?: string | null
    }) =>
      request<SocialPostMetric>('/social/post-metrics/manual', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    getSocialAccountSnapshots: (filters?: { limit?: number; offset?: number }) =>
      request<SocialAccountSnapshotResult>(`/social/account-snapshots${queryString(filters ?? {})}`),
    getSocialWeeklyReviews: (filters?: { limit?: number; offset?: number }) =>
      request<SocialWeeklyReviewResult>(`/social/analytics/weekly-reviews${queryString(filters ?? {})}`),
    runSocialWeeklyReview: (data?: { days?: number; dry_run?: boolean }) =>
      request<Record<string, unknown>>('/social/analytics/weekly-reviews/run', {
        method: 'POST',
        body: JSON.stringify(data ?? { days: 7, dry_run: false }),
      }),
  }
}
