import type { SocialContentAssetDetail, SocialReplyItem } from '../apiSocialDistribution'
import { InfoBlock, StateBadge, copyText, statusTone } from './SocialDistributionWidgets'
import type { useToast } from './workbench'

type ReplyAction = (reply: SocialReplyItem) => void

export function ReplyTaskDetailView({
  asset,
  formatDateTime,
  busy,
  toast,
  onGenerateXReplyBlock,
  onMarkManualPublished,
  onPublishReplyToX,
  onRegenerateReply,
}: {
  asset: SocialContentAssetDetail
  formatDateTime: (value: string | null | undefined) => string
  busy: boolean
  toast: ReturnType<typeof useToast>
  onGenerateXReplyBlock: () => void
  onMarkManualPublished: ReplyAction
  onPublishReplyToX: ReplyAction
  onRegenerateReply: ReplyAction
}) {
  const replyBlock = objectValue(asset.agent_metadata.reply_block)
  const replies = asset.reply_items ?? []
  const sourcePosts = uniqueSourcePosts(replies)
  const compliance = complianceSummary(replyBlock, replies)
  const generatedCount = replies.length
  const reviewedCount = replies.filter((reply) => reply.reviewed_by || reply.status.includes('approved')).length
  const publishedCount = replies.filter((reply) => ['published', 'published_manual'].includes(reply.status)).length
  const failedCount = replies.filter((reply) => ['failed', 'rejected'].includes(reply.status)).length
  const targetCount = numberValue(replyBlock.target_count) || numberValue(replyBlock.processed_source_count) || 5
  const manualQueue = replies.map((reply, index) => {
    const source = reply.source_url ? `Source: ${reply.source_url}` : `Source post: ${reply.source_post_id ?? 'unknown'}`
    return `${index + 1}. ${source}\nReply: ${reply.suggested_reply ?? ''}`.trim()
  }).join('\n\n')

  return (
    <div className="space-y-5">
      <section className="grid gap-3 md:grid-cols-5">
        <InfoBlock title="状态">{asset.status}</InfoBlock>
        <InfoBlock title="目标">{targetCount}</InfoBlock>
        <InfoBlock title="已生成">{generatedCount}</InfoBlock>
        <InfoBlock title="已审核">{reviewedCount}</InfoBlock>
        <InfoBlock title="已发布 / 失败">{publishedCount} / {failedCount}</InfoBlock>
      </section>
      <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4">
        <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Plan</div>
        <div className="max-h-[260px] overflow-auto whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-body)]">
          {sourcePlanText(asset)}
        </div>
      </section>
      <section className="rounded-2xl border border-cyan-300/30 bg-cyan-500/10 p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="text-[11px] uppercase tracking-[0.18em] text-cyan-100/80">Compliance Gate</div>
          <StateBadge tone={compliance.tone}>{compliance.label}</StateBadge>
        </div>
        <div className="text-sm leading-6 text-[color:var(--ops-text-body)]">{compliance.message}</div>
        <div className="mt-3 grid gap-2 text-xs text-cyan-100/80 md:grid-cols-3">
          <span>publish mode: {stringValue(replyBlock.publish_mode, 'manual')}</span>
          <span>approval ref: {String(Boolean(replyBlock.approval_ref_configured))}</span>
          <span>auto publish: {String(Boolean(replyBlock.auto_publish))}</span>
        </div>
      </section>
      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Source Posts</div>
            <p className="mt-1 text-sm text-[color:var(--ops-text-muted)]">每条回复必须绑定真实 X source post；同一 source post 不重复发布。</p>
          </div>
          <StateBadge tone={sourcePosts.length ? 'ready' : 'blocked'}>{sourcePosts.length} posts</StateBadge>
        </div>
        {sourcePosts.length ? (
          <div className="grid gap-3">
            {sourcePosts.map((post) => (
              <SourcePostCard key={post.key} post={post} />
            ))}
          </div>
        ) : (
          <InfoBlock title="No Real Source Posts">缺少真实 source_url/source_text 时会 fail closed，不补假数据。</InfoBlock>
        )}
      </section>
      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Reply Candidates</div>
            <p className="mt-1 text-sm text-[color:var(--ops-text-muted)]">候选回复经过 agent policy/quality review；无 X approval 时只进入人工发布队列。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {replies.length ? (
              <button type="button" className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100" onClick={() => copyText(manualQueue, toast)}>
                复制人工发布队列
              </button>
            ) : null}
            <button type="button" disabled={busy} className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={onGenerateXReplyBlock}>
              {busy ? '生成中...' : '生成 5 条 X 回复候选'}
            </button>
          </div>
        </div>
        {replies.length ? (
          <div className="grid gap-3">
            {replies.map((reply, index) => (
              <ReplyCandidateCard
                key={reply.id}
                index={index}
                reply={reply}
                busy={busy}
                toast={toast}
                onMarkManualPublished={onMarkManualPublished}
                onPublishReplyToX={onPublishReplyToX}
                onRegenerateReply={onRegenerateReply}
              />
            ))}
          </div>
        ) : (
          <InfoBlock title="No Reply Candidates">粘贴或同步真实 X source posts 后，点击“生成 5 条 X 回复候选”。</InfoBlock>
        )}
      </section>
      <section>
        <div className="mb-3 text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Events</div>
        <div className="grid gap-2">
          {asset.events.length ? asset.events.map((event) => (
            <div key={event.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-3 text-sm">
              <div className="font-semibold text-[color:var(--ops-text-title)]">{event.event_type}</div>
              <div className="mt-1 text-[color:var(--ops-text-muted)]">{event.summary || 'No summary.'}</div>
              <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">{event.actor} · {formatDateTime(event.created_at)}</div>
            </div>
          )) : <InfoBlock title="No Events">暂无事件。</InfoBlock>}
        </div>
      </section>
    </div>
  )
}

function SourcePostCard({ post }: { post: SourcePost }) {
  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-mono text-xs uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)]">{post.sourcePostId || 'unknown-post-id'}</div>
          <div className="mt-1 text-sm font-semibold text-[color:var(--ops-text-title)]">{post.author || 'Unknown author'}</div>
        </div>
        {post.sourceUrl ? <a className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100" href={post.sourceUrl} target="_blank" rel="noreferrer">打开原帖</a> : null}
      </div>
      <div className="mt-3 line-clamp-3 text-sm leading-6 text-[color:var(--ops-text-body)]">{post.sourceText || 'No source text captured.'}</div>
      {post.optInEvidence ? (
        <div className="mt-3 rounded-xl border border-emerald-300/30 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-100">opt-in: {post.optInEvidence}</div>
      ) : null}
    </div>
  )
}

function ReplyCandidateCard({
  index,
  reply,
  busy,
  toast,
  onMarkManualPublished,
  onPublishReplyToX,
  onRegenerateReply,
}: {
  index: number
  reply: SocialReplyItem
  busy: boolean
  toast: ReturnType<typeof useToast>
  onMarkManualPublished: ReplyAction
  onPublishReplyToX: ReplyAction
  onRegenerateReply: ReplyAction
}) {
  const review = objectValue(reply.metadata.agent_quality_review)
  const compliance = objectValue(reply.metadata.x_reply_compliance)
  const weightedCount = xWeightedCount(reply.suggested_reply ?? '')
  const canApiPublish = Boolean(compliance.approval_ref_configured && compliance.opt_in_evidence && reply.status === 'approved')
  return (
    <article className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-mono text-xs uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)]">Reply {index + 1} · {reply.source_post_id ?? 'unknown source'}</div>
          <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{reply.source_author_handle ?? 'unknown author'}</div>
        </div>
        <StateBadge tone={statusTone(reply.status)}>{reply.status}</StateBadge>
      </div>
      <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-3">
        <div className="mb-2 text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Suggested Reply</div>
        <div className="whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-body)]">{reply.suggested_reply || 'No reply generated.'}</div>
      </div>
      <div className="mt-3 grid gap-2 text-xs text-[color:var(--ops-text-caption)] md:grid-cols-4">
        <span>{weightedCount}/280 weighted chars</span>
        <span>risk: {reply.risk_level}</span>
        <span>review: {stringValue(review.status, 'pending')}</span>
        <span>generated: {stringValue(reply.metadata.model, 'unknown')}</span>
      </div>
      {reply.source_text ? <div className="mt-3 line-clamp-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">{reply.source_text}</div> : null}
      {reply.failure_summary ? <InfoBlock title="Blocker">{reply.failure_summary}</InfoBlock> : null}
      {reply.published_external_post_id ? (
        <div className="mt-3 rounded-xl border border-emerald-300/30 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-100">
          published reply id: {reply.published_external_post_id}
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => copyText(reply.suggested_reply ?? '', toast)}>复制回复</button>
        {reply.source_url ? <a className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" href={reply.source_url} target="_blank" rel="noreferrer">打开原帖</a> : null}
        <button type="button" disabled={busy || ['published', 'published_manual'].includes(reply.status)} className="rounded-xl border border-emerald-300/40 px-3 py-2 text-sm text-emerald-100 disabled:opacity-50" onClick={() => onMarkManualPublished(reply)}>标记已手动发布</button>
        {reply.source_candidate_id ? (
          <button type="button" disabled={busy || ['published', 'published_manual'].includes(reply.status)} className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100 disabled:opacity-50" onClick={() => onRegenerateReply(reply)}>重新生成</button>
        ) : null}
        {canApiPublish ? (
          <button type="button" disabled={busy || weightedCount > 280} className="rounded-xl bg-[color:var(--ops-accent-strong)] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={() => onPublishReplyToX(reply)}>通过 X API 发布</button>
        ) : null}
      </div>
    </article>
  )
}

interface SourcePost {
  key: string
  sourcePostId: string | null
  author: string | null
  sourceUrl: string | null
  sourceText: string | null
  optInEvidence: string
}

function uniqueSourcePosts(replies: SocialReplyItem[]): SourcePost[] {
  const byKey = new Map<string, SourcePost>()
  for (const reply of replies) {
    const compliance = objectValue(reply.metadata.x_reply_compliance)
    const key = reply.source_post_id || reply.source_url || String(reply.id)
    if (!byKey.has(key)) {
      byKey.set(key, {
        key,
        sourcePostId: reply.source_post_id,
        author: reply.source_author_handle,
        sourceUrl: reply.source_url,
        sourceText: reply.source_text,
        optInEvidence: stringValue(compliance.opt_in_evidence),
      })
    }
  }
  return [...byKey.values()]
}

function complianceSummary(replyBlock: Record<string, unknown>, replies: SocialReplyItem[]) {
  const approvalConfigured = Boolean(replyBlock.approval_ref_configured)
  const missingOptIn = replies.some((reply) => !stringValue(objectValue(reply.metadata.x_reply_compliance).opt_in_evidence))
  if (!approvalConfigured) {
    return {
      label: 'manual publish required',
      tone: 'validating' as const,
      message: 'Agent 可以生成和审核候选回复，但缺少 X AI automated replies prior written approval，系统不会自动公开发布。',
    }
  }
  if (missingOptIn) {
    return {
      label: 'blocked',
      tone: 'blocked' as const,
      message: '已配置 X approval ref，但至少一条 source post 缺少 opt-in evidence；自动 API 发布保持阻断。',
    }
  }
  return {
    label: 'API auto-publish eligible',
    tone: 'ready' as const,
    message: 'X approval ref 与 opt-in evidence 已满足；候选通过审核后可以走 X API reply 发布。',
  }
}

function sourcePlanText(asset: SocialContentAssetDetail): string {
  const plan = asset.documents.find((doc) => doc.document_kind === 'source_plan')
  return plan?.body_markdown || asset.summary || asset.body || 'No source plan yet.'
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function numberValue(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return 0
}

function stringValue(value: unknown, fallback = ''): string {
  if (typeof value === 'number') return String(value)
  return typeof value === 'string' && value.trim() ? value : fallback
}

function xWeightedCount(text: string): number {
  const urlPattern = /https?:\/\/\S+/g
  let count = 0
  let cursor = 0
  for (const match of text.matchAll(urlPattern)) {
    count += weightedText(text.slice(cursor, match.index))
    count += 23
    cursor = (match.index ?? 0) + match[0].length
  }
  return count + weightedText(text.slice(cursor))
}

function weightedText(text: string): number {
  let total = 0
  for (const char of text) {
    total += char.charCodeAt(0) > 0x7f ? 2 : 1
  }
  return total
}
