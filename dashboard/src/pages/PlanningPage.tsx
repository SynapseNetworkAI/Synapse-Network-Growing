import { useEffect, useState } from 'react'
import {
  api,
  DropGoalResult,
  GoalMissionLane,
  PlanningManifest,
  PlanningManifestHistory,
  PlanningMissionControl,
  RequirementCandidate,
} from '../api'

type Goal = {
  goal_key?: string
  domain?: string
  status?: string
  intent?: string
  success_metric?: string
  weight?: number
}

type ActiveTab = 'mission' | 'history' | 'debug'

type SteeringDraft = {
  focusWeights: Record<string, number>
  globalBudget: Record<string, unknown>
  constraintsText: string
}

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function badgeTone(status: string) {
  if (['active', 'approved', 'materialized', 'succeeded', 'released'].includes(status)) return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  if (['pending', 'draft', 'running', 'awaiting_operator'].includes(status)) return 'border-blue-200 bg-blue-50 text-blue-700'
  if (['dropped', 'cancelled', 'suppressed', 'rejected', 'failed', 'blocked'].includes(status)) return 'border-rose-200 bg-rose-50 text-rose-700'
  return 'border-slate-200 bg-slate-50 text-slate-600'
}

function asGoal(value: Record<string, unknown>): Goal {
  return value as Goal
}

function numberValue(value: unknown, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function weightToPercent(value: unknown) {
  const parsed = numberValue(value)
  return parsed <= 1 ? Math.round(parsed * 100) : Math.round(parsed)
}

function constraintsToText(value: unknown[]) {
  return value.map((item) => String(item ?? '').trim()).filter(Boolean).join('\n')
}

function steeringDraftFrom(mission: PlanningMissionControl | null): SteeringDraft {
  const weights: Record<string, number> = {}
  Object.entries(mission?.global_steering.focus_weights || {}).forEach(([key, value]) => {
    weights[key] = weightToPercent(value)
  })
  return {
    focusWeights: weights,
    globalBudget: { ...(mission?.global_steering.global_budget || {}) },
    constraintsText: constraintsToText(mission?.global_steering.global_constraints || []),
  }
}

function weightTotal(weights: Record<string, number>) {
  return Object.values(weights).reduce((sum, value) => sum + numberValue(value), 0)
}

function JsonBlock({ value }: Readonly<{ value: unknown }>) {
  return (
    <pre className="max-h-[420px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-relaxed text-slate-100">
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  )
}

function StatusCounts({ title, counts }: Readonly<{ title: string; counts: Record<string, number> }>) {
  const entries = Object.entries(counts || {}).filter(([, value]) => value > 0)
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">{title}</div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {entries.length ? entries.map(([key, value]) => (
          <span key={key} className={['rounded-full border px-2 py-1 text-[11px] font-medium', badgeTone(key)].join(' ')}>
            {key}: {value}
          </span>
        )) : <span className="text-xs text-[color:var(--ops-text-muted)]">none</span>}
      </div>
    </div>
  )
}

function GoalRollupStrip({ lane }: Readonly<{ lane: GoalMissionLane }>) {
  return (
    <div className="grid gap-4 border-y border-[color:var(--ops-stroke-soft)] py-4 md:grid-cols-4">
      <StatusCounts title="Candidates" counts={lane.rollup.candidate_status_counts} />
      <StatusCounts title="Requirements" counts={lane.rollup.requirement_status_counts} />
      <StatusCounts title="Workflows" counts={lane.rollup.workflow_status_counts} />
      <StatusCounts title="Releases" counts={lane.rollup.release_status_counts} />
    </div>
  )
}

function CandidateActions({
  candidate,
  busy,
  onAction,
}: Readonly<{
  candidate: RequirementCandidate
  busy: string | null
  onAction: (candidate: RequirementCandidate, action: 'approve' | 'reject' | 'materialize') => void
}>) {
  const busyForCandidate = busy?.endsWith(`:${candidate.id}`)
  return (
    <div className="flex flex-wrap gap-2">
      {candidate.status === 'pending' && (
        <button className="rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-700" disabled={busyForCandidate} onClick={() => onAction(candidate, 'approve')}>Approve</button>
      )}
      {candidate.status === 'approved' && (
        <button className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700" disabled={busyForCandidate} onClick={() => onAction(candidate, 'materialize')}>Materialize Requirement</button>
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

function CandidateMiniQueue({
  candidates,
  busy,
  onAction,
}: Readonly<{
  candidates: RequirementCandidate[]
  busy: string | null
  onAction: (candidate: RequirementCandidate, action: 'approve' | 'reject' | 'materialize') => void
}>) {
  const active = candidates.filter((candidate) => ['pending', 'approved', 'materialized'].includes(candidate.status))
  const quiet = candidates.filter((candidate) => !['pending', 'approved', 'materialized'].includes(candidate.status))
  return (
    <div className="space-y-3" data-testid="candidate-mini-queue">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Candidate Ammunition</div>
          <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">Planner proposals for this exact goal.</div>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">{candidates.length} total</span>
      </div>
      {active.map((candidate) => (
        <article key={candidate.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white px-4 py-3" data-testid="goal-candidate-card">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{candidate.title}</div>
              <div className="mt-1 font-mono text-[11px] text-[color:var(--ops-text-caption)]">{candidate.workflow_key || 'workflow TBD'} · confidence {Math.round((candidate.confidence || 0) * 100)}%</div>
            </div>
            <span className={['rounded-full border px-2.5 py-1 text-[11px] font-medium', badgeTone(candidate.status)].join(' ')}>{candidate.status}</span>
          </div>
          <p className="mt-2 line-clamp-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{candidate.description_markdown || candidate.rationale || 'No description yet.'}</p>
          <div className="mt-3"><CandidateActions candidate={candidate} busy={busy} onAction={onAction} /></div>
        </article>
      ))}
      {!active.length && <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] px-4 py-5 text-sm text-[color:var(--ops-text-muted)]">No active proposals for this goal. Run Planner Sweep when capacity is available.</div>}
      {quiet.length > 0 && (
        <details className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-50 px-4 py-3">
          <summary className="cursor-pointer text-sm font-medium text-[color:var(--ops-text-body)]">Show rejected / suppressed ({quiet.length})</summary>
          <div className="mt-3 space-y-2">
            {quiet.map((candidate) => (
              <div key={candidate.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-[color:var(--ops-stroke-soft)] pt-2 text-sm">
                <span className="text-[color:var(--ops-text-body)]">{candidate.title}</span>
                <span className={['rounded-full border px-2 py-1 text-[11px]', badgeTone(candidate.status)].join(' ')}>{candidate.status}{candidate.suppression_reason ? ` · ${candidate.suppression_reason}` : ''}</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}

function GoalMissionLane({
  lane,
  busy,
  onCandidateAction,
  onDropGoal,
}: Readonly<{
  lane: GoalMissionLane
  busy: string | null
  onCandidateAction: (candidate: RequirementCandidate, action: 'approve' | 'reject' | 'materialize') => void
  onDropGoal: (goal: Goal) => void
}>) {
  const goal = asGoal(lane.goal)
  const status = goal.status || 'active'
  return (
    <section className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-white p-5 shadow-sm" data-testid="goal-mission-lane">
      <div className="grid gap-5 xl:grid-cols-[0.75fr_1.25fr]">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={['rounded-full border px-3 py-1 text-xs font-medium', badgeTone(status)].join(' ')}>{status}</span>
            <span className="font-mono text-xs text-[color:var(--ops-text-caption)]">{goal.goal_key || lane.goal_key}</span>
          </div>
          <h3 className="mt-3 text-xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">{goal.domain || 'operations'}</h3>
          <p className="mt-3 text-sm leading-6 text-[color:var(--ops-text-body)]">{goal.intent || 'No intent defined.'}</p>
          <div className="mt-4 rounded-2xl bg-slate-50 px-4 py-3 text-sm text-[color:var(--ops-text-muted)]">
            <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Success Metric</div>
            <div className="mt-1">{goal.success_metric || '-'}</div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-[color:var(--ops-text-muted)]">
            <span>Weight: {goal.weight != null ? `${weightToPercent(goal.weight)}%` : '-'}</span>
            {status === 'dropped' ? <span className="text-rose-700">Delivered artifacts retained.</span> : null}
          </div>
          {status !== 'dropped' && (
            <button className="mt-4 rounded-xl border border-rose-200 bg-white px-3 py-2 text-xs font-medium text-rose-700" onClick={() => onDropGoal(goal)}>Drop Goal</button>
          )}
        </div>
        <div className="space-y-4">
          <GoalRollupStrip lane={lane} />
          <CandidateMiniQueue candidates={lane.candidates} busy={busy} onAction={onCandidateAction} />
        </div>
      </div>
    </section>
  )
}

function FocusWeightSliders({ draft, onChange }: Readonly<{ draft: SteeringDraft; onChange: (draft: SteeringDraft) => void }>) {
  const entries = Object.entries(draft.focusWeights)
  const total = weightTotal(draft.focusWeights)
  return (
    <div data-testid="focus-weight-sliders">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Focus Weights</div>
          <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">Total must equal 100% before saving.</div>
        </div>
        <span className={['rounded-full border px-3 py-1 text-xs font-medium', Math.abs(total - 100) <= 0.01 ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-700'].join(' ')}>{total}%</span>
      </div>
      <div className="mt-4 space-y-3">
        {entries.length ? entries.map(([key, value]) => (
          <label key={key} className="block">
            <div className="mb-1 flex justify-between text-sm">
              <span className="font-medium text-[color:var(--ops-text-body)]">{key}</span>
              <span className="font-mono text-[color:var(--ops-text-muted)]">{value}%</span>
            </div>
            <input
              aria-label={`Weight ${key}`}
              className="w-full accent-blue-600"
              min={0}
              max={100}
              step={1}
              type="range"
              value={value}
              onChange={(event) => onChange({ ...draft, focusWeights: { ...draft.focusWeights, [key]: Number(event.target.value) } })}
            />
          </label>
        )) : <div className="text-sm text-[color:var(--ops-text-muted)]">No focus weights configured.</div>}
      </div>
    </div>
  )
}

function GlobalBudgetEditor({ draft, onChange }: Readonly<{ draft: SteeringDraft; onChange: (draft: SteeringDraft) => void }>) {
  const entries = Object.entries(draft.globalBudget)
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Global Budget</div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {entries.length ? entries.map(([key, value]) => {
          const numeric = typeof value === 'number' || !Number.isNaN(Number(value))
          return (
            <label key={key} className="block rounded-2xl border border-[color:var(--ops-stroke-soft)] px-3 py-2">
              <span className="font-mono text-[10px] text-[color:var(--ops-text-caption)]">{key}</span>
              <input
                className="mt-1 w-full bg-transparent text-sm font-semibold text-[color:var(--ops-text-title)] outline-none"
                type={numeric ? 'number' : 'text'}
                value={String(value ?? '')}
                onChange={(event) => onChange({
                  ...draft,
                  globalBudget: {
                    ...draft.globalBudget,
                    [key]: numeric ? Number(event.target.value) : event.target.value,
                  },
                })}
              />
            </label>
          )
        }) : <div className="text-sm text-[color:var(--ops-text-muted)]">No budget fields configured.</div>}
      </div>
    </div>
  )
}

function GlobalConstraintsEditor({ draft, onChange }: Readonly<{ draft: SteeringDraft; onChange: (draft: SteeringDraft) => void }>) {
  return (
    <label className="block">
      <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Global Constraints</div>
      <textarea
        className="mt-3 h-28 w-full rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white px-3 py-2 text-sm leading-6 text-[color:var(--ops-text-body)]"
        value={draft.constraintsText}
        onChange={(event) => onChange({ ...draft, constraintsText: event.target.value })}
        placeholder="One constraint per line"
      />
    </label>
  )
}

function PlanningSteeringPanel({
  mission,
  draft,
  busy,
  onDraftChange,
  onSave,
  onRefresh,
  onRunSweep,
  onOpenRaw,
  onOpenArchive,
}: Readonly<{
  mission: PlanningMissionControl | null
  draft: SteeringDraft
  busy: string | null
  onDraftChange: (draft: SteeringDraft) => void
  onSave: () => void
  onRefresh: () => void
  onRunSweep: (dryRun: boolean) => void
  onOpenRaw: () => void
  onOpenArchive: () => void
}>) {
  const manifest = mission?.manifest
  const total = weightTotal(draft.focusWeights)
  const canSave = Math.abs(total - 100) <= 0.01
  return (
    <section className="rounded-[32px] border border-[color:var(--ops-stroke-soft)] bg-white p-5 shadow-sm" data-testid="planning-steering-panel">
      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Planning Mission Control</div>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">经营规划</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[color:var(--ops-text-muted)]">唯一活跃 Manifest 控制预算、目标和 Planner 输出。候选需求必须回到所属 Goal 上下文里审批。</p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onRefresh}>刷新</button>
            <button className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700" disabled={busy === 'dry_sweep'} onClick={() => onRunSweep(true)}>Dry Run Planner</button>
            <button className="rounded-xl bg-[color:var(--ops-accent)] px-4 py-2 text-sm font-semibold text-white" disabled={busy === 'sweep'} onClick={() => onRunSweep(false)}>Run Planner Sweep</button>
            <button className="rounded-xl border border-slate-200 px-4 py-2 text-sm" onClick={onOpenArchive}>Archive & Start New Cycle</button>
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Version</div>
              <div className="mt-1 text-sm font-semibold text-[color:var(--ops-text-title)]">{manifest?.version_name || '-'}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Revision</div>
              <div className="mt-1 text-sm font-semibold text-[color:var(--ops-text-title)]">{manifest?.revision ?? '-'}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Cycle</div>
              <div className="mt-1 text-sm font-semibold text-[color:var(--ops-text-title)]">{manifest?.cycle_label || '-'}</div>
            </div>
          </div>
        </div>
        <div className="space-y-5 border-t border-[color:var(--ops-stroke-soft)] pt-5 xl:border-l xl:border-t-0 xl:pl-6 xl:pt-0">
          <FocusWeightSliders draft={draft} onChange={onDraftChange} />
          <GlobalBudgetEditor draft={draft} onChange={onDraftChange} />
          <GlobalConstraintsEditor draft={draft} onChange={onDraftChange} />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button className="rounded-xl border border-slate-200 px-4 py-2 text-sm" onClick={onOpenRaw}>{'</>'} Edit raw JSON</button>
            <button className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50" disabled={!canSave || busy === 'save'} onClick={onSave}>Save Steering Revision</button>
          </div>
          {!canSave && <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800" data-testid="weight-total-warning">Focus weights total must equal 100% before saving.</div>}
        </div>
      </div>
    </section>
  )
}

function ManifestHistoryPanel({
  history,
  historySearch,
  setHistorySearch,
  setHistoryPage,
  loadHistory,
}: Readonly<{
  history: PlanningManifestHistory | null
  historySearch: string
  setHistorySearch: (value: string) => void
  setHistoryPage: (value: number) => void
  loadHistory: (page: number) => void
}>) {
  return (
    <section className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-white p-5" data-testid="manifest-history-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">History & Archive</div>
          <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">Manifest history</h3>
        </div>
        <div className="flex gap-2">
          <input className="rounded-xl border px-3 py-2 text-sm" placeholder="Search goal / version" value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} />
          <button className="rounded-xl border px-3 py-2 text-sm" onClick={() => { setHistoryPage(1); loadHistory(1) }}>搜索</button>
        </div>
      </div>
      <div className="mt-4 overflow-hidden rounded-2xl border border-[color:var(--ops-stroke-soft)]">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">
            <tr>
              <th className="px-4 py-3">Cycle</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Goals</th>
              <th className="px-4 py-3">Updated</th>
            </tr>
          </thead>
          <tbody>
            {(history?.items || []).map((item) => (
              <tr key={item.id} className="border-t border-[color:var(--ops-stroke-soft)]">
                <td className="px-4 py-3">
                  <div className="font-medium text-[color:var(--ops-text-title)]">{item.version_name || item.manifest_key}</div>
                  <div className="font-mono text-xs text-[color:var(--ops-text-caption)]">{item.cycle_label}</div>
                </td>
                <td className="px-4 py-3"><span className={['rounded-full border px-3 py-1 text-xs', badgeTone(item.status)].join(' ')}>{item.status}</span></td>
                <td className="px-4 py-3 text-[color:var(--ops-text-muted)]">{item.active_goal_count} active · {item.dropped_goal_count} dropped</td>
                <td className="px-4 py-3 text-[color:var(--ops-text-muted)]">{formatTime(item.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center justify-between text-sm text-[color:var(--ops-text-muted)]">
        <span>Page {history?.page || 1} / {history?.total_pages || 1} · total {history?.total || 0}</span>
        <div className="flex gap-2">
          <button className="rounded-lg border px-3 py-1" disabled={(history?.page || 1) <= 1} onClick={() => { const page = Math.max(1, (history?.page || 1) - 1); setHistoryPage(page); loadHistory(page) }}>Prev</button>
          <button className="rounded-lg border px-3 py-1" disabled={(history?.page || 1) >= (history?.total_pages || 1)} onClick={() => { const page = (history?.page || 1) + 1; setHistoryPage(page); loadHistory(page) }}>Next</button>
        </div>
      </div>
    </section>
  )
}

function RawManifestDrawer({
  open,
  manifest,
  rawDraft,
  setRawDraft,
  rawError,
  onClose,
  onSave,
}: Readonly<{
  open: boolean
  manifest: PlanningManifest | null
  rawDraft: string
  setRawDraft: (value: string) => void
  rawError: string | null
  onClose: () => void
  onSave: () => void
}>) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/40" data-testid="raw-manifest-drawer">
      <aside className="h-full w-full max-w-2xl overflow-auto bg-white p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Debug Drawer</div>
            <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">Raw Manifest JSON</h3>
            <p className="mt-1 text-sm text-[color:var(--ops-text-muted)]">Use this only for fields not covered by the steering form.</p>
          </div>
          <button className="rounded-xl border px-3 py-2 text-sm" onClick={onClose}>Close</button>
        </div>
        <textarea className="mt-5 h-[65vh] w-full rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-100" value={rawDraft || JSON.stringify(manifest?.payload || {}, null, 2)} onChange={(event) => setRawDraft(event.target.value)} spellCheck={false} />
        {rawError && <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{rawError}</div>}
        <button className="mt-4 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white" onClick={onSave}>Save raw JSON</button>
      </aside>
    </div>
  )
}

function ArchiveCycleModal({
  open,
  mission,
  busy,
  onClose,
  onArchive,
}: Readonly<{
  open: boolean
  mission: PlanningMissionControl | null
  busy: string | null
  onClose: () => void
  onArchive: (versionName: string, cycleLabel: string) => void
}>) {
  const [versionName, setVersionName] = useState('')
  const [cycleLabel, setCycleLabel] = useState('')
  useEffect(() => {
    if (open) {
      setVersionName(`Next cycle after ${mission?.manifest.cycle_label || 'current'}`)
      setCycleLabel('')
    }
  }, [open, mission?.manifest.cycle_label])
  if (!open) return null
  const activeGoals = (mission?.goal_lanes || []).filter((lane) => asGoal(lane.goal).status !== 'dropped' && asGoal(lane.goal).status !== 'achieved')
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
      <div className="w-full max-w-2xl rounded-[28px] bg-white p-6 shadow-2xl">
        <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Archive Cycle</div>
        <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">Archive & Start New Cycle</h3>
        <p className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">Active goals will carry forward. Achieved and dropped goals stay in the archived review.</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="block text-sm font-medium text-[color:var(--ops-text-title)]">Version name<input className="mt-2 w-full rounded-xl border px-3 py-2 text-sm" value={versionName} onChange={(event) => setVersionName(event.target.value)} /></label>
          <label className="block text-sm font-medium text-[color:var(--ops-text-title)]">Cycle label<input className="mt-2 w-full rounded-xl border px-3 py-2 text-sm" placeholder="2026-W17" value={cycleLabel} onChange={(event) => setCycleLabel(event.target.value)} /></label>
        </div>
        <div className="mt-4 rounded-2xl bg-slate-50 px-4 py-3 text-sm text-[color:var(--ops-text-muted)]">Carry forward: {activeGoals.map((lane) => lane.goal_key).join(', ') || 'none'}</div>
        <div className="mt-5 flex justify-end gap-2">
          <button className="rounded-xl border px-4 py-2 text-sm" onClick={onClose}>Cancel</button>
          <button className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white" disabled={!versionName.trim() || !cycleLabel.trim() || busy === 'archive'} onClick={() => onArchive(versionName, cycleLabel)}>Archive Current Cycle</button>
        </div>
      </div>
    </div>
  )
}

function DropGoalModal({
  goal,
  reason,
  busy,
  setReason,
  onCancel,
  onConfirm,
}: Readonly<{
  goal: Goal | null
  reason: string
  busy: string | null
  setReason: (value: string) => void
  onCancel: () => void
  onConfirm: () => void
}>) {
  if (!goal) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
      <div className="w-full max-w-xl rounded-[28px] bg-white p-6 shadow-2xl">
        <div className="text-[11px] uppercase tracking-[0.22em] text-rose-600">Danger Zone</div>
        <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">Drop Goal: {goal.goal_key}</h3>
        <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
          会 suppress pending candidates、cancel 未开始 requirements、pause / human-gate running workflows，并保留已发布产物。不会自动 rollback / revert / 删除数据库 / 撤回已发布内容。
        </div>
        <label className="mt-4 block text-sm font-medium text-[color:var(--ops-text-title)]">Reason required</label>
        <textarea className="mt-2 h-28 w-full rounded-2xl border border-[color:var(--ops-stroke-soft)] p-3 text-sm" value={reason} onChange={(event) => setReason(event.target.value)} />
        <div className="mt-5 flex justify-end gap-2">
          <button className="rounded-xl border px-4 py-2 text-sm" onClick={onCancel}>Cancel</button>
          <button className="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white" disabled={!reason.trim() || busy === 'drop'} onClick={onConfirm}>Confirm Safe Halt</button>
        </div>
      </div>
    </div>
  )
}

export default function PlanningPage() {
  const [mission, setMission] = useState<PlanningMissionControl | null>(null)
  const [history, setHistory] = useState<PlanningManifestHistory | null>(null)
  const [historyPage, setHistoryPage] = useState(1)
  const [historySearch, setHistorySearch] = useState('')
  const [activeTab, setActiveTab] = useState<ActiveTab>('mission')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [steeringDraft, setSteeringDraft] = useState<SteeringDraft>({ focusWeights: {}, globalBudget: {}, constraintsText: '' })
  const [rawOpen, setRawOpen] = useState(false)
  const [rawDraft, setRawDraft] = useState('')
  const [rawError, setRawError] = useState<string | null>(null)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [dropGoal, setDropGoal] = useState<Goal | null>(null)
  const [dropReason, setDropReason] = useState('')
  const [dropResult, setDropResult] = useState<DropGoalResult | null>(null)

  const candidateTotals = mission?.candidate_totals || {}
  const pendingActions = numberValue(candidateTotals.pending) + numberValue(candidateTotals.approved)

  async function load(nextPage = historyPage) {
    setLoading(true)
    setError(null)
    try {
      const [nextMission, nextHistory] = await Promise.all([
        api.getPlanningMissionControl(),
        api.getPlanningManifestHistory({ page: nextPage, page_size: 10, search: historySearch || undefined }),
      ])
      setMission(nextMission)
      setHistory(nextHistory)
      setSteeringDraft(steeringDraftFrom(nextMission))
      setRawDraft(JSON.stringify(nextMission.manifest.payload, null, 2))
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载 Planning 数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(1).catch(() => {})
  }, [])

  function buildPayloadFromSteering() {
    const payload = { ...(mission?.manifest.payload || {}) }
    const nextWeights: Record<string, number> = {}
    Object.entries(steeringDraft.focusWeights).forEach(([key, value]) => {
      nextWeights[key] = Math.round((numberValue(value) / 100) * 10000) / 10000
    })
    payload.focus_weights = nextWeights
    payload.global_budget = { ...steeringDraft.globalBudget }
    payload.global_constraints = steeringDraft.constraintsText.split('\n').map((line) => line.trim()).filter(Boolean)
    return payload
  }

  async function savePayload(payload: Record<string, unknown>, source: 'steering' | 'raw') {
    if (!mission) return
    setBusy(source === 'raw' ? 'save_raw' : 'save')
    setError(null)
    try {
      const next = await api.saveActivePlanningManifest({
        version_name: mission.manifest.version_name,
        cycle_label: mission.manifest.cycle_label,
        payload,
        operator: 'operator',
      })
      const nextMission = await api.getPlanningMissionControl()
      setMission({ ...nextMission, manifest: next })
      setSteeringDraft(steeringDraftFrom({ ...nextMission, manifest: next }))
      setRawDraft(JSON.stringify(next.payload, null, 2))
      setRawOpen(false)
      await load(historyPage)
    } catch (err) {
      if (source === 'raw') setRawError(err instanceof Error ? err.message : '保存 raw JSON 失败')
      else setError(err instanceof Error ? err.message : '保存 Manifest 失败')
    } finally {
      setBusy(null)
    }
  }

  async function saveSteering() {
    await savePayload(buildPayloadFromSteering(), 'steering')
  }

  async function saveRaw() {
    setRawError(null)
    try {
      const payload = JSON.parse(rawDraft) as Record<string, unknown>
      await savePayload(payload, 'raw')
    } catch (err) {
      setRawError(err instanceof Error ? err.message : 'Raw Manifest JSON 格式错误')
    }
  }

  async function runSweep(dryRun: boolean) {
    setBusy(dryRun ? 'dry_sweep' : 'sweep')
    setError(null)
    try {
      await api.runPlannerSweep({ dry_run: dryRun, triggered_by: 'operator' })
      await load(historyPage)
    } catch (err) {
      setError(err instanceof Error ? err.message : '运行 Planner Sweep 失败')
    } finally {
      setBusy(null)
    }
  }

  async function archiveCycle(versionName: string, cycleLabel: string) {
    if (!mission) return
    setBusy('archive')
    setError(null)
    try {
      await api.archiveAndStartPlanningCycle(mission.manifest.id, { version_name: versionName, cycle_label: cycleLabel, operator: 'operator', payload_patch: {} })
      setArchiveOpen(false)
      await load(1)
      setHistoryPage(1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Archive cycle failed')
    } finally {
      setBusy(null)
    }
  }

  async function confirmDropGoal() {
    if (!mission || !dropGoal?.goal_key) return
    setBusy('drop')
    setError(null)
    try {
      const result = await api.dropPlanningGoal(mission.manifest.id, dropGoal.goal_key, {
        reason: dropReason,
        operator: 'operator',
        halt_mode: 'safe_halt',
      })
      setDropResult(result)
      setDropGoal(null)
      setDropReason('')
      await load(historyPage)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Drop Goal 失败')
    } finally {
      setBusy(null)
    }
  }

  async function actOnCandidate(candidate: RequirementCandidate, action: 'approve' | 'reject' | 'materialize') {
    setBusy(`${action}:${candidate.id}`)
    setError(null)
    try {
      if (action === 'approve') await api.approveRequirementCandidate(candidate.id, { operator: 'operator' })
      if (action === 'reject') await api.rejectRequirementCandidate(candidate.id, { operator: 'operator', reason: 'operator_rejected' })
      if (action === 'materialize') await api.materializeRequirementCandidate(candidate.id, { operator: 'operator' })
      await load(historyPage)
    } catch (err) {
      setError(err instanceof Error ? err.message : `${action} candidate failed`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-5" data-testid="planning-page">
      {error && <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      <PlanningSteeringPanel
        mission={mission}
        draft={steeringDraft}
        busy={busy}
        onDraftChange={setSteeringDraft}
        onSave={saveSteering}
        onRefresh={() => load(historyPage).catch(() => {})}
        onRunSweep={runSweep}
        onOpenRaw={() => setRawOpen(true)}
        onOpenArchive={() => setArchiveOpen(true)}
      />

      <nav className="flex flex-wrap gap-2 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white p-2" data-testid="planning-tabs">
        {([
          ['mission', `Mission Control · ${pendingActions} actions`],
          ['history', `History · ${history?.total || mission?.history_preview.total || 0}`],
          ['debug', 'Debug'],
        ] as Array<[ActiveTab, string]>).map(([key, label]) => (
          <button key={key} className={['rounded-xl px-4 py-2 text-sm font-medium transition', activeTab === key ? 'bg-slate-900 text-white' : 'text-[color:var(--ops-text-muted)] hover:bg-slate-100'].join(' ')} onClick={() => setActiveTab(key)}>{label}</button>
        ))}
      </nav>

      {dropResult && (
        <section className="rounded-[28px] border border-amber-200 bg-amber-50 p-5">
          <div className="text-[11px] uppercase tracking-[0.22em] text-amber-700">Halt Summary</div>
          <div className="mt-2 text-lg font-semibold text-amber-950">Goal `{dropResult.goal_key}` 已停止未来投入</div>
          <p className="mt-2 text-sm text-amber-800">已发布产物保留；如需下线，请创建新的 decommission requirement，不会自动 rollback。</p>
          <div className="mt-4 grid gap-3 md:grid-cols-5">
            {Object.entries(dropResult.halt_summary).map(([key, value]) => (
              <div key={key} className="rounded-2xl bg-white/70 p-3">
                <div className="font-mono text-[10px] text-amber-700">{key}</div>
                <div className="mt-1 text-lg font-semibold text-amber-950">{String(value)}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === 'mission' && (
        <main className="space-y-4" data-testid="mission-control-tab">
          <div className="grid gap-3 md:grid-cols-5">
            {['pending', 'approved', 'materialized', 'rejected', 'suppressed'].map((status) => (
              <div key={status} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white px-4 py-3">
                <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">{status}</div>
                <div className="mt-1 text-2xl font-semibold text-[color:var(--ops-text-title)]">{candidateTotals[status] || 0}</div>
              </div>
            ))}
          </div>
          {(mission?.goal_lanes || []).map((lane) => (
            <GoalMissionLane key={lane.goal_key} lane={lane} busy={busy} onCandidateAction={actOnCandidate} onDropGoal={setDropGoal} />
          ))}
          {!mission?.goal_lanes.length && <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] bg-white px-5 py-8 text-sm text-[color:var(--ops-text-muted)]">No goals in the active manifest.</div>}
        </main>
      )}

      {activeTab === 'history' && (
        <ManifestHistoryPanel history={history} historySearch={historySearch} setHistorySearch={setHistorySearch} setHistoryPage={setHistoryPage} loadHistory={(page) => load(page).catch(() => {})} />
      )}

      {activeTab === 'debug' && (
        <section className="grid gap-5 xl:grid-cols-2" data-testid="planning-debug-tab">
          <div className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-white p-5">
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Raw Manifest</div>
            <div className="mt-4"><JsonBlock value={mission?.manifest.payload} /></div>
          </div>
          <div className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-white p-5">
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Last Sweep</div>
            <div className="mt-4"><JsonBlock value={mission?.last_sweep} /></div>
          </div>
        </section>
      )}

      <RawManifestDrawer open={rawOpen} manifest={mission?.manifest || null} rawDraft={rawDraft} setRawDraft={setRawDraft} rawError={rawError} onClose={() => setRawOpen(false)} onSave={saveRaw} />
      <ArchiveCycleModal open={archiveOpen} mission={mission} busy={busy} onClose={() => setArchiveOpen(false)} onArchive={archiveCycle} />
      <DropGoalModal goal={dropGoal} reason={dropReason} busy={busy} setReason={setDropReason} onCancel={() => setDropGoal(null)} onConfirm={confirmDropGoal} />
      {loading && <div className="text-sm text-[color:var(--ops-text-muted)]">Loading planning control plane...</div>}
    </div>
  )
}
