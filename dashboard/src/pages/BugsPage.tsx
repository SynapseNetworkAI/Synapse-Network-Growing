import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api, BugDetail, BugRecord } from '../api'
import { EmptyPane, OverlayModal, StateBadge, useToast } from '../components/workbench'

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function severityTone(value: string) {
  if (value === 'critical' || value === 'high') return 'blocked'
  if (value === 'normal') return 'running'
  return 'muted'
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

function uniqueValues(items: BugRecord[], key: keyof BugRecord) {
  return Array.from(new Set(items.map((item) => String(item[key] || '')).filter(Boolean))).sort()
}

function metricValue(items: BugRecord[], predicate: (item: BugRecord) => boolean) {
  return items.filter(predicate).length
}

export default function BugsPage() {
  const toast = useToast()
  const [items, setItems] = useState<BugRecord[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [project, setProject] = useState('')
  const [status, setStatus] = useState('')
  const [severity, setSeverity] = useState('')
  const [detail, setDetail] = useState<BugDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [linkDraft, setLinkDraft] = useState({ branch_name: '', commit_sha: '', pr_url: '' })
  const [verificationSummary, setVerificationSummary] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const payload = await api.getBugs({
        q: search || undefined,
        project_key: project || undefined,
        status: status || undefined,
        severity: severity || undefined,
        limit: 100,
      })
      setItems(payload.items)
      setTotal(payload.total)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [])

  const projectOptions = useMemo(() => uniqueValues(items, 'project_key'), [items])
  const statusOptions = useMemo(() => uniqueValues(items, 'status'), [items])
  const severityOptions = useMemo(() => uniqueValues(items, 'severity'), [items])

  const openDetail = async (id: number) => {
    setBusy(true)
    try {
      const payload = await api.getBugDetail(id)
      setDetail(payload)
      setLinkDraft({
        branch_name: payload.latest_fix_attempt?.branch_name || '',
        commit_sha: payload.latest_fix_attempt?.commit_sha || '',
        pr_url: payload.latest_fix_attempt?.pr_url || '',
      })
      setVerificationSummary(payload.latest_fix_attempt?.verification_summary || '')
    } finally {
      setBusy(false)
    }
  }

  const refreshDetail = async () => {
    if (!detail) return
    const payload = await api.getBugDetail(detail.bug.id)
    setDetail(payload)
    await load()
  }

  const runAction = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true)
    try {
      await action()
      toast.success(message)
      await refreshDetail()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5" data-testid="bugs-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Agent Fix Queue</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">Bug List</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
              Agent 原生 bug backlog：记录项目、状态、修复分支、commit、PR 和验证截图，供 agent 读取、领取、修复并回填证据。
            </p>
          </div>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>
            刷新
          </button>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          {[
            ['Open bugs', metricValue(items, (item) => ['open', 'ready_for_agent', 'triaged', 'reopened'].includes(item.status))],
            ['Ready for agent', metricValue(items, (item) => ['open', 'ready_for_agent', 'reopened'].includes(item.status))],
            ['Fixing', metricValue(items, (item) => item.status === 'fixing')],
            ['Pending verification', metricValue(items, (item) => item.status === 'fixed_pending_verification')],
            ['Verified', metricValue(items, (item) => item.status === 'verified' || item.status === 'closed')],
            ['Critical / High', metricValue(items, (item) => ['critical', 'high'].includes(item.severity))],
          ].map(([label, value]) => (
            <div key={label} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div>
              <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{value}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
        <div className="grid gap-3 md:grid-cols-5">
          <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm md:col-span-2" placeholder="搜索 title / fingerprint / summary" value={search} onChange={(event) => setSearch(event.target.value)} />
          <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" value={project} onChange={(event) => setProject(event.target.value)}>
            <option value="">全部项目</option>
            {projectOptions.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">全部状态</option>
            {statusOptions.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <div className="flex gap-2">
            <select className="min-w-0 flex-1 rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" value={severity} onChange={(event) => setSeverity(event.target.value)}>
              <option value="">全部级别</option>
              {severityOptions.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm text-white" onClick={() => load().catch(() => {})}>查询</button>
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
        <div className="border-b border-[color:var(--ops-stroke-soft)] px-5 py-4 text-sm text-[color:var(--ops-text-muted)]">共 {total} 个 bug</div>
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse">
            <thead className="bg-[color:var(--ops-panel-subtle)]">
              <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                <th className="px-5 py-4 font-medium">Bug</th>
                <th className="px-4 py-4 font-medium">项目</th>
                <th className="px-4 py-4 font-medium">级别</th>
                <th className="px-4 py-4 font-medium">状态</th>
                <th className="px-4 py-4 font-medium">来源 / 次数</th>
                <th className="px-4 py-4 font-medium">修复证据</th>
                <th className="px-4 py-4 font-medium">最后出现</th>
                <th className="px-5 py-4 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const latestFix = item.metadata.latest_fix as Record<string, unknown> | undefined
                return (
                  <tr key={item.id} className="border-t border-[color:var(--ops-stroke-soft)] hover:bg-[color:var(--ops-panel-subtle)]">
                    <td className="max-w-md px-5 py-4">
                      <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{item.title}</div>
                      <div className="mt-1 truncate text-xs text-[color:var(--ops-text-caption)]">{item.fingerprint}</div>
                    </td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{item.project_key || '-'}</td>
                    <td className="px-4 py-4"><StateBadge tone={severityTone(item.severity)}>{item.severity}</StateBadge></td>
                    <td className="px-4 py-4"><StateBadge tone={statusTone(item.status)}>{item.status}</StateBadge></td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{item.source_key} · {item.occurrence_count}</td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                      <div>{String(latestFix?.branch_name || '-')}</div>
                      <div className="mt-1 text-xs">commit {shortSha(String(latestFix?.commit_sha || '') || null)}</div>
                    </td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(item.last_seen_at)}</td>
                    <td className="px-5 py-4 text-right">
                      <button type="button" className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white" disabled={busy} onClick={() => openDetail(item.id).catch(() => {})}>详情</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {!loading && items.length === 0 ? <div className="p-6"><EmptyPane>暂无 bug 记录。</EmptyPane></div> : null}
      </section>

      <BugDetailModal
        detail={detail}
        busy={busy}
        linkDraft={linkDraft}
        verificationSummary={verificationSummary}
        setLinkDraft={setLinkDraft}
        setVerificationSummary={setVerificationSummary}
        onClose={() => setDetail(null)}
        onClaim={() => runAction(() => api.claimBug(detail!.bug.id, { agent_id: 'codex' }), 'Agent 已领取 bug')}
        onMaterialize={() => runAction(() => api.materializeBugRequirement(detail!.bug.id), '已创建或绑定修复需求')}
        onLinkFix={() => runAction(() => api.linkBugFix(detail!.bug.id, { agent_id: 'codex', ...linkDraft }), '修复分支和 commit 已记录')}
        onVerify={() => runAction(() => api.addBugVerification(detail!.bug.id, {
          agent_id: 'codex',
          status: 'verified',
          summary: verificationSummary || 'Verified by agent.',
          commands: [{ command: 'manual verification evidence registered', status: 'passed' }],
          screenshots: [],
        }), '验证证据已记录')}
        onCloseBug={() => runAction(() => api.closeBug(detail!.bug.id, { actor: 'codex', resolution: 'verified' }), 'Bug 已关闭')}
        onReopen={() => runAction(() => api.reopenBug(detail!.bug.id, { actor: 'codex', reason: 'Regression or verification failed.' }), 'Bug 已重新打开')}
      />
    </div>
  )
}

function BugDetailModal({
  detail,
  busy,
  linkDraft,
  verificationSummary,
  setLinkDraft,
  setVerificationSummary,
  onClose,
  onClaim,
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
  onMaterialize: () => void
  onLinkFix: () => void
  onVerify: () => void
  onCloseBug: () => void
  onReopen: () => void
}>) {
  const bug = detail?.bug
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
            <button type="button" disabled={busy || bug.status === 'fixing'} className="rounded-2xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={onClaim}>Agent 领取</button>
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
              {detail.latest_fix_attempt?.pr_url ? <a className="rounded-xl border border-cyan-300/30 px-4 py-2 text-sm text-cyan-100" href={detail.latest_fix_attempt.pr_url} target="_blank" rel="noreferrer">打开 PR</a> : null}
            </div>
            <div className="mt-4 space-y-2">
              {detail.fix_attempts.map((attempt) => (
                <div key={attempt.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2"><StateBadge tone={statusTone(attempt.status)}>{attempt.status}</StateBadge><span>{attempt.agent_id}</span><span>{attempt.branch_name || '-'}</span><span>{shortSha(attempt.commit_sha)}</span></div>
                  {attempt.verification_summary ? <p className="mt-2 text-[color:var(--ops-text-muted)]">{attempt.verification_summary}</p> : null}
                </div>
              ))}
            </div>
          </DetailSection>

          <DetailSection title="Verification">
            <textarea className="min-h-24 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" placeholder="验证摘要、截图路径或 artifact URL" value={verificationSummary} onChange={(event) => setVerificationSummary(event.target.value)} />
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" disabled={busy} className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onVerify}>登记验证证据</button>
              <button type="button" disabled={busy} className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white" onClick={onCloseBug}>关闭 Bug</button>
              <button type="button" disabled={busy} className="rounded-xl border border-red-300/40 px-4 py-2 text-sm text-red-100" onClick={onReopen}>重新打开</button>
            </div>
            {detail.latest_fix_attempt?.verification_screenshots.length ? (
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {detail.latest_fix_attempt.verification_screenshots.map((item, index) => (
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
