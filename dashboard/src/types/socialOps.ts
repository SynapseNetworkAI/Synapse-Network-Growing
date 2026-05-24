export interface SocialOpsOverview {
  active_goal_count: number
  draft_queue_count: number
  needs_review_count: number
  trend_count: number
  reply_needs_review_count: number
  repost_candidate_count: number
  published_count: number
  daily_planner_target_count: number
  daily_planner_active_count: number
  daily_planner_local_date: string | null
  daily_planner_active_post_ids: number[]
  human_gate_required: boolean
  safety_summary: string
}

export interface SocialPostMetricTopPost {
  post_id: number | null
  external_post_id: string | null
  title: string | null
  impressions: number
  likes: number
  replies: number
  reposts: number
  link_clicks: number
  profile_visits: number
  bookmarks: number
  engagement_total: number
  topic_tags: string[]
  hook_text: string | null
  observed_at: string | null
}

export interface SocialPostMetricSummary {
  observed_post_count: number
  metric_row_count: number
  total_impressions: number
  total_likes: number
  total_replies: number
  total_reposts: number
  total_link_clicks: number
  total_profile_visits: number
  total_bookmarks: number
  total_negative_feedback: number
  total_subscription_conversions: number
  average_engagement: number
  top_posts: SocialPostMetricTopPost[]
  last_observed_at: string | null
  diagnostic: string | null
}
