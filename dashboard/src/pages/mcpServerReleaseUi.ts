export const MCP_STATUS_LABEL: Record<string, string> = {
  planned: '已计划',
  readiness_running: 'Readiness 中',
  ready_to_publish: '可发布 npm',
  npm_publishing: 'npm 发布中',
  npm_published: 'npm 已发布',
  registry_submitting: 'Registry 提交中',
  registry_listed: 'Registry 已收录',
  prod_smoke_running: 'Prod Smoke 中',
  directories_pending: '目录待分发',
  completed: '完成',
  failed: '失败',
  cancelled: '已取消',
  active: 'Active',
  blocked_missing_artifact: '缺少 npm artifact',
  blocked_requires_remote_mcp: '需要 Remote MCP',
  package_ready: 'Package ready',
  submitted: '已提交',
  under_review: '审核中',
  listed: '已收录',
  verified: '已验证',
  not_configured: '未配置',
  configured: '已配置',
  expired: '已过期',
  blocked: '已阻塞',
  submit_eligible: '可提交',
  needs_fix: '需修复',
  candidate: 'Candidate',
}

export const MCP_STATUS_OPTIONS = [
  '',
  'planned',
  'readiness_running',
  'ready_to_publish',
  'npm_publishing',
  'npm_published',
  'registry_submitting',
  'registry_listed',
  'prod_smoke_running',
  'directories_pending',
  'completed',
  'failed',
  'cancelled',
]

export function mcpReleaseTone(status: string | null | undefined) {
  if (status === 'completed' || status === 'registry_listed' || status === 'npm_published' || status === 'listed' || status === 'verified' || status === 'active' || status === 'submit_eligible') return 'delivered'
  if (status === 'ready_to_publish' || status === 'directories_pending' || status === 'planned' || status === 'package_ready' || status === 'candidate' || status === 'configured') return 'ready'
  if (String(status || '').endsWith('_running') || status === 'npm_publishing' || status === 'registry_submitting') return 'running'
  if (status === 'failed' || status === 'cancelled' || String(status || '').startsWith('blocked_') || status === 'needs_fix' || status === 'not_configured' || status === 'blocked' || status === 'expired') return 'blocked'
  return 'muted'
}

export function formatMcpTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

export function isSemVer(value: string) {
  return /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(value.trim())
}

export function openExternalUrl(url: string | null | undefined) {
  if (!url) return
  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  if (opened) opened.opener = null
}

export function directoryProgress(statuses: string[]) {
  const done = statuses.filter((status) => ['listed', 'verified'].includes(status)).length
  return `${done}/${statuses.length || 0}`
}
