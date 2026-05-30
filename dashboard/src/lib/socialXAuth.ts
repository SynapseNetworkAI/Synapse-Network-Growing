import type { ApiError } from '../api'

const X_OAUTH_CONFIG_HINT = '请配置 X_OAUTH_CLIENT_ID、X_OAUTH_CLIENT_SECRET 和 X_OAUTH_REDIRECT_URI 后重试。'

export function formatXOAuthReconnectError(error: unknown): string {
  const detail = error instanceof Error ? (error as ApiError).detail : null
  const message = messageFromDetail(detail)
  if (message) return withConfigHint(message)
  if (error instanceof Error && error.message.trim()) return withConfigHint(error.message)
  return `X 授权启动失败。${X_OAUTH_CONFIG_HINT}`
}

function messageFromDetail(detail: unknown): string | null {
  if (typeof detail === 'string') return detail.trim() || null
  if (!detail || typeof detail !== 'object') return null
  const payload = detail as { message?: unknown; error?: unknown; detail?: unknown }
  for (const value of [payload.message, payload.error, payload.detail]) {
    if (typeof value === 'string' && value.trim()) return value
  }
  return null
}

function withConfigHint(message: string): string {
  if (message.includes('X_OAUTH_CLIENT_ID')) return message
  return `${message} ${X_OAUTH_CONFIG_HINT}`
}
