import type { SocialDistributionTask } from '../api'
import { Field, InfoBlock, textareaClass } from './SocialDistributionWidgets'

export interface XDraftRow {
  tweet: string
  count: number
}

export interface XDraftView {
  xFormat: string | null
  xRows: XDraftRow[]
  xLimit: number
  xHasOverLimit: boolean
  combined: string
  canPublishX: boolean
}

export function buildXDraftView(task: SocialDistributionTask | null): XDraftView {
  if (!task || task.platform !== 'x') {
    return {
      xFormat: null,
      xRows: [],
      xLimit: 280,
      xHasOverLimit: false,
      combined: `Title:\n${task?.platform_title ?? ''}\n\nBody:\n${task?.platform_body ?? ''}`,
      canPublishX: false,
    }
  }
  const metadata = task.metadata ?? {}
  const xTweets = stringArray(metadata.tweets)
  const xFormat = xFormatFromMetadata(metadata, xTweets)
  const xWeightedCounts = numberArray(metadata.weighted_counts)
  const xPostRows = xRowsFromTask(xTweets, task.platform_body, xFormat, metadata)
  const xRows = xPostRows.map((tweet, index) => ({
    tweet,
    count: xFormat === 'long_post' || xFormat === 'article_pack'
      ? Number(metadata.character_count) || tweet.length
      : xWeightedCounts[index] ?? conservativeXCount(tweet),
  }))
  const xLimit = xFormat === 'article_pack' ? Number(metadata.article_character_count) || xRows[0]?.count || 0 : xFormat === 'long_post' ? Number(metadata.soft_max_chars) || 4000 : 280
  const xHasOverLimit = xRows.some((row) => row.count > xLimit)
  const isManualArticlePack = xFormat === 'article_pack'
  return {
    xFormat,
    xRows,
    xLimit,
    xHasOverLimit,
    combined: xRows.length
      ? xCombinedCopy(xFormat, xRows)
      : `Title:\n${task.platform_title ?? ''}\n\nBody:\n${task.platform_body ?? ''}`,
    canPublishX:
      task.publish_mode === 'api_human_gated' &&
      !isManualArticlePack &&
      ['needs_review', 'approved', 'draft_ready', 'failed'].includes(task.status) &&
      !xHasOverLimit &&
      (xFormat !== 'long_post' || hasCapability(task.api_capability, 'long_post')) &&
      (xFormat !== 'long_post' || xRows.length === 1) &&
      (xFormat !== 'thread' || xRows.length >= 2),
  }
}

export function PlatformFormatSummary({
  task,
  xFormat,
  xRows,
}: {
  task: SocialDistributionTask
  xFormat: string | null
  xRows: XDraftRow[]
}) {
  const formatKind = stringValue(task.metadata.format_kind)
  const targetLength = stringValue(task.metadata.target_length)
  const xLimit = xFormat === 'long_post' ? Number(task.metadata.soft_max_chars) || 4000 : 280
  const countLabel =
    task.platform === 'x' && xRows.length
      ? xRows.map((row) => `${row.count}/${xLimit}`).join(' · ')
      : stringValue(task.metadata.word_count)
        ? `${task.metadata.word_count} words`
        : stringValue(task.metadata.character_count)
          ? `${task.metadata.character_count} chars`
          : 'not measured'
  return (
    <section className="grid gap-3 md:grid-cols-3">
      <InfoBlock title="发布方式">{task.platform === 'x' ? xFormatLabel(xFormat) : 'Manual human publish'}</InfoBlock>
      <InfoBlock title="格式类型">{formatKind || 'platform draft'}</InfoBlock>
      <InfoBlock title="目标 / 当前">{targetLength ? `${targetLength} · ${countLabel}` : countLabel}</InfoBlock>
    </section>
  )
}

export function XDraftPreview({
  xFormat,
  rows,
}: {
  xFormat: string | null
  rows: XDraftRow[]
}) {
  if (xFormat === 'article_pack') {
    const row = rows[0]
    return (
      <Field label={`X Article 正文（手动发布 · ${row.count} chars）`}>
        <textarea readOnly className={`${textareaClass} min-h-[420px]`} value={row.tweet} />
      </Field>
    )
  }
  if (xFormat === 'long_post') {
    const row = rows[0]
    return (
      <Field label={`X 长文 (${row.count}/4000 chars)`}>
        <textarea readOnly className={`${textareaClass} min-h-[360px]`} value={row.tweet} />
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

export function xPublishButtonLabel(xFormat: string | null): string {
  if (xFormat === 'article_pack') return 'Article 需手动发布'
  if (xFormat === 'thread') return '一键发布 Thread'
  if (xFormat === 'long_post') return '发布长文到 X'
  return '发布到 X'
}

export function copyCombinedLabel(platform: string, xFormat: string | null, rowCount: number): string {
  if (platform !== 'x' || rowCount === 0) return '一键复制标题和正文'
  if (xFormat === 'article_pack') return '复制 Article 正文'
  if (xFormat === 'long_post') return '复制长文'
  if (xFormat === 'thread') return '复制整条 Thread'
  return '复制推文'
}

function xFormatFromMetadata(metadata: Record<string, unknown>, tweets: string[]): string {
  const explicit = stringValue(metadata.x_format).toLowerCase()
  const formatKind = stringValue(metadata.format_kind).toLowerCase()
  if (['article_pack', 'x_article_pack'].includes(explicit)) return 'article_pack'
  if (['article_pack', 'x_article_pack'].includes(formatKind)) return 'article_pack'
  if (['long_post', 'x_long_post', 'premium_long_post'].includes(explicit)) return 'long_post'
  if (['long_post', 'x_long_post', 'premium_long_post'].includes(formatKind)) return 'long_post'
  if (explicit === 'single' || explicit === 'thread') return explicit
  return tweets.length > 1 ? 'thread' : 'single'
}

function xRowsFromTask(
  tweets: string[],
  body: string | null | undefined,
  xFormat: string | null,
  metadata: Record<string, unknown>,
): string[] {
  if (tweets.length) return tweets
  if (xFormat === 'article_pack') {
    const articleBody = String(body ?? '').trim() || stringValue(metadata.article_body_markdown)
    return articleBody ? [articleBody] : []
  }
  if (xFormat === 'long_post') {
    const longPost = stringValue(metadata.long_post_text) || stringValue(metadata.post_text) || String(body ?? '').trim()
    return longPost ? [longPost] : []
  }
  const bodyText = String(body ?? '').trim()
  if (bodyText) return [bodyText]
  const metadataBody = stringValue(metadata.body_text)
  return metadataBody ? [metadataBody] : []
}

function xCombinedCopy(xFormat: string | null, rows: XDraftRow[]): string {
  if (xFormat === 'article_pack') return rows[0]?.tweet ?? ''
  if (xFormat === 'long_post') return rows[0]?.tweet ?? ''
  return rows.map((row, index) => `Tweet ${index + 1}/${rows.length}\n${row.tweet}`).join('\n\n')
}

function xFormatLabel(xFormat: string | null): string {
  if (xFormat === 'article_pack') return 'X Article Pack (manual)'
  if (xFormat === 'thread') return 'X Thread'
  if (xFormat === 'long_post') return 'X Premium Long Post'
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
