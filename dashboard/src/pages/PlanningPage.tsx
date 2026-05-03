import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ProductOpportunitiesPanel } from '../components/ProductOpportunitiesPanel'
import { EngineeringQueue, MarkdownTabs, UnassignedQueue } from '../components/PlanningQueues'
import { MissionWorkbenchPanel } from '../components/MissionWorkbenchPanel'
import { PlanningTaskBoardPanel } from '../components/PlanningTaskBoardPanel'
import { CandidateActions, type CandidateAction, RequirementCandidateDetailModal } from '../components/RequirementCandidateDetailModal'
import { useRequirementCandidateDetail } from '../hooks/useRequirementCandidateDetail'
import {
  api,
  DropGoalResult,
  GoalMissionLane,
  MissionBoard,
  MissionWorkbench,
  PlanningTaskBoard,
  PlanningGoal,
  PlanningManifest,
  PlanningManifestHistory,
  PlanningMissionControl,
  PlanningGoalTrace,
  RequirementCandidate,
} from '../api'

type Goal = PlanningGoal

type ActiveTab = 'board' | 'hierarchy' | 'opportunities' | 'goals' | 'engineering' | 'unassigned' | 'history' | 'debug'
type GoalStatusView = 'active' | 'achieved' | 'dropped' | 'all'
type SteeringDraft = {
  focusWeights: Record<string, number>
  globalBudget: Record<string, unknown>
  constraintsText: string
}
type GoalSettingsDraft = {
  goal_key: string
  title: string
  intent_markdown: string
  success_metric: string
  domain: string
  workflow_key: string
  project_key: string
  priority: string
  risk_level: string
  weight: string
  acceptance_kind: string
}

type CachedGoalDetail = {
  goal: PlanningGoal
  cacheKey: string
}

const overlayStack: string[] = []

function initialPlanningTab(search = window.location.search): ActiveTab {
  const params = new URLSearchParams(search)
  const value = params.get('tab')
  if (value === 'workbench' || value === 'hierarchy') return 'hierarchy'
  if (value === 'board') return 'board'
  if (value === 'opportunities' || value === 'goals' || value === 'engineering' || value === 'unassigned' || value === 'history' || value === 'debug') return value
  return 'board'
}

const selectedOpportunityId = (search = window.location.search) => Number(new URLSearchParams(search).get('opportunity') || 0) || null
const selectedBoardColumn = (search = window.location.search) => new URLSearchParams(search).get('column')

function useTopOverlayEscape(open: boolean, overlayId: string, onClose: () => void) {
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])
  useEffect(() => {
    if (!open) return undefined
    overlayStack.push(overlayId)
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || overlayStack[overlayStack.length - 1] !== overlayId) return
      event.preventDefault()
      event.stopPropagation()
      onCloseRef.current()
    }
    window.addEventListener('keydown', onKeyDown, true)
    return () => {
      window.removeEventListener('keydown', onKeyDown, true)
      const index = overlayStack.lastIndexOf(overlayId)
      if (index >= 0) overlayStack.splice(index, 1)
    }
  }, [open, overlayId])
}

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

function candidateAcceptanceStepCount(candidate: RequirementCandidate) {
  const metadata = candidate.metadata || {}
  const contract = metadata.acceptance_contract
  if (!contract || typeof contract !== 'object') return 0
  const steps = (contract as { execution_acceptance_steps?: unknown }).execution_acceptance_steps
  return Array.isArray(steps) ? steps.length : 0
}

function candidateTimestamp(candidate: RequirementCandidate) {
  return candidate.updated_at || candidate.created_at || candidate.approved_at || candidate.rejected_at || ''
}

function sortCandidatesNewestFirst(items: RequirementCandidate[]) {
  return [...items].sort((left, right) => candidateTimestamp(right).localeCompare(candidateTimestamp(left)))
}

function failClosedReason(candidate: RequirementCandidate) {
  return String(
    candidate.metadata?.planner_agent_error
      || candidate.metadata?.acceptance_validation_error
      || candidate.suppression_reason
      || 'validation failed',
  )
}

function interceptSignature(reason: string) {
  return reason
    .toLowerCase()
    .replace(/\d{4}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}(?:\.\d+)?z/g, '<timestamp>')
    .replace(/\d{1,2}\/\d{1,2}\/\d{4},?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]m)?/g, '<timestamp>')
    .replace(/candidate\s*#?\d+/g, 'candidate')
    .replace(/requirement\s*#?\d+/g, 'requirement')
    .replace(/workflow\s*#?\d+/g, 'workflow')
    .replace(/\s+/g, ' ')
    .trim()
}

function groupValidationFailedCandidates(candidates: RequirementCandidate[]) {
  const groups = new Map<string, { signature: string; reason: string; attempts: RequirementCandidate[] }>()
  candidates.forEach((candidate) => {
    const reason = failClosedReason(candidate)
    const signature = interceptSignature(reason)
    const current = groups.get(signature)
    if (current) {
      current.attempts.push(candidate)
      return
    }
    groups.set(signature, { signature, reason, attempts: [candidate] })
  })
  return Array.from(groups.values()).map((group) => {
    const attempts = sortCandidatesNewestFirst(group.attempts)
    return { ...group, reason: failClosedReason(attempts[0]), latest: attempts[0], attempts }
  }).sort((left, right) => candidateTimestamp(right.latest).localeCompare(candidateTimestamp(left.latest)))
}

function interceptNeedsSettings(reason: string) {
  return /workflow|risk|project|setting|unknown workflow|workflow_key/i.test(reason)
}

function workflowOutcomeLabel(candidate: RequirementCandidate) {
  const metadata = candidate.metadata || {}
  const workflowStatus = String(metadata.workflow_status || metadata.auto_run_status || metadata.workflow_current_state || '')
  if (workflowStatus.includes('completed') || workflowStatus.includes('succeeded') || workflowStatus.includes('done')) return 'Workflow Completed'
  if (metadata.auto_started_workflow_run_id || metadata.workflow_run_id || workflowStatus) return 'Workflow Started'
  return 'Requirement Created'
}

function candidateSummaryLabel(groups: {
  actionRequired: RequirementCandidate[]
  materialized: RequirementCandidate[]
  validationFailed: RequirementCandidate[]
}) {
  const parts = [
    groups.actionRequired.length ? `${groups.actionRequired.length} Pending` : '',
    groups.materialized.length ? `${groups.materialized.length} Materialized` : '',
    groups.validationFailed.length ? `${groups.validationFailed.length} Failed` : '',
  ].filter(Boolean)
  return `Candidates${parts.length ? ` (${parts.join(', ')})` : ''}`
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

function goalSettingsDraftFrom(goal?: PlanningGoal | null): GoalSettingsDraft {
  return {
    goal_key: goal?.goal_key || '',
    title: goal?.title || '',
    intent_markdown: goal?.intent_markdown || '',
    success_metric: goal?.success_metric || '',
    domain: goal?.domain || 'ops',
    workflow_key: goal?.workflow_key || 'gateway_reliability_repair',
    project_key: goal?.project_key || 'synapse-network-growing',
    priority: goal?.priority || 'normal',
    risk_level: goal?.risk_level || 'normal',
    weight: goal?.weight != null ? String(goal.weight) : '0.1',
    acceptance_kind: goal?.acceptance_kind || 'business',
  }
}

function slugifyGoalKey(title: string) {
  const slug = title
    .trim()
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 48)
  return slug || `goal_${Date.now().toString(36)}`
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

function GoalCandidateSummary({
  goal,
  candidates,
  busy,
  onAction,
  onEditIntent,
  onEditSettings,
  onTraceGoal,
  onRunSweep,
}: Readonly<{
  goal: PlanningGoal
  candidates: RequirementCandidate[]
  busy: string | null
  onAction: (candidate: RequirementCandidate, action: CandidateAction) => void
  onEditIntent: (goal: PlanningGoal) => void
  onEditSettings: (goal: PlanningGoal) => void
  onTraceGoal: (goal: PlanningGoal) => void
  onRunSweep: () => void
}>) {
  const groups = {
    actionRequired: sortCandidatesNewestFirst(candidates.filter((candidate) => ['pending', 'approved'].includes(candidate.status))),
    materialized: sortCandidatesNewestFirst(candidates.filter((candidate) => candidate.status === 'materialized')),
    validationFailed: sortCandidatesNewestFirst(candidates.filter((candidate) => candidate.status === 'validation_failed')),
    quiet: sortCandidatesNewestFirst(candidates.filter((candidate) => !['pending', 'approved', 'materialized', 'validation_failed'].includes(candidate.status))),
  }
  const interceptGroups = groupValidationFailedCandidates(groups.validationFailed)
  const visibleMaterialized = groups.materialized.slice(0, 2)
  const olderMaterialized = groups.materialized.slice(2)
  return (
    <div className="space-y-4" data-testid="candidate-mini-queue">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Candidates</div>
          <div className="mt-1 text-sm font-semibold text-[color:var(--ops-text-title)]">{candidateSummaryLabel(groups)}</div>
        </div>
        <span className="rounded-full bg-[color:var(--ops-panel-strong)] px-3 py-1 text-xs text-[color:var(--ops-text-muted)]">{candidates.length} total</span>
      </div>

      {groups.actionRequired.length > 0 ? (
        <section className="space-y-2" data-testid="candidate-action-required">
          <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Action Required</div>
          {groups.actionRequired.map((candidate) => (
            <article key={candidate.id} className="rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.045] px-4 py-3" data-testid="goal-candidate-card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-1 text-sm font-semibold text-[color:var(--ops-text-title)]">{candidate.title}</div>
                  <div className="mt-1 font-mono text-[11px] text-[color:var(--ops-text-caption)]">{candidate.workflow_key || 'workflow TBD'} · confidence {Math.round((candidate.confidence || 0) * 100)}%</div>
                </div>
                <span className={['rounded-full border px-2.5 py-1 text-[11px] font-medium', badgeTone(candidate.status)].join(' ')}>{candidate.status}</span>
              </div>
              {candidateAcceptanceStepCount(candidate) > 0 ? (
                <div className="mt-3 rounded-xl border border-emerald-300/20 bg-emerald-300/[0.06] px-3 py-2 text-xs text-emerald-100">
                  Acceptance: {candidateAcceptanceStepCount(candidate)} evidence-bound step(s)
                </div>
              ) : null}
              {candidate.metadata?.routing_decision ? (
                <div className="mt-3 rounded-xl border border-cyan-300/20 bg-cyan-300/[0.06] px-3 py-2 text-xs text-cyan-100">
                  Risk Router: {String(candidate.metadata.routing_decision)}
                  {candidate.metadata.routing_reason ? ` · ${String(candidate.metadata.routing_reason)}` : ''}
                </div>
              ) : null}
              <div className="mt-3"><CandidateActions candidate={candidate} busy={busy} onAction={onAction} /></div>
            </article>
          ))}
        </section>
      ) : null}

      {groups.materialized.length > 0 ? (
        <section className="space-y-2" data-testid="candidate-materialized">
          <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Materialized</div>
          {visibleMaterialized.map((candidate) => (
            <article key={candidate.id} className="rounded-2xl border border-emerald-300/20 bg-emerald-300/[0.055] px-4 py-3" data-testid="materialized-candidate-row">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-1 text-sm font-semibold text-[color:var(--ops-text-title)]">Materialized: {candidate.title}</div>
                  <div className="mt-1 font-mono text-[11px] text-[color:var(--ops-text-caption)]">{candidate.workflow_key || 'workflow TBD'} · {workflowOutcomeLabel(candidate)}</div>
                </div>
                <span className={['rounded-full border px-2.5 py-1 text-[11px] font-medium', badgeTone(candidate.status)].join(' ')}>{candidate.status}</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {candidate.materialized_requirement_id ? (
                  <a className="rounded-xl border border-emerald-300/25 px-3 py-2 text-xs font-medium text-emerald-100" href={`/requirements/${candidate.materialized_requirement_id}`}>Requirement #{candidate.materialized_requirement_id}</a>
                ) : null}
                <span className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-3 py-2 text-xs text-[color:var(--ops-text-muted)]">{workflowOutcomeLabel(candidate)}</span>
              </div>
            </article>
          ))}
          {olderMaterialized.length > 0 ? (
            <details className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
              <summary className="cursor-pointer text-sm font-medium text-[color:var(--ops-text-body)]">Show older materialized ({olderMaterialized.length})</summary>
              <div className="mt-3 space-y-2">
                {olderMaterialized.map((candidate) => (
                  <div key={candidate.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-[color:var(--ops-stroke-soft)] pt-2 text-sm">
                    <span className="line-clamp-1 text-[color:var(--ops-text-body)]">{candidate.title}</span>
                    {candidate.materialized_requirement_id ? <a className="text-cyan-100" href={`/requirements/${candidate.materialized_requirement_id}`}>Requirement #{candidate.materialized_requirement_id}</a> : null}
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </section>
      ) : null}

      {groups.validationFailed.length > 0 ? (
        <details className="rounded-2xl border border-rose-300/25 bg-rose-400/[0.06] px-4 py-3" data-testid="planner-intercepts">
          <summary className="cursor-pointer text-sm font-medium text-rose-100">
            展开查看 {interceptGroups.length} 类 Planner 拦截记录 ({groups.validationFailed.length} failed attempts)
          </summary>
          <div className="mt-3 rounded-xl border border-rose-300/20 bg-slate-950/30 px-3 py-2 text-xs leading-5 text-rose-100/80">
            Planner Intercepts are planning diagnostics, not Human Gates. Fix PRD or policy, then run sweep again.
          </div>
          <div className="mt-3 space-y-2">
            {interceptGroups.map((group) => (
              <article key={group.signature} className="rounded-xl border border-rose-300/20 bg-slate-950/35 px-3 py-2" data-testid="validation-failed-candidate-row">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-rose-50">
                      <span className="rounded-full border border-rose-300/30 bg-rose-400/[0.12] px-2 py-0.5 text-[11px] text-rose-100">{group.attempts.length}x Failed</span>
                      <LocalTime value={candidateTimestamp(group.latest)} />
                      <span className="line-clamp-1">- Fail Closed: {group.reason}</span>
                    </div>
                    <div className="mt-1 line-clamp-1 text-xs text-rose-100/65">{group.latest.title}</div>
                  </div>
                  <span className={['rounded-full border px-2 py-1 text-[11px]', badgeTone(group.latest.status)].join(' ')}>{group.latest.status}</span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button className="rounded-lg border border-cyan-300/25 bg-cyan-300/[0.06] px-3 py-1.5 text-xs font-medium text-cyan-100" onClick={() => onEditIntent(goal)}>Edit Goal PRD</button>
                  {interceptNeedsSettings(group.reason) ? (
                    <button className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-1.5 text-xs font-medium text-[color:var(--ops-text-body)]" onClick={() => onEditSettings(goal)}>Edit Settings</button>
                  ) : null}
                  <button className="rounded-lg border border-emerald-300/25 bg-emerald-300/[0.06] px-3 py-1.5 text-xs font-medium text-emerald-100" onClick={() => onTraceGoal(goal)}>Trace Path</button>
                  <button className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-1.5 text-xs font-medium text-[color:var(--ops-text-body)]" disabled={busy === 'sweep'} onClick={onRunSweep}>Run Sweep Now</button>
                </div>
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs font-medium text-rose-100/80">Show attempts ({group.attempts.length})</summary>
                  <div className="mt-2 space-y-2">
                    {group.attempts.map((candidate) => (
                      <div key={candidate.id} className="rounded-xl border border-rose-300/15 bg-slate-950/50 p-3 text-xs leading-5 text-rose-50/80">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span><LocalTime value={candidateTimestamp(candidate)} /> · {candidate.title}</span>
                          <span className={['rounded-full border px-2 py-1 text-[11px]', badgeTone(candidate.status)].join(' ')}>{candidate.status}</span>
                        </div>
                        <details className="mt-2">
                          <summary className="cursor-pointer font-medium text-rose-100/80">View Agent Raw Output</summary>
                          <div className="mt-2 rounded-xl border border-rose-300/15 bg-slate-950/50 p-3">
                            {candidate.description_markdown ? <p className="whitespace-pre-wrap">{candidate.description_markdown}</p> : null}
                            {candidate.rationale ? <p className="mt-2 whitespace-pre-wrap">Rationale: {candidate.rationale}</p> : null}
                            <div className="mt-2 font-mono">generated_by: {String(candidate.metadata?.generated_by || 'unknown')}</div>
                          </div>
                        </details>
                      </div>
                    ))}
                  </div>
                </details>
              </article>
            ))}
          </div>
        </details>
      ) : null}

      {!groups.actionRequired.length && !groups.materialized.length && !groups.validationFailed.length ? (
        <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] px-4 py-5 text-sm text-[color:var(--ops-text-muted)]">
          No active proposals for this goal. Run Planner Sweep when capacity is available.
        </div>
      ) : null}

      {groups.quiet.length > 0 && (
        <details className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
          <summary className="cursor-pointer text-sm font-medium text-[color:var(--ops-text-body)]">Quiet History ({groups.quiet.length})</summary>
          <div className="mt-3 space-y-2">
            {groups.quiet.map((candidate) => (
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

function GoalMissionLaneSection({
  lane,
  busy,
  onCandidateAction,
  onEditIntent,
  onPrefetchIntent,
  onEditSettings,
  onDropGoal,
  onTraceGoal,
  onRunSweep,
}: Readonly<{
  lane: GoalMissionLane
  busy: string | null
  onCandidateAction: (candidate: RequirementCandidate, action: CandidateAction) => void
  onEditIntent: (goal: PlanningGoal) => void
  onPrefetchIntent: (goal: PlanningGoal) => void
  onEditSettings: (goal: PlanningGoal) => void
  onDropGoal: (goal: Goal) => void
  onTraceGoal: (goal: PlanningGoal) => void
  onRunSweep: () => void
}>) {
  const goal = lane.goal
  const status = goal.status || 'active'
  return (
    <section className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5 shadow-sm" data-testid="goal-mission-lane">
      <div className="grid gap-5 xl:grid-cols-[0.75fr_1.25fr]">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={['rounded-full border px-3 py-1 text-xs font-medium', badgeTone(status)].join(' ')}>{status}</span>
            <span className="font-mono text-xs text-[color:var(--ops-text-caption)]">{goal.goal_key || lane.goal_key}</span>
          </div>
          <h3 className="mt-3 text-xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">{goal.title || goal.domain || 'operations'}</h3>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-[color:var(--ops-text-muted)]">
            <span>Domain: {goal.domain || 'ops'}</span>
            <span>|</span>
            <span>Weight: {goal.weight != null ? `${weightToPercent(goal.weight)}%` : '-'}</span>
            <span>|</span>
            <span>Success Metric: {goal.success_metric || 'Pending'}</span>
          </div>
          <p className="mt-4 line-clamp-3 text-sm leading-6 text-[color:var(--ops-text-body)]">Intent: {goal.intent_excerpt || 'No intent defined.'}</p>
          <div className="mt-4 rounded-2xl bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-sm text-[color:var(--ops-text-muted)]">
            <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Success Metric</div>
            <div className="mt-1">{goal.success_metric || '-'}</div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-[color:var(--ops-text-muted)]">
            <span>Weight: {goal.weight != null ? `${weightToPercent(goal.weight)}%` : '-'}</span>
            {status === 'dropped' ? <span className="text-rose-700">Delivered artifacts retained.</span> : null}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              className="rounded-xl border border-cyan-300/25 bg-cyan-300/[0.06] px-3 py-2 text-xs font-medium text-cyan-100"
              onFocus={() => onPrefetchIntent(goal)}
              onMouseEnter={() => onPrefetchIntent(goal)}
              onClick={() => onEditIntent(goal)}
            >
              Edit Intent
            </button>
            <button
              className="rounded-xl border border-cyan-300/25 bg-cyan-300/[0.06] px-3 py-2 text-xs font-medium text-cyan-100"
              onFocus={() => onPrefetchIntent(goal)}
              onMouseEnter={() => onPrefetchIntent(goal)}
              onClick={() => onEditIntent(goal)}
            >
              查看完整 PRD
            </button>
            <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-xs font-medium text-[color:var(--ops-text-body)]" onClick={() => onEditSettings(goal)}>Edit Settings</button>
            <button className="rounded-xl border border-emerald-300/25 bg-emerald-300/[0.06] px-3 py-2 text-xs font-medium text-emerald-100" onClick={() => onTraceGoal(goal)}>Trace Path</button>
            {status !== 'dropped' && (
              <button className="rounded-xl border border-rose-200 bg-[color:var(--ops-panel)] px-3 py-2 text-xs font-medium text-rose-700" onClick={() => onDropGoal(goal)}>Drop Goal</button>
            )}
          </div>
        </div>
        <div className="space-y-4">
          <GoalRollupStrip lane={lane} />
          <GoalCandidateSummary
            goal={goal}
            candidates={lane.candidates}
            busy={busy}
            onAction={onCandidateAction}
            onEditIntent={onEditIntent}
            onEditSettings={onEditSettings}
            onTraceGoal={onTraceGoal}
            onRunSweep={onRunSweep}
          />
        </div>
      </div>
    </section>
  )
}

function goalSearchText(lane: GoalMissionLane) {
  const goal = lane.goal
  return [
    goal.title,
    goal.goal_key,
    goal.domain,
    goal.success_metric,
    goal.intent_excerpt,
  ].filter(Boolean).join(' ').toLowerCase()
}

function HistoricalGoalRow({
  lane,
  onEditIntent,
  onTraceGoal,
}: Readonly<{
  lane: GoalMissionLane
  onEditIntent: (goal: PlanningGoal) => void
  onTraceGoal: (goal: PlanningGoal) => void
}>) {
  const goal = lane.goal
  const counts = lane.rollup
  const candidates = Object.values(counts.candidate_status_counts || {}).reduce((sum, value) => sum + value, 0)
  const requirements = Object.values(counts.requirement_status_counts || {}).reduce((sum, value) => sum + value, 0)
  const workflows = Object.values(counts.workflow_status_counts || {}).reduce((sum, value) => sum + value, 0)
  return (
    <article className="h-[132px] rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-4 py-3" data-testid="historical-goal-row">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={['rounded-full border px-2.5 py-1 text-[11px] font-medium', badgeTone(goal.status)].join(' ')}>{goal.status}</span>
            <span className="font-mono text-xs text-[color:var(--ops-text-caption)]">{goal.goal_key}</span>
          </div>
          <h4 className="mt-2 line-clamp-1 text-sm font-semibold text-[color:var(--ops-text-title)]">{goal.title || goal.goal_key}</h4>
          <p className="mt-1 line-clamp-1 text-xs text-[color:var(--ops-text-muted)]">{goal.intent_excerpt || goal.success_metric || 'No intent excerpt.'}</p>
        </div>
        <div className="flex flex-wrap gap-2 text-[11px] text-[color:var(--ops-text-muted)]">
          <span>{candidates} candidates</span>
          <span>{requirements} requirements</span>
          <span>{workflows} workflows</span>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="rounded-lg border border-cyan-300/25 bg-cyan-300/[0.06] px-3 py-1.5 text-xs font-medium text-cyan-100" onClick={() => onEditIntent(goal)}>Edit Intent</button>
        <button className="rounded-lg border border-emerald-300/25 bg-emerald-300/[0.06] px-3 py-1.5 text-xs font-medium text-emerald-100" onClick={() => onTraceGoal(goal)}>Trace Path</button>
      </div>
    </article>
  )
}

function VirtualizedGoalList({
  lanes,
  group,
  onEditIntent,
  onTraceGoal,
}: Readonly<{
  lanes: GoalMissionLane[]
  group: 'achieved' | 'dropped'
  onEditIntent: (goal: PlanningGoal) => void
  onTraceGoal: (goal: PlanningGoal) => void
}>) {
  const [query, setQuery] = useState('')
  const [scrollTop, setScrollTop] = useState(0)
  const itemHeight = 144
  const viewportHeight = 640
  const filtered = query.trim()
    ? lanes.filter((lane) => goalSearchText(lane).includes(query.trim().toLowerCase()))
    : lanes
  const shouldVirtualize = filtered.length > 20
  const totalHeight = filtered.length * itemHeight
  const startIndex = shouldVirtualize ? Math.max(0, Math.floor(scrollTop / itemHeight) - 2) : 0
  const visibleCount = shouldVirtualize ? Math.ceil(viewportHeight / itemHeight) + 4 : filtered.length
  const visible = filtered.slice(startIndex, startIndex + visibleCount)
  const placeholder = group === 'achieved' ? 'Filter achieved goals...' : 'Filter dropped goals...'

  return (
    <div className="space-y-3">
      <input
        className="w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm text-[color:var(--ops-text-title)] outline-none"
        placeholder={placeholder}
        value={query}
        onChange={(event) => {
          setQuery(event.target.value)
          setScrollTop(0)
        }}
      />
      {shouldVirtualize ? (
        <div
          className="overflow-auto rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-950/20 p-2"
          style={{ height: viewportHeight }}
          onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
          data-testid={`virtualized-${group}-goals`}
        >
          <div style={{ height: totalHeight, position: 'relative' }}>
            <div style={{ transform: `translateY(${startIndex * itemHeight}px)` }} className="space-y-3">
              {visible.map((lane) => (
                <HistoricalGoalRow key={lane.goal.id} lane={lane} onEditIntent={onEditIntent} onTraceGoal={onTraceGoal} />
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-3" data-testid={`${group}-goals-list`}>
          {filtered.map((lane) => (
            <HistoricalGoalRow key={lane.goal.id} lane={lane} onEditIntent={onEditIntent} onTraceGoal={onTraceGoal} />
          ))}
        </div>
      )}
      {!filtered.length ? (
        <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] px-4 py-5 text-sm text-[color:var(--ops-text-muted)]">No {group} goals match this filter.</div>
      ) : null}
    </div>
  )
}

function GoalLaneGroups({
  lanes,
  view,
  setView,
  busy,
  onCandidateAction,
  onEditIntent,
  onPrefetchIntent,
  onEditSettings,
  onDropGoal,
  onTraceGoal,
  onRunSweep,
}: Readonly<{
  lanes: GoalMissionLane[]
  view: GoalStatusView
  setView: (view: GoalStatusView) => void
  busy: string | null
  onCandidateAction: (candidate: RequirementCandidate, action: CandidateAction) => void
  onEditIntent: (goal: PlanningGoal) => void
  onPrefetchIntent: (goal: PlanningGoal) => void
  onEditSettings: (goal: PlanningGoal) => void
  onDropGoal: (goal: Goal) => void
  onTraceGoal: (goal: PlanningGoal) => void
  onRunSweep: () => void
}>) {
  const [historicalExpanded, setHistoricalExpanded] = useState({ achieved: false, dropped: false })
  useEffect(() => {
    if (view === 'achieved') setHistoricalExpanded((current) => ({ ...current, achieved: true }))
    if (view === 'dropped') setHistoricalExpanded((current) => ({ ...current, dropped: true }))
  }, [view])
  const groups = {
    active: lanes.filter((lane) => lane.goal.status === 'active'),
    achieved: lanes.filter((lane) => lane.goal.status === 'achieved'),
    dropped: lanes.filter((lane) => lane.goal.status === 'dropped'),
  }
  const showActive = view === 'all' || view === 'active'
  const showAchieved = view === 'all' || view === 'achieved'
  const showDropped = view === 'all' || view === 'dropped'
  const achievedOpen = historicalExpanded.achieved
  const droppedOpen = historicalExpanded.dropped
  return (
    <section className="space-y-4" data-testid="goal-lane-groups">
      <nav className="sticky top-0 z-10 flex flex-wrap gap-2 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-2">
        {([
          ['active', `Active (${groups.active.length})`],
          ['achieved', `Achieved (${groups.achieved.length})`],
          ['dropped', `Dropped (${groups.dropped.length})`],
          ['all', `All (${lanes.length})`],
        ] as Array<[GoalStatusView, string]>).map(([key, label]) => (
          <button
            key={key}
            className={['rounded-xl px-4 py-2 text-sm font-medium transition', view === key ? 'bg-cyan-300/[0.14] text-cyan-100' : 'text-[color:var(--ops-text-muted)] hover:bg-[color:var(--ops-panel-strong)]'].join(' ')}
            onClick={() => setView(key)}
          >
            {label}
          </button>
        ))}
      </nav>

      {showActive ? (
        <section id="active-goals" className="space-y-4" data-testid="active-goals-section">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-lg font-semibold text-[color:var(--ops-text-title)]">Active Goals</h3>
            <span className="rounded-full bg-[color:var(--ops-panel-strong)] px-3 py-1 text-xs text-[color:var(--ops-text-muted)]">{groups.active.length} current fronts</span>
          </div>
          {groups.active.map((lane) => (
            <GoalMissionLaneSection
              key={lane.goal_key}
              lane={lane}
              busy={busy}
              onCandidateAction={onCandidateAction}
              onEditIntent={onEditIntent}
              onPrefetchIntent={onPrefetchIntent}
              onEditSettings={onEditSettings}
              onDropGoal={onDropGoal}
              onTraceGoal={onTraceGoal}
              onRunSweep={onRunSweep}
            />
          ))}
          {!groups.active.length ? <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-8 text-sm text-[color:var(--ops-text-muted)]">No active goals in this manifest.</div> : null}
        </section>
      ) : null}

      {showAchieved ? (
        <details className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="achieved-goals-section" open={achievedOpen}>
          <summary
            className="cursor-pointer text-base font-semibold text-[color:var(--ops-text-title)]"
            onClick={(event) => {
              event.preventDefault()
              setHistoricalExpanded((current) => ({ ...current, achieved: !current.achieved }))
            }}
          >
            Achieved Goals ({groups.achieved.length})
          </summary>
          {achievedOpen ? (
            <div className="mt-4">
              <VirtualizedGoalList lanes={groups.achieved} group="achieved" onEditIntent={onEditIntent} onTraceGoal={onTraceGoal} />
            </div>
          ) : null}
        </details>
      ) : null}

      {showDropped ? (
        <details className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4" data-testid="dropped-goals-section" open={droppedOpen}>
          <summary
            className="cursor-pointer text-base font-semibold text-[color:var(--ops-text-title)]"
            onClick={(event) => {
              event.preventDefault()
              setHistoricalExpanded((current) => ({ ...current, dropped: !current.dropped }))
            }}
          >
            Dropped Goals ({groups.dropped.length})
          </summary>
          {droppedOpen ? (
            <div className="mt-4">
              <VirtualizedGoalList lanes={groups.dropped} group="dropped" onEditIntent={onEditIntent} onTraceGoal={onTraceGoal} />
            </div>
          ) : null}
        </details>
      ) : null}
    </section>
  )
}

function traceTone(status: string) {
  if (status === 'ok') return 'border-emerald-300/30 bg-emerald-300/[0.07] text-emerald-100'
  if (status === 'warning') return 'border-amber-300/30 bg-amber-300/[0.08] text-amber-100'
  if (status === 'blocked') return 'border-rose-300/30 bg-rose-400/10 text-rose-100'
  return 'border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] text-[color:var(--ops-text-body)]'
}

function GoalTraceModal({
  open,
  trace,
  busy,
  error,
  onClose,
  onSupersedeRetry,
}: Readonly<{
  open: boolean
  trace: PlanningGoalTrace | null
  busy: string | null
  error: string | null
  onClose: () => void
  onSupersedeRetry: (trace: PlanningGoalTrace) => void
}>) {
  useTopOverlayEscape(open, 'goal-trace-modal', onClose)
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4" data-testid="goal-trace-modal">
      <section className="max-h-[90vh] w-full max-w-4xl overflow-auto rounded-[28px] bg-[color:var(--ops-bg)] p-6 shadow-2xl" role="dialog" aria-modal="true">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Single-Goal Trace</div>
            <h3 className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{String(trace?.goal?.title || 'Goal trace')}</h3>
            <p className="mt-1 font-mono text-xs text-[color:var(--ops-text-muted)]">
              {String(trace?.goal?.goal_key || '')} · diagnostics are filtered to this exact goal.
            </p>
          </div>
          <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm text-[color:var(--ops-text-body)]" onClick={onClose}>Close</button>
        </div>
        {error ? <div className="mt-4 rounded-2xl border border-rose-300/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">{error}</div> : null}
        {trace?.objective_status ? (
          <div className="mt-4 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-950/25 px-4 py-3 text-sm text-[color:var(--ops-text-body)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Objective</span>
                <div className="mt-1 font-semibold">{trace.objective_status} · next: {trace.next_action || 'inspect_trace'}</div>
                {trace.missing_evidence?.length ? <div className="mt-1 text-xs text-[color:var(--ops-text-muted)]">Missing evidence: {trace.missing_evidence.join(', ')}</div> : null}
              </div>
              {trace.next_action === 'supersede_and_retry_planner' ? (
                <button
                  className="rounded-xl border border-amber-300/35 bg-amber-300/[0.08] px-3 py-2 text-xs font-semibold text-amber-100"
                  onClick={() => onSupersedeRetry(trace)}
                  disabled={busy === 'supersede_retry'}
                >
                  {busy === 'supersede_retry' ? 'Retrying...' : 'Supersede & Retry Planner'}
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
        {busy === 'trace_goal' ? (
          <div className="mt-6 space-y-3">
            {[1, 2, 3, 4].map((item) => <div key={item} className="h-24 animate-pulse rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]" />)}
          </div>
        ) : (
          <div className="mt-6 space-y-3">
            {(trace?.nodes || []).map((node, index) => (
              <article key={`${node.kind}:${node.object_id || index}`} className={['rounded-2xl border p-4', traceTone(node.status)].join(' ')}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.18em] opacity-70">{index + 1}. {node.kind} · {node.status}</div>
                    <h4 className="mt-1 text-base font-semibold">{node.title}</h4>
                    {node.summary ? <p className="mt-2 text-sm leading-6 opacity-85">{node.summary}</p> : null}
                  </div>
                  {node.deep_link ? <a className="rounded-xl border border-current/25 px-3 py-2 text-xs font-medium" href={node.deep_link}>Open</a> : null}
                </div>
                {node.diagnostic?.reason ? (
                  <div className="mt-3 rounded-xl border border-current/15 bg-slate-950/20 px-3 py-2 text-xs">
                    {node.kind === 'candidate' && node.status === 'blocked' ? (
                      <div className="mb-2 rounded-lg border border-current/15 bg-slate-950/25 px-2 py-1 font-semibold">
                        Planner Intercept · not a Human Gate. Fix the Goal PRD or command safety policy, then run Planner Sweep again.
                      </div>
                    ) : null}
                    <div>why: {node.diagnostic.reason}</div>
                    <div className="mt-1 opacity-75">source: {node.diagnostic.source || '-'} · {node.diagnostic.timestamp || '-'}</div>
                  </div>
                ) : null}
                {Object.keys(node.metadata || {}).length ? (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs font-medium opacity-80">metadata</summary>
                    <JsonBlock value={node.metadata} />
                  </details>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
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
        className="mt-3 h-28 w-full rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm leading-6 text-[color:var(--ops-text-body)]"
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
  onOpenCreateGoal,
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
  onOpenCreateGoal: () => void
}>) {
  const manifest = mission?.manifest
  const total = weightTotal(draft.focusWeights)
  const canSave = Math.abs(total - 100) <= 0.01
  return (
    <section className="rounded-[32px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5 shadow-sm" data-testid="planning-steering-panel">
      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Planning Mission Control</div>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">经营规划</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[color:var(--ops-text-muted)]">唯一活跃 Manifest 控制预算、目标和 Planner 输出。候选需求必须回到所属 Goal 上下文里审批。</p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onRefresh}>刷新</button>
            <button className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700" disabled={busy === 'dry_sweep'} onClick={() => onRunSweep(true)}>Dry Run Planner</button>
            <button className="rounded-xl bg-[color:var(--ops-accent)] px-4 py-2 text-sm font-semibold text-white" disabled={busy === 'sweep'} onClick={() => onRunSweep(false)}>Run Planner Sweep</button>
            <button className="rounded-xl border border-cyan-300/25 bg-cyan-300/[0.06] px-4 py-2 text-sm font-medium text-cyan-100" onClick={onOpenCreateGoal}>New Goal</button>
            <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onOpenArchive}>Archive & Start New Plan</button>
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
              <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Plan label</div>
              <div className="mt-1 text-sm font-semibold text-[color:var(--ops-text-title)]">{manifest?.cycle_label || '-'}</div>
            </div>
          </div>
        </div>
        <div className="space-y-4 border-t border-[color:var(--ops-stroke-soft)] pt-5 xl:border-l xl:border-t-0 xl:pl-6 xl:pt-0">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
              <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Focus</div>
              <div className="mt-1 font-mono text-sm text-[color:var(--ops-text-title)]">{Object.entries(draft.focusWeights).map(([key, value]) => `${key} ${value}%`).join(' · ') || '-'}</div>
            </div>
            <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
              <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Budget</div>
              <div className="mt-1 font-mono text-sm text-[color:var(--ops-text-title)]">
                ${String(draft.globalBudget.daily_usd_limit ?? '-')} / day · {String(draft.globalBudget.max_concurrent_workers ?? '-')} workers
              </div>
            </div>
            <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
              <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Constraints</div>
              <div className="mt-1 font-mono text-sm text-[color:var(--ops-text-title)]">{draft.constraintsText.split('\n').filter(Boolean).length} active</div>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <details className="min-w-[260px] flex-1 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
              <summary className="cursor-pointer text-sm font-medium text-[color:var(--ops-text-body)]">Steering Details</summary>
              <div className="mt-5 space-y-5">
                <FocusWeightSliders draft={draft} onChange={onDraftChange} />
                <GlobalBudgetEditor draft={draft} onChange={onDraftChange} />
                <GlobalConstraintsEditor draft={draft} onChange={onDraftChange} />
                <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onOpenRaw}>{'</>'} Edit raw JSON</button>
              </div>
            </details>
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
    <section className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5" data-testid="manifest-history-panel">
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
          <thead className="bg-[color:var(--ops-panel-subtle)] text-xs uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">
            <tr>
              <th className="px-4 py-3">Plan label</th>
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
                <td className="px-4 py-3 text-[color:var(--ops-text-muted)]"><LocalTime value={item.updated_at} /></td>
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

function RawManifestModal({
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
  useTopOverlayEscape(open, 'raw-manifest-modal', onClose)
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" data-testid="raw-manifest-modal">
      <section className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-[28px] bg-[color:var(--ops-panel)] p-6 shadow-2xl" role="dialog" aria-modal="true">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Debug Modal</div>
            <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">Raw Manifest JSON</h3>
            <p className="mt-1 text-sm text-[color:var(--ops-text-muted)]">Use this only for steering fields. Goals are first-class records and live under /api/planning/goals.</p>
          </div>
          <button className="rounded-xl border px-3 py-2 text-sm" onClick={onClose}>Close</button>
        </div>
        <textarea className="mt-5 h-[65vh] w-full rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-100" value={rawDraft || JSON.stringify(manifest?.payload || {}, null, 2)} onChange={(event) => setRawDraft(event.target.value)} spellCheck={false} />
        {rawError && <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{rawError}</div>}
        <button className="mt-4 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white" onClick={onSave}>Save raw JSON</button>
      </section>
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
  useTopOverlayEscape(open, 'archive-cycle-modal', onClose)
  useEffect(() => {
    if (open) {
      setVersionName(`Next company plan after ${mission?.manifest.cycle_label || 'current'}`)
      setCycleLabel('')
    }
  }, [open, mission?.manifest.cycle_label])
  if (!open) return null
  const activeGoals = (mission?.goal_lanes || []).filter((lane) => lane.goal.status !== 'dropped' && lane.goal.status !== 'achieved')
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
      <div className="w-full max-w-2xl rounded-[28px] bg-[color:var(--ops-panel)] p-6 shadow-2xl" role="dialog" aria-modal="true">
        <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Archive Plan</div>
        <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">Archive & Start New Company Plan</h3>
        <p className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">Active goals will carry forward. Achieved and dropped goals stay in the archived review.</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="block text-sm font-medium text-[color:var(--ops-text-title)]">Version name<input className="mt-2 w-full rounded-xl border px-3 py-2 text-sm" value={versionName} onChange={(event) => setVersionName(event.target.value)} /></label>
          <label className="block text-sm font-medium text-[color:var(--ops-text-title)]">Plan label<input className="mt-2 w-full rounded-xl border px-3 py-2 text-sm" placeholder="Active" value={cycleLabel} onChange={(event) => setCycleLabel(event.target.value)} /></label>
        </div>
        <div className="mt-4 rounded-2xl bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-sm text-[color:var(--ops-text-muted)]">Carry forward: {activeGoals.map((lane) => lane.goal_key).join(', ') || 'none'}</div>
        <div className="mt-5 flex justify-end gap-2">
          <button className="rounded-xl border px-4 py-2 text-sm" onClick={onClose}>Cancel</button>
          <button className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white" disabled={!versionName.trim() || !cycleLabel.trim() || busy === 'archive'} onClick={() => onArchive(versionName, cycleLabel)}>Archive Current Plan</button>
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
  useTopOverlayEscape(Boolean(goal), 'drop-goal-modal', onCancel)
  if (!goal) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
      <div className="w-full max-w-xl rounded-[28px] bg-[color:var(--ops-panel)] p-6 shadow-2xl" role="dialog" aria-modal="true">
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

function GoalIntentModal({
  goal,
  draft,
  loading,
  busy,
  error,
  setDraft,
  onClose,
  onSave,
}: Readonly<{
  goal: PlanningGoal | null
  draft: string
  loading: boolean
  busy: string | null
  error: string | null
  setDraft: (value: string) => void
  onClose: () => void
  onSave: () => void
}>) {
  useTopOverlayEscape(Boolean(goal), 'goal-intent-modal', onClose)
  if (!goal) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4" data-testid="goal-intent-modal">
      <section className="max-h-[90vh] w-full max-w-6xl overflow-auto rounded-[28px] bg-[color:var(--ops-bg)] p-6 shadow-2xl" role="dialog" aria-modal="true">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Goal Intent Data Plane</div>
            <h3 className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{goal.title || goal.goal_key}</h3>
            <p className="mt-1 font-mono text-xs text-[color:var(--ops-text-muted)]">{goal.goal_key} · full Markdown is loaded only from the goal detail API.</p>
          </div>
          <div className="flex gap-2">
            <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm text-[color:var(--ops-text-body)]" onClick={onClose}>Close</button>
            <button className="rounded-xl bg-[color:var(--ops-accent)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={loading || busy === 'save_intent'} onClick={onSave}>Save Intent</button>
          </div>
        </div>
        {error && <div className="mt-4 rounded-2xl border border-rose-300/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">{error}</div>}
        <div className="mt-6">
          {loading ? (
            <div className="min-h-[70vh] animate-pulse rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]" data-testid="goal-intent-skeleton" />
          ) : draft.trim() ? (
            <MarkdownTabs value={draft} onChange={setDraft} minHeightClass="min-h-[70vh]" />
          ) : (
            <div>
              <div className="mb-3 rounded-2xl border border-amber-300/25 bg-amber-300/[0.08] px-4 py-3 text-sm text-amber-100">
                No PRD saved for this goal yet.
              </div>
              <MarkdownTabs value={draft} onChange={setDraft} minHeightClass="min-h-[70vh]" />
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

function GoalSettingsModal({
  open,
  goal,
  draft,
  busy,
  error,
  setDraft,
  onClose,
  onSave,
}: Readonly<{
  open: boolean
  goal: PlanningGoal | null
  draft: GoalSettingsDraft
  busy: string | null
  error: string | null
  setDraft: (value: GoalSettingsDraft) => void
  onClose: () => void
  onSave: () => void
}>) {
  useTopOverlayEscape(open, 'goal-settings-modal', onClose)
  if (!open) return null
  const isCreate = !goal
  const update = (key: keyof GoalSettingsDraft, value: string) => setDraft({ ...draft, [key]: value })
  const canSave = Boolean(draft.title.trim()) && Boolean((draft.goal_key || slugifyGoalKey(draft.title)).trim())
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4" data-testid="goal-settings-modal">
      <section className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-[28px] bg-[color:var(--ops-bg)] p-6 shadow-2xl" role="dialog" aria-modal="true">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Goal Settings</div>
            <h3 className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{isCreate ? 'Create Goal' : draft.title || goal?.goal_key}</h3>
            <p className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{isCreate ? 'Write the goal once: core intent, Markdown PRD, then optional execution defaults.' : 'Short execution metadata lives here. Long PRD text belongs in Edit Intent & PRD.'}</p>
          </div>
          <div className="flex gap-2">
            <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm text-[color:var(--ops-text-body)]" onClick={onClose}>Close</button>
            <button className="rounded-xl bg-[color:var(--ops-accent)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={busy === 'save_goal_settings' || !canSave} onClick={onSave}>{isCreate ? 'Create Goal' : 'Save Settings'}</button>
          </div>
        </div>
        {error && <div className="mt-4 rounded-2xl border border-rose-300/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">{error}</div>}
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <label className="block text-sm text-[color:var(--ops-text-body)]">Goal key
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm text-[color:var(--ops-text-title)] disabled:opacity-60" disabled={!isCreate} value={draft.goal_key} onChange={(event) => update('goal_key', event.target.value)} />
          </label>
          <label className="block text-sm text-[color:var(--ops-text-body)]">Title
            <input
              className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm text-[color:var(--ops-text-title)]"
              value={draft.title}
              onBlur={() => {
                if (isCreate && !draft.goal_key.trim() && draft.title.trim()) update('goal_key', slugifyGoalKey(draft.title))
              }}
              onChange={(event) => update('title', event.target.value)}
            />
          </label>
          <label className="block text-sm text-[color:var(--ops-text-body)]">Domain
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm text-[color:var(--ops-text-title)]" value={draft.domain} onChange={(event) => update('domain', event.target.value)} />
          </label>
          <label className="block text-sm text-[color:var(--ops-text-body)]">Success metric
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm text-[color:var(--ops-text-title)]" value={draft.success_metric} onChange={(event) => update('success_metric', event.target.value)} />
          </label>
        </div>
        {isCreate && (
          <div className="mt-5">
            <MarkdownTabs value={draft.intent_markdown} onChange={(value) => update('intent_markdown', value)} />
          </div>
        )}
        <details className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
          <summary className="cursor-pointer text-sm font-semibold text-[color:var(--ops-text-title)]">Advanced Settings</summary>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <label className="block text-sm text-[color:var(--ops-text-body)]">Workflow key
              <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm text-[color:var(--ops-text-title)]" value={draft.workflow_key} onChange={(event) => update('workflow_key', event.target.value)} />
            </label>
            <label className="block text-sm text-[color:var(--ops-text-body)]">Project key
              <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm text-[color:var(--ops-text-title)]" value={draft.project_key} onChange={(event) => update('project_key', event.target.value)} />
            </label>
            <label className="block text-sm text-[color:var(--ops-text-body)]">Priority
              <select className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm text-[color:var(--ops-text-title)]" value={draft.priority} onChange={(event) => update('priority', event.target.value)}>
                {['low', 'normal', 'high', 'critical'].map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
            <label className="block text-sm text-[color:var(--ops-text-body)]">Risk level
              <select className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm text-[color:var(--ops-text-title)]" value={draft.risk_level} onChange={(event) => update('risk_level', event.target.value)}>
                {['low', 'normal', 'high', 'critical'].map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
            <label className="block text-sm text-[color:var(--ops-text-body)]">Weight
              <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm text-[color:var(--ops-text-title)]" type="number" step="0.01" value={draft.weight} onChange={(event) => update('weight', event.target.value)} />
            </label>
            <label className="block text-sm text-[color:var(--ops-text-body)]">Acceptance kind
              <select className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm text-[color:var(--ops-text-title)]" value={draft.acceptance_kind} onChange={(event) => update('acceptance_kind', event.target.value)}>
                {['business', 'system_dogfood'].map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
          </div>
          {draft.acceptance_kind === 'system_dogfood' ? (
            <div className="mt-4 rounded-xl border border-amber-300/30 bg-amber-300/[0.08] px-3 py-2 text-xs text-amber-100">
              system_dogfood is only for GoalB-style system validation. Use business for normal company goals.
            </div>
          ) : null}
          <div className="mt-4 rounded-xl border border-cyan-300/20 bg-cyan-300/[0.06] px-3 py-2 text-xs text-cyan-100">
            Acceptance steps are generated at Candidate level by Planner. If the Candidate lacks evidence-bound acceptance, materialize/start will fail closed.
          </div>
        </details>
      </section>
    </div>
  )
}

export default function PlanningPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const [mission, setMission] = useState<PlanningMissionControl | null>(null)
  const [missionBoard, setMissionBoard] = useState<MissionBoard | null>(null)
  const [missionWorkbench, setMissionWorkbench] = useState<MissionWorkbench | null>(null)
  const [taskBoard, setTaskBoard] = useState<PlanningTaskBoard | null>(null)
  const [history, setHistory] = useState<PlanningManifestHistory | null>(null)
  const [historyPage, setHistoryPage] = useState(1)
  const [historySearch, setHistorySearch] = useState('')
  const [activeTab, setActiveTab] = useState<ActiveTab>(() => initialPlanningTab(location.search))
  const [focusedOpportunityId, setFocusedOpportunityId] = useState<number | null>(() => selectedOpportunityId(location.search))
  const [focusedColumn, setFocusedColumn] = useState<string | null>(() => selectedBoardColumn(location.search))
  const [goalStatusView, setGoalStatusView] = useState<GoalStatusView>('active')
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
  const [intentGoal, setIntentGoal] = useState<PlanningGoal | null>(null)
  const [intentDraft, setIntentDraft] = useState('')
  const [intentError, setIntentError] = useState<string | null>(null)
  const [intentLoading, setIntentLoading] = useState(false)
  const [optimisticExcerpts, setOptimisticExcerpts] = useState<Record<number, string>>({})
  const goalDetailCache = useRef<Record<number, CachedGoalDetail>>({})
  const prefetchTimers = useRef<Record<number, ReturnType<typeof setTimeout>>>({})
  const [traceOpen, setTraceOpen] = useState(false)
  const [goalTrace, setGoalTrace] = useState<PlanningGoalTrace | null>(null)
  const [traceError, setTraceError] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsGoal, setSettingsGoal] = useState<PlanningGoal | null>(null)
  const [settingsDraft, setSettingsDraft] = useState<GoalSettingsDraft>(goalSettingsDraftFrom(null))
  const [settingsError, setSettingsError] = useState<string | null>(null)
  const candidateModal = useRequirementCandidateDetail(location, navigate)

  const candidateTotals = mission?.candidate_totals || {}
  const pendingActions = numberValue(candidateTotals.pending) + numberValue(candidateTotals.approved)

  function goalCacheKey(goal: PlanningGoal) {
    return `${goal.id}:${goal.updated_at || ''}`
  }

  function localIntentExcerpt(value: string) {
    const text = value.split(/\s+/).filter(Boolean).join(' ')
    return text.length > 200 ? `${text.slice(0, 200).trim()}...` : text
  }

  async function load(nextPage = historyPage) {
    setLoading(true)
    setError(null)
    try {
      const [nextMission, nextBoard, nextWorkbench, nextTaskBoard, nextHistory] = await Promise.all([
        api.getPlanningMissionControl(),
        api.getPlanningMissionBoard(),
        api.getPlanningMissionWorkbench(),
        api.getPlanningTaskBoard(),
        api.getPlanningManifestHistory({ page: nextPage, page_size: 10, search: historySearch || undefined }),
      ])
      setMission(nextMission)
      setMissionBoard(nextBoard)
      setMissionWorkbench(nextWorkbench)
      setTaskBoard(nextTaskBoard)
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

  useEffect(() => {
    setActiveTab(initialPlanningTab(location.search))
    setFocusedOpportunityId(selectedOpportunityId(location.search))
    setFocusedColumn(selectedBoardColumn(location.search))
  }, [location.search])

  useEffect(() => () => {
    Object.values(prefetchTimers.current).forEach((timer) => clearTimeout(timer))
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
    if (!dropGoal?.id) return
    setBusy('drop')
    setError(null)
    try {
      const result = await api.dropPlanningGoal(dropGoal.id, {
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

  async function fetchGoalDetail(goal: PlanningGoal) {
    const cached = goalDetailCache.current[goal.id]
    if (cached?.cacheKey === goalCacheKey(goal)) return cached.goal
    const detail = await api.getPlanningGoal(goal.id)
    goalDetailCache.current[goal.id] = { goal: detail, cacheKey: goalCacheKey(detail) }
    return detail
  }

  function prefetchGoalIntent(goal: PlanningGoal) {
    if (goalDetailCache.current[goal.id]?.cacheKey === goalCacheKey(goal) || prefetchTimers.current[goal.id]) return
    prefetchTimers.current[goal.id] = setTimeout(() => {
      delete prefetchTimers.current[goal.id]
      fetchGoalDetail(goal).catch(() => {})
    }, 150)
  }

  async function openIntentEditor(goal: PlanningGoal) {
    setIntentGoal(goal)
    setIntentDraft('')
    setIntentLoading(true)
    setIntentError(null)
    try {
      const detail = await fetchGoalDetail(goal)
      setIntentGoal(detail)
      setIntentDraft(detail.intent_markdown || '')
    } catch (err) {
      setIntentError(err instanceof Error ? err.message : '加载 Goal Markdown 失败')
    } finally {
      setIntentLoading(false)
    }
  }

  async function saveIntent() {
    if (!intentGoal) return
    setBusy('save_intent')
    setIntentError(null)
    const previous = intentGoal
    const previousDraft = previous.intent_markdown || ''
    const nextGoal = {
      ...previous,
      intent_markdown: intentDraft,
      intent_excerpt: localIntentExcerpt(intentDraft),
      updated_at: new Date().toISOString(),
    }
    goalDetailCache.current[previous.id] = { goal: nextGoal, cacheKey: goalCacheKey(nextGoal) }
    setOptimisticExcerpts((current) => ({ ...current, [previous.id]: nextGoal.intent_excerpt }))
    setIntentGoal(null)
    setIntentDraft('')
    try {
      await api.updatePlanningGoal(intentGoal.id, { intent_markdown: intentDraft, operator: 'operator' })
      await load(historyPage)
    } catch (err) {
      goalDetailCache.current[previous.id] = { goal: previous, cacheKey: goalCacheKey(previous) }
      setIntentGoal(previous)
      setIntentDraft(previousDraft)
      setIntentError(err instanceof Error ? err.message : '保存 Goal Markdown 失败')
    } finally {
      setBusy(null)
    }
  }

  function closeIntentEditor() {
    const original = intentGoal?.intent_markdown || ''
    if (intentGoal && intentDraft !== original) {
      setIntentError('有未保存的 PRD。请先保存，或恢复原文后再关闭。')
      return
    }
    setIntentGoal(null)
    setIntentDraft('')
    setIntentError(null)
  }

  function openSettingsEditor(goal: PlanningGoal) {
    setSettingsGoal(goal)
    setSettingsDraft(goalSettingsDraftFrom(goal))
    setSettingsError(null)
    setSettingsOpen(true)
  }

  function openCreateGoal() {
    setSettingsGoal(null)
    setSettingsDraft(goalSettingsDraftFrom(null))
    setSettingsError(null)
    setSettingsOpen(true)
  }

  function closeSettingsEditor() {
    const original = goalSettingsDraftFrom(settingsGoal)
    if (settingsOpen && JSON.stringify(settingsDraft) !== JSON.stringify(original)) {
      setSettingsError('有未保存的 Goal 内容。请先保存，或恢复原内容后再关闭。')
      return
    }
    setSettingsOpen(false)
    setSettingsGoal(null)
    setSettingsError(null)
  }

  async function saveGoalSettings() {
    if (!mission) return
    setBusy('save_goal_settings')
    setSettingsError(null)
    try {
      const goalKey = settingsDraft.goal_key.trim() || slugifyGoalKey(settingsDraft.title)
      const payload = {
        manifest_id: mission.manifest.id,
        goal_key: goalKey,
        title: settingsDraft.title.trim(),
        intent_markdown: settingsDraft.intent_markdown,
        success_metric: settingsDraft.success_metric.trim(),
        domain: settingsDraft.domain.trim(),
        workflow_key: settingsDraft.workflow_key.trim(),
        project_key: settingsDraft.project_key.trim() || null,
        priority: settingsDraft.priority,
        risk_level: settingsDraft.risk_level,
        weight: numberValue(settingsDraft.weight, 0),
        acceptance_kind: settingsDraft.acceptance_kind,
        operator: 'operator',
      }
      if (settingsGoal) {
        await api.updatePlanningGoal(settingsGoal.id, payload)
      } else {
        await api.createPlanningGoal(payload)
      }
      setSettingsOpen(false)
      setSettingsGoal(null)
      await load(historyPage)
    } catch (err) {
      setSettingsError(err instanceof Error ? err.message : '保存 Goal 设置失败')
    } finally {
      setBusy(null)
    }
  }

  async function actOnCandidate(candidate: RequirementCandidate, action: CandidateAction) {
    setBusy(`${action}:${candidate.id}`)
    setError(null)
    try {
      let nextCandidate: RequirementCandidate | null = null
      if (action === 'approve') await api.approveRequirementCandidate(candidate.id, { operator: 'operator' })
      if (action === 'approve_run') await api.approveAndRunRequirementCandidate(candidate.id, { operator: 'operator' })
      if (action === 'reject') await api.rejectRequirementCandidate(candidate.id, { operator: 'operator', reason: 'operator_rejected' })
      if (action === 'materialize') await api.materializeRequirementCandidate(candidate.id, { operator: 'operator' })
      if (action === 'retry_validation') nextCandidate = await api.retryRequirementCandidateValidation(candidate.id, { operator: 'operator' })
      await load(historyPage)
      if (nextCandidate) {
        candidateModal.showCandidateDetail(nextCandidate)
      } else if (candidateModal.candidateDetail?.id === candidate.id) {
        await candidateModal.refreshCandidateDetail(candidate.id)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : `${action} candidate failed`)
    } finally {
      setBusy(null)
    }
  }

  async function openGoalTrace(goal: PlanningGoal) {
    setTraceOpen(true)
    setGoalTrace(null)
    setTraceError(null)
    setBusy('trace_goal')
    try {
      setGoalTrace(await api.getPlanningGoalTrace(goal.id))
    } catch (err) {
      setTraceError(err instanceof Error ? err.message : '加载 Goal Trace 失败')
    } finally {
      setBusy(null)
    }
  }

  async function supersedeAndRetryPlanner(trace: PlanningGoalTrace) {
    const workflowRunId = Number(trace.latest_chain?.workflow_run_id || 0)
    const goalId = Number(trace.goal?.id || 0)
    if (!workflowRunId || !goalId) {
      setTraceError('Trace does not include a workflow run to supersede.')
      return
    }
    setBusy('supersede_retry')
    setTraceError(null)
    try {
      await api.supersedeWorkflowAndRetryPlanner(workflowRunId, {
        operator: 'operator',
        comment: 'Superseded from Goal Trace to retry Planner with repository-state context.',
      })
      setGoalTrace(await api.getPlanningGoalTrace(goalId))
      await load(historyPage)
    } catch (err) {
      setTraceError(err instanceof Error ? err.message : 'Supersede & Retry Planner failed')
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
        onOpenCreateGoal={openCreateGoal}
      />

      <nav className="flex flex-wrap gap-2 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-2" data-testid="planning-tabs">
        {([
          ['board', 'Task Board'],
          ['hierarchy', 'Hierarchy'],
          ['opportunities', '产品机会'],
          ['goals', `业务目标 · ${mission?.manifest.active_goal_count || 0} active`],
          ['engineering', `工程队列 · ${missionBoard?.lanes.software_engineer.length || pendingActions}`],
          ['unassigned', `未归属 · ${missionBoard?.unassigned.count || 0}`],
          ['history', `历史 · ${history?.total || mission?.history_preview.total || 0}`],
          ['debug', 'Debug'],
        ] as Array<[ActiveTab, string]>).map(([key, label]) => (
          <button key={key} className={['rounded-xl px-4 py-2 text-sm font-medium transition', activeTab === key ? 'bg-slate-900 text-white' : 'text-[color:var(--ops-text-muted)] hover:bg-[color:var(--ops-panel-strong)]'].join(' ')} onClick={() => setActiveTab(key)}>{label}</button>
        ))}
      </nav>

      {dropResult && (
        <section className="rounded-[28px] border border-amber-200 bg-amber-50 p-5">
          <div className="text-[11px] uppercase tracking-[0.22em] text-amber-700">Halt Summary</div>
          <div className="mt-2 text-lg font-semibold text-amber-950">Goal `{dropResult.goal_key}` 已停止未来投入</div>
          <p className="mt-2 text-sm text-amber-800">已发布产物保留；如需下线，请创建新的 decommission requirement，不会自动 rollback。</p>
          <div className="mt-4 grid gap-3 md:grid-cols-5">
            {Object.entries(dropResult.halt_summary).map(([key, value]) => (
              <div key={key} className="rounded-2xl bg-[color:var(--ops-panel)] p-3">
                <div className="font-mono text-[10px] text-amber-700">{key}</div>
                <div className="mt-1 text-lg font-semibold text-amber-950">{String(value)}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === 'board' && <PlanningTaskBoardPanel board={taskBoard} focusedColumn={focusedColumn} />}

      {activeTab === 'hierarchy' && <MissionWorkbenchPanel workbench={missionWorkbench} />}

      {activeTab === 'opportunities' && (
        <main className="space-y-4" data-testid="product-opportunities-tab">
          <div className="grid gap-3 md:grid-cols-5">
            {['pending', 'approved', 'materialized', 'rejected', 'suppressed'].map((status) => (
              <div key={status} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-4 py-3">
                <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">{status}</div>
                <div className="mt-1 text-2xl font-semibold text-[color:var(--ops-text-title)]">{candidateTotals[status] || 0}</div>
              </div>
            ))}
          </div>
          {mission?.last_sweep ? (
            <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-4 py-3 text-sm text-[color:var(--ops-text-muted)]">
              <span className="font-mono text-xs uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Last Planner Sweep</span>
              <span className="ml-3"><LocalTime value={mission.last_sweep.completed_at || mission.last_sweep.started_at} /></span>
              <span className="ml-3">created {(mission.last_sweep.created_candidate_ids || []).length}</span>
              <span className="ml-3">auto materialized {(mission.last_sweep.auto_materialized_requirement_ids || []).length}</span>
              <span className="ml-3">auto started {(mission.last_sweep.auto_started_workflow_run_ids || []).length}</span>
              <span className="ml-3">suppressed {(mission.last_sweep.suppressed_items || []).length}</span>
            </div>
          ) : null}
          <ProductOpportunitiesPanel focusedOpportunityId={focusedOpportunityId} onChanged={() => load(historyPage).catch(() => {})} />
        </main>
      )}

      {activeTab === 'goals' && (
        <main className="space-y-4" data-testid="planning-goals-tab">
          <section className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
            <div className="machine-label text-[color:var(--ops-text-caption)]">Business Goals</div>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">业务目标</h2>
            <p className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">这里管理正式 Goal；产品机会通过人审后才会进入这条主线。</p>
          </section>
          <GoalLaneGroups
          lanes={(mission?.goal_lanes || []).map((lane) => ({
            ...lane,
            goal: optimisticExcerpts[lane.goal.id] ? { ...lane.goal, intent_excerpt: optimisticExcerpts[lane.goal.id] } : lane.goal,
          }))}
            view={goalStatusView}
            setView={setGoalStatusView}
            busy={busy}
            onCandidateAction={actOnCandidate}
            onEditIntent={openIntentEditor}
            onPrefetchIntent={prefetchGoalIntent}
            onEditSettings={openSettingsEditor}
            onDropGoal={setDropGoal}
            onTraceGoal={openGoalTrace}
            onRunSweep={() => runSweep(false)}
          />
          {!mission?.goal_lanes.length && <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-8 text-sm text-[color:var(--ops-text-muted)]">No goals in the active manifest.</div>}
        </main>
      )}

      {activeTab === 'engineering' && (
        <EngineeringQueue
          board={missionBoard}
          onRunSweep={() => runSweep(false)}
          busy={busy === 'sweep'}
        />
      )}

      {activeTab === 'unassigned' && <UnassignedQueue items={missionBoard?.unassigned.items || []} />}

      {activeTab === 'history' && (
        <ManifestHistoryPanel history={history} historySearch={historySearch} setHistorySearch={setHistorySearch} setHistoryPage={setHistoryPage} loadHistory={(page) => load(page).catch(() => {})} />
      )}

      {activeTab === 'debug' && (
        <section className="grid gap-5 xl:grid-cols-2" data-testid="planning-debug-tab">
          <div className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Raw Manifest</div>
            <div className="mt-4"><JsonBlock value={mission?.manifest.payload} /></div>
          </div>
          <div className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Last Sweep</div>
            <div className="mt-4"><JsonBlock value={mission?.last_sweep} /></div>
          </div>
        </section>
      )}

      <RawManifestModal open={rawOpen} manifest={mission?.manifest || null} rawDraft={rawDraft} setRawDraft={setRawDraft} rawError={rawError} onClose={() => setRawOpen(false)} onSave={saveRaw} />
      <ArchiveCycleModal open={archiveOpen} mission={mission} busy={busy} onClose={() => setArchiveOpen(false)} onArchive={archiveCycle} />
      <DropGoalModal goal={dropGoal} reason={dropReason} busy={busy} setReason={setDropReason} onCancel={() => setDropGoal(null)} onConfirm={confirmDropGoal} />
      <GoalIntentModal goal={intentGoal} draft={intentDraft} loading={intentLoading} busy={busy} error={intentError} setDraft={setIntentDraft} onClose={closeIntentEditor} onSave={saveIntent} />
      <GoalTraceModal
        open={traceOpen}
        trace={goalTrace}
        busy={busy}
        error={traceError}
        onSupersedeRetry={supersedeAndRetryPlanner}
        onClose={() => { setTraceOpen(false); setGoalTrace(null); setTraceError(null) }}
      />
      <GoalSettingsModal open={settingsOpen} goal={settingsGoal} draft={settingsDraft} busy={busy} error={settingsError} setDraft={setSettingsDraft} onClose={closeSettingsEditor} onSave={saveGoalSettings} />
      <RequirementCandidateDetailModal
        candidate={candidateModal.candidateDetail}
        loading={candidateModal.candidateDetailLoading}
        error={candidateModal.candidateDetailError}
        busy={busy}
        onClose={candidateModal.closeCandidateDetail}
        onAction={actOnCandidate}
      />
      {loading && <div className="text-sm text-[color:var(--ops-text-muted)]">Loading planning control plane...</div>}
    </div>
  )
}
