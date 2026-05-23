import { RecurringWorkflow, RecurringWorkflowRun } from '../api'
import { OverlayModal, StateBadge } from '../components/workbench'
import { presentationFor } from './schedulesPresentation'
import { JsonBlock, recordFrom, ScheduleJsonObject, scheduleLabel, tone } from './SchedulesPageShared'

export type InspectorRun = RecurringWorkflowRun & {
  optimistic?: boolean
}

export type InspectorAnchor = {
  runId?: number | null
  completedAt?: string | null
  optimisticRun?: InspectorRun | null
}

export type InspectorTab = 'history' | 'configuration'

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString()
}

function LocalTime({ value }: Readonly<{ value: string | null | undefined }>) {
  return <time dateTime={value || ''} title={value || ''}>{formatTime(value)}</time>
}

function runTone(run: InspectorRun | null, fallbackStatus: string) {
  if (run?.optimistic) return 'running'
  if (run?.dry_run) return 'muted'
  return tone(run?.status || fallbackStatus)
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

export function chooseAnchoredRun(runs: InspectorRun[], anchor?: InspectorAnchor | null) {
  if (anchor?.runId !== undefined && anchor.runId !== null) {
    const byId = runs.find((run) => run.id === anchor.runId)
    if (byId) return byId
  }
  if (anchor?.completedAt) {
    const byTime = runs.find((run) => run.completed_at === anchor.completedAt || run.started_at === anchor.completedAt)
    if (byTime) return byTime
  }
  return runs[0] || null
}

export function RunInspectorModal({
  open,
  workflow,
  run,
  runs,
  loading,
  error,
  activeTab,
  onClose,
  onSelectRun,
  onRefresh,
  onSelectTab,
  onRunWorkflow,
}: Readonly<{
  open: boolean
  workflow: RecurringWorkflow | null
  run: InspectorRun | null
  runs: InspectorRun[]
  loading: boolean
  error: string | null
  activeTab: InspectorTab
  onClose: () => void
  onSelectRun: (run: InspectorRun) => void
  onRefresh: () => void
  onSelectTab: (tab: InspectorTab) => void
  onRunWorkflow: (workflow: RecurringWorkflow, dryRun: boolean) => void
}>) {
  const summaryLines = summarizeRun(run, workflow?.last_result)
  const tabClass = (tab: InspectorTab) => [
    'rounded-xl px-4 py-2 text-sm font-semibold transition',
    activeTab === tab ? 'bg-cyan-300/15 text-cyan-50' : 'text-[color:var(--ops-text-muted)] hover:bg-white/[0.06] hover:text-[color:var(--ops-text-body)]',
  ].join(' ')
  return (
    <OverlayModal
      open={open}
      eyebrow="Run Inspector"
      title={workflow?.display_name || 'Run Inspector'}
      description="最近 50 次运行的可读战报。Raw params / result 保留在 Debug details。"
      actions={workflow ? (
        <button
          type="button"
          disabled={loading}
          onClick={onRefresh}
          className="rounded-2xl border border-white/12 bg-white/[0.04] px-4 py-2 text-sm font-semibold text-[color:var(--ops-text-body)] hover:bg-white/[0.08] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      ) : null}
      onClose={onClose}
    >
      {workflow ? (
        <div className="space-y-5" data-testid="schedule-run-inspector">
          <div className="flex flex-wrap gap-2 rounded-2xl border border-white/8 bg-white/[0.03] p-1">
            <button type="button" className={tabClass('history')} onClick={() => onSelectTab('history')}>Run History</button>
            <button type="button" className={tabClass('configuration')} onClick={() => onSelectTab('configuration')}>Configuration</button>
          </div>
          {loading ? <div className="rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.08] px-4 py-3 text-sm text-cyan-100">Loading run history...</div> : null}
          {error ? (
            <div className="rounded-2xl border border-rose-300/25 bg-rose-400/[0.08] px-4 py-3 text-sm text-rose-100">
              <div>{error}</div>
              <button type="button" className="mt-3 rounded-xl border border-rose-200/30 px-3 py-2 text-xs font-semibold" onClick={onRefresh}>Retry Load History</button>
            </div>
          ) : null}
          {activeTab === 'history' ? (
            <>
              <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <StateBadge tone={runTone(run, workflow.health_status)}>{run?.optimistic ? 'running' : run?.status || workflow.health_status}</StateBadge>
                  {run?.dry_run ? <StateBadge tone="validating">DRY RUN</StateBadge> : run ? <StateBadge tone="ready">REAL RUN</StateBadge> : null}
                  <StateBadge tone="muted">{workflow.workflow_key}</StateBadge>
                </div>
                {run?.optimistic ? (
                  <div className="mt-4 rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.08] p-4 text-sm leading-6 text-cyan-100">
                    Running... this optimistic entry will be replaced by the recorded run when the request completes.
                  </div>
                ) : null}
                {run?.dry_run ? (
                  <div className="mt-4 rounded-2xl border border-amber-300/20 bg-amber-300/[0.08] p-4 text-sm leading-6 text-amber-100">
                    Sandbox preview only. No auto-start or acceptance dispatch.
                  </div>
                ) : null}
                <div className="mt-4 grid gap-3 text-sm md:grid-cols-2">
                  <div><span className="text-[color:var(--ops-text-caption)]">Started:</span> <LocalTime value={run?.started_at || workflow.last_run_at} /></div>
                  <div><span className="text-[color:var(--ops-text-caption)]">Completed:</span> <LocalTime value={run?.completed_at || null} /></div>
                  <div><span className="text-[color:var(--ops-text-caption)]">Triggered by:</span> {run?.triggered_by || 'last result'}</div>
                  <div><span className="text-[color:var(--ops-text-caption)]">Duration:</span> {run?.duration_ms ?? 0}ms</div>
                </div>
                <div className="mt-5 rounded-2xl border border-white/8 bg-white/[0.03] p-4">
                  <div className="machine-label text-[color:var(--ops-text-caption)]">Summary</div>
                  <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-[color:var(--ops-text-body)]">
                    {summaryLines.map((line) => <li key={line}>{line}</li>)}
                  </ul>
                </div>
                {run?.error_excerpt ? <div className="mt-4 rounded-2xl border border-rose-300/25 bg-rose-400/[0.08] p-4 text-sm text-rose-100">{run.error_excerpt}</div> : null}
                {run && !run.optimistic ? (
                  <div className="mt-4 flex justify-end">
                    <button
                      type="button"
                      className="rounded-xl border border-cyan-300/30 bg-cyan-300/[0.08] px-4 py-2 text-sm font-semibold text-cyan-50 hover:bg-cyan-300/[0.14]"
                      onClick={() => onRunWorkflow(workflow, Boolean(run.dry_run))}
                    >
                      Re-run with this context
                    </button>
                  </div>
                ) : null}
              </div>
              <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="machine-label text-[color:var(--ops-text-caption)]">Run History</div>
                  <div className="text-xs text-[color:var(--ops-text-muted)]">Showing latest 50 runs</div>
                </div>
                <div className="mt-4 space-y-2">
                  {runs.map((item) => (
                    <button key={item.id} type="button" className="flex w-full items-center justify-between gap-3 rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3 text-left hover:bg-white/[0.06]" onClick={() => onSelectRun(item)}>
                      <span className="flex min-w-0 flex-wrap items-center gap-2 text-sm text-[color:var(--ops-text-body)]">
                        <span>#{item.optimistic ? 'pending' : item.id}</span>
                        <span>·</span>
                        {item.optimistic ? <StateBadge tone="running">Running...</StateBadge> : null}
                        {item.dry_run ? <StateBadge tone="validating">DRY RUN</StateBadge> : <StateBadge tone="ready">REAL RUN</StateBadge>}
                        <span className="truncate">{item.dry_run ? 'safe preview' : item.triggered_by}</span>
                      </span>
                      <span className="shrink-0 text-xs text-[color:var(--ops-text-muted)]"><LocalTime value={item.started_at} /></span>
                    </button>
                  ))}
                  {!runs.length && !loading ? <div className="rounded-2xl border border-dashed border-white/14 px-4 py-6 text-sm text-[color:var(--ops-text-muted)]">No runs recorded yet. Use Dry Run to create a safe history entry.</div> : null}
                </div>
              </div>
              <details className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
                <summary className="cursor-pointer text-sm font-semibold text-[color:var(--ops-text-title)]">Debug params / result JSON</summary>
                <div className="mt-4 grid gap-4 xl:grid-cols-2">
                  <JsonBlock value={run?.params || {}} />
                  <JsonBlock value={run?.result || workflow.last_result || {}} />
                </div>
              </details>
            </>
          ) : (
            <div className="space-y-5" data-testid="schedule-configuration-panel">
              <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <StateBadge tone={tone(workflow.health_status)}>{workflow.health_status}</StateBadge>
                  <StateBadge tone="muted">{scheduleLabel(workflow)}</StateBadge>
                  <StateBadge tone="muted">{workflow.owner_role}</StateBadge>
                </div>
                <p className="mt-4 text-sm leading-6 text-[color:var(--ops-text-muted)]">{workflow.description}</p>
                <div className="mt-5"><IpoFlow workflow={workflow} /></div>
              </div>
              <div className="rounded-3xl border border-cyan-300/20 bg-cyan-300/[0.06] p-5">
                <div className="machine-label text-cyan-100">Run Controls</div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <button type="button" aria-label="Dry Run" onClick={() => onRunWorkflow(workflow, true)} className="rounded-2xl border border-white/12 bg-white/[0.04] p-4 text-left hover:bg-white/[0.08]">
                    <div className="font-semibold text-[color:var(--ops-text-title)]">Dry Run</div>
                    <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">安全预演：记录历史，不 auto-start requirement，不 dispatch acceptance。</div>
                  </button>
                  <button type="button" aria-label="Run Now" onClick={() => onRunWorkflow(workflow, false)} className="rounded-2xl border border-cyan-300/35 bg-cyan-300/[0.12] p-4 text-left hover:bg-cyan-300/[0.18]">
                    <div className="font-semibold text-cyan-50">Run Now</div>
                    <div className="mt-2 text-sm leading-6 text-cyan-100/80">立即执行：仍使用安全默认值，Human Gate 和高风险约束仍生效。</div>
                  </button>
                </div>
              </div>
              <details className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
                <summary className="cursor-pointer text-sm font-semibold text-[color:var(--ops-text-title)]">Read-only configuration JSON</summary>
                <div className="mt-4 grid gap-4 xl:grid-cols-2">
                  <JsonBlock value={{ schedule: workflow.schedule, input_query: workflow.input_query, output_action: workflow.output_action }} />
                  <JsonBlock value={{ escalation_rule: workflow.escalation_rule, validation_signal: workflow.validation_signal, status: workflow.status }} />
                </div>
              </details>
            </div>
          )}
        </div>
      ) : <div className="text-sm text-[color:var(--ops-text-muted)]">选择一个任务查看运行战报。</div>}
    </OverlayModal>
  )
}
