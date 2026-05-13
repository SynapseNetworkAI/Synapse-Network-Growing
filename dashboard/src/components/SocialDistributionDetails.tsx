import type {
  SocialContentAssetDetail,
  SocialDistributionAccount,
  SocialDistributionTask,
} from '../api'
import type { SocialDistributionDocument } from '../apiSocialDistribution'
import { OverlayModal, type useToast } from './workbench'
import {
  Field,
  InfoBlock,
  StateBadge,
  copyText,
  inputClass,
  statusTone,
  textareaClass,
} from './SocialDistributionWidgets'

export function TaskDetailModal({
  task,
  manualUrl,
  manualNote,
  toast,
  onManualUrlChange,
  onManualNoteChange,
  onClose,
  onMarkLive,
  onMarkRemoved,
  onSkip,
  onPublishX,
}: {
  task: SocialDistributionTask | null
  manualUrl: string
  manualNote: string
  toast: ReturnType<typeof useToast>
  onManualUrlChange: (value: string) => void
  onManualNoteChange: (value: string) => void
  onClose: () => void
  onMarkLive: () => void
  onMarkRemoved: () => void
  onSkip: () => void
  onPublishX: () => void
}) {
  const metadata = task?.metadata ?? {}
  const xTweets = task?.platform === 'x' ? stringArray(metadata.tweets) : []
  const xFormat = task?.platform === 'x' ? xFormatFromMetadata(metadata, xTweets) : null
  const xWeightedCounts = numberArray(metadata.weighted_counts)
  const xRows = xTweets.map((tweet, index) => ({
    tweet,
    count: xWeightedCounts[index] ?? conservativeXCount(tweet),
  }))
  const xHasOverLimit = xRows.some((row) => row.count > 280)
  const combined =
    task?.platform === 'x' && xRows.length
      ? xRows.map((row, index) => `Tweet ${index + 1}/${xRows.length}\n${row.tweet}`).join('\n\n')
      : `Title:\n${task?.platform_title ?? ''}\n\nBody:\n${task?.platform_body ?? ''}`
  const canPublishX =
    task?.platform === 'x' &&
    task.publish_mode === 'api_human_gated' &&
    ['needs_review', 'approved', 'draft_ready', 'failed'].includes(task.status) &&
    !xHasOverLimit &&
    (xFormat !== 'thread' || xRows.length >= 2)
  return (
    <OverlayModal
      open={Boolean(task)}
      eyebrow="Distribution Task"
      title={task ? `${task.account_display_name ?? task.channel_key}` : 'Task'}
      description="非 X 平台只辅助复制和人工回填；不会自动登录、发帖、评论或投票。"
      onClose={onClose}
    >
      {task ? (
        <div className="space-y-4">
          <InfoBlock title="平台规则提醒">
            {task.operator_checklist || 'Human Gate required.'}
          </InfoBlock>
          <PlatformFormatSummary task={task} xFormat={xFormat} xRows={xRows} />
          {task.platform === 'x' && xRows.length ? (
            <XDraftPreview xFormat={xFormat} rows={xRows} />
          ) : (
            <>
              <Field label="标题">
                <textarea
                  readOnly
                  className={`${textareaClass} min-h-[64px]`}
                  value={task.platform_title ?? ''}
                />
              </Field>
              <Field label="正文">
                <textarea
                  readOnly
                  className={`${textareaClass} min-h-[180px]`}
                  value={task.platform_body ?? ''}
                />
              </Field>
            </>
          )}
          <div className="flex flex-wrap gap-2">
            {task.submission_url ? (
              <a
                className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm"
                href={task.submission_url}
                target="_blank"
                rel="noreferrer"
              >
                打开平台
              </a>
            ) : null}
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => copyText(task.platform_title ?? '', toast)}>复制标题</button>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => copyText(task.platform_body ?? '', toast)}>复制正文</button>
            <button type="button" className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100" onClick={() => copyText(combined, toast)}>{task.platform === 'x' && xRows.length ? '复制整条 Thread' : '一键复制标题和正文'}</button>
          </div>
          {xHasOverLimit ? (
            <InfoBlock title="X 超限">有推文超过 280 weighted chars，发布按钮已禁用。</InfoBlock>
          ) : null}
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Published URL"><input className={inputClass} value={manualUrl} onChange={(event) => onManualUrlChange(event.target.value)} /></Field>
            <Field label="人工备注 / removed 原因"><input className={inputClass} value={manualNote} onChange={(event) => onManualNoteChange(event.target.value)} /></Field>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={onSkip}>跳过</button>
            <button type="button" className="rounded-xl border border-rose-300/40 px-3 py-2 text-sm text-rose-100" onClick={onMarkRemoved}>标记 removed</button>
            {task.platform === 'x' ? <button type="button" disabled={!canPublishX} className="rounded-xl border border-emerald-300/50 px-4 py-2 text-sm font-semibold text-emerald-100 disabled:opacity-50" onClick={onPublishX}>{xFormat === 'thread' ? '一键发布 Thread' : '发布到 X'}</button> : null}
            <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={onMarkLive}>标记已发布</button>
          </div>
        </div>
      ) : null}
    </OverlayModal>
  )
}

export function ContentTaskDetailModal({
  asset,
  accounts,
  selectedAccountIds,
  formatDateTime,
  busy,
  onToggleAccount,
  onClose,
  onGeneratePlan,
  onExpandCanonicalArticle,
  onApproveCanonicalArticle,
  onApproveGenerate,
  onOpenTask,
}: {
  asset: SocialContentAssetDetail | null
  accounts: SocialDistributionAccount[]
  selectedAccountIds: number[]
  formatDateTime: (value: string | null | undefined) => string
  busy: boolean
  onToggleAccount: (id: number) => void
  onClose: () => void
  onGeneratePlan: () => void
  onExpandCanonicalArticle: () => void
  onApproveCanonicalArticle: (documentId: number | null) => void
  onApproveGenerate: () => void
  onOpenTask: (task: SocialDistributionTask) => void
}) {
  const documents = asset?.documents ?? []
  const sourcePlan = documents.find((doc) => doc.document_kind === 'source_plan')
  const canonicalArticle = latestDocument(documents, 'canonical_article')
  const canonicalApproved = canonicalArticle?.status === 'approved'
  const platformDocs = documents.filter((doc) => doc.document_kind === 'platform_draft')
  return (
    <OverlayModal
      open={Boolean(asset)}
      eyebrow="Content Task"
      title={asset?.title ?? '内容任务'}
      description="一张卡代表一篇源内容；平台文档和发布动作都挂在这张任务卡下面。"
      actions={
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" disabled={!asset || busy} className="rounded-2xl border border-cyan-300/40 px-4 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50" onClick={onGeneratePlan}>
            {busy ? '生成中…' : '重新生成方案'}
          </button>
          {!canonicalArticle ? (
            <button type="button" disabled={!asset || busy} className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={onExpandCanonicalArticle}>
              {busy ? '扩写中…' : '扩写母稿'}
            </button>
          ) : !canonicalApproved ? (
            <button type="button" disabled={!asset || busy} className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={() => onApproveCanonicalArticle(canonicalArticle.id)}>
              {busy ? '审核中…' : '审核通过母稿'}
            </button>
          ) : (
            <button type="button" disabled={!asset || busy} className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={onApproveGenerate}>
              {busy ? '生成中…' : '批准并生成平台任务'}
            </button>
          )}
        </div>
      }
      onClose={onClose}
    >
      {asset ? (
        <div className="space-y-5">
          <section className="grid gap-3 md:grid-cols-3">
            <InfoBlock title="状态">{asset.status}</InfoBlock>
            <InfoBlock title="平台任务">{asset.tasks.length}</InfoBlock>
            <InfoBlock title="文档">{documents.length}</InfoBlock>
          </section>
          <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4">
            <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Plan</div>
            <div className="max-h-[320px] overflow-auto whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-body)]">
              {sourcePlan?.body_markdown || asset.summary || asset.body || 'No source plan yet.'}
            </div>
            {sourcePlan ? <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">v{sourcePlan.version} · {formatDateTime(sourcePlan.updated_at)}</div> : null}
          </section>
          <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Canonical Article</div>
              <StateBadge tone={canonicalApproved ? 'ready' : canonicalArticle ? 'validating' : 'muted'}>
                {canonicalArticle ? canonicalArticle.status : 'missing'}
              </StateBadge>
            </div>
            {canonicalArticle ? (
              <>
                <div className="mb-2 text-sm font-semibold text-[color:var(--ops-text-title)]">{canonicalArticle.title}</div>
                <div className="max-h-[360px] overflow-auto whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-body)]">{canonicalArticle.body_markdown}</div>
                <div className="mt-3 flex flex-wrap gap-3 text-xs text-[color:var(--ops-text-caption)]">
                  <span>{canonicalArticle.body_markdown.length} chars</span>
                  <span>v{canonicalArticle.version}</span>
                  <span>updated {formatDateTime(canonicalArticle.updated_at)}</span>
                  <span>generated by {String(canonicalArticle.metadata.generated_by ?? 'unknown')}</span>
                </div>
              </>
            ) : (
              <InfoBlock title="Mother Draft Required">请先把短大纲扩写成 canonical_article 母稿；母稿审核通过前，系统不会生成正式平台任务。</InfoBlock>
            )}
          </section>
          <section>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Platform Docs</div>
                <p className="mt-1 text-sm text-[color:var(--ops-text-muted)]">每个平台都有独立文档；非 X 仍然是复制、打开平台、人工回填。</p>
              </div>
              <StateBadge tone={platformDocs.length ? 'ready' : 'muted'}>{platformDocs.length} docs</StateBadge>
            </div>
            {platformDocs.length ? (
              <div className="grid gap-3">
                {platformDocs.map((doc) => (
                  <DocumentRow key={doc.id} doc={doc} formatDateTime={formatDateTime} />
                ))}
              </div>
            ) : (
              <InfoBlock title="No Platform Docs">{canonicalApproved ? '选择渠道后点击“批准并生成平台任务”。' : '母稿审核通过后才可以生成平台任务。'}</InfoBlock>
            )}
          </section>
          <section>
            <div className="mb-3 text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Channel Selection</div>
            <div className="grid gap-2 md:grid-cols-2">
              {accounts.map((account) => (
                <label key={account.id} className="flex items-start gap-3 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-3 text-sm">
                  <input type="checkbox" checked={selectedAccountIds.includes(account.id)} onChange={() => onToggleAccount(account.id)} />
                  <span><b>{account.display_name}</b><span className="block text-xs text-[color:var(--ops-text-caption)]">{account.platform} · {account.channel_key}</span></span>
                </label>
              ))}
            </div>
          </section>
          <section>
            <div className="mb-3 text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Publish</div>
            {asset.tasks.length ? (
              <div className="grid gap-2">
                {asset.tasks.map((task) => (
                  <div key={task.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-3">
                    <div>
                      <b>{task.account_display_name ?? task.channel_key}</b>
                      <div className="text-xs text-[color:var(--ops-text-caption)]">{task.platform} · {task.channel_key} · {task.status}</div>
                    </div>
                    <button type="button" className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100" onClick={() => onOpenTask(task)}>
                      {task.platform === 'x' ? '发布到 X / 详情' : '复制并打开平台'}
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <InfoBlock title="No Publish Tasks">还没有平台任务。</InfoBlock>
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
      ) : null}
    </OverlayModal>
  )
}

function latestDocument(documents: SocialDistributionDocument[], kind: string) {
  return documents
    .filter((doc) => doc.document_kind === kind)
    .sort((left, right) => {
      if (right.version !== left.version) return right.version - left.version
      return String(right.updated_at ?? '').localeCompare(String(left.updated_at ?? ''))
    })[0]
}

function DocumentRow({ doc, formatDateTime }: { doc: SocialDistributionDocument; formatDateTime: (value: string | null | undefined) => string }) {
  const formatKind = stringValue(doc.metadata.format_kind)
  const targetLength = stringValue(doc.metadata.target_length)
  const weightedCounts = numberArray(doc.metadata.weighted_counts)
  return (
    <details className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4">
      <summary className="cursor-pointer">
        <span className="font-semibold text-[color:var(--ops-text-title)]">{doc.title}</span>
        <span className="ml-2 font-mono text-xs text-[color:var(--ops-text-caption)]">{doc.platform ?? 'source'} · {doc.channel_key ?? 'plan'} · {doc.status} · v{doc.version}</span>
      </summary>
      {formatKind || targetLength ? (
        <div className="mt-3 grid gap-2 text-xs text-[color:var(--ops-text-caption)] md:grid-cols-3">
          {formatKind ? <span>格式：{formatKind}</span> : null}
          {targetLength ? <span>目标：{targetLength}</span> : null}
          {weightedCounts.length ? <span>X counts：{weightedCounts.join(' / ')}</span> : null}
        </div>
      ) : null}
      <div className="mt-3 max-h-[360px] overflow-auto whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-body)]">{doc.body_markdown}</div>
      <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">updated {formatDateTime(doc.updated_at)}</div>
    </details>
  )
}

function PlatformFormatSummary({
  task,
  xFormat,
  xRows,
}: {
  task: SocialDistributionTask
  xFormat: string | null
  xRows: { tweet: string; count: number }[]
}) {
  const formatKind = stringValue(task.metadata.format_kind)
  const targetLength = stringValue(task.metadata.target_length)
  const countLabel =
    task.platform === 'x' && xRows.length
      ? xRows.map((row) => `${row.count}/280`).join(' · ')
      : stringValue(task.metadata.word_count)
        ? `${task.metadata.word_count} words`
        : stringValue(task.metadata.character_count)
          ? `${task.metadata.character_count} chars`
          : 'not measured'
  return (
    <section className="grid gap-3 md:grid-cols-3">
      <InfoBlock title="发布方式">{task.platform === 'x' ? (xFormat === 'thread' ? 'X Thread' : 'X Single') : 'Manual human publish'}</InfoBlock>
      <InfoBlock title="格式类型">{formatKind || 'platform draft'}</InfoBlock>
      <InfoBlock title="目标 / 当前">{targetLength ? `${targetLength} · ${countLabel}` : countLabel}</InfoBlock>
    </section>
  )
}

function XDraftPreview({
  xFormat,
  rows,
}: {
  xFormat: string | null
  rows: { tweet: string; count: number }[]
}) {
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
  if (explicit === 'single' || explicit === 'thread') return explicit
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

export function AssetDetail({
  asset,
  accounts,
  selectedAccountIds,
  formatDateTime,
  onToggle,
}: {
  asset: SocialContentAssetDetail
  accounts: SocialDistributionAccount[]
  selectedAccountIds: number[]
  formatDateTime: (value: string | null | undefined) => string
  onToggle: (id: number) => void
}) {
  const metadata = asset.agent_metadata ?? {}
  const recommended = Array.isArray(metadata.recommended_channels)
    ? metadata.recommended_channels.join(', ')
    : 'manual selection'
  const sourceRefs = Array.isArray(metadata.source_signal_refs)
    ? metadata.source_signal_refs.join(', ')
    : 'manual'
  const canonicalArticle = latestDocument(asset.documents, 'canonical_article')
  const canonicalApproved = canonicalArticle?.status === 'approved'
  return (
    <div className="space-y-4">
      <InfoBlock title="资产摘要">{asset.summary || asset.body || 'No summary yet.'}</InfoBlock>
      <div className="grid gap-3 md:grid-cols-2">
        <InfoBlock title="推荐渠道">{recommended}</InfoBlock>
        <InfoBlock title="来源信号">{sourceRefs}</InfoBlock>
      </div>
      <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Canonical Article</div>
          <StateBadge tone={canonicalApproved ? 'ready' : canonicalArticle ? 'validating' : 'muted'}>{canonicalArticle ? canonicalArticle.status : 'missing'}</StateBadge>
        </div>
        {canonicalArticle ? (
          <>
            <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{canonicalArticle.title}</div>
            <div className="mt-2 max-h-[300px] overflow-auto whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-body)]">{canonicalArticle.body_markdown}</div>
            <div className="mt-3 flex flex-wrap gap-3 text-xs text-[color:var(--ops-text-caption)]">
              <span>{canonicalArticle.body_markdown.length} chars</span>
              <span>v{canonicalArticle.version}</span>
              <span>generated by {String(canonicalArticle.metadata.generated_by ?? 'unknown')}</span>
            </div>
          </>
        ) : (
          <InfoBlock title="Mother Draft Required">缺少母稿时只能扩写母稿，不能直接从短大纲生成平台任务。</InfoBlock>
        )}
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        {accounts.map((account) => (
          <label key={account.id} className="flex items-start gap-3 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-3 text-sm">
            <input type="checkbox" checked={selectedAccountIds.includes(account.id)} onChange={() => onToggle(account.id)} />
            <span><b>{account.display_name}</b><span className="block text-xs text-[color:var(--ops-text-caption)]">{account.platform} · {account.channel_key}</span></span>
          </label>
        ))}
      </div>
      {asset.tasks.length ? (
        <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4">
          <div className="mb-3 text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Generated Platform Tasks</div>
          <div className="grid gap-2">
            {asset.tasks.map((task) => (
              <div key={task.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] px-3 py-2">
                <div>
                  <b>{task.account_display_name ?? task.channel_key}</b>
                  <div className="text-xs text-[color:var(--ops-text-caption)]">{task.platform} · updated {formatDateTime(task.updated_at)}</div>
                </div>
                <div className="flex items-center gap-2">
                  <StateBadge tone={statusTone(task.status)}>{task.status}</StateBadge>
                  {task.submission_url ? <a className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-2 py-1 text-xs" href={task.submission_url} target="_blank" rel="noreferrer">打开平台</a> : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}
