import type { ReactNode } from 'react'
import { BugDetail } from '../../api'
import { EmptyPane, OverlayModal, StateBadge } from '../../components/workbench'

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function statusTone(value: string) {
  if (['closed', 'verified'].includes(value)) return 'delivered'
  if (['fixing', 'fixed_pending_verification'].includes(value)) return 'validating'
  if (['open', 'ready_for_agent', 'reopened', 'triaged'].includes(value)) return 'running'
  if (['wontfix', 'duplicate', 'failed'].includes(value)) return 'blocked'
  return 'muted'
}

function shortSha(value: string | null) {
  return value ? value.slice(0, 10) : '-'
}

function verificationCommandLabel(item: Record<string, unknown>) {
  return String(item.command || item.cmd || 'validation command')
}

function verificationCommandStatus(item: Record<string, unknown>) {
  return String(item.status || item.result || 'unknown')
}

function closeRequirements(detail: BugDetail | null) {
  const attempt = detail?.latest_fix_attempt
  const bug = detail?.bug
  const missing: string[] = []
  if (!attempt || attempt.status !== 'verified') missing.push('需要 verified fix attempt')
  if (!attempt?.verification_commands?.length) missing.push('需要验证命令证据')
  if (!attempt?.commit_sha && !attempt?.pr_url) missing.push('需要 commit 或 PR')
  const requiresScreenshot = Boolean(
    bug &&
      `${bug.title} ${bug.summary} ${JSON.stringify(bug.metadata || {})}`.toLowerCase().match(/frontend|ui|page|screenshot|browser/),
  )
  if (requiresScreenshot && !attempt?.verification_screenshots?.length) missing.push('UI 类 bug 需要截图证据')
  return missing
}

export function BugDetailModal({
  detail,
  busy,
  linkDraft,
  verificationSummary,
  setLinkDraft,
  setVerificationSummary,
  onClose,
  onClaim,
  onClaimAndRun,
  onMaterialize,
  onLinkFix,
  onVerify,
  onCloseBug,
  onReopen,
}: Readonly<{
  detail: BugDetail | null
  busy: boolean
  linkDraft: { branch_name: string; commit_sha: string; pr_url: string }
  verificationSummary: string
  setLinkDraft: (value: { branch_name: string; commit_sha: string; pr_url: string }) => void
  setVerificationSummary: (value: string) => void
  onClose: () => void
  onClaim: () => void
  onClaimAndRun: () => void
  onMaterialize: () => void
  onLinkFix: () => void
  onVerify: () => void
  onCloseBug: () => void
  onReopen: () => void
}>) {
  const bug = detail?.bug
  const latestAttempt = detail?.latest_fix_attempt || null
  const missingClose = closeRequirements(detail)
  const canClose = missingClose.length === 0
  const allowed = new Set(detail?.agent_context.allowed_next_actions || [])

  return (
    <OverlayModal
      open={Boolean(detail)}
      eyebrow="Bug Detail"
      title={bug?.title || 'Bug'}
      description="结构化 bug 上下文、修复尝试、验证证据和事件记录，供 agent 安全接力。"
      actions={
        bug ? (
          <>
            <button type="button" disabled={busy} className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onMaterialize}>创建修复需求</button>
            <button type="button" disabled={busy || !allowed.has('claim')} className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm disabled:opacity-50" onClick={onClaim}>仅领取</button>
            <button type="button" disabled={busy || !allowed.has('claim')} className="rounded-2xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={onClaimAndRun}>Agent 领取并启动修复</button>
          </>
        ) : null
      }
      onClose={onClose}
    >
      {detail ? (
        <div className="max-h-[78vh] space-y-5 overflow-auto px-6 py-5">
          <section className="grid gap-3 md:grid-cols-4">
            <InfoTile label="项目" value={bug?.project_key || '-'} />
            <InfoTile label="状态" value={bug?.status || '-'} />
            <InfoTile label="严重级别" value={bug?.severity || '-'} />
            <InfoTile label="出现次数" value={String(bug?.occurrence_count || 0)} />
          </section>

          <DetailSection title="Summary">
            <p className="text-sm leading-6 text-[color:var(--ops-text-muted)]">{bug?.summary || 'No summary.'}</p>
            <div className="mt-3 grid gap-3 text-sm md:grid-cols-2">
              <Field label="Fingerprint" value={bug?.fingerprint || '-'} />
              <Field label="Source Ref" value={bug?.source_ref || '-'} />
              <Field label="Environment" value={bug?.environment || '-'} />
              <Field label="Requirement" value={bug?.converted_requirement_id ? `#${bug.converted_requirement_id}` : '-'} />
            </div>
          </DetailSection>

          <DetailSection title="Agent Context">
            <div className="grid gap-3 text-sm md:grid-cols-2">
              <Field label="Target Project Path" value={detail.agent_context.target_project_path || '-'} />
              <Field label="Allowed Actions" value={detail.agent_context.allowed_next_actions.join(', ') || '-'} />
            </div>
            {detail.agent_context.acceptance_checks.length ? (
              <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-[color:var(--ops-text-muted)]">
                {detail.agent_context.acceptance_checks.map((item) => <li key={item}>{item}</li>)}
              </ul>
            ) : null}
          </DetailSection>

          <DetailSection title="Evidence">
            <div className="space-y-3">
              {bug?.evidence.length ? bug.evidence.map((item, index) => (
                <pre key={index} className="overflow-auto rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4 text-xs leading-5 text-[color:var(--ops-text-muted)]">{JSON.stringify(item, null, 2)}</pre>
              )) : <EmptyPane>暂无证据。</EmptyPane>}
            </div>
          </DetailSection>

          <DetailSection title="Fix Attempts">
            <div className="grid gap-3 md:grid-cols-3">
              <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="branch name" value={linkDraft.branch_name} onChange={(event) => setLinkDraft({ ...linkDraft, branch_name: event.target.value })} />
              <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="commit sha" value={linkDraft.commit_sha} onChange={(event) => setLinkDraft({ ...linkDraft, commit_sha: event.target.value })} />
              <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="PR URL" value={linkDraft.pr_url} onChange={(event) => setLinkDraft({ ...linkDraft, pr_url: event.target.value })} />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" disabled={busy} className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onLinkFix}>链接修复分支 / Commit</button>
              {latestAttempt?.workflow_run_id ? <a className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" href={`/workflows/${latestAttempt.workflow_run_id}`}>打开 Workflow</a> : null}
              {latestAttempt?.pr_url ? <a className="rounded-xl border border-cyan-300/30 px-4 py-2 text-sm text-cyan-100" href={latestAttempt.pr_url} target="_blank" rel="noreferrer">打开 PR</a> : null}
            </div>
            <div className="mt-4 space-y-2">
              {detail.fix_attempts.map((attempt) => (
                <div key={attempt.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <StateBadge tone={statusTone(attempt.status)}>{attempt.status}</StateBadge>
                    <span>{attempt.agent_id}</span>
                    <span>{attempt.branch_name || '-'}</span>
                    <span>{shortSha(attempt.commit_sha)}</span>
                    {attempt.workflow_run_id ? <span>workflow #{attempt.workflow_run_id}</span> : null}
                  </div>
                  {attempt.verification_summary ? <p className="mt-2 text-[color:var(--ops-text-muted)]">{attempt.verification_summary}</p> : null}
                </div>
              ))}
            </div>
          </DetailSection>

          <DetailSection title="Verification">
            <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <StateBadge tone={canClose ? 'delivered' : 'validating'}>{canClose ? 'Ready to close' : 'Evidence incomplete'}</StateBadge>
                <span className="text-sm text-[color:var(--ops-text-muted)]">
                  {canClose ? '已满足关闭门禁。' : `缺失：${missingClose.join('、')}`}
                </span>
              </div>
            </div>
            <textarea className="mt-3 min-h-24 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" placeholder="验证摘要、截图路径或 artifact URL" value={verificationSummary} onChange={(event) => setVerificationSummary(event.target.value)} />
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" disabled={busy} className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onVerify}>登记验证证据</button>
              <button type="button" disabled={busy || !canClose || !allowed.has('close')} className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={onCloseBug}>关闭 Bug</button>
              <button type="button" disabled={busy} className="rounded-xl border border-red-300/40 px-4 py-2 text-sm text-red-100" onClick={onReopen}>重新打开</button>
            </div>
            {latestAttempt?.verification_commands?.length ? (
              <div className="mt-3 grid gap-2">
                {latestAttempt.verification_commands.map((item, index) => (
                  <div key={index} className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-3 py-3 text-sm">
                    <div className="font-mono text-xs text-[color:var(--ops-text-muted)]">{verificationCommandLabel(item)}</div>
                    <div className="mt-1">status: {verificationCommandStatus(item)}</div>
                  </div>
                ))}
              </div>
            ) : <p className="mt-3 text-sm text-[color:var(--ops-text-muted)]">暂无验证命令证据。</p>}
            {latestAttempt?.verification_screenshots?.length ? (
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {latestAttempt.verification_screenshots.map((item, index) => (
                  <pre key={index} className="overflow-auto rounded-xl border border-[color:var(--ops-stroke-soft)] p-3 text-xs">{JSON.stringify(item, null, 2)}</pre>
                ))}
              </div>
            ) : <p className="mt-3 text-sm text-[color:var(--ops-text-muted)]">暂无截图证据。</p>}
          </DetailSection>

          <DetailSection title="Events">
            <div className="space-y-2">
              {detail.events.map((event) => (
                <div key={event.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] px-4 py-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <b className="text-[color:var(--ops-text-title)]">{event.event_type}</b>
                    <span className="text-xs text-[color:var(--ops-text-caption)]">{formatTime(event.created_at)}</span>
                  </div>
                  <div className="mt-1 text-[color:var(--ops-text-muted)]">
                    {event.actor} · {event.from_status || '-'} {'->'} {event.to_status || '-'}
                  </div>
                </div>
              ))}
              {!detail.events.length ? <EmptyPane>暂无事件。</EmptyPane> : null}
            </div>
          </DetailSection>
        </div>
      ) : <div className="p-6"><EmptyPane>未选择 bug。</EmptyPane></div>}
    </OverlayModal>
  )
}

function InfoTile({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className="mt-2 truncate text-sm font-semibold text-[color:var(--ops-text-title)]">{value}</div>
    </div>
  )
}

function DetailSection({ title, children }: Readonly<{ title: string; children: ReactNode }>) {
  return (
    <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-4 py-4">
      <div className="mb-3 text-[11px] uppercase tracking-[0.2em] text-[color:var(--ops-text-caption)]">{title}</div>
      {children}
    </section>
  )
}

function Field({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className="mt-1 break-words text-[color:var(--ops-text-muted)]">{value}</div>
    </div>
  )
}
