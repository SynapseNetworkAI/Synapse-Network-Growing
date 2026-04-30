import type { SocialPostDraft } from '../api'

export type QueueScope = 'today' | 'all'

export function rawString(post: SocialPostDraft, key: string) {
  const value = post.raw_agent_output?.[key]
  return typeof value === 'string' ? value : ''
}

export function plannerLocalDate(post: SocialPostDraft) {
  return rawString(post, 'planner_local_date')
}

export function plannerSlot(post: SocialPostDraft) {
  const value = post.raw_agent_output?.planner_slot
  return typeof value === 'number' || typeof value === 'string' ? String(value) : ''
}

export function localDateString(value: string | null | undefined) {
  if (!value) return ''
  const isoDate = value.match(/^\d{4}-\d{2}-\d{2}/)?.[0]
  if (isoDate) return isoDate
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function isActiveDraftInventoryStatus(status: string) {
  return ['generating', 'needs_review', 'approved'].includes(status)
}

export function isTodayQueuePost(post: SocialPostDraft, localDate: string | null | undefined) {
  if (!localDate) return true
  if (post.source_type === 'daily_planner') {
    return plannerLocalDate(post) === localDate && isActiveDraftInventoryStatus(post.status)
  }
  if (!['generating', 'needs_review', 'approved', 'draft', 'failed', 'publishing'].includes(post.status)) return false
  return localDateString(post.created_at) === localDate || localDateString(post.updated_at) === localDate
}

export function activeMediaAssets(post: SocialPostDraft | null) {
  return (post?.media_assets ?? []).filter((asset) => asset.status !== 'removed')
}

export function mediaStatusLabel(status: string) {
  const map: Record<string, string> = {
    generating: '图片生成中',
    ready: '图片已生成',
    uploaded: '图片已上传',
    failed: '图片失败',
    removed: '已移除',
  }
  return map[status] ?? status
}
