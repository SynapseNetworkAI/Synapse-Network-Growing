import { useEffect, useRef } from 'react'
import { RequirementCandidate } from '../api'

export type CandidateAction = 'approve' | 'approve_run' | 'reject' | 'materialize' | 'retry_validation'

function formatLocalDateTime(date: Date) {
  const pad = (value: number) => String(value).padStart(2, '0')
  const offsetMinutes = -date.getTimezoneOffset()
  const offsetSign = offsetMinutes >= 0 ? '+' : '-'
  const absoluteOffset = Math.abs(offsetMinutes)
  const offset = `GMT${offsetSign}${pad(Math.floor(absoluteOffset / 60))}:${pad(absoluteOffset % 60)}`
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())} ${offset}`
}

function LocalTime({ value }: Readonly<{ value: string | null | undefined }>) {
  if (!value) return <span>-</span>
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return <span>-</span>
  const utcIso = date.toISOString()
  return <time dateTime={utcIso} title={utcIso}>{formatLocalDateTime(date)}</time>
}

function badgeTone(status: string) {
  if (['active', 'approved', 'materialized', 'succeeded', 'released'].includes(status)) return 'border-emerald-300/30 bg-emerald-300/[0.08] text-emerald-100'
  if (['pending', 'draft', 'running', 'awaiting_operator'].includes(status)) return 'border-blue-300/30 bg-blue-300/[0.08] text-blue-100'
  if (['dropped', 'cancelled', 'suppressed', 'rejected', 'failed', 'blocked', 'validation_failed'].includes(status)) return 'border-rose-300/30 bg-rose-400/[0.10] text-rose-100'
  return 'border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-subtle)] text-[color:var(--ops-text-muted)]'
}

function failClosedReason(candidate: RequirementCandidate) {
  return String(
    candidate.metadata?.planner_agent_error
      || candidate.metadata?.acceptance_validation_error
      || candidate.suppression_reason
      || 'validation failed',
  )
}

function candidateAcceptanceSteps(candidate: RequirementCandidate) {
  const contract = candidate.metadata?.acceptance_contract
  if (!contract || typeof contract !== 'object') return []
  const steps = (contract as { execution_acceptance_steps?: unknown }).execution_acceptance_steps
  return Array.isArray(steps) ? steps : []
}

function useEscape(open: boolean, onClose: () => void) {
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])
  useEffect(() => {
    if (!open) return undefined
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      event.stopPropagation()
      onCloseRef.current()
    }
    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [open])
}

export function CandidateActions({
  candidate,
  busy,
  onAction,
}: Readonly<{
  candidate: RequirementCandidate
  busy: string | null
  onAction: (candidate: RequirementCandidate, action: CandidateAction) => void
}>) {
  const busyForCandidate = busy?.endsWith(`:${candidate.id}`)
  return (
    <div className="flex flex-wrap gap-2">
      {candidate.status === 'pending' && (
        <button className="rounded-xl border border-blue-300 bg-blue-500 px-3 py-2 text-xs font-semibold text-white shadow-[0_0_18px_rgba(59,130,246,0.25)]" disabled={busyForCandidate} onClick={() => onAction(candidate, 'approve_run')}>Approve & Run</button>
      )}
      {candidate.status === 'validation_failed' && (
        <button className="rounded-xl border border-amber-200 bg-amber-300 px-3 py-2 text-xs font-semibold text-slate-950" disabled={busyForCandidate} onClick={() => onAction(candidate, 'retry_validation')}>Retry validation</button>
      )}
      {candidate.status === 'pending' && (
        <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-xs font-medium text-[color:var(--ops-text-body)]" disabled={busyForCandidate} onClick={() => onAction(candidate, 'approve')}>Approve only</button>
      )}
      {candidate.status === 'approved' && (
        <button className="rounded-xl border border-emerald-300 bg-emerald-500 px-3 py-2 text-xs font-semibold text-slate-950" disabled={busyForCandidate} onClick={() => onAction(candidate, 'approve_run')}>Materialize & Run</button>
      )}
      {['pending', 'approved'].includes(candidate.status) && (
        <button className="rounded-xl border border-rose-200 px-3 py-2 text-xs font-medium text-rose-700" disabled={busyForCandidate} onClick={() => onAction(candidate, 'reject')}>Reject</button>
      )}
      {candidate.status === 'materialized' && candidate.materialized_requirement_id && (
        <a className="rounded-xl border px-3 py-2 text-xs font-medium text-[color:var(--ops-text-body)]" href={`/requirements/${candidate.materialized_requirement_id}`}>Requirement #{candidate.materialized_requirement_id}</a>
      )}
    </div>
  )
}

export function RequirementCandidateDetailModal({
  candidate,
  loading,
  error,
  busy,
  onClose,
  onAction,
}: Readonly<{
  candidate: RequirementCandidate | null
  loading: boolean
  error: string | null
  busy: string | null
  onClose: () => void
  onAction: (candidate: RequirementCandidate, action: CandidateAction) => void
}>) {
  const open = Boolean(candidate) || loading || Boolean(error)
  useEscape(open, onClose)
  if (!open) return null
  const steps = candidate ? candidateAcceptanceSteps(candidate) : []
  const failureReason = candidate ? failClosedReason(candidate) : ''
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/72 p-4 backdrop-blur-sm" data-testid="candidate-detail-modal">
      <section className="max-h-[90vh] w-full max-w-5xl overflow-auto rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-bg)] p-6 shadow-[0_32px_110px_rgba(0,0,0,0.55)]" role="dialog" aria-modal="true" aria-label="Requirement candidate detail">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="machine-label text-[color:var(--ops-text-caption)]">Requirement Candidate</div>
            <h3 className="mt-2 max-w-3xl text-2xl font-semibold text-[color:var(--ops-text-title)]">{candidate?.title || 'Loading candidate...'}</h3>
            {candidate ? (
              <p className="mt-2 font-mono text-xs text-[color:var(--ops-text-muted)]">
                #{candidate.id} · {candidate.goal_key || 'goal missing'} · {candidate.project_key || 'project missing'} · {candidate.workflow_key || 'workflow TBD'}
              </p>
            ) : null}
          </div>
          <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm text-[color:var(--ops-text-body)]" onClick={onClose}>关闭</button>
        </div>
        {loading ? <div className="mt-6 h-56 animate-pulse rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]" /> : null}
        {error ? <div className="mt-5 rounded-2xl border border-rose-300/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">{error}</div> : null}
        {candidate ? (
          <div className="mt-6 space-y-5">
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-2xl border border-white/8 bg-white/[0.035] p-4">
                <div className="machine-label text-[color:var(--ops-text-caption)]">Status</div>
                <div className={['mt-2 inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em]', badgeTone(candidate.status)].join(' ')}>{candidate.status}</div>
              </div>
              <div className="rounded-2xl border border-white/8 bg-white/[0.035] p-4">
                <div className="machine-label text-[color:var(--ops-text-caption)]">Project</div>
                <div className="mt-2 text-sm text-[color:var(--ops-text-body)]">{candidate.project_key || '-'}</div>
              </div>
              <div className="rounded-2xl border border-white/8 bg-white/[0.035] p-4">
                <div className="machine-label text-[color:var(--ops-text-caption)]">Workflow</div>
                <div className="mt-2 text-sm text-[color:var(--ops-text-body)]">{candidate.workflow_key || '-'}</div>
              </div>
              <div className="rounded-2xl border border-white/8 bg-white/[0.035] p-4">
                <div className="machine-label text-[color:var(--ops-text-caption)]">Updated</div>
                <div className="mt-2 text-sm text-[color:var(--ops-text-body)]"><LocalTime value={candidate.updated_at} /></div>
              </div>
            </div>
            {candidate.status === 'validation_failed' || candidate.suppression_reason ? (
              <div className="rounded-2xl border border-rose-300/25 bg-rose-400/[0.08] p-4 text-sm leading-6 text-rose-100">
                <div className="font-semibold">Fail-Closed 原因</div>
                <p className="mt-2 whitespace-pre-wrap">{failureReason}</p>
                <p className="mt-3 text-xs text-rose-100/75">这是候选验证拦截，不是 Human Gate。修复 PRD / 项目归属 / 安全命令后重新运行 Planner Sweep，历史失败记录会保留。</p>
              </div>
            ) : null}
            <div className="rounded-2xl border border-white/8 bg-white/[0.035] p-4">
              <div className="machine-label text-[color:var(--ops-text-caption)]">Description</div>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-body)]">{candidate.description_markdown || 'No description provided.'}</p>
              {candidate.rationale ? <p className="mt-4 whitespace-pre-wrap text-xs leading-5 text-[color:var(--ops-text-muted)]">Rationale: {candidate.rationale}</p> : null}
            </div>
            <div className="rounded-2xl border border-white/8 bg-white/[0.035] p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="machine-label text-[color:var(--ops-text-caption)]">Evidence-bound Acceptance</div>
                  <p className="mt-1 text-xs text-[color:var(--ops-text-muted)]">{steps.length} execution acceptance step(s)</p>
                </div>
                <CandidateActions candidate={candidate} busy={busy} onAction={onAction} />
              </div>
              <div className="mt-4 space-y-3">
                {steps.length ? steps.map((step, index) => {
                  const payload = step && typeof step === 'object' ? step as Record<string, unknown> : {}
                  const commands = Array.isArray(payload.required_commands) ? payload.required_commands : []
                  return (
                    <article key={`${String(payload.step_key || payload.title || index)}:${index}`} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-950/25 p-4">
                      <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{index + 1}. {String(payload.title || payload.step_key || 'Acceptance step')}</div>
                      <p className="mt-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">{String(payload.expected_result || '')}</p>
                      {commands.length ? (
                        <div className="mt-3 space-y-2">
                          {commands.map((command, commandIndex) => (
                            <code key={`${String(command)}:${commandIndex}`} className="block overflow-auto rounded-xl border border-white/10 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100">{String(command)}</code>
                          ))}
                        </div>
                      ) : null}
                    </article>
                  )
                }) : (
                  <div className="rounded-xl border border-dashed border-[color:var(--ops-stroke-soft)] px-4 py-5 text-sm text-[color:var(--ops-text-muted)]">No execution acceptance steps recorded.</div>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  )
}
