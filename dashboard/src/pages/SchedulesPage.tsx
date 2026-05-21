import { useEffect, useMemo, useRef, useState } from 'react'
import { api, RecurringWorkflow, RecurringWorkflowHealth, RecurringWorkflowRun, ScheduleTemplate } from '../api'
import { ActionButton, CockpitPanel, MetricTile } from '../components/controlPlane'
import { ConfirmDialog, StateBadge, useToast } from '../components/workbench'
import { hasPresentation, LaneKey, laneDefinitions, presentationFor } from './schedulesPresentation'
import { CreateScheduleModal, EditScheduleModal, ScheduleDraft, ScheduleEditDraft, ScheduleTaskTable, TemplatesPanel } from './SchedulesPageTaskPanels'
import { chooseAnchoredRun, InspectorAnchor, InspectorRun, InspectorTab, RunInspectorModal } from './SchedulesPageRunInspector'
import { recordFrom, ScheduleJsonObject, scheduleLabel, tone } from './SchedulesPageShared'

type ScheduleCenterTab = 'overview' | 'tasks' | 'history' | 'templates'

type PendingRunConfirmation = {
  workflow: RecurringWorkflow
  dryRun: boolean
} | null

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString()
}

function LocalTime({ value }: Readonly<{ value: string | null | undefined }>) {
  return <time dateTime={value || ''} title={value || ''}>{formatTime(value)}</time>
}

function delayLabel(from: string | null | undefined, now = new Date()) {
  if (!from) return ''
  const date = new Date(from)
  if (Number.isNaN(date.getTime())) return ''
  const diffMs = Math.max(0, now.getTime() - date.getTime())
  const days = Math.floor(diffMs / 86_400_000)
  const hours = Math.floor((diffMs % 86_400_000) / 3_600_000)
  const minutes = Math.floor((diffMs % 3_600_000) / 60_000)
  if (days) return `${days}d ${hours}h`
  if (hours) return `${hours}h ${minutes}m`
  return `${Math.max(1, minutes)}m`
}

function lastResultStatus(workflow: RecurringWorkflow) {
  return String(recordFrom(workflow.last_result).status || '').toLowerCase()
}

function needsAttention(workflow: RecurringWorkflow) {
  const lastStatus = lastResultStatus(workflow)
  return workflow.health_status === 'failed' || workflow.is_due || ['failed', 'error', 'skipped_locked'].includes(lastStatus)
}

function overdueInfo(workflow: RecurringWorkflow, now = new Date()) {
  const next = workflow.next_run_at ? new Date(workflow.next_run_at) : null
  const isOverdue = Boolean(workflow.is_due && next && !Number.isNaN(next.getTime()) && next.getTime() < now.getTime())
  const result = recordFrom(workflow.last_result)
  const lastStatus = String(result.status || '').toLowerCase()
  const rawReason = result.reason || result.error || (workflow.health_status === 'failed' ? 'Recent run failed' : '')
  const reason = lastStatus === 'skipped_locked'
    ? 'Worker locked'
    : String(rawReason)
  return {
    isOverdue,
    delay: isOverdue ? delayLabel(workflow.next_run_at, now) : '',
    reason: isOverdue ? reason || 'Scheduler tick missed after next_run_at' : '',
    severity: isOverdue && next && now.getTime() - next.getTime() > 86_400_000 ? 'blocked' : 'validating',
  }
}

function summarizeRun(run: RecurringWorkflowRun | null, fallbackResult?: ScheduleJsonObject) {
  const result = run ? recordFrom(run.result) : recordFrom(fallbackResult)
  if (!run && !Object.keys(result).length) return ['No run result recorded yet.']
  const lines: string[] = []
  const knownKeys = [
    'created_candidate_ids',
    'validation_failed_candidate_ids',
    'auto_materialized_requirement_ids',
    'auto_started_workflow_run_ids',
    'created_requirement_ids',
    'materialized_requirement_ids',
    'reused_requirement_ids',
    'pushed_task_ids',
    'archived_requirement_ids',
    'follow_up_actions',
    'operator_attention_items',
    'acceptance_candidates',
    'repo_findings',
    'ops_findings',
    'created_candidate_id',
    'materialized_requirement_id',
    'started_workflow_run_id',
    'pr_expected',
    'blocked_reason',
    'bundle_item_count',
    'incident_count',
    'reason',
  ]
  for (const key of knownKeys) {
    const value = result[key]
    if (Array.isArray(value)) lines.push(`${key}: ${value.length}${value.length ? ` (${value.slice(0, 5).join(', ')})` : ''}`)
    else if (value !== undefined && value !== null && value !== '') lines.push(`${key}: ${String(value)}`)
  }
  if (run?.error_excerpt) lines.push(`error: ${run.error_excerpt}`)
  return lines.length ? lines.slice(0, 7) : [`status: ${String(result.status || run?.status || 'recorded')}`]
}

function HealthStrip({ health, stats }: Readonly<{ health: RecurringWorkflowHealth | null; stats: Record<string, number> }>) {
  const dispatcher = recordFrom(health?.notification_dispatcher)
  const registry = recordFrom(health?.recurring_registry)
  return (
    <section className="grid gap-3 md:grid-cols-5" data-testid="schedule-health-overview">
      <MetricTile label="Total Jobs" value={stats.total} detail="registered recurring workflows" tone="info" />
      <MetricTile label="Due" value={stats.due} detail="needs a scheduler tick or manual review" tone={stats.due ? 'warning' : 'muted'} />
      <MetricTile label="Failed" value={stats.failed} detail="requires operator attention" tone={stats.failed ? 'danger' : 'muted'} />
      <MetricTile label="Registry" value={String(registry.active ?? stats.active)} detail="active recurring definitions" tone="success" />
      <MetricTile label="Queue" value={String(dispatcher.queued_count ?? 0)} detail="notification dispatcher backlog" tone={Number(dispatcher.queued_count || 0) ? 'warning' : 'muted'} />
    </section>
  )
}

function IpoFlow({ workflow }: Readonly<{ workflow: RecurringWorkflow }>) {
  const presentation = presentationFor(workflow)
  return (
    <div className="grid gap-2 text-xs text-[color:var(--ops-text-muted)] md:grid-cols-[1fr_auto_1fr_auto_1fr]" data-testid="schedule-ipo-flow">
      <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-3 py-3">
        <div className="machine-label text-[color:var(--ops-text-caption)]">Input</div>
        <div className="mt-2 leading-5 text-[color:var(--ops-text-body)]">{presentation.input}</div>
      </div>
      <div className="hidden items-center text-cyan-300/70 md:flex">→</div>
      <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-3 py-3">
        <div className="machine-label text-[color:var(--ops-text-caption)]">Action</div>
        <div className="mt-2 leading-5 text-[color:var(--ops-text-body)]">{presentation.action}</div>
      </div>
      <div className="hidden items-center text-cyan-300/70 md:flex">→</div>
      <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-3 py-3">
        <div className="machine-label text-[color:var(--ops-text-caption)]">Output</div>
        <div className="mt-2 leading-5 text-[color:var(--ops-text-body)]">{presentation.outputs.join(' | ')}</div>
      </div>
    </div>
  )
}

function CompactIpoFlow({ workflow }: Readonly<{ workflow: RecurringWorkflow }>) {
  const presentation = presentationFor(workflow)
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-[color:var(--ops-text-muted)]" data-testid="schedule-compact-ipo">
      <span className="rounded-full border border-cyan-300/20 bg-cyan-300/[0.06] px-2.5 py-1"><span className="text-cyan-100">Input</span> {presentation.input}</span>
      <span className="text-cyan-300/60">→</span>
      <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1"><span className="text-[color:var(--ops-text-body)]">Action</span> {presentation.action}</span>
      <span className="text-cyan-300/60">→</span>
      <span className="rounded-full border border-emerald-300/20 bg-emerald-300/[0.06] px-2.5 py-1"><span className="text-emerald-100">Output</span> {presentation.outputs.join(' | ')}</span>
    </div>
  )
}

function ScheduledJobCard({
  workflow,
  inAttention = false,
  running,
  latestRun,
  onRun,
  onInspect,
}: Readonly<{
  workflow: RecurringWorkflow
  inAttention?: boolean
  running: boolean
  latestRun: InspectorRun | null
  onRun: (workflow: RecurringWorkflow, dryRun: boolean) => void
  onInspect: (workflow: RecurringWorkflow, anchor?: InspectorAnchor) => void
}>) {
  const presentation = presentationFor(workflow)
  const missingMetadata = !hasPresentation(workflow.workflow_key)
  const summary = summarizeRun(latestRun, workflow.last_result)[0]
  const overdue = overdueInfo(workflow)
  return (
    <article
      className={[
        'rounded-[24px] border bg-[color:var(--ops-panel)] p-4 transition',
        inAttention ? 'border-rose-300/35 shadow-[0_0_0_1px_rgba(251,113,133,0.08)]' : 'border-[color:var(--ops-stroke-soft)]',
        running ? 'opacity-80 ring-1 ring-cyan-300/30' : '',
      ].join(' ')}
      data-testid="scheduled-job-card"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StateBadge tone={tone(workflow.health_status)}>{running ? 'running' : workflow.health_status}</StateBadge>
            {overdue.isOverdue ? <StateBadge tone={overdue.severity === 'blocked' ? 'blocked' : 'validating'}>OVERDUE</StateBadge> : workflow.is_due ? <StateBadge tone="validating">due</StateBadge> : null}
            {missingMetadata ? <StateBadge tone="validating">Missing Presentation Metadata</StateBadge> : null}
          </div>
          <button
            type="button"
            className="mt-3 block text-left text-lg font-semibold text-[color:var(--ops-text-title)] hover:text-cyan-100"
            onClick={() => onInspect(workflow, { runId: latestRun?.id, completedAt: workflow.last_run_at })}
          >
            {workflow.display_name}
          </button>
          <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{workflow.workflow_key}</div>
        </div>
        <div className="flex items-start gap-3 text-right text-xs text-[color:var(--ops-text-muted)]">
          <div>
            <div className="machine-label text-[color:var(--ops-text-caption)]">{presentation.label}</div>
            <div className="mt-2">Owner: {workflow.owner_role}</div>
            <div className="mt-1">{scheduleLabel(workflow)}</div>
          </div>
          <button
            type="button"
            disabled={running}
            title="Execute now with safety defaults. Human gates and production/funds/auth constraints still apply."
            onClick={() => onRun(workflow, false)}
            className="rounded-xl border border-cyan-300/40 bg-cyan-400/15 px-3 py-2 text-sm font-semibold text-cyan-50 shadow-[0_0_18px_rgba(34,211,238,0.1)] transition hover:bg-cyan-400/25 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-cyan-400/15"
          >
            {running ? 'Running...' : 'Run Now'}
          </button>
        </div>
      </div>

      <div className="mt-4"><CompactIpoFlow workflow={workflow} /></div>

      {overdue.isOverdue ? (
        <div className="mt-4 rounded-2xl border border-rose-300/25 bg-rose-400/[0.08] px-3 py-2 text-sm text-rose-100" data-testid="schedule-overdue-alert">
          <strong>Delayed {overdue.delay}</strong>
          <span className="ml-2 text-rose-100/80">{overdue.reason}</span>
        </div>
      ) : null}

      <details className="mt-4 rounded-2xl border border-white/8 bg-white/[0.025] px-3 py-2">
        <summary className="cursor-pointer text-xs font-semibold text-[color:var(--ops-text-body)]">Show definition</summary>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)]">{workflow.description}</p>
        <div className="mt-3"><IpoFlow workflow={workflow} /></div>
      </details>

      <div className="mt-4 grid gap-3 border-t border-white/8 pt-4 text-xs text-[color:var(--ops-text-muted)] md:grid-cols-2">
        <button
          type="button"
          className="rounded-2xl border border-white/8 bg-white/[0.03] px-3 py-3 text-left hover:bg-white/[0.06]"
          onClick={() => onInspect(workflow, { runId: latestRun?.id, completedAt: workflow.last_run_at })}
        >
          <div className="machine-label text-[color:var(--ops-text-caption)]">Last Run</div>
          <div className="mt-2 text-[color:var(--ops-text-body)]">{workflow.last_run_at ? <LocalTime value={workflow.last_run_at} /> : 'No run yet'}</div>
          <div className="mt-1 line-clamp-1">{summary}</div>
        </button>
        <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-3 py-3">
          <div className="machine-label text-[color:var(--ops-text-caption)]">Next Run</div>
          <div className="mt-2 text-[color:var(--ops-text-body)]"><LocalTime value={workflow.next_run_at} /></div>
          <div className="mt-1">Status: {workflow.status}</div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap justify-end gap-2">
        {running ? <span className="rounded-xl border border-cyan-300/25 bg-cyan-300/10 px-4 py-2.5 text-sm font-semibold text-cyan-100">Running...</span> : null}
        <ActionButton onClick={() => onInspect(workflow, { runId: latestRun?.id })}>View History</ActionButton>
      </div>
    </article>
  )
}

function AttentionGhostRow({ workflow, onInspect }: Readonly<{ workflow: RecurringWorkflow; onInspect: (workflow: RecurringWorkflow, anchor?: InspectorAnchor) => void }>) {
  return (
    <button
      type="button"
      className="flex w-full items-center justify-between rounded-2xl border border-white/8 bg-white/[0.025] px-4 py-3 text-left text-sm text-[color:var(--ops-text-muted)] hover:bg-white/[0.05]"
      onClick={() => onInspect(workflow, { completedAt: workflow.last_run_at })}
    >
      <span className="font-semibold text-[color:var(--ops-text-body)]">{workflow.display_name}</span>
      <span className="text-xs text-rose-100/80">Elevated to Attention</span>
    </button>
  )
}

function ScheduleLane({
  title,
  description,
  workflows,
  attentionKeys,
  runningKey,
  latestRuns,
  onRun,
  onInspect,
}: Readonly<{
  title: string
  description: string
  workflows: RecurringWorkflow[]
  attentionKeys: Set<string>
  runningKey: string | null
  latestRuns: Record<string, InspectorRun | null>
  onRun: (workflow: RecurringWorkflow, dryRun: boolean) => void
  onInspect: (workflow: RecurringWorkflow, anchor?: InspectorAnchor) => void
}>) {
  if (!workflows.length) return null
  const isAttentionLane = title === 'Attention Required'
  const visibleWorkflows = isAttentionLane ? workflows : workflows.filter((workflow) => !attentionKeys.has(workflow.workflow_key))
  const ghostWorkflows = isAttentionLane ? [] : workflows.filter((workflow) => attentionKeys.has(workflow.workflow_key))
  if (!visibleWorkflows.length && !ghostWorkflows.length) return null
  return (
    <CockpitPanel eyebrow="Scheduled Lane" title={`${title} (${visibleWorkflows.length + ghostWorkflows.length})`} description={description} className={isAttentionLane ? 'border-rose-300/25' : ''}>
      <div className="grid gap-4">
        {visibleWorkflows.map((workflow) => (
          <ScheduledJobCard
            key={`${title}-${workflow.workflow_key}`}
            workflow={workflow}
            inAttention={isAttentionLane}
            running={runningKey === workflow.workflow_key}
            latestRun={latestRuns[workflow.workflow_key] || null}
            onRun={onRun}
            onInspect={onInspect}
          />
        ))}
        {ghostWorkflows.map((workflow) => (
          <AttentionGhostRow key={`${title}-${workflow.workflow_key}-ghost`} workflow={workflow} onInspect={onInspect} />
        ))}
      </div>
    </CockpitPanel>
  )
}

function ScheduleTabs({ active, onChange }: Readonly<{ active: ScheduleCenterTab; onChange: (tab: ScheduleCenterTab) => void }>) {
  const tabs: Array<{ key: ScheduleCenterTab; label: string }> = [
    { key: 'overview', label: 'Overview' },
    { key: 'tasks', label: 'Tasks' },
    { key: 'history', label: 'Run History' },
    { key: 'templates', label: 'Templates' },
  ]
  return (
    <div className="flex flex-wrap gap-2">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          className={[
            'rounded-2xl border px-4 py-2 text-sm font-semibold transition',
            active === tab.key
              ? 'border-cyan-300/35 bg-cyan-300/[0.12] text-cyan-50'
              : 'border-white/10 text-[color:var(--ops-text-muted)] hover:bg-white/[0.055]',
          ].join(' ')}
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

function ScheduleFilters({
  category,
  status,
  risk,
  onCategory,
  onStatus,
  onRisk,
}: Readonly<{
  category: string
  status: string
  risk: string
  onCategory: (value: string) => void
  onStatus: (value: string) => void
  onRisk: (value: string) => void
}>) {
  return (
    <div className="flex flex-wrap gap-3">
      <select value={category} onChange={(event) => onCategory(event.target.value)} className="rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-2 text-sm">
        <option value="all">All categories</option>
        <option value="infra_cleanup">Infra Cleanup</option>
        <option value="release_runner">Release / Runner</option>
        <option value="system_health">System Health</option>
        <option value="planning">Planning</option>
        <option value="growth">Growth</option>
      </select>
      <select value={status} onChange={(event) => onStatus(event.target.value)} className="rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-2 text-sm">
        <option value="all">All statuses</option>
        <option value="active">Active</option>
        <option value="paused">Paused</option>
        <option value="disabled">Disabled</option>
      </select>
      <select value={risk} onChange={(event) => onRisk(event.target.value)} className="rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-2 text-sm">
        <option value="all">All risk</option>
        <option value="high">High</option>
        <option value="medium">Medium</option>
        <option value="low">Low</option>
      </select>
    </div>
  )
}

export default function SchedulesPage() {
  const toast = useToast()
  const [items, setItems] = useState<RecurringWorkflow[]>([])
  const [templates, setTemplates] = useState<ScheduleTemplate[]>([])
  const [health, setHealth] = useState<RecurringWorkflowHealth | null>(null)
  const [activeTab, setActiveTab] = useState<ScheduleCenterTab>('overview')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [riskFilter, setRiskFilter] = useState('all')
  const [inspectorWorkflow, setInspectorWorkflow] = useState<RecurringWorkflow | null>(null)
  const [inspectorRun, setInspectorRun] = useState<InspectorRun | null>(null)
  const [inspectorRuns, setInspectorRuns] = useState<InspectorRun[]>([])
  const [optimisticRun, setOptimisticRun] = useState<InspectorRun | null>(null)
  const [inspectorLoading, setInspectorLoading] = useState(false)
  const [inspectorError, setInspectorError] = useState<string | null>(null)
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('history')
  const [loading, setLoading] = useState(true)
  const [runningKey, setRunningKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pendingRunConfirmation, setPendingRunConfirmation] = useState<PendingRunConfirmation>(null)
  const [createTemplate, setCreateTemplate] = useState<ScheduleTemplate | null>(null)
  const [createDraft, setCreateDraft] = useState<ScheduleDraft | null>(null)
  const [createBusy, setCreateBusy] = useState(false)
  const [editDraft, setEditDraft] = useState<ScheduleEditDraft | null>(null)
  const [editBusy, setEditBusy] = useState(false)
  const inspectorWorkflowKeyRef = useRef<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const [nextItems, nextHealth] = await Promise.all([
        api.getSchedules(),
        api.getRecurringWorkflowHealth(),
      ])
      setItems(nextItems)
      setHealth(nextHealth)
      api.getScheduleTemplates().then(setTemplates).catch(() => setTemplates([]))
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载定时任务失败')
    } finally {
      setLoading(false)
    }
  }

  async function loadRuns(workflowKey: string) {
    return api.getScheduleRuns(workflowKey, 50)
  }

  useEffect(() => {
    load().catch(() => {})
  }, [])

  const displayRuns = useMemo<InspectorRun[]>(() => {
    if (!optimisticRun) return inspectorRuns
    return [optimisticRun, ...inspectorRuns.filter((run) => run.id !== optimisticRun.id)]
  }, [inspectorRuns, optimisticRun])

  const latestRuns = useMemo<Record<string, InspectorRun | null>>(() => {
    const next: Record<string, InspectorRun | null> = {}
    if (inspectorWorkflow && displayRuns.length) next[inspectorWorkflow.workflow_key] = displayRuns[0]
    return next
  }, [inspectorWorkflow, displayRuns])

  async function loadInspectorRuns(workflow: RecurringWorkflow, anchor?: InspectorAnchor, options?: { preserveMissingAnchor?: boolean }) {
    inspectorWorkflowKeyRef.current = workflow.workflow_key
    setInspectorWorkflow(workflow)
    setInspectorLoading(true)
    setInspectorError(null)
    try {
      const nextRuns = await loadRuns(workflow.workflow_key)
      if (inspectorWorkflowKeyRef.current !== workflow.workflow_key) return
      setInspectorRuns(nextRuns)
      const hasAnchor = Boolean(anchor?.runId || anchor?.completedAt)
      const anchoredRun = hasAnchor ? chooseAnchoredRun(nextRuns, anchor) : null
      const anchorFound = Boolean(anchoredRun && (anchoredRun.id === anchor?.runId || anchoredRun.completed_at === anchor?.completedAt || anchoredRun.started_at === anchor?.completedAt))
      const nextRun = anchoredRun || nextRuns[0] || null
      if (hasAnchor && !anchorFound && nextRuns.length && options?.preserveMissingAnchor) {
        toast.info('Previously selected run is no longer in the latest 50 history.')
      }
      setInspectorRun(nextRun)
    } catch (err) {
      if (inspectorWorkflowKeyRef.current !== workflow.workflow_key) return
      setInspectorError(err instanceof Error ? err.message : '加载运行历史失败')
    } finally {
      if (inspectorWorkflowKeyRef.current === workflow.workflow_key) setInspectorLoading(false)
    }
  }

  async function openInspector(workflow: RecurringWorkflow, anchor?: InspectorAnchor) {
    setInspectorTab('history')
    setOptimisticRun(anchor?.optimisticRun || null)
    setInspectorRun(anchor?.optimisticRun || null)
    setInspectorRuns([])
    await loadInspectorRuns(workflow, anchor)
  }

  async function refreshInspector() {
    if (!inspectorWorkflow) return
    await loadInspectorRuns(inspectorWorkflow, { runId: inspectorRun?.optimistic ? null : inspectorRun?.id }, { preserveMissingAnchor: true })
  }

  function closeInspector() {
    inspectorWorkflowKeyRef.current = null
    setInspectorWorkflow(null)
    setInspectorRun(null)
    setInspectorRuns([])
    setOptimisticRun(null)
    setInspectorLoading(false)
    setInspectorError(null)
    setInspectorTab('history')
  }

  async function runWorkflow(workflow: RecurringWorkflow, dryRun: boolean) {
    const risky = ['bug_log_sweep', 'morning_intake_sweep', 'forum_feedback_sweep'].includes(workflow.workflow_key)
    if (!dryRun && risky) {
      setPendingRunConfirmation({ workflow, dryRun })
      return
    }
    await executeWorkflow(workflow, dryRun)
  }

  async function executeWorkflow(workflow: RecurringWorkflow, dryRun: boolean) {
    const optimistic: InspectorRun = {
      id: -Date.now(),
      workflow_key: workflow.workflow_key,
      status: 'running',
      triggered_by: 'operator',
      dry_run: dryRun,
      params: {
        dry_run: dryRun,
        auto_start: false,
        auto_dispatch_acceptance: false,
      },
      result: {
        status: 'running',
        safe_defaults: true,
      },
      error_excerpt: null,
      started_at: new Date().toISOString(),
      completed_at: null,
      duration_ms: 0,
      optimistic: true,
    }
    inspectorWorkflowKeyRef.current = workflow.workflow_key
    setInspectorWorkflow(workflow)
    setInspectorRun(optimistic)
    setOptimisticRun(optimistic)
    setInspectorTab('history')
    setInspectorRuns([])
    setInspectorError(null)
    setInspectorLoading(false)
    setRunningKey(workflow.workflow_key)
    setError(null)
    try {
      const result = await api.runSchedule(workflow.workflow_key, {
        dry_run: dryRun,
        auto_start: false,
        auto_dispatch_acceptance: false,
      })
      await load()
      const nextRuns = await loadRuns(workflow.workflow_key)
      const createdRun = nextRuns.find((run) => run.id === result.run_id) || nextRuns[0] || null
      if (inspectorWorkflowKeyRef.current === workflow.workflow_key) {
        setOptimisticRun(null)
        setInspectorWorkflow(workflow)
        setInspectorRuns(nextRuns)
        setInspectorRun(createdRun)
      } else {
        toast.success(`${workflow.display_name} completed.`)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '运行定时任务失败'
      setError(message)
      if (inspectorWorkflowKeyRef.current === workflow.workflow_key) {
        setOptimisticRun(null)
        setInspectorError(message)
      } else {
        toast.error(`${workflow.display_name} failed: ${message}`)
      }
    } finally {
      setRunningKey(null)
    }
  }

  function openCreateFromTemplate(template: ScheduleTemplate) {
    const suffix = Date.now().toString().slice(-5)
    setCreateTemplate(template)
    setCreateDraft({
      template_key: template.template_key,
      workflow_key: `custom_${template.template_key}_${suffix}`,
      display_name: template.display_name,
      owner_role: 'runtime_reliability_engineer',
      suggested_local_time: String(recordFrom(template.schedule).suggested_local_time || '12:00'),
    })
  }

  async function submitCreateSchedule() {
    if (!createDraft) return
    setCreateBusy(true)
    try {
      await api.createSchedule({
        template_key: createDraft.template_key,
        workflow_key: createDraft.workflow_key,
        display_name: createDraft.display_name,
        owner_role: createDraft.owner_role,
        schedule: { cadence: 'daily', suggested_local_time: createDraft.suggested_local_time },
      })
      setCreateDraft(null)
      setCreateTemplate(null)
      toast.success('Schedule created.')
      await load()
      setActiveTab('tasks')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '创建定时任务失败')
    } finally {
      setCreateBusy(false)
    }
  }

  function openEditSchedule(workflow: RecurringWorkflow) {
    const schedule = recordFrom(workflow.schedule)
    setEditDraft({
      workflow_key: workflow.workflow_key,
      display_name: workflow.display_name,
      owner_role: workflow.owner_role,
      suggested_local_time: String(schedule.suggested_local_time || '12:00'),
      status: workflow.status,
    })
  }

  async function submitEditSchedule() {
    if (!editDraft) return
    setEditBusy(true)
    try {
      await api.updateSchedule(editDraft.workflow_key, {
        display_name: editDraft.display_name,
        owner_role: editDraft.owner_role,
        status: editDraft.status,
        schedule: { cadence: 'daily', suggested_local_time: editDraft.suggested_local_time },
      })
      toast.success('Schedule updated.')
      setEditDraft(null)
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '修改定时任务失败')
    } finally {
      setEditBusy(false)
    }
  }

  async function toggleScheduleStatus(workflow: RecurringWorkflow) {
    try {
      const nextStatus = workflow.status === 'active' ? 'disabled' : 'active'
      await api.updateSchedule(workflow.workflow_key, { status: nextStatus })
      toast.success(`${workflow.display_name} ${nextStatus}.`)
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '更新定时任务失败')
    }
  }

  async function deleteCustomSchedule(workflow: RecurringWorkflow) {
    try {
      await api.deleteSchedule(workflow.workflow_key)
      toast.success(`${workflow.display_name} deleted.`)
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除定时任务失败')
    }
  }

  const stats = {
    total: items.length,
    active: items.filter((item) => item.status === 'active').length,
    due: items.filter((item) => item.is_due).length,
    failed: items.filter((item) => item.health_status === 'failed').length,
  }

  const attentionItems = items.filter(needsAttention)
  const attentionKeys = new Set(attentionItems.map((item) => item.workflow_key))
  const grouped = laneDefinitions.reduce<Record<LaneKey, RecurringWorkflow[]>>((acc, lane) => {
    acc[lane.key] = []
    return acc
  }, {} as Record<LaneKey, RecurringWorkflow[]>)
  grouped.attention = attentionItems
  for (const item of items) {
    const presentation = presentationFor(item)
    grouped[presentation.lane].push(item)
  }

  const filteredItems = items.filter((item) => {
    if (categoryFilter !== 'all' && item.category !== categoryFilter) return false
    if (statusFilter !== 'all' && item.status !== statusFilter) return false
    if (riskFilter !== 'all' && item.risk_level !== riskFilter) return false
    return true
  })

  return (
    <div className="space-y-5" data-testid="schedules-page">
      <CockpitPanel
        eyebrow="Schedule Center"
        title="定时任务控制台"
        description="这里不是 crontab 列表，而是可查询、可执行、可观测、可模板化维护的后台自动化控制台。"
        actions={<div className="flex flex-wrap gap-2"><ActionButton onClick={() => setActiveTab('templates')}>新增定时任务</ActionButton><ActionButton onClick={() => load().catch(() => {})}>刷新</ActionButton></div>}
      >
        <ScheduleTabs active={activeTab} onChange={setActiveTab} />
        <div className="mt-4">
          <ScheduleFilters
            category={categoryFilter}
            status={statusFilter}
            risk={riskFilter}
            onCategory={setCategoryFilter}
            onStatus={setStatusFilter}
            onRisk={setRiskFilter}
          />
        </div>
        <HealthStrip health={health} stats={stats} />
      </CockpitPanel>

      {error ? <div className="rounded-2xl border border-rose-300/25 bg-rose-400/[0.08] px-4 py-3 text-sm text-rose-100">{error}</div> : null}
      {loading ? <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-6 text-center text-sm text-[color:var(--ops-text-muted)]">加载中…</div> : null}

      {activeTab === 'overview' ? laneDefinitions.map((lane) => (
          <ScheduleLane
            key={lane.key}
            title={lane.title}
            description={lane.description}
            workflows={grouped[lane.key].filter((workflow) => filteredItems.some((item) => item.workflow_key === workflow.workflow_key))}
            attentionKeys={attentionKeys}
            runningKey={runningKey}
            latestRuns={latestRuns}
            onRun={runWorkflow}
            onInspect={openInspector}
          />
        )) : null}

      {activeTab === 'tasks' ? (
        <ScheduleTaskTable
          workflows={filteredItems}
          runningKey={runningKey}
          onInspect={openInspector}
          onRun={runWorkflow}
          onEdit={openEditSchedule}
          onToggleStatus={(workflow) => toggleScheduleStatus(workflow).catch(() => {})}
          onDelete={(workflow) => deleteCustomSchedule(workflow).catch(() => {})}
        />
      ) : null}

      {activeTab === 'history' ? (
        <ScheduleTaskTable
          workflows={filteredItems}
          runningKey={runningKey}
          onInspect={openInspector}
          onRun={runWorkflow}
          onEdit={openEditSchedule}
          onToggleStatus={(workflow) => toggleScheduleStatus(workflow).catch(() => {})}
          onDelete={(workflow) => deleteCustomSchedule(workflow).catch(() => {})}
        />
      ) : null}

      {activeTab === 'templates' ? <TemplatesPanel templates={templates} onCreate={openCreateFromTemplate} /> : null}

      {!loading && !items.length ? <CockpitPanel eyebrow="Empty State" title="暂无 recurring workflow" description="后台自动化 registry 还没有同步出任务定义。"><div /></CockpitPanel> : null}

      <RunInspectorModal
        open={Boolean(inspectorWorkflow)}
        workflow={inspectorWorkflow}
        run={inspectorRun}
        runs={displayRuns}
        loading={inspectorLoading}
        error={inspectorError}
        activeTab={inspectorTab}
        onClose={closeInspector}
        onSelectRun={setInspectorRun}
        onRefresh={refreshInspector}
        onSelectTab={setInspectorTab}
        onRunWorkflow={runWorkflow}
      />
      <ConfirmDialog
        open={Boolean(pendingRunConfirmation)}
        title="确认运行高影响任务"
        description={`${pendingRunConfirmation?.workflow.display_name || '该任务'} 可能创建候选、复用 requirement 或推送审核草稿。默认不会 auto-start。`}
        confirmLabel="确认运行"
        cancelLabel="取消"
        onClose={() => setPendingRunConfirmation(null)}
        onConfirm={() => {
          const next = pendingRunConfirmation
          setPendingRunConfirmation(null)
          if (next) executeWorkflow(next.workflow, next.dryRun).catch(() => {})
        }}
      />
      <CreateScheduleModal
        draft={createDraft}
        template={createTemplate}
        busy={createBusy}
        onChange={(patch) => setCreateDraft((current) => current ? { ...current, ...patch } : current)}
        onClose={() => {
          setCreateDraft(null)
          setCreateTemplate(null)
        }}
        onSubmit={() => submitCreateSchedule().catch(() => {})}
      />
      <EditScheduleModal
        draft={editDraft}
        busy={editBusy}
        onChange={(patch) => setEditDraft((current) => current ? { ...current, ...patch } : current)}
        onClose={() => setEditDraft(null)}
        onSubmit={() => submitEditSchedule().catch(() => {})}
      />
    </div>
  )
}
