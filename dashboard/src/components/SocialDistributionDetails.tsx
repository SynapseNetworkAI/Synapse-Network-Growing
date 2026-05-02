import type {
  SocialContentAssetDetail,
  SocialDistributionAccount,
  SocialDistributionTask,
} from '../api'
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
  const combined = `Title:\n${task?.platform_title ?? ''}\n\nBody:\n${task?.platform_body ?? ''}`
  const canPublishX =
    task?.platform === 'x' &&
    task.publish_mode === 'api_human_gated' &&
    ['needs_review', 'approved', 'draft_ready', 'failed'].includes(task.status)
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
            <button type="button" className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100" onClick={() => copyText(combined, toast)}>一键复制标题和正文</button>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Published URL"><input className={inputClass} value={manualUrl} onChange={(event) => onManualUrlChange(event.target.value)} /></Field>
            <Field label="人工备注 / removed 原因"><input className={inputClass} value={manualNote} onChange={(event) => onManualNoteChange(event.target.value)} /></Field>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={onSkip}>跳过</button>
            <button type="button" className="rounded-xl border border-rose-300/40 px-3 py-2 text-sm text-rose-100" onClick={onMarkRemoved}>标记 removed</button>
            {canPublishX ? <button type="button" className="rounded-xl border border-emerald-300/50 px-4 py-2 text-sm font-semibold text-emerald-100" onClick={onPublishX}>发布到 X</button> : null}
            <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white" onClick={onMarkLive}>标记已发布</button>
          </div>
        </div>
      ) : null}
    </OverlayModal>
  )
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
  return (
    <div className="space-y-4">
      <InfoBlock title="资产摘要">{asset.summary || asset.body || 'No summary yet.'}</InfoBlock>
      <div className="grid gap-3 md:grid-cols-2">
        <InfoBlock title="推荐渠道">{recommended}</InfoBlock>
        <InfoBlock title="来源信号">{sourceRefs}</InfoBlock>
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
