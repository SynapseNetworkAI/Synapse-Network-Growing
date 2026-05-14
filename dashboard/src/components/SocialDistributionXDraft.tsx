import type { SocialDistributionTask } from '../api'
import { Field, InfoBlock, textareaClass } from './SocialDistributionWidgets'

export type XDraftRow = {
  tweet: string
  count: number
}

export type XDraftState = {
  xFormat: string | null
  xRows: XDraftRow[]
  xLongPostText: string
  xLongPostLimit: number
  xHasOverLimit: boolean
  xLongPostOverLimit: boolean
  combined: string
  canPublishX: boolean
}

export function getXDraftState(task: SocialDistributionTask | null): XDraftState {
  const metadata = task?.metadata ?? {}
  const xTweets = task?.platform === 'x' ? stringArray(metadata.tweets) : []
  const xFormat = task?.platform === 'x' ? xFormatFromMetadata(metadata, xTweets) : null
  const xLongPostText = task?.platform === 'x' && xFormat === 'long_post'
    ? stringValue(metadata.long_post_text) || stringValue(metadata.post_text) || task.platform_body || ''
    : ''
  const xWeightedCounts = numberArray(metadata.weighted_counts)
  const xRows = xTweets.map((tweet, index) => ({
    tweet,
    count: xWeightedCounts[index] ?? conservativeXCount(tweet),
  }))
  const xHasOverLimit = xRows.some((row) => row.count > 280)
  const xLongPostLimit = Number(metadata.soft_max_chars) || 4000
  const xLongPostOverLimit = Boolean(xLongPostText) && xLongPostText.length > xLongPostLimit
  const combined =
    task?.platform === 'x' && xFormat === 'long_post'
      ? xLongPostText
      : task?.platform === 'x' && xRows.length
        ? xRows.map((row, index) => `Tweet ${index + 1}/${xRows.length}\n${row.tweet}`).join('\n\n')
        : `Title:\n${task?.platform_title ?? ''}\n\nBody:\n${task?.platform_body ?? ''}`
  const canPublishX =
    task?.platform === 'x' &&
    task.publish_mode === 'api_human_gated' &&
    ['needs_review', 'approved', 'draft_ready', 'failed'].includes(task.status) &&
    !xHasOverLimit &&
    !xLongPostOverLimit &&
    (xFormat !== 'long_post' || hasCapability(task.api_capability, 'long_post')) &&
    (xFormat !== 'long_post' || Boolean(xLongPostText)) &&
    (xFormat !== 'thread' || xRows.length >= 2)
  return {
    xFormat,
    xRows,
    xLongPostText,
    xLongPostLimit,
    xHasOverLimit,
    xLongPostOverLimit,
    combined,
    canPublishX,
  }
}

export function PlatformFormatSummary({
  task,
  xFormat,
  xRows,
  xLongPostText,
}: {
  task: SocialDistributionTask
  xFormat: string | null
  xRows: XDraftRow[]
  xLongPostText: string
}) {
  const formatKind = stringValue(task.metadata.format_kind)
  const targetLength = stringValue(task.metadata.target_length)
  const countLabel =
    task.platform === 'x' && xRows.length
      ? xRows.map((row) => `${row.count}/280`).join(' · ')
      : task.platform === 'x' && xFormat === 'long_post'
        ? `${xLongPostText.length}/${Number(task.metadata.soft_max_chars) || 4000} chars`
        : stringValue(task.metadata.word_count)
          ? `${task.metadata.word_count} words`
          : stringValue(task.metadata.character_count)
            ? `${task.metadata.character_count} chars`
            : 'not measured'
  return (
    <section className="grid gap-3 md:grid-cols-3">
      <InfoBlock title="发布方式">{task.platform === 'x' ? xPublishLabel(xFormat) : 'Manual human publish'}</InfoBlock>
      <InfoBlock title="格式类型">{formatKind || 'platform draft'}</InfoBlock>
      <InfoBlock title="目标 / 当前">{targetLength ? `${targetLength} · ${countLabel}` : countLabel}</InfoBlock>
    </section>
  )
}

export function XDraftPreview({
  xFormat,
  rows,
  longPostText,
  longPostLimit,
}: {
  xFormat: string | null
  rows: XDraftRow[]
  longPostText: string
  longPostLimit: number
}) {
  if (xFormat === 'long_post') {
    return (
      <Field label={`X 长文 (${longPostText.length}/${longPostLimit} chars)`}>
        <textarea readOnly className={`${textareaClass} min-h-[360px]`} value={longPostText} />
      </Field>
    )
  }
  if (xFormat !== 'thread') {
    const row = rows[0]
    return (
      <Field label={`Tweet (${row.count}/280)`}>
        <textarea readOnly className={`${textareaClass} min-h-[150px]`} value={row.tweet} />
      </Field>
    )
  }
  return (
    <div className="grid gap-3">
      {rows.map((row, index) => (
        <div key={`${index}-${row.count}`} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-3">
          <div className="mb-2 flex items-center justify-between text-xs text-[color:var(--ops-text-caption)]">
            <span>推文 {index + 1}/{rows.length}</span>
            <span className={row.count > 280 ? 'text-rose-200' : 'text-emerald-200'}>{row.count}/280</span>
          </div>
          <textarea readOnly className={`${textareaClass} min-h-[120px]`} value={row.tweet} />
        </div>
      ))}
    </div>
  )
}

function xPublishLabel(xFormat: string | null): string {
  if (xFormat === 'long_post') return 'X Premium Long Post'
  if (xFormat === 'thread') return 'X Thread'
  return 'X Single'
}

function hasCapability(value: unknown, capability: string): boolean {
  return String(value ?? '').split(',').map((item) => item.trim()).includes(capability)
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item).trim()).filter(Boolean)
    : []
}

function numberArray(value: unknown): number[] {
  return Array.isArray(value)
    ? value.map((item) => Number(item)).filter((item) => Number.isFinite(item))
    : []
}

function stringValue(value: unknown): string {
  if (typeof value === 'number') return String(value)
  return typeof value === 'string' ? value : ''
}

function xFormatFromMetadata(metadata: Record<string, unknown>, tweets: string[]): string {
  const explicit = stringValue(metadata.x_format)
  if (explicit === 'single' || explicit === 'thread' || explicit === 'long_post') return explicit
  return tweets.length > 1 ? 'thread' : 'single'
}

function conservativeXCount(value: string): number {
  let total = 0
  const parts = value.split(/(https?:\/\/\S+)/)
  for (const part of parts) {
    if (/^https?:\/\//.test(part)) {
      total += 23
      continue
    }
    for (const char of Array.from(part)) {
      total += /[^\u0000-\u10ff]/.test(char) ? 2 : 1
    }
  }
  return total
}
