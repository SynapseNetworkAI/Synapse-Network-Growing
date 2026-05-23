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
      format_kind?: string | null
      posted_at?: string | null
      summary?: string | null
    }) =>
      request<SocialPostMetric>('/social/post-metrics/manual', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
  }
}
