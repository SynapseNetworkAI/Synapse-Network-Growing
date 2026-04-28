import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, DeclarativeHumanGate, DeclarativeWorkflowDefinition, DeclarativeWorkflowRunDetail, DeclarativeWorkflowTimelineItem } from '../api'
import { useToast } from '../components/workbench'
import {
  artifactDisplayTitle,
  buildCorrectnessItems,
  buildNextAction,
  buildStepViewModels,
  hasSimulatedEvidence,
  StepViewModel,
} from '../workflows/workflowStepExplain'

type WorkflowTab = 'overview' | 'timeline' | 'evidence' | 'gates' | 'debug'

const WORKFLOW_TABS: Array<{ key: WorkflowTab; label: string }> = [
  { key: 'overview', label: 'Overview' },
  { key: 'timeline', label: 'Timeline' },
  { key: 'evidence', label: 'Evidence' },
  { key: 'gates', label: 'Gates & Delivery' },
  { key: 'debug', label: 'Debug' },
]

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function useNowTick(enabled: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!enabled) return undefined
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [enabled])
  return now
}

function elapsedSecondsSince(value: unknown, now: number) {
  const startedAt = typeof value === 'string' ? Date.parse(value) : Number.NaN
  if (!Number.isFinite(startedAt)) return 0
  return Math.max(0, Math.floor((now - startedAt) / 1000))
}

function prettyJson(value: unknown) {
  if (value == null) return '{}'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function statusClass(status: string) {
  if (['completed', 'done', 'passed', 'succeeded'].includes(status)) return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  if (['failed', 'error', 'rejected'].includes(status)) return 'border-rose-200 bg-rose-50 text-rose-700'
  if (['pending', 'awaiting_operator', 'awaiting_human'].includes(status)) return 'border-amber-200 bg-amber-50 text-amber-700'
  if (status === 'not_started') return 'border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-subtle)] text-slate-500'
  return 'border-blue-200 bg-blue-50 text-blue-700'
}

function isTrulyCompleted(detail: DeclarativeWorkflowRunDetail) {
  return Boolean(detail.is_truly_completed ?? (['succeeded', 'completed', 'done'].includes(detail.status) && detail.pending_human_gate_count === 0))
}

function hasPendingGate(detail: DeclarativeWorkflowRunDetail) {
  return detail.pending_human_gate_count > 0 || Boolean(detail.needs_human)
}

function actionClass(tone: 'ready' | 'blocked' | 'running' | 'muted') {
  if (tone === 'ready') return 'border-emerald-400/40 bg-emerald-500/16 text-emerald-100'
  if (tone === 'blocked') return 'border-rose-400/45 bg-rose-500/20 text-rose-50'
  if (tone === 'running') return 'border-cyan-300/40 bg-cyan-300/16 text-cyan-100'
  return 'border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] text-[color:var(--ops-text-title)]'
}

type GateBusyState = { id: number; decision: string } | null
type OperatorSummary = NonNullable<DeclarativeWorkflowRunDetail['operator_decision_summary']>
type DecisionFeedback = { tone: 'info' | 'success' | 'warning' | 'error'; message: string } | null
type DeliveryView = {
  visible: boolean
  status: string
  prStatus: string
  branch: string
  baseBranch: string
  vcsStatus: string
  rebaseStatus: string
  humanCommitsDetected: boolean
  blockerType: string
  simulated: boolean
  prUrl: string
  compareUrl: string
  changedFilesCount: number
  commandEvidenceCount: number
  syncAction: string
}

const TRUSTED_DELIVERY_STATES = new Set([
  'delivery_blocked',
  'delivery_blocked_no_changes',
  'pr_opened',
  'pr_created',
  'pr_updated',
  'delivered',
  'completed',
  'created',
  'updated',
  'draft',
  'open',
])

function compactString(value: unknown) {
  return String(value || '').trim()
}

function statusToneClass(tone: OperatorSummary['status_tone']) {
  if (tone === 'ok') return 'border-emerald-300/35 bg-emerald-400/10 text-emerald-100'
  if (tone === 'blocked') return 'border-rose-300/45 bg-rose-500/16 text-rose-50'
  if (tone === 'running') return 'border-cyan-300/40 bg-cyan-300/12 text-cyan-100'
  return 'border-amber-300/40 bg-amber-400/12 text-amber-100'
}

function workflowDecisionSummary(detail: DeclarativeWorkflowRunDetail): OperatorSummary {
  if (detail.operator_decision_summary) return detail.operator_decision_summary
  const blocked = hasPendingGate(detail)
  return {
    headline: `Agent 正在处理：${detail.requirement_title || detail.workflow_key}`,
    status_label: blocked ? '已暂停等待指示' : isTrulyCompleted(detail) ? '已完成' : '运行中',
    status_tone: blocked ? 'blocked' : isTrulyCompleted(detail) ? 'ok' : 'running',
    what_happened: blocked ? '工作流停在人工门禁，等待你确认下一步。' : `工作流当前状态为 ${detail.status}。`,
    root_cause_kind: null,
    root_cause: null,
    error_excerpt: null,
    recommended_next_action: blocked ? '根据证据选择继续修复、驳回当前结果，或确认你已人工处理。' : '继续观察证据和交付状态。',
    can_continue_retry: blocked,
    can_reject: blocked,
    can_supersede_retry: false,
    can_terminate: false,
  }
}

function workflowDeliveryView(detail: DeclarativeWorkflowRunDetail): DeliveryView {
  const pr = (detail.blackboard.pr || {}) as Record<string, unknown>
  const delivery = detail.delivery_summary
  const sync = (pr.sync || {}) as Record<string, unknown>
  const vcs = (pr.vcs || {}) as Record<string, unknown>
  const prUrl = compactString(delivery?.pr_url || detail.delivery_pr_url || detail.pr_url || pr.url || sync.pr_url)
  const compareUrl = compactString(delivery?.compare_url || detail.delivery_compare_url || pr.compare_url || sync.compare_url)
  const branch = compactString(delivery?.branch_name || detail.delivery_branch || pr.branch_name || sync.branch_name || sync.head_branch || vcs.branch_name)
  const baseBranch = compactString(detail.delivery_base_branch || (delivery as Record<string, unknown> | undefined)?.base_branch || pr.base_branch || sync.base_branch || vcs.base_branch)
  const prStatus = compactString(delivery?.pr_status || pr.pr_status || sync.pr_status || pr.status)
  const syncAction = compactString(delivery?.sync_action || pr.sync_action || sync.sync_action)
  const statusCandidates = [
    detail.delivery_status,
    delivery?.release_status,
    detail.release_status,
    prStatus,
    syncAction ? `pr_${syncAction}` : '',
    syncAction,
  ]
    .map((item) => compactString(item).toLowerCase())
    .filter(Boolean)
  const blockerType = compactString(delivery?.delivery_blocker_type || vcs.delivery_blocker_type)
  const humanCommitsDetected = Boolean(delivery?.human_commits_detected || sync.human_commits_detected || vcs.human_commits_detected)
  const rebaseStatus = compactString(delivery?.rebase_status || vcs.rebase_status)
  const simulated = Boolean(delivery?.simulated || detail.delivery_is_simulated || detail.simulated_delivery)
  const hasTrustedStatus = statusCandidates.some((status) => TRUSTED_DELIVERY_STATES.has(status))
  const hasExplicitBlocker = Boolean(blockerType || statusCandidates.includes('awaiting_operator') && (detail.pending_human_gate_count > 0 || detail.needs_human))
  const hasRealPr = Boolean(prUrl && (statusCandidates.includes('pr_opened') || statusCandidates.includes('pr_created') || statusCandidates.includes('pr_updated') || TRUSTED_DELIVERY_STATES.has(prStatus.toLowerCase()) || syncAction))
  const visible = hasTrustedStatus || hasExplicitBlocker || hasRealPr
  const status = compactString(statusCandidates.find((item) => TRUSTED_DELIVERY_STATES.has(item)) || detail.delivery_status || delivery?.release_status || detail.release_status || blockerType)
  return {
    visible,
    status,
    prStatus,
    branch,
    baseBranch,
    vcsStatus: compactString(vcs.status || delivery?.release_status || detail.delivery_status),
    rebaseStatus,
    humanCommitsDetected,
    blockerType,
    simulated,
    prUrl,
    compareUrl,
    changedFilesCount: Number(detail.changed_files_count || 0),
    commandEvidenceCount: Number(detail.command_evidence_count || 0),
    syncAction,
  }
}

function hasDeliverySignal(detail: DeclarativeWorkflowRunDetail) {
  const deliveryView = workflowDeliveryView(detail)
  return Boolean(
    deliveryView.visible
    || ((detail.blackboard.pr as Record<string, unknown> | undefined)?.blockers as unknown[] | undefined)?.length,
  )
}

function gateDecisionLabel(decision: string, summary: OperatorSummary, detail: DeclarativeWorkflowRunDetail) {
  if (decision === 'continue_retry') return '继续让 Agent 修复'
  if (decision === 'reject') return '驳回当前结果'
  if (decision === 'approve') {
    if (detail.delivery_summary?.pr_url || detail.pr_url) return '确认已人工处理'
    return summary.status_tone === 'blocked' || summary.root_cause ? '确认并放行' : '确认通过'
  }
  return decision
}

function gateDecisionClass(decision: string, summary: OperatorSummary) {
  if (decision === 'continue_retry') return 'border-cyan-300/45 bg-cyan-300/16 text-cyan-100'
  if (decision === 'reject') return 'border-rose-300/45 bg-rose-500/10 text-rose-100'
  if (decision === 'approve' && summary.status_tone === 'ok') return 'border-emerald-300/40 bg-emerald-400/10 text-emerald-100'
  return 'border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] text-[color:var(--ops-text-body)]'
}

function Panel({ title, children, testId, action }: { title: string; children: ReactNode; testId?: string; action?: ReactNode }) {
  return (
    <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5" data-testid={testId}>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{title}</h3>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )
}

function JsonBlock({ value, maxHeight = 'max-h-[260px]' }: Readonly<{ value: unknown; maxHeight?: string }>) {
  return <pre className={`${maxHeight} overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100`}>{prettyJson(value)}</pre>
}

function AcceptanceMatrixRuntimePanel({ detail }: Readonly<{ detail: DeclarativeWorkflowRunDetail }>) {
  const matrix = (detail.blackboard.acceptance_matrix || {}) as Record<string, unknown>
  const status = String(matrix.status || '')
  const currentStartedAt = matrix.current_command_started_at
  const isRunning = status === 'running' && typeof currentStartedAt === 'string'
  const now = useNowTick(isRunning)
  const elapsed = elapsedSecondsSince(currentStartedAt, now)
  const failureSummary = String(matrix.failure_summary || '')
  if (!status) return null

  return (
    <Panel title="Acceptance Matrix Runtime" testId="workflow-acceptance-matrix-runtime">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className={['rounded-full border px-3 py-1 text-xs', statusClass(status === 'running' ? 'pending' : status)].join(' ')}>
            {status}
          </span>
          {matrix.verify_phase_started_at ? <span className="text-xs text-[color:var(--ops-text-caption)]">verify started {formatTime(String(matrix.verify_phase_started_at))}</span> : null}
        </div>
        {isRunning ? (
          <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
            <div className="font-semibold">Running acceptance command for {elapsed}s</div>
            <div className="mt-2 text-xs uppercase tracking-[0.16em]">Step</div>
            <div className="mt-1 font-mono text-xs">{String(matrix.current_step_key || '-')}</div>
            <div className="mt-2 text-xs uppercase tracking-[0.16em]">Command</div>
            <div className="mt-1 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-xs">{String(matrix.current_command || '-')}</div>
          </div>
        ) : null}
        {status === 'failed' && failureSummary ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            {failureSummary.includes('timed out') ? 'Timed out: ' : 'Fail Closed: '}
            {failureSummary}
          </div>
        ) : null}
        {status === 'passed' ? <div className="text-sm text-[color:var(--ops-text-muted)]">Planner acceptance matrix has passing workflow evidence for this run.</div> : null}
      </div>
    </Panel>
  )
}

function WorkflowRunHeader({
  detail,
  nextAction,
  onRefresh,
  onNavigateRequirement,
  onSetTab,
}: Readonly<{
  detail: DeclarativeWorkflowRunDetail
  nextAction: ReturnType<typeof buildNextAction>
  onRefresh: () => void
  onNavigateRequirement: () => void
  onSetTab: (tab: WorkflowTab) => void
}>) {
  const pr = (detail.blackboard.pr || {}) as Record<string, unknown>
  const summary = workflowDecisionSummary(detail)
  return (
    <section className="sticky top-0 z-10 rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5 shadow-sm backdrop-blur" data-testid="workflow-run-header">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-4xl">
          <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Operator Decision Workbench</div>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">{summary.headline}</h2>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className={['rounded-full border px-3 py-1 text-sm font-semibold', statusToneClass(summary.status_tone)].join(' ')}>{summary.status_label}</span>
            <span className="text-sm text-[color:var(--ops-text-muted)]">需求 #{detail.requirement_id} · {formatTime(detail.updated_at)}</span>
            {pr.url ? <a className="rounded-full border border-cyan-300/35 bg-cyan-300/10 px-3 py-1 text-sm text-cyan-100" href={String(pr.url)} target="_blank" rel="noreferrer">Open PR</a> : null}
          </div>
          <details className="mt-3 text-xs text-[color:var(--ops-text-caption)]">
            <summary className="cursor-pointer">Technical details</summary>
            <div className="mt-2 flex flex-wrap gap-2">
              <span>run #{detail.id}</span>
              <span>workflow {detail.workflow_key}</span>
              <span>Current state {detail.current_state}</span>
              <span>Resolution {detail.resolution || '-'}</span>
              <span>risk {detail.risk_level}</span>
            </div>
          </details>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          {nextAction.href ? (
            <a className={['rounded-xl border px-4 py-2.5 text-sm font-semibold', actionClass(nextAction.tone)].join(' ')} href={nextAction.href} target="_blank" rel="noreferrer">
              {nextAction.label}
            </a>
          ) : (
            <button type="button" className={['rounded-xl border px-4 py-2.5 text-sm font-semibold', actionClass(nextAction.tone)].join(' ')} onClick={() => nextAction.tab && onSetTab(nextAction.tab)}>
              {nextAction.label}
            </button>
          )}
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={onNavigateRequirement}>
            查看需求
          </button>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={onRefresh}>
            刷新
          </button>
        </div>
      </div>
    </section>
  )
}

function WorkflowRunTabs({ activeTab, onChange }: Readonly<{ activeTab: WorkflowTab; onChange: (tab: WorkflowTab) => void }>) {
  return (
    <div className="flex flex-wrap gap-2 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-2" data-testid="workflow-run-tabs">
      {WORKFLOW_TABS.map((tab) => (
        <button
          key={tab.key}
          type="button"
          className={[
            'rounded-xl px-4 py-2 text-sm font-medium transition',
            activeTab === tab.key
              ? 'bg-cyan-300/15 text-cyan-100 shadow-[0_0_0_1px_rgba(103,232,249,0.32)]'
              : 'text-[color:var(--ops-text-muted)] hover:bg-[color:var(--ops-panel-subtle)] hover:text-[color:var(--ops-text-title)]',
          ].join(' ')}
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

function RunBriefPanel({ detail, nextAction }: Readonly<{ detail: DeclarativeWorkflowRunDetail; nextAction: ReturnType<typeof buildNextAction> }>) {
  const pr = (detail.blackboard.pr || {}) as Record<string, unknown>
  const observation = (detail.blackboard.observation || {}) as Record<string, unknown>
  const outcome = hasPendingGate(detail)
    ? '需要 operator 审查后才能继续。'
    : isTrulyCompleted(detail)
      ? '工作流已完成，关键验证与收口状态已记录。'
      : `工作流当前停在 ${detail.current_state}。`
  return (
    <Panel title="Run Brief" testId="workflow-run-brief">
      <div className="space-y-4">
        <p className="max-w-4xl text-lg leading-8 text-[color:var(--ops-text-title)]">
          Run #{detail.id} 执行 `{detail.workflow_key}`，关联需求 #{detail.requirement_id}「{detail.requirement_title || '未命名需求'}」。{outcome}
        </p>
        <div className="grid gap-3 md:grid-cols-4">
          <MiniFact label="Outcome" value={detail.outcome_label || detail.status} />
          <MiniFact label="Current State" value={detail.current_state} />
          <MiniFact label="Resolution" value={detail.resolution || '-'} />
          <MiniFact label="PR" value={detail.simulated_delivery ? 'simulated' : pr.url ? 'created' : pr.created ? 'created without url' : '-'} />
          <MiniFact label="Observation" value={observation.restored ? 'restored' : observation.not_restored ? 'not restored' : '-'} />
        </div>
        <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Next Action</div>
          <div className="mt-2 text-base font-semibold text-[color:var(--ops-text-title)]">{nextAction.label}</div>
          <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{nextAction.detail}</div>
        </div>
      </div>
    </Panel>
  )
}

function MiniFact({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className="mt-2 truncate text-sm font-semibold text-[color:var(--ops-text-title)]">{value}</div>
    </div>
  )
}

function CompletionArchivePanel({
  detail,
  onArchive,
  onCreateFollowup,
}: Readonly<{
  detail: DeclarativeWorkflowRunDetail
  onArchive: () => void
  onCreateFollowup: () => void
}>) {
  const completed = isTrulyCompleted(detail)
  const prUrl = detail.delivery_summary?.pr_url || detail.pr_url || String(((detail.blackboard.pr || {}) as Record<string, unknown>).url || '')
  const archiveLabel = hasPendingGate(detail) ? 'Pause / Hide from active' : 'Archive Run'
  return (
    <Panel title="Outcome Summary" testId="workflow-outcome-summary">
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div>
          <p className="text-base leading-7 text-[color:var(--ops-text-title)]">
            {completed
              ? '这次 workflow 已进入完成档案。后续不删除运行证据，只通过归档从默认管理视图隐藏。'
              : detail.status === 'failed'
                ? '这次 workflow 未完成。优先检查失败 atom、verification evidence 和下一步修复建议。'
                : hasPendingGate(detail)
                  ? '这次 workflow 正在等待人工门禁。请在 Gates & Delivery 里处理决策。'
                  : '这次 workflow 仍在运行或暂停中。请查看 Timeline 和当前 atom 输出。'}
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <MiniFact label="Atoms" value={String(detail.atom_count ?? detail.atom_invocations.length)} />
            <MiniFact label="Artifacts" value={String(detail.artifact_count ?? detail.artifacts.length)} />
            <MiniFact label="Human Gates" value={String(detail.human_gates.length)} />
            <MiniFact label="Goal" value={String(detail.goal_key || '-')} />
          </div>
        </div>
        <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Next Actions</div>
          <p className="mt-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">
            后续需求用于把本次 workflow 未覆盖的新问题、遗留风险或下一步工作重新放回 Requirement 链路；它不会修改当前 run 的完成状态。
          </p>
          <div className="mt-3 grid gap-2">
            {prUrl ? (
              <a className="rounded-xl bg-blue-600 px-4 py-2.5 text-center text-sm font-semibold text-white" href={prUrl} target="_blank" rel="noreferrer">
                Open PR
              </a>
            ) : null}
            <button
              type="button"
              className="rounded-xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-2.5 text-sm font-medium text-[color:var(--ops-text-body)] hover:bg-[color:var(--ops-panel-strong)]"
              title="创建一个新的后续需求，用于处理当前 workflow 之外的遗留事项或下一步动作。"
              onClick={onCreateFollowup}
            >
              创建后续需求
            </button>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-2.5 text-sm text-[color:var(--ops-text-body)] hover:bg-[color:var(--ops-panel-strong)] disabled:bg-[color:var(--ops-panel-subtle)]" disabled={Boolean(detail.archived_at)} onClick={onArchive}>
              {detail.archived_at ? (hasPendingGate(detail) ? 'Hidden while gate pending' : 'Archived') : archiveLabel}
            </button>
          </div>
        </div>
      </div>
    </Panel>
  )
}

function CorrectnessPanel({ detail }: Readonly<{ detail: DeclarativeWorkflowRunDetail }>) {
  const items = buildCorrectnessItems(detail)
  const simulated = hasSimulatedEvidence(detail)
  return (
    <Panel title="Correctness" testId="workflow-correctness-panel">
      <div className="grid gap-3 md:grid-cols-2">
        {items.map((item) => (
          <div key={item.key} className={['rounded-2xl border px-4 py-3', item.passed ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'].join(' ')}>
            <div className="flex items-center gap-2">
              <span className={['h-2.5 w-2.5 rounded-full', item.passed ? 'bg-emerald-500' : 'bg-amber-500'].join(' ')} />
              <span className="text-sm font-semibold text-[color:var(--ops-text-title)]">{item.label}</span>
            </div>
            <div className="mt-1 text-xs text-[color:var(--ops-text-muted)]">{item.detail}</div>
          </div>
        ))}
      </div>
      {simulated ? (
        <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          This run contains simulated evidence. Do not treat it as production proof.
        </div>
      ) : null}
      {detail.observability_warnings?.length ? (
        <div className="mt-4 space-y-2" data-testid="workflow-observability-warnings">
          {detail.observability_warnings.map((warning) => (
            <div key={warning} className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              {warning}
            </div>
          ))}
        </div>
      ) : null}
    </Panel>
  )
}

function AgentOutputPanel({ detail }: Readonly<{ detail: DeclarativeWorkflowRunDetail }>) {
  const outputs = detail.agent_outputs || []
  return (
    <Panel title="Agent Output" testId="workflow-agent-output-panel">
      <div className="space-y-3">
        {outputs.map((output) => (
          <details key={`${output.state_key}-${output.raw_artifact_id || output.atom_key}`} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4" open>
            <summary className="cursor-pointer text-sm font-semibold text-[color:var(--ops-text-title)]">
              {output.state_key}: {output.agent_name}
            </summary>
            <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">{output.summary || output.status}</div>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              <div>
                <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Parsed Writes</div>
                <div className="mt-2">
                  <JsonBlock value={output.parsed_writes || {}} maxHeight="max-h-[220px]" />
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Raw Output</div>
                <pre className="mt-2 max-h-[220px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{output.raw_output || 'No raw output artifact recorded.'}</pre>
              </div>
            </div>
            <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">
              artifact #{output.raw_artifact_id || '-'} · {output.input_summary || 'no input summary'} · {formatTime(output.created_at)}
            </div>
          </details>
        ))}
        {!outputs.length ? <div className="text-sm text-[color:var(--ops-text-muted)]">No agent output artifacts recorded.</div> : null}
      </div>
    </Panel>
  )
}

function ChangedFilesPanel({ detail }: Readonly<{ detail: DeclarativeWorkflowRunDetail }>) {
  const summary = detail.changed_files_summary
  const files = summary?.changed_files || []
  return (
    <Panel title="Changed Files / Diff" testId="workflow-changed-files-panel">
      {summary?.planned_change_only ? (
        <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Planned change only. This is not proof of an actual committed diff.
        </div>
      ) : null}
      <div className="grid gap-3 md:grid-cols-4">
        <MiniFact label="Changed" value={String(summary?.changed_files_count ?? files.length)} />
        <MiniFact label="Added" value={String(summary?.added_files?.length ?? 0)} />
        <MiniFact label="Modified" value={String(summary?.modified_files?.length ?? 0)} />
        <MiniFact label="Deleted" value={String(summary?.deleted_files?.length ?? 0)} />
      </div>
      <div className="mt-4 space-y-2">
        {files.map((file) => (
          <div key={file} className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2 font-mono text-sm text-[color:var(--ops-text-title)]">
            {file}
          </div>
        ))}
        {!files.length ? <div className="text-sm text-[color:var(--ops-text-muted)]">No changed files recorded.</div> : null}
      </div>
      {summary?.diff_summary ? (
        <div className="mt-4 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4 text-sm leading-6 text-[color:var(--ops-text-muted)]">
          {summary.diff_summary}
        </div>
      ) : null}
    </Panel>
  )
}

function CommandEvidencePanel({ detail }: Readonly<{ detail: DeclarativeWorkflowRunDetail }>) {
  const commands = detail.command_results || []
  return (
    <Panel title="Commands Run" testId="workflow-command-evidence-panel">
      <div className="space-y-3">
        {commands.map((command, index) => (
          <details key={`${command.command}-${index}`} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4" open>
            <summary className="cursor-pointer font-mono text-sm font-semibold text-[color:var(--ops-text-title)]">{command.command}</summary>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <span className={['rounded-full border px-3 py-1', command.exit_code === 0 ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-rose-200 bg-rose-50 text-rose-700'].join(' ')}>
                exit {command.exit_code}
              </span>
              {command.simulated ? <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">Simulated verification</span> : null}
              {command.timeout ? <span className="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-rose-700">Timed out after {command.timeout_seconds ?? '?'}s</span> : null}
              {command.killed ? <span className="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-rose-700">process group killed</span> : null}
              {command.step_key ? <span className="rounded-full border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-subtle)] px-3 py-1 text-[color:var(--ops-text-muted)]">step {command.step_key}</span> : null}
              {command.log_artifact_id ? <span className="rounded-full border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-subtle)] px-3 py-1 text-[color:var(--ops-text-muted)]">log artifact #{command.log_artifact_id}</span> : null}
            </div>
            <div className="mt-3 text-sm text-[color:var(--ops-text-muted)]">{command.purpose || 'No purpose recorded.'}</div>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              <pre className="max-h-[180px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{command.stdout_excerpt || 'No stdout excerpt.'}</pre>
              <pre className="max-h-[180px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{command.stderr_excerpt || 'No stderr excerpt.'}</pre>
            </div>
            <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">
              cwd: {command.cwd || '-'} · duration {command.duration_ms ?? 0}ms
            </div>
          </details>
        ))}
        {!commands.length ? <div className="text-sm text-[color:var(--ops-text-muted)]">No command evidence recorded.</div> : null}
      </div>
    </Panel>
  )
}

function timelineTone(kind: string) {
  if (kind === 'human_gate') return 'border-rose-300/45 bg-rose-500/12'
  if (kind === 'workflow_terminal') return 'border-emerald-300/40 bg-emerald-500/12'
  if (kind === 'artifact_created') return 'border-amber-300/40 bg-amber-500/12'
  if (kind === 'atom_invocation') return 'border-cyan-300/40 bg-cyan-500/12'
  return 'border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]'
}

function timelineIcon(kind: string) {
  if (kind === 'human_gate') return 'gate'
  if (kind === 'workflow_terminal') return 'done'
  if (kind === 'artifact_created') return 'artifact'
  if (kind === 'atom_invocation') return 'atom'
  return 'state'
}

function TimelineArtifactPreview({ item }: Readonly<{ item: DeclarativeWorkflowTimelineItem }>) {
  const previews = [
    ...(item.artifacts || []),
    ...(item.artifact ? [item.artifact] : []),
  ]
  if (!previews.length) return null
  return (
    <div className="mt-3 space-y-2">
      {previews.map((artifact) => (
        <details key={artifact.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-3">
          <summary className="cursor-pointer text-sm font-medium text-[color:var(--ops-text-title)]">
            {artifact.artifact_type} #{artifact.id}: {artifact.summary || 'preview'}
          </summary>
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <div>
              <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Payload</div>
              <JsonBlock value={artifact.payload || {}} maxHeight="max-h-[220px]" />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Raw Excerpt</div>
              <pre className="mt-2 max-h-[220px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{artifact.raw_excerpt || 'No raw excerpt.'}</pre>
            </div>
          </div>
        </details>
      ))}
    </div>
  )
}

function WorkflowTimelinePanel({ detail }: Readonly<{ detail: DeclarativeWorkflowRunDetail }>) {
  const timeline = detail.timeline || []
  return (
    <Panel title="Vertical Timeline" testId="workflow-timeline-panel">
      <div className="space-y-4">
        {timeline.map((item, index) => (
          <article key={`${item.kind}-${item.id}-${index}`} className={['relative rounded-3xl border p-4', timelineTone(item.kind)].join(' ')}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-[color:var(--ops-text-caption)]">
                    {timelineIcon(item.kind)}
                  </span>
                  <h3 className="text-base font-semibold text-[color:var(--ops-text-title)]">{item.title}</h3>
                </div>
                <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{item.summary || 'No summary recorded.'}</div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-[color:var(--ops-text-caption)]">
                  <span>{formatTime(item.created_at)}</span>
                  {item.state_key ? <span>state: {item.state_key}</span> : null}
                  {item.atom_key ? <span>atom: {item.atom_key}</span> : null}
                  {item.condition ? <span>condition: {item.condition}</span> : null}
                </div>
              </div>
              <span className={['rounded-full border px-3 py-1 text-xs', statusClass(item.status || item.kind)].join(' ')}>
                {item.status || item.kind}
              </span>
            </div>
            <TimelineArtifactPreview item={item} />
          </article>
        ))}
        {!timeline.length ? (
          <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] p-6 text-sm text-[color:var(--ops-text-muted)]">
            No timeline items recorded yet.
          </div>
        ) : null}
      </div>
    </Panel>
  )
}

function CompactStepRail({
  steps,
}: Readonly<{
  steps: StepViewModel[]
}>) {
  return (
    <Panel title="Compact Step Rail" testId="workflow-compact-step-rail">
      <div className="overflow-x-auto pb-2">
        <div className="flex min-w-max gap-2">
          {steps.map((step, index) => (
            <div
              key={step.stateKey}
              className={[
                'min-w-[160px] rounded-2xl border px-4 py-3 text-left',
                step.status === 'not_started' ? 'border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] opacity-70' : 'border-cyan-300/30 bg-cyan-300/10',
              ].join(' ')}
            >
              <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Step {index + 1}</div>
              <div className="mt-1 font-mono text-sm font-semibold text-[color:var(--ops-text-title)]">{step.stateKey}</div>
              <div className="mt-2">
                <span className={['rounded-full border px-2 py-0.5 text-[11px]', statusClass(step.status)].join(' ')}>{step.status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="mt-3 text-xs text-[color:var(--ops-text-muted)]">
        Static progress only. Use the Timeline for the chronological execution narrative.
      </div>
    </Panel>
  )
}

function EvidenceMap({ steps }: Readonly<{ steps: StepViewModel[] }>) {
  return (
    <Panel title="Evidence Map" testId="workflow-evidence-map">
      <div className="space-y-4">
        {steps.map((step) => (
          <div key={step.stateKey} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="font-mono text-sm font-semibold text-[color:var(--ops-text-title)]">{step.stateKey}</div>
                <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{step.evidenceArtifacts.length} evidence artifacts</div>
              </div>
              <span className={['rounded-full border px-3 py-1 text-xs', statusClass(step.status)].join(' ')}>{step.status}</span>
            </div>
            <div className="mt-3 space-y-2">
              {step.evidenceArtifacts.map((artifact) => (
                <details key={artifact.id} className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-2">
                  <summary className="cursor-pointer text-sm font-medium text-[color:var(--ops-text-title)]">{artifactDisplayTitle(artifact)}</summary>
                  <div className="mt-2 text-xs text-[color:var(--ops-text-muted)]">{artifact.content_summary || '-'}</div>
                  <div className="mt-3">
                    <JsonBlock value={artifact.payload} maxHeight="max-h-[220px]" />
                  </div>
                </details>
              ))}
              {!step.evidenceArtifacts.length ? <div className="text-sm text-[color:var(--ops-text-muted)]">No artifacts linked.</div> : null}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  )
}

function workflowAcceptance(detail: DeclarativeWorkflowRunDetail) {
  const value = detail.blackboard.acceptance
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

function acceptanceSteps(detail: DeclarativeWorkflowRunDetail) {
  const acceptance = workflowAcceptance(detail)
  return Array.isArray(acceptance.execution_acceptance_steps) ? acceptance.execution_acceptance_steps as Array<Record<string, unknown>> : []
}

function isHumanOverride(detail: DeclarativeWorkflowRunDetail) {
  return Boolean(detail.acceptance_override || workflowAcceptance(detail).acceptance_override)
}

function ManualReviewPanel({
  detail,
  busy,
  onConfirm,
  onReject,
  onFollowup,
}: Readonly<{
  detail: DeclarativeWorkflowRunDetail
  busy: boolean
  onConfirm: () => void
  onReject: () => void
  onFollowup: () => void
}>) {
  const acceptance = workflowAcceptance(detail)
  const prompt = detail.manual_review_prompt || String(acceptance.manual_review_prompt || acceptance.markdown || 'Operator requested manual review without a structured step matrix.')
  const confirmed = detail.business_outcome_status === 'confirmed'
  const rejected = detail.business_outcome_status === 'rejected'
  return (
    <Panel title="Manual Review Panel" testId="workflow-manual-review-panel">
      <div className="space-y-4">
        <div className="rounded-2xl border border-amber-300/35 bg-amber-400/10 p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-amber-100">Human Override</div>
          <p className="mt-2 text-base leading-7 text-[color:var(--ops-text-title)]">{prompt}</p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-[color:var(--ops-text-caption)]">
            <span>override by: {String(acceptance.override_by || 'operator')}</span>
            {acceptance.override_reason ? <span>reason: {String(acceptance.override_reason)}</span> : null}
            {acceptance.override_at ? <span>at: {formatTime(String(acceptance.override_at))}</span> : null}
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <MiniFact label="Changed Files" value={String(detail.changed_files_summary?.changed_files?.length ?? 0)} />
          <MiniFact label="Commands" value={String(detail.command_results?.length ?? 0)} />
          <MiniFact label="Artifacts" value={String(detail.artifact_count ?? detail.artifacts.length)} />
          <MiniFact label="Delivery" value={detail.delivery_summary?.simulated ? 'simulated' : detail.delivery_summary?.pr_url ? 'PR linked' : detail.release_status || '-'} />
        </div>

        <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Business Outcome</div>
          <div className="mt-2 text-sm text-[color:var(--ops-text-body)]">
            {confirmed
              ? `Confirmed by ${detail.business_outcome_confirmed_by || 'operator'} at ${formatTime(detail.business_outcome_confirmed_at || null)}.`
              : rejected
                ? 'Rejected by operator. Create a follow-up requirement if the outcome needs another pass.'
                : 'Technical workflow evidence is available. Operator must confirm the real business outcome before this run is fully Done.'}
          </div>
          {detail.business_outcome_note ? <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">{detail.business_outcome_note}</div> : null}
        </div>

        {!confirmed ? (
          <div className="flex flex-wrap gap-2">
            <button type="button" className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50" disabled={busy} onClick={onConfirm}>
              Confirm Business Outcome
            </button>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm text-[color:var(--ops-text-body)] disabled:opacity-50" disabled={busy} onClick={onFollowup}>
              Request Follow-up Fix
            </button>
            <button type="button" className="rounded-xl border border-[color:var(--ops-state-blocked-border)] px-4 py-2.5 text-sm text-[color:var(--ops-state-blocked-text)] disabled:opacity-50" disabled={busy} onClick={onReject}>
              Reject Outcome
            </button>
          </div>
        ) : null}
      </div>
    </Panel>
  )
}

function StepVerificationMatrix({ detail }: Readonly<{ detail: DeclarativeWorkflowRunDetail }>) {
  const steps = acceptanceSteps(detail)
  return (
    <Panel title="Step Verification Matrix" testId="workflow-step-verification-matrix">
      <div className="space-y-3">
        {steps.map((step, index) => {
          const requiredCommands = Array.isArray(step.required_commands) ? step.required_commands.map(String) : []
          const requiredEvidence = Array.isArray(step.required_evidence_types) ? step.required_evidence_types.map(String) : []
          const commandSatisfied = !requiredCommands.length || requiredCommands.some((command) => detail.command_results?.some((result) => result.command.includes(command) && result.exit_code === 0))
          const evidenceSatisfied = !requiredEvidence.length || requiredEvidence.some((kind) => detail.artifacts.some((artifact) => artifact.artifact_type === kind || artifact.content_summary.includes(kind)))
          const passed = commandSatisfied && evidenceSatisfied && detail.evidence_complete !== false
          return (
            <div key={String(step.step_key || index)} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{String(step.title || step.step_key || `Step ${index + 1}`)}</div>
                  <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{String(step.expected_result || 'No expected result recorded.')}</div>
                </div>
                <span className={['rounded-full border px-3 py-1 text-xs', statusClass(passed ? 'passed' : 'pending')].join(' ')}>
                  {passed ? 'passed' : 'pending evidence'}
                </span>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-3">
                  <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Required Commands</div>
                  <div className="mt-2 text-xs text-[color:var(--ops-text-muted)]">{requiredCommands.length ? requiredCommands.join('; ') : 'none'}</div>
                </div>
                <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-3">
                  <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Required Evidence</div>
                  <div className="mt-2 text-xs text-[color:var(--ops-text-muted)]">{requiredEvidence.length ? requiredEvidence.join('; ') : String(step.manual_review_prompt || 'none')}</div>
                </div>
              </div>
            </div>
          )
        })}
        {!steps.length ? (
          <div className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] p-4 text-sm text-[color:var(--ops-state-blocked-text)]">
            Acceptance Missing / Blocked. This workflow has no Human Override and no structured execution acceptance steps, so the UI will not render a fake verification matrix.
          </div>
        ) : null}
      </div>
    </Panel>
  )
}

function WorkflowAcceptanceSourcePanel({ detail }: Readonly<{ detail: DeclarativeWorkflowRunDetail }>) {
  const candidateId = detail.requirement_candidate_id
  return (
    <Panel title="Acceptance Source">
      <div className="flex flex-wrap gap-2 text-sm text-[color:var(--ops-text-body)]">
        <span className="rounded-full border border-cyan-300/25 bg-cyan-300/[0.08] px-3 py-1 text-cyan-100">
          {candidateId ? `Generated from Candidate #${candidateId}` : 'Requirement acceptance contract'}
        </span>
        {detail.requirement_source ? <span className="rounded-full border border-[color:var(--ops-stroke-soft)] px-3 py-1">source: {detail.requirement_source}</span> : null}
        {detail.goal_key ? <span className="rounded-full border border-[color:var(--ops-stroke-soft)] px-3 py-1">goal: {detail.goal_key}</span> : null}
      </div>
    </Panel>
  )
}

function GateDeliveryPanel({
  detail,
  busyGate,
  decisionFeedback,
  onDecide,
  onSupersede,
}: Readonly<{
  detail: DeclarativeWorkflowRunDetail
  busyGate: GateBusyState
  decisionFeedback: DecisionFeedback
  onDecide: (gate: DeclarativeHumanGate, decision: string) => void
  onSupersede: () => void
}>) {
  const summary = workflowDecisionSummary(detail)
  const pr = (detail.blackboard.pr || {}) as Record<string, unknown>
  const deliveryView = workflowDeliveryView(detail)
  const deliveryCallout = deliveryView.blockerType === 'delivery_branch_rebase_conflict'
    ? { label: 'Rebase conflict requires operator', tone: 'blocked' }
    : deliveryView.humanCommitsDetected && deliveryView.rebaseStatus === 'succeeded'
      ? { label: 'Human commits detected and rebased', tone: 'ok' }
      : deliveryView.syncAction === 'updated'
        ? { label: 'Existing PR updated', tone: 'ok' }
        : deliveryView.syncAction === 'created'
          ? { label: 'PR created', tone: 'ok' }
          : deliveryView.status === 'delivery_blocked'
            ? { label: 'Delivery blocked before PR handoff', tone: 'blocked' }
          : null
  const pendingGates = detail.human_gates.filter((gate) => gate.status === 'pending')
  const decidedGates = detail.human_gates.filter((gate) => gate.status !== 'pending')
  const showDelivery = hasDeliverySignal(detail)
  return (
    <div className="space-y-5" data-testid="workflow-gates-delivery">
      <Panel title="Decision Summary" testId="workflow-operator-decision-summary">
        <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-4">
            <div className={['rounded-[var(--ops-radius-panel)] border p-5', statusToneClass(summary.status_tone)].join(' ')}>
              <div className="text-xs uppercase tracking-[0.2em] opacity-80">Current Decision</div>
              <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{summary.status_label}</div>
              <p className="mt-3 max-w-3xl text-base leading-7 text-[color:var(--ops-text-body)]">{summary.what_happened}</p>
            </div>
            <div className="rounded-[var(--ops-radius-panel)] bg-[color:var(--ops-panel-subtle)] p-5">
              <div className="text-xs uppercase tracking-[0.2em] text-[color:var(--ops-text-caption)]">Root Cause</div>
              <p className="mt-2 text-base leading-7 text-[color:var(--ops-text-title)]">{summary.root_cause || summary.what_happened}</p>
              {summary.error_excerpt ? (
                <pre className="mt-4 max-h-[180px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{summary.error_excerpt}</pre>
              ) : null}
            </div>
          </div>
          <div className="rounded-[var(--ops-radius-panel)] bg-[color:var(--ops-panel-subtle)] p-5">
            <div className="text-xs uppercase tracking-[0.2em] text-[color:var(--ops-text-caption)]">Recommended Next Action</div>
            <p className="mt-3 text-base leading-7 text-[color:var(--ops-text-title)]">{summary.recommended_next_action}</p>
            <p className="mt-4 text-xs leading-5 text-[color:var(--ops-text-muted)]">
              确认并放行不等于合并 PR，也不会绕过生产、资金、auth、deploy、settlement 等高风险门禁。
            </p>
            <details className="mt-4 text-xs text-[color:var(--ops-text-caption)]">
              <summary className="cursor-pointer">Technical details</summary>
              <div className="mt-2 space-y-1 font-mono">
                <div>run #{detail.id}</div>
                <div>workflow {detail.workflow_key}</div>
                <div>Current state {detail.current_state}</div>
                <div>Resolution {detail.resolution || '-'}</div>
                <div>root cause {summary.root_cause_kind || '-'}</div>
              </div>
            </details>
          </div>
        </div>
      </Panel>

      <Panel title="Your Decision" testId="workflow-human-action-panel">
        <div className="space-y-3">
          {decisionFeedback ? (
            <div
              data-testid="workflow-gate-decision-feedback"
              className={[
                'rounded-[var(--ops-radius-panel)] border px-4 py-3 text-sm font-medium',
                decisionFeedback.tone === 'error'
                  ? 'border-rose-300/45 bg-rose-500/16 text-rose-50'
                  : decisionFeedback.tone === 'warning'
                    ? 'border-amber-300/45 bg-amber-400/12 text-amber-100'
                    : decisionFeedback.tone === 'success'
                      ? 'border-emerald-300/35 bg-emerald-400/10 text-emerald-100'
                      : 'border-cyan-300/40 bg-cyan-300/12 text-cyan-100',
              ].join(' ')}
            >
              {decisionFeedback.message}
            </div>
          ) : null}
          {pendingGates.map((gate) => {
            const gateBusy = busyGate?.id === gate.id
            const decisions = ['continue_retry', 'approve', 'reject']
            return (
              <div key={gate.id} className="rounded-[var(--ops-radius-panel)] bg-[color:var(--ops-panel-subtle)] p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">需要你的判断</div>
                    <div className="mt-1 text-sm leading-6 text-[color:var(--ops-text-muted)]">{summary.what_happened}</div>
                    <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">created {formatTime(gate.created_at)} · risk {gate.risk_level}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {decisions.map((decision) => (
                      <button
                        key={decision}
                        type="button"
                        className={['rounded-xl border px-4 py-2.5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-55', gateDecisionClass(decision, summary)].join(' ')}
                        disabled={gateBusy}
                        onClick={() => onDecide(gate, decision)}
                      >
                        {gateBusy && busyGate?.decision === decision ? '处理中...' : gateDecisionLabel(decision, summary, detail)}
                      </button>
                    ))}
                    {summary.can_supersede_retry ? (
                      <button
                        type="button"
                        className="rounded-xl border border-amber-300/45 bg-amber-400/10 px-4 py-2.5 text-sm font-semibold text-amber-100 disabled:cursor-not-allowed disabled:opacity-55"
                        disabled={gateBusy}
                        onClick={onSupersede}
                      >
                        {gateBusy && busyGate?.decision === 'supersede' ? '处理中...' : '废弃并重新规划'}
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            )
          })}
          {!pendingGates.length ? (
            <div className="rounded-[var(--ops-radius-panel)] bg-[color:var(--ops-panel-subtle)] p-5 text-sm text-[color:var(--ops-text-muted)]">
              当前没有需要你处理的门禁。
            </div>
          ) : null}
          {decidedGates.length ? (
            <details className="rounded-[var(--ops-radius-panel)] bg-[color:var(--ops-panel-subtle)] p-4">
              <summary className="cursor-pointer text-sm font-semibold text-[color:var(--ops-text-title)]">已处理门禁 ({decidedGates.length})</summary>
              <div className="mt-3 space-y-2">
                {decidedGates.map((gate) => (
                  <div key={gate.id} className="text-sm text-[color:var(--ops-text-muted)]">
                    {gate.decision || gate.status} · {formatTime(gate.created_at)}
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </div>
      </Panel>

      {showDelivery ? <Panel title="Delivery Summary" testId="workflow-pr-delivery">
        <div className="grid gap-3 md:grid-cols-2">
          <MiniFact label="Delivery Status" value={deliveryView.status || '-'} />
          <MiniFact label="PR Status" value={deliveryView.prStatus || '-'} />
          <MiniFact label="Branch" value={deliveryView.branch || '-'} />
          <MiniFact label="Base" value={deliveryView.baseBranch || '-'} />
          <MiniFact label="Changed Files" value={String(deliveryView.changedFilesCount)} />
          <MiniFact label="Command Evidence" value={String(deliveryView.commandEvidenceCount)} />
          <MiniFact label="VCS" value={deliveryView.vcsStatus || '-'} />
          <MiniFact label="Rebase" value={deliveryView.rebaseStatus || '-'} />
          <MiniFact label="Human Commits" value={deliveryView.humanCommitsDetected ? 'detected' : 'none'} />
        </div>
        {deliveryCallout ? (
          <div className={[
            'mt-4 rounded-2xl border px-4 py-3 text-sm font-medium',
            deliveryCallout.tone === 'blocked'
              ? 'border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] text-[color:var(--ops-state-blocked-text)]'
              : 'border-emerald-300/35 bg-emerald-400/10 text-emerald-100',
          ].join(' ')}>
            {deliveryCallout.label}
          </div>
        ) : null}
        {detail.delivery_summary?.simulated || detail.simulated_delivery ? (
          <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800">
            Simulated PR. This delivery did not create a real external GitHub PR.
          </div>
        ) : null}
        {deliveryView.prUrl ? (
          <a className="mt-4 inline-flex rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white" href={deliveryView.prUrl} target="_blank" rel="noreferrer">
            Open GitHub PR
          </a>
        ) : null}
        {deliveryView.compareUrl ? (
          <a className="ml-2 mt-4 inline-flex rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" href={deliveryView.compareUrl} target="_blank" rel="noreferrer">
            Compare
          </a>
        ) : null}
        {Array.isArray(pr.blockers) && pr.blockers.length ? (
          <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            {pr.blockers.map((blocker) => String(blocker)).join('; ')}
          </div>
        ) : null}
      </Panel> : null}
    </div>
  )
}

function DebugPanel({ detail }: Readonly<{ detail: DeclarativeWorkflowRunDetail }>) {
  const notifications = detail.notifications || []
  function downloadDebugDump() {
    const blob = new Blob([prettyJson(detail)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `workflow-run-${detail.id}-debug-dump.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-5" data-testid="workflow-debug-panel">
      <Panel
        title="Debug Dump"
        action={(
          <button type="button" className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white" onClick={downloadDebugDump}>
            Download Debug Dump
          </button>
        )}
      >
        <p className="text-sm leading-6 text-[color:var(--ops-text-muted)]">
          Raw payloads are hidden by default. Download the dump for rare deep debugging, or expand the sections below.
        </p>
      </Panel>
      <div className="grid gap-5 xl:grid-cols-2">
        <details className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
          <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Raw Blackboard JSON</summary>
          <div className="mt-4"><JsonBlock value={detail.blackboard} maxHeight="max-h-[620px]" /></div>
        </details>
        <details className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
          <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Raw Artifacts</summary>
          <div className="mt-4 space-y-3">
            {detail.artifacts.map((artifact) => (
              <details key={artifact.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] p-4">
                <summary className="cursor-pointer font-semibold text-[color:var(--ops-text-title)]">{artifact.artifact_type} #{artifact.id}</summary>
                <div className="mt-3">
                  <JsonBlock value={artifact.payload} maxHeight="max-h-[320px]" />
                </div>
              </details>
            ))}
          </div>
        </details>
        <details className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
          <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Raw Transition Events</summary>
          <div className="mt-4"><JsonBlock value={detail.events} maxHeight="max-h-[520px]" /></div>
        </details>
        <details className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
          <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Raw Atom Invocations</summary>
          <div className="mt-4"><JsonBlock value={detail.atom_invocations} maxHeight="max-h-[520px]" /></div>
        </details>
        <details className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5" data-testid="workflow-lark-notifications-debug">
          <summary className="cursor-pointer text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Lark Notifications</summary>
          <div className="mt-4 space-y-3">
            {notifications.map((delivery) => (
              <div key={delivery.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={['rounded-full border px-3 py-1 text-xs', statusClass(delivery.status)].join(' ')}>{delivery.status}</span>
                  <span className="rounded-full border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-subtle)] px-3 py-1 text-xs text-[color:var(--ops-text-muted)]">{delivery.channel}</span>
                  <span className="font-mono text-xs text-[color:var(--ops-text-caption)]">{delivery.event_type}</span>
                </div>
                <div className="mt-3 text-sm font-medium text-[color:var(--ops-text-title)]">{String(delivery.payload?.summary || delivery.event_key)}</div>
                <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">
                  {formatTime(delivery.delivered_at || delivery.created_at)} · {delivery.response_excerpt || 'no response excerpt'}
                </div>
                {delivery.fingerprint_key ? (
                  <div className="mt-3 rounded-xl border border-amber-300/30 bg-amber-400/10 px-3 py-2 text-xs text-amber-100">
                    <div className="font-mono break-all">fingerprint: {delivery.fingerprint_key}</div>
                    <div className="mt-1">
                      occurrence {Number(delivery.fingerprint?.occurrence_count || 0)}
                      {' · '}suppressed {Number(delivery.fingerprint?.suppressed_count || 0)}
                      {delivery.fingerprint?.cooldown_until ? ` · cooldown until ${formatTime(delivery.fingerprint.cooldown_until)}` : ''}
                    </div>
                  </div>
                ) : null}
              </div>
            ))}
            {!notifications.length ? <div className="text-sm text-[color:var(--ops-text-muted)]">暂无 Lark 通知投递记录。</div> : null}
          </div>
        </details>
      </div>
    </div>
  )
}

export default function WorkflowRunDetailPage() {
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const toast = useToast()
  const workflowRunId = Number(id)
  const [detail, setDetail] = useState<DeclarativeWorkflowRunDetail | null>(null)
  const [definition, setDefinition] = useState<DeclarativeWorkflowDefinition | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyGate, setBusyGate] = useState<GateBusyState>(null)
  const [decisionFeedback, setDecisionFeedback] = useState<DecisionFeedback>(null)
  const inFlightGateDecisions = useRef(new Set<number>())
  const decisionPollTimers = useRef<number[]>([])
  const activeWorkflowRunId = useRef(workflowRunId)
  const [businessOutcomeBusy, setBusinessOutcomeBusy] = useState(false)
  const [activeTab, setActiveTab] = useState<WorkflowTab>('overview')

  useEffect(() => {
    activeWorkflowRunId.current = workflowRunId
    return () => {
      decisionPollTimers.current.forEach((timer) => window.clearTimeout(timer))
      decisionPollTimers.current = []
      inFlightGateDecisions.current.clear()
    }
  }, [workflowRunId])

  async function load() {
    if (!Number.isFinite(workflowRunId)) return
    setLoading(true)
    setError(null)
    try {
      const nextDetail = await api.getWorkflowRun(workflowRunId)
      setDetail(nextDetail)
      try {
        setDefinition(await api.getWorkflowDefinition(nextDetail.workflow_key))
      } catch {
        setDefinition(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载工作流失败')
    } finally {
      setLoading(false)
    }
  }

  function clearDecisionPollTimers() {
    decisionPollTimers.current.forEach((timer) => window.clearTimeout(timer))
    decisionPollTimers.current = []
  }

  function detailNeedsOperator(nextDetail: DeclarativeWorkflowRunDetail) {
    const state = String(nextDetail.current_state || '').toLowerCase()
    const status = String(nextDetail.status || '').toLowerCase()
    return state === 'awaiting_operator' || status === 'awaiting_operator' || nextDetail.pending_human_gate_count > 0 || Boolean(nextDetail.needs_human)
  }

  function detailTerminallySucceeded(nextDetail: DeclarativeWorkflowRunDetail) {
    const state = String(nextDetail.current_state || '').toLowerCase()
    const status = String(nextDetail.status || '').toLowerCase()
    return Boolean(nextDetail.is_truly_completed) || ['done', 'completed', 'succeeded'].includes(state) || ['done', 'completed', 'succeeded'].includes(status)
  }

  function detailTerminallyFailed(nextDetail: DeclarativeWorkflowRunDetail) {
    const state = String(nextDetail.current_state || '').toLowerCase()
    const status = String(nextDetail.status || '').toLowerCase()
    return ['failed', 'error'].includes(state) || ['failed', 'error'].includes(status)
  }

  function startDecisionStatusPolling(runId: number) {
    clearDecisionPollTimers()
    const pollDelays = [1000, 3000, 5000]
    pollDelays.forEach((delay, index) => {
      const timer = window.setTimeout(async () => {
        if (activeWorkflowRunId.current !== runId) return
        try {
          const nextDetail = await api.getWorkflowRun(runId)
          if (activeWorkflowRunId.current !== runId) return
          setDetail(nextDetail)
          if (detailNeedsOperator(nextDetail)) {
            setDecisionFeedback({
              tone: 'warning',
              message: 'Agent 已继续尝试，但工作流仍停在人工门禁，请查看新的根因摘要。',
            })
            clearDecisionPollTimers()
            return
          }
          if (detailTerminallySucceeded(nextDetail)) {
            setDecisionFeedback({ tone: 'success', message: '决策已记录，Runner 已推进到完成状态。' })
            clearDecisionPollTimers()
            return
          }
          if (detailTerminallyFailed(nextDetail)) {
            setDecisionFeedback({ tone: 'warning', message: '决策已记录，但 Runner 推进后进入失败状态，请查看根因摘要。' })
            clearDecisionPollTimers()
            return
          }
          setDecisionFeedback({ tone: 'info', message: '决策已记录，Agent 正在继续尝试。' })
          if (index === pollDelays.length - 1) {
            setDecisionFeedback({ tone: 'info', message: '决策已记录，等待 Runner 推进或再次阻断。' })
          }
        } catch {
          if (activeWorkflowRunId.current !== runId) return
          setDecisionFeedback({ tone: 'warning', message: '决策已记录，但状态刷新失败，请手动刷新确认。' })
        }
      }, delay)
      decisionPollTimers.current.push(timer)
    })
  }

  async function decideGate(gate: DeclarativeHumanGate, decision: string) {
    if (!detail) return
    if (inFlightGateDecisions.current.has(gate.id)) return
    inFlightGateDecisions.current.add(gate.id)
    setBusyGate({ id: gate.id, decision })
    setError(null)
    setDecisionFeedback({ tone: 'info', message: `正在提交“${gateDecisionLabel(decision, workflowDecisionSummary(detail), detail)}”…` })
    try {
      const nextDetail = await api.decideWorkflowHumanGate(detail.id, gate.id, {
        decision,
        reviewer: 'operator',
        comment: `Operator ${decision} from workflow detail`,
      })
      setDetail(nextDetail)
      setDecisionFeedback({ tone: 'info', message: '决策已记录，等待 Runner 推进或再次阻断。' })
      if (nextDetail.resume_status === 'failed') {
        toast.error('Gate decision saved, but runner resume failed. Inspect Timeline evidence.')
        setDecisionFeedback({ tone: 'warning', message: '决策已记录，但 Runner resume 失败，请查看 Timeline evidence。' })
      } else if (nextDetail.resume_attempted) {
        toast.success(`Gate decision saved; runner ${nextDetail.resume_status || 'resumed'}.`)
      }
      startDecisionStatusPolling(detail.id)
    } catch (err) {
      const message = err instanceof Error ? err.message : '门禁决策失败'
      setError(message)
      setDecisionFeedback({ tone: 'error', message })
    } finally {
      inFlightGateDecisions.current.delete(gate.id)
      setBusyGate(null)
    }
  }

  async function supersedeAndRetryPlanner() {
    if (!detail) return
    const pendingGate = detail.human_gates.find((gate) => gate.status === 'pending')
    if (pendingGate && inFlightGateDecisions.current.has(pendingGate.id)) return
    if (pendingGate) {
      inFlightGateDecisions.current.add(pendingGate.id)
      setBusyGate({ id: pendingGate.id, decision: 'supersede' })
    }
    setError(null)
    try {
      await api.supersedeWorkflowAndRetryPlanner(detail.id, {
        operator: 'operator',
        comment: 'Supersede and retry from workflow decision workbench.',
      })
      toast.success('已废弃当前阻塞链路并触发 Planner 重试')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : '废弃并重新规划失败')
    } finally {
      if (pendingGate) inFlightGateDecisions.current.delete(pendingGate.id)
      setBusyGate(null)
    }
  }

  async function archiveRun() {
    if (!detail) return
    try {
      await api.archiveWorkflowRun(detail.id, { archived_by: 'operator', reason: 'Archived from workflow detail' })
      await load()
      toast.success('Workflow run 已归档')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '归档失败')
    }
  }

  async function createFollowup() {
    if (!detail) return
    try {
      const payload = await api.createWorkflowFollowup(detail.id, {
        title: `Follow-up: ${detail.requirement_title || detail.workflow_key}`,
        operator: 'operator',
      })
      toast.success(`已创建 follow-up requirement #${payload.requirement_id}`)
      navigate(`/requirements/${payload.requirement_id}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '创建 follow-up 失败')
    }
  }

  async function confirmBusinessOutcome() {
    if (!detail) return
    setBusinessOutcomeBusy(true)
    try {
      const nextDetail = await api.confirmWorkflowBusinessOutcome(detail.id, {
        operator: 'operator',
        note: 'Business outcome confirmed from workflow Evidence tab.',
      })
      setDetail(nextDetail)
      toast.success('Business outcome confirmed')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '业务结果确认失败')
    } finally {
      setBusinessOutcomeBusy(false)
    }
  }

  async function rejectBusinessOutcome() {
    if (!detail) return
    setBusinessOutcomeBusy(true)
    try {
      const nextDetail = await api.rejectWorkflowBusinessOutcome(detail.id, {
        operator: 'operator',
        note: 'Business outcome rejected from workflow Evidence tab.',
      })
      setDetail(nextDetail)
      toast.success('Business outcome rejected; create a follow-up if needed')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '业务结果拒绝失败')
    } finally {
      setBusinessOutcomeBusy(false)
    }
  }

  async function requestBusinessFollowup() {
    if (!detail) return
    setBusinessOutcomeBusy(true)
    try {
      const payload = await api.requestWorkflowBusinessFollowup(detail.id, {
        title: `Follow-up: ${detail.requirement_title || detail.workflow_key}`,
        operator: 'operator',
        note: 'Follow-up requested from manual business review.',
      })
      setDetail(payload.workflow)
      toast.success(`已创建 follow-up requirement #${payload.requirement_id}`)
      navigate(`/requirements/${payload.requirement_id}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '创建 follow-up 失败')
    } finally {
      setBusinessOutcomeBusy(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [workflowRunId])

  useEffect(() => {
    const tab = new URLSearchParams(location.search).get('tab')
    if (tab === 'delivery') {
      setActiveTab('gates')
    } else if (tab === 'steps') {
      setActiveTab('timeline')
    } else if (tab && WORKFLOW_TABS.some((item) => item.key === tab)) {
      setActiveTab(tab as WorkflowTab)
    }
  }, [location.search])

  const steps = useMemo(() => detail ? buildStepViewModels(detail, definition) : [], [detail, definition])
  const nextAction = detail ? buildNextAction(detail) : null

  const setWorkflowTab = (tab: WorkflowTab) => {
    setActiveTab(tab)
    const nextSearch = `?tab=${tab}`
    if (location.search !== nextSearch) {
      navigate({ pathname: location.pathname, search: nextSearch }, { replace: false })
    }
    if (tab === 'gates') {
      window.requestAnimationFrame(() => {
        const target = document.querySelector('[data-testid="workflow-gates-tab"]')
        if (target && typeof target.scrollIntoView === 'function') {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
      })
    }
  }

  if (loading && !detail) {
    return <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-6 text-sm text-[color:var(--ops-text-muted)]">加载工作流中…</div>
  }

  if (!detail || !nextAction) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
        {error || '工作流不存在'}
      </div>
    )
  }

  return (
    <div className="space-y-5" data-testid="workflow-run-detail-page">
      <WorkflowRunHeader
        detail={detail}
        nextAction={nextAction}
        onRefresh={() => load().catch(() => {})}
        onNavigateRequirement={() => navigate(`/requirements/${detail.requirement_id}`)}
        onSetTab={setWorkflowTab}
      />

      <WorkflowRunTabs activeTab={activeTab} onChange={setWorkflowTab} />

      {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}

      {activeTab === 'overview' ? (
        <div className="space-y-5" data-testid="workflow-overview-tab">
          <RunBriefPanel detail={detail} nextAction={nextAction} />
          <CompletionArchivePanel detail={detail} onArchive={() => archiveRun().catch(() => {})} onCreateFollowup={() => createFollowup().catch(() => {})} />
          <CorrectnessPanel detail={detail} />
          <AgentOutputPanel detail={detail} />
          <ChangedFilesPanel detail={detail} />
          <CommandEvidencePanel detail={detail} />
          <CompactStepRail steps={steps} />
        </div>
      ) : null}

      {activeTab === 'timeline' ? (
        <div data-testid="workflow-timeline-tab">
          <WorkflowTimelinePanel detail={detail} />
        </div>
      ) : null}

      {activeTab === 'evidence' ? (
        <div className="space-y-5">
          <WorkflowAcceptanceSourcePanel detail={detail} />
          <AcceptanceMatrixRuntimePanel detail={detail} />
          {isHumanOverride(detail) ? (
            <ManualReviewPanel
              detail={detail}
              busy={businessOutcomeBusy}
              onConfirm={() => confirmBusinessOutcome().catch(() => {})}
              onReject={() => rejectBusinessOutcome().catch(() => {})}
              onFollowup={() => requestBusinessFollowup().catch(() => {})}
            />
          ) : (
            <StepVerificationMatrix detail={detail} />
          )}
          <AgentOutputPanel detail={detail} />
          <ChangedFilesPanel detail={detail} />
          <CommandEvidencePanel detail={detail} />
          {!isHumanOverride(detail) && !acceptanceSteps(detail).length ? <EvidenceMap steps={steps} /> : null}
        </div>
      ) : null}

      {activeTab === 'gates' ? (
        <div data-testid="workflow-gates-tab">
          <GateDeliveryPanel
            detail={detail}
            busyGate={busyGate}
            decisionFeedback={decisionFeedback}
            onDecide={(gate, decision) => { decideGate(gate, decision).catch(() => {}) }}
            onSupersede={() => { supersedeAndRetryPlanner().catch(() => {}) }}
          />
        </div>
      ) : null}

      {activeTab === 'debug' ? <DebugPanel detail={detail} /> : null}
    </div>
  )
}
