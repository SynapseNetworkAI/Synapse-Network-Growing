export interface SocialDistributionAccountAuthStatus {
  account_id: number
  platform: string
  channel_key: string
  display_name: string
  login_url: string | null
  publish_path: 'official_api' | 'browser_assisted' | 'manual_only' | 'blocked' | string
  api_status: string
  browser_status: string
  api_supported: boolean
  can_publish_via_api: boolean
  can_use_browser_assist: boolean
  private_web_adapter_enabled: boolean
  blockers: string[]
  next_action: string
  oauth_status: string | null
  requires_authorization: boolean
  auth_message: string | null
  last_checked_at: string | null
}

export interface SocialDistributionAccountAuthStatusList {
  items: SocialDistributionAccountAuthStatus[]
  generated_at: string | null
}

export interface SocialDistributionDocument {
  id: number
  asset_id: number
  task_id: number | null
  document_kind: 'source_plan' | 'canonical_article' | 'platform_draft' | string
  platform: string | null
  channel_key: string | null
  title: string
  body_markdown: string
  status: string
  version: number
  metadata: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}
