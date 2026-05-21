import type { SocialContentAssetDetail, SocialDistributionAccount, SocialDistributionTask } from '../api'
import type { SocialDistributionAccountAuthStatus, SocialDistributionDocument } from '../apiSocialDistribution'
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
import {
  PlatformFormatSummary,
  XDraftPreview,
  buildXDraftView,
  copyCombinedLabel,
  xPublishButtonLabel,
} from './SocialDistributionXDraft'
import { PublishAuditControls, PublishAuditSummary } from './SocialDistributionPublishAudit'

export function TaskDetailModal({
  task,
  manualUrl,
  manualNote,
  toast,
  onManualUrlChange,
  onManualNoteChange,
  auditVisibility,
  auditLayout,
  onAuditVisibilityChange,
  onAuditLayoutChange,
  onClose,
  onMarkLive,
  onMarkRemoved,
  onSkip,
  onAuditPublishedPage,
  onPublishX,
  publishBusy = false,
  xAuthNotice,
  authStatus,
  onCheckAuth,
}: {
  task: SocialDistributionTask | null
  manualUrl: string
  manualNote: string
  toast: ReturnType<typeof useToast>
  onManualUrlChange: (value: string) => void
  onManualNoteChange: (value: string) => void
  auditVisibility: string
  auditLayout: string
  onAuditVisibilityChange: (value: string) => void
  onAuditLayoutChange: (value: string) => void
  onClose: () => void
  onMarkLive: () => void
  onMarkRemoved: () => void
  onSkip: () => void
  onAuditPublishedPage: () => void
  onPublishX: () => void
  publishBusy?: boolean
  xAuthNotice?: string | null
  authStatus?: SocialDistributionAccountAuthStatus
  onCheckAuth?: () => void
}) {
  const { xFormat, xRows, xLimit, xHasOverLimit, combined, canPublishX } = buildXDraftView(task)
  const browserCommand = task ? `python scripts/social/browser_publish_task.py --task-id ${task.id} --platform ${task.platform}` : ''
  const taskIsLive = task?.status === 'live'
  const publishedUrl = task?.published_url?.trim() ?? ''
  const liveMissingUrl = taskIsLive && !publishedUrl
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
          <section className="grid gap-3 md:grid-cols-3">
            <InfoBlock title="当前状态">
              {task.status}
              {task.failure_summary ? ` · ${task.failure_summary}` : ''}
            </InfoBlock>
            <InfoBlock title="发布路径">
              {authStatus
                ? `${publishPathLabel(authStatus.publish_path)} · API: ${authStatus.api_status} · Browser: ${authStatus.browser_status}`
                : '尚未检查登录/API 状态。'}
            </InfoBlock>
            <InfoBlock title="发布证据">
              {publishedUrl ? publishedUrl : liveMissingUrl ? '已发布但缺少 URL，请补录。' : '尚未记录 published URL。'}
            </InfoBlock>
          </section>
          <PublishAuditSummary task={task} />
          <InfoBlock title="下一步">
            {authStatus
              ? authStatus.next_action
              : '点击“检查发布状态”后，系统会给出 API / 浏览器辅助 / 人工发布建议。'}
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
            {publishedUrl ? (
              <a
                className="rounded-xl border border-emerald-300/50 px-3 py-2 text-sm font-semibold text-emerald-100"
                href={publishedUrl}
                target="_blank"
                rel="noreferrer"
              >
                查看帖子
              </a>
            ) : null}
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
            <button type="button" className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100" onClick={() => copyText(combined, toast)}>{copyCombinedLabel(task.platform, xFormat, xRows.length)}</button>
            <button type="button" className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100" onClick={onCheckAuth}>检查发布状态</button>
            {publishedUrl ? (
              <button type="button" className="rounded-xl border border-amber-300/40 px-3 py-2 text-sm text-amber-100" onClick={onAuditPublishedPage}>检查页面状态</button>
            ) : null}
            {task.platform !== 'x' ? (
              <button type="button" className="rounded-xl border border-amber-300/40 px-3 py-2 text-sm text-amber-100" onClick={() => copyText(browserCommand, toast)}>
                复制浏览器辅助 CLI
              </button>
            ) : null}
          </div>
          {xHasOverLimit ? (
            <InfoBlock title="X 超限">
              {xFormat === 'long_post' ? `X 长文超过 ${xLimit} chars，发布按钮已禁用。` : '有推文超过 280 weighted chars，发布按钮已禁用。'}
            </InfoBlock>
          ) : null}
          {xAuthNotice ? (
            <InfoBlock title="X 授权状态">{xAuthNotice}</InfoBlock>
          ) : null}
          {liveMissingUrl ? (
            <InfoBlock title="Published URL 缺失">
              这个任务已经是 live，但没有帖子地址。请补录真实 published URL 后再次标记，后续指标和查看按钮才有证据来源。
            </InfoBlock>
          ) : null}
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Published URL"><input className={inputClass} value={manualUrl} onChange={(event) => onManualUrlChange(event.target.value)} /></Field>
            <Field label="人工备注 / removed 原因"><input className={inputClass} value={manualNote} onChange={(event) => onManualNoteChange(event.target.value)} /></Field>
          </div>
          <PublishAuditControls
            visible={Boolean(publishedUrl)}
            auditVisibility={auditVisibility}
            auditLayout={auditLayout}
            onAuditVisibilityChange={onAuditVisibilityChange}
            onAuditLayoutChange={onAuditLayoutChange}
          />
          <div className="flex flex-wrap justify-end gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={onSkip}>跳过</button>
            <button type="button" className="rounded-xl border border-rose-300/40 px-3 py-2 text-sm text-rose-100" onClick={onMarkRemoved}>标记 removed</button>
            {task.platform === 'x' && !taskIsLive ? <button type="button" disabled={!canPublishX || publishBusy} className="rounded-xl border border-emerald-300/50 px-4 py-2 text-sm font-semibold text-emerald-100 disabled:opacity-50" onClick={onPublishX}>{publishBusy ? '验证授权中…' : xPublishButtonLabel(xFormat)}</button> : null}
            {!taskIsLive || liveMissingUrl ? <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={onMarkLive}>标记为已发布</button> : null}
          </div>
        </div>
      ) : null}
    </OverlayModal>
  )
}

function publishPathLabel(value: string): string {
  if (value === 'official_api') return '官方 API'
  if (value === 'browser_assisted') return '浏览器辅助'
  if (value === 'blocked') return '已阻断'
  return '人工发布'
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
                      <div className="flex flex-wrap items-center gap-2">
                        <b>{task.account_display_name ?? task.channel_key}</b>
                        <StateBadge tone={statusTone(task.status)}>{task.status}</StateBadge>
                      </div>
                      <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">
                        {task.platform} · {task.channel_key}
                        {task.published_url ? ' · published URL recorded' : ''}
                        {task.failure_summary ? ` · ${task.failure_summary}` : ''}
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {task.published_url ? (
                        <a className="rounded-xl border border-emerald-300/50 px-3 py-2 text-sm text-emerald-100" href={task.published_url} target="_blank" rel="noreferrer">查看帖子</a>
                      ) : null}
                      <button type="button" className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100" onClick={() => onOpenTask(task)}>
                        {task.status === 'live'
                          ? '详情'
                          : task.platform === 'x'
                            ? '发布到 X / 详情'
                            : '复制并打开平台'}
                      </button>
                    </div>
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

function numberArray(value: unknown): number[] {
  return Array.isArray(value) ? value.map((item) => Number(item)).filter((item) => Number.isFinite(item)) : []
}

function stringValue(value: unknown): string {
  if (typeof value === 'number') return String(value)
  return typeof value === 'string' ? value : ''
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
