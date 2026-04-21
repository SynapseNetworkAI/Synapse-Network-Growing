import { useEffect, useMemo, useRef, useState } from 'react'
import { api, RecurringWorkflow, RecurringWorkflowHealth, RecurringWorkflowRun } from '../api'
import { ActionButton, CockpitPanel, MetricTile } from '../components/controlPlane'
import { OverlayDrawer, StateBadge, useToast } from '../components/workbench'

type LaneKey = 'attention' | 'strategy' | 'execution' | 'intake' | 'health' | 'uncategorized'

type Presentation = {
  lane: Exclude<LaneKey, 'attention'>
  label: string
  input: string
  action: string
  outputs: string[]
}

type InspectorRun = RecurringWorkflowRun & {
  optimistic?: boolean
}

type InspectorAnchor = {
  runId?: number | null
  completedAt?: string | null
  optimisticRun?: InspectorRun | null
}

type InspectorTab = 'history' | 'configuration'

const laneDefinitions: Array<{ key: LaneKey; title: string; description: string }> = [
  { key: 'attention', title: 'Attention Required', description: '失败、到期、锁冲突或最近运行异常会自动置顶，不被业务分组淹没。' },
  { key: 'strategy', title: 'Strategy & Planning', description: '公司目标、Planner Sweep、周度复盘这些“大脑层”自动化。' },
  { key: 'execution', title: 'Execution & Dispatch', description: '推进需求队列、审批巡检、收尾压缩这些 COO duty cycle。' },
  { key: 'intake', title: 'Intake & Support', description: '外部信号、论坛反馈、早间输入这些前台触角。' },
  { key: 'health', title: 'System Health & Reliability', description: '日志转 bug、重复需求清理和系统免疫。' },
  { key: 'uncategorized', title: 'New / Uncategorized Initiates', description: '新增任务还没有 presentation metadata，仍可运行和追踪，但需要补齐说明。' },
]

const presentationMap: Record<string, Presentation> = {
  goal_planner_sweep: {
    lane: 'strategy',
    label: '生成候选需求',
    input: 'Active goals + Operating Manifest',
    action: 'Planner Agent 拆解目标',
    outputs: ['Requirement Candidates', 'Fail-Closed Intercepts'],
  },
  weekly_operating_review: {
    lane: 'strategy',
    label: '生成周报与复盘',
    input: '上周运行、需求、事故、门禁',
    action: '刷新 company review',
    outputs: ['Operating Review', 'Next-cycle bundle'],
  },
  dispatcher_loop: {
    lane: 'execution',
    label: '推进状态机',
    input: 'Ready / blocked / paused requirements',
    action: '扫描队列并提出推进动作',
    outputs: ['Follow-up actions', 'Stuck work signals'],
  },
  approval_sweep: {
    lane: 'execution',
    label: '审批巡检',
    input: 'Pending gates + stale approvals',
    action: '刷新 human gate backlog',
    outputs: ['Approval reminders', 'Gate health'],
  },
  closeout_and_compact_sweep: {
    lane: 'execution',
    label: '上下文归档',
    input: 'Done / paused / blocked requirements',
    action: '收尾检查与上下文压缩',
    outputs: ['Acceptance candidates', 'Compaction snapshots'],
  },
  morning_intake_sweep: {
    lane: 'intake',
    label: '生成待办',
    input: 'Signals + review bundle + bug intake',
    action: '刷新输入源并创建高置信事项',
    outputs: ['Requirements', 'Operator attention items'],
  },
  forum_feedback_sweep: {
    lane: 'intake',
    label: '客服回复 / 提 Bug',
    input: 'Forum unreplied response tasks',
    action: '分类、提取、生成回复建议',
    outputs: ['Reply drafts', 'Bug candidates'],
  },
  bug_log_sweep: {
    lane: 'health',
    label: '日志转 Bug 工单',
    input: 'Runtime logs + workflow incidents',
    action: '归一化错误并尝试 materialize',
    outputs: ['Bug backlog', 'Materialized requirements'],
  },
  requirement_family_cleanup_sweep: {
    lane: 'health',
    label: '去重归档',
    input: 'Draft / ready / paused requirement families',
    action: '清理重复实验需求',
    outputs: ['Archived requirements', 'Merge recommendations'],
  },
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

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

function tone(value: string) {
  if (['healthy', 'succeeded', 'completed', 'active'].includes(value)) return 'ready'
  if (['due', 'running'].includes(value)) return 'running'
  if (['failed', 'error', 'dead_letter'].includes(value)) return 'blocked'
  return 'muted'
}

function runTone(run: InspectorRun | null, fallbackStatus: string) {
  if (run?.optimistic) return 'running'
  if (run?.dry_run) return 'muted'
  return tone(run?.status || fallbackStatus)
}

function chooseAnchoredRun(runs: InspectorRun[], anchor?: InspectorAnchor | null) {
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

function JsonBlock({ value }: Readonly<{ value: unknown }>) {
  const text = JSON.stringify(value ?? {}, null, 2)
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2">
        <span className="machine-label text-slate-400">JSON</span>
        <button
          type="button"
          className="rounded-lg border border-white/12 px-2 py-1 text-xs font-semibold text-slate-200 hover:bg-white/10"
          onClick={() => copyJson(value)}
        >
          Copy JSON
        </button>
      </div>
      <pre className="max-h-[360px] overflow-auto p-4 text-xs leading-relaxed text-slate-100">
        {text}
      </pre>
    </div>
  )
}

function copyJson(value: unknown) {
  const text = JSON.stringify(value ?? {}, null, 2)
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    void navigator.clipboard.writeText(text)
  }
}

function scheduleLabel(workflow: RecurringWorkflow) {
  const schedule = workflow.schedule || {}
  const cadence = String(schedule.cadence || '-')
  if (cadence === 'interval') return `Every ${String(schedule.interval_minutes || '?')} min`
  if (cadence === 'hourly') return `Every ${String(schedule.interval_hours || '?')} h`
  if (cadence === 'daily') return `Daily ${String(schedule.suggested_local_time || '')}`.trim()
  if (cadence === 'weekly') return `Weekly ${String(schedule.day || '')} ${String(schedule.suggested_local_time || '')}`.trim()
  return cadence
}

function presentationFor(workflow: RecurringWorkflow): Presentation {
  const mapped = presentationMap[workflow.workflow_key]
  if (mapped) return mapped
  const input = Object.keys(record(workflow.input_query)).slice(0, 3).join(', ') || 'custom input query'
  const action = String(record(workflow.output_action).kind || workflow.description || 'custom recurring action')
  const output = String(record(workflow.validation_signal).success_metric || 'custom output')
  return {
    lane: 'uncategorized',
    label: 'Missing Presentation Metadata',
    input,
    action,
    outputs: [output],
  }
}

function lastResultStatus(workflow: RecurringWorkflow) {
  return String(record(workflow.last_result).status || '').toLowerCase()
}

function needsAttention(workflow: RecurringWorkflow) {
  const lastStatus = lastResultStatus(workflow)
  return workflow.health_status === 'failed' || workflow.is_due || ['failed', 'error', 'skipped_locked'].includes(lastStatus)
}

function overdueInfo(workflow: RecurringWorkflow, now = new Date()) {
  const next = workflow.next_run_at ? new Date(workflow.next_run_at) : null
  const isOverdue = Boolean(workflow.is_due && next && !Number.isNaN(next.getTime()) && next.getTime() < now.getTime())
  const result = record(workflow.last_result)
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

function summarizeRun(run: RecurringWorkflowRun | null, fallbackResult?: Record<string, unknown>) {
  const result = run ? record(run.result) : record(fallbackResult)
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
  const dispatcher = record(health?.notification_dispatcher)
  const registry = record(health?.recurring_registry)
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
  const missingMetadata = !presentationMap[workflow.workflow_key]
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

function RunInspectorDrawer({
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
    <OverlayDrawer
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
                <button
                  key={item.id}
                  type="button"
                  className={[
                    'flex w-full items-center justify-between gap-3 rounded-2xl border px-4 py-3 text-left hover:bg-white/[0.06]',
                    item.id === run?.id ? 'border-cyan-300/35 bg-cyan-300/[0.08]' : item.dry_run ? 'border-amber-300/20 bg-amber-300/[0.05]' : 'border-white/8 bg-white/[0.03]',
                  ].join(' ')}
                  onClick={() => onSelectRun(item)}
                >
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
                  <button
                    type="button"
                    aria-label="Dry Run"
                    title="Safe preview. Records history. Does not auto-start requirement or dispatch acceptance."
                    onClick={() => onRunWorkflow(workflow, true)}
                    className="rounded-2xl border border-white/12 bg-white/[0.04] p-4 text-left hover:bg-white/[0.08]"
                  >
                    <div className="font-semibold text-[color:var(--ops-text-title)]">Dry Run</div>
                    <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">安全预演：记录历史，不 auto-start requirement，不 dispatch acceptance。</div>
                  </button>
                  <button
                    type="button"
                    aria-label="Run Now"
                    title="Execute now with safety defaults. Human gates and production/funds/auth constraints still apply."
                    onClick={() => onRunWorkflow(workflow, false)}
                    className="rounded-2xl border border-cyan-300/35 bg-cyan-300/[0.12] p-4 text-left hover:bg-cyan-300/[0.18]"
                  >
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
    </OverlayDrawer>
  )
}

export default function SchedulesPage() {
  const toast = useToast()
  const [items, setItems] = useState<RecurringWorkflow[]>([])
  const [health, setHealth] = useState<RecurringWorkflowHealth | null>(null)
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
  const inspectorWorkflowKeyRef = useRef<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const [nextItems, nextHealth] = await Promise.all([
        api.getRecurringWorkflows(),
        api.getRecurringWorkflowHealth(),
      ])
      setItems(nextItems)
      setHealth(nextHealth)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载定时任务失败')
    } finally {
      setLoading(false)
    }
  }

  async function loadRuns(workflowKey: string) {
    return api.getRecurringWorkflowRuns(workflowKey, 50)
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
      const confirmed = window.confirm(`${workflow.display_name} 可能创建候选、复用 requirement 或推送审核草稿。默认不会 auto-start，确认现在运行吗？`)
      if (!confirmed) return
    }
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
      const result = await api.runRecurringWorkflow(workflow.workflow_key, {
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

  return (
    <div className="space-y-5" data-testid="schedules-page">
      <CockpitPanel
        eyebrow="Scheduled Jobs Operations Center"
        title="定时任务"
        description="这里不是 crontab 列表，而是虚拟部门的自动化运转大屏：看输入、动作、产出、异常和最近战报。"
        actions={<ActionButton onClick={() => load().catch(() => {})}>刷新</ActionButton>}
      >
        <HealthStrip health={health} stats={stats} />
      </CockpitPanel>

      {error ? <div className="rounded-2xl border border-rose-300/25 bg-rose-400/[0.08] px-4 py-3 text-sm text-rose-100">{error}</div> : null}
      {loading ? <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-6 text-center text-sm text-[color:var(--ops-text-muted)]">加载中…</div> : null}

      {laneDefinitions.map((lane) => (
        <ScheduleLane
          key={lane.key}
          title={lane.title}
          description={lane.description}
          workflows={grouped[lane.key]}
          attentionKeys={attentionKeys}
          runningKey={runningKey}
          latestRuns={latestRuns}
          onRun={runWorkflow}
          onInspect={openInspector}
        />
      ))}

      {!loading && !items.length ? <CockpitPanel eyebrow="Empty State" title="暂无 recurring workflow" description="后台自动化 registry 还没有同步出任务定义。"><div /></CockpitPanel> : null}

      <RunInspectorDrawer
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
    </div>
  )
}
