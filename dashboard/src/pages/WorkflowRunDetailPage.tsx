import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, DeclarativeHumanGate, DeclarativeWorkflowDefinition, DeclarativeWorkflowRunDetail } from '../api'
import { useToast } from '../components/workbench'
import {
  artifactDisplayTitle,
  buildCorrectnessItems,
  buildNextAction,
  buildStepViewModels,
  hasSimulatedEvidence,
  StepViewModel,
} from '../workflows/workflowStepExplain'

type WorkflowTab = 'overview' | 'steps' | 'evidence' | 'gates' | 'debug'
type InspectorTab = 'overview' | 'inputs' | 'outputs' | 'evidence' | 'transition'

const WORKFLOW_TABS: Array<{ key: WorkflowTab; label: string }> = [
  { key: 'overview', label: 'Overview' },
  { key: 'steps', label: 'Steps' },
  { key: 'evidence', label: 'Evidence' },
  { key: 'gates', label: 'Gates & Delivery' },
  { key: 'debug', label: 'Debug' },
]

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
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
  if (status === 'not_started') return 'border-slate-200 bg-slate-50 text-slate-500'
  return 'border-blue-200 bg-blue-50 text-blue-700'
}

function actionClass(tone: 'ready' | 'blocked' | 'running' | 'muted') {
  if (tone === 'ready') return 'border-emerald-200 bg-emerald-600 text-white'
  if (tone === 'blocked') return 'border-rose-200 bg-rose-600 text-white'
  if (tone === 'running') return 'border-blue-200 bg-blue-600 text-white'
  return 'border-[color:var(--ops-stroke-strong)] bg-white text-[color:var(--ops-text-title)]'
}

function Panel({ title, children, testId, action }: { title: string; children: ReactNode; testId?: string; action?: ReactNode }) {
  return (
    <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white p-5" data-testid={testId}>
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
  return (
    <section className="sticky top-0 z-10 rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white/95 px-5 py-5 shadow-sm backdrop-blur" data-testid="workflow-run-header">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Explainable Workflow Run</div>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">{detail.workflow_key}</h2>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <span className={['rounded-full border px-3 py-1 font-medium', statusClass(detail.status)].join(' ')}>{detail.status}</span>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-600">run #{detail.id}</span>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-600">state: {detail.current_state}</span>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-600">risk: {detail.risk_level}</span>
            {detail.resolution ? <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-emerald-700">resolution: {detail.resolution}</span> : null}
            {pr.url ? <a className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-blue-700" href={String(pr.url)} target="_blank" rel="noreferrer">PR</a> : null}
          </div>
          <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">
            requirement #{detail.requirement_id} · updated {formatTime(detail.updated_at)}
          </div>
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
    <div className="flex flex-wrap gap-2 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white p-2" data-testid="workflow-run-tabs">
      {WORKFLOW_TABS.map((tab) => (
        <button
          key={tab.key}
          type="button"
          className={[
            'rounded-xl px-4 py-2 text-sm font-medium transition',
            activeTab === tab.key
              ? 'bg-[color:var(--ops-text-title)] text-white'
              : 'text-[color:var(--ops-text-muted)] hover:bg-slate-50 hover:text-[color:var(--ops-text-title)]',
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
  const outcome = detail.pending_human_gate_count > 0
    ? '需要 operator 审查后才能继续。'
    : detail.status === 'succeeded'
      ? '工作流已完成，关键验证与收口状态已记录。'
      : `工作流当前停在 ${detail.current_state}。`
  return (
    <Panel title="Run Brief" testId="workflow-run-brief">
      <div className="space-y-4">
        <p className="max-w-4xl text-lg leading-8 text-[color:var(--ops-text-title)]">
          Run #{detail.id} 执行 `{detail.workflow_key}`，关联需求 #{detail.requirement_id}「{detail.requirement_title || '未命名需求'}」。{outcome}
        </p>
        <div className="grid gap-3 md:grid-cols-4">
          <MiniFact label="Current State" value={detail.current_state} />
          <MiniFact label="Resolution" value={detail.resolution || '-'} />
          <MiniFact label="PR" value={pr.url ? 'created' : pr.created ? 'created without url' : '-'} />
          <MiniFact label="Observation" value={observation.restored ? 'restored' : observation.not_restored ? 'not restored' : '-'} />
        </div>
        <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-50/80 p-4">
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
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white px-4 py-3">
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
  const completed = ['succeeded', 'completed', 'done'].includes(detail.status)
  const prUrl = detail.pr_url || String(((detail.blackboard.pr || {}) as Record<string, unknown>).url || '')
  return (
    <Panel title="Outcome Summary" testId="workflow-outcome-summary">
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div>
          <p className="text-base leading-7 text-[color:var(--ops-text-title)]">
            {completed
              ? '这次 workflow 已进入完成档案。后续不删除运行证据，只通过归档从默认管理视图隐藏。'
              : detail.status === 'failed'
                ? '这次 workflow 未完成。优先检查失败 atom、verification evidence 和下一步修复建议。'
                : detail.status === 'awaiting_operator'
                  ? '这次 workflow 正在等待人工门禁。请在 Gates & Delivery 里处理决策。'
                  : '这次 workflow 仍在运行或暂停中。请查看 Step Timeline 和当前 atom 输出。'}
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <MiniFact label="Atoms" value={String(detail.atom_count ?? detail.atom_invocations.length)} />
            <MiniFact label="Artifacts" value={String(detail.artifact_count ?? detail.artifacts.length)} />
            <MiniFact label="Human Gates" value={String(detail.human_gates.length)} />
            <MiniFact label="Goal" value={String(detail.goal_key || '-')} />
          </div>
        </div>
        <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-50/80 p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Next Actions</div>
          <div className="mt-3 grid gap-2">
            {prUrl ? (
              <a className="rounded-xl bg-blue-600 px-4 py-2.5 text-center text-sm font-semibold text-white" href={prUrl} target="_blank" rel="noreferrer">
                Open PR
              </a>
            ) : null}
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={onCreateFollowup}>
              Create Follow-up Requirement
            </button>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm disabled:opacity-50" disabled={Boolean(detail.archived_at)} onClick={onArchive}>
              {detail.archived_at ? 'Archived' : 'Archive Run'}
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
    </Panel>
  )
}

function CompactStepRail({
  steps,
  selectedStepKey,
  onSelect,
}: Readonly<{
  steps: StepViewModel[]
  selectedStepKey: string
  onSelect: (stepKey: string) => void
}>) {
  return (
    <Panel title="Compact Step Rail" testId="workflow-compact-step-rail">
      <div className="overflow-x-auto pb-2">
        <div className="flex min-w-max gap-2">
          {steps.map((step, index) => (
            <button
              key={step.stateKey}
              type="button"
              className={[
                'min-w-[160px] rounded-2xl border px-4 py-3 text-left transition',
                selectedStepKey === step.stateKey ? 'border-blue-300 bg-blue-50' : 'border-[color:var(--ops-stroke-soft)] bg-white hover:bg-slate-50',
              ].join(' ')}
              onClick={() => onSelect(step.stateKey)}
            >
              <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Step {index + 1}</div>
              <div className="mt-1 font-mono text-sm font-semibold text-[color:var(--ops-text-title)]">{step.stateKey}</div>
              <div className="mt-2">
                <span className={['rounded-full border px-2 py-0.5 text-[11px]', statusClass(step.status)].join(' ')}>{step.status}</span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </Panel>
  )
}

function StepExplorer({
  steps,
  selectedStepKey,
  onSelect,
}: Readonly<{
  steps: StepViewModel[]
  selectedStepKey: string
  onSelect: (stepKey: string) => void
}>) {
  return (
    <div className="space-y-3" data-testid="workflow-step-explorer">
      {steps.map((step) => (
        <button
          key={step.stateKey}
          type="button"
          className={[
            'w-full rounded-2xl border p-4 text-left transition',
            selectedStepKey === step.stateKey ? 'border-blue-300 bg-blue-50/80' : 'border-[color:var(--ops-stroke-soft)] bg-white hover:bg-slate-50',
          ].join(' ')}
          onClick={() => onSelect(step.stateKey)}
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <div className="font-mono text-base font-semibold text-[color:var(--ops-text-title)]">{step.stateKey}</div>
              <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{step.actorLabel} · {step.atomKey || step.atomType}</div>
            </div>
            <span className={['rounded-full border px-3 py-1 text-xs', statusClass(step.status)].join(' ')}>{step.status}</span>
          </div>
          <p className="mt-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">{step.purpose}</p>
          <div className="mt-3 grid gap-2 text-xs md:grid-cols-2">
            <KeyList label="Inputs" values={step.reads} />
            <KeyList label="Outputs" values={step.writes} />
          </div>
          <div className="mt-3">
            <KeyList label="Correctness Signal" values={step.successSignals} />
          </div>
          <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">
            Decision: {step.matchedTransition ? `${step.matchedTransition} -> ${step.nextState || '-'}` : 'not evaluated'} · Evidence {step.evidenceArtifacts.length}
          </div>
        </button>
      ))}
    </div>
  )
}

function KeyList({ label, values }: Readonly<{ label: string; values: string[] }>) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className="mt-1 flex flex-wrap gap-1">
        {values.length ? values.map((value) => (
          <span key={value} className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-600">{value}</span>
        )) : <span className="text-[color:var(--ops-text-caption)]">-</span>}
      </div>
    </div>
  )
}

function StepInspector({ step }: Readonly<{ step: StepViewModel }>) {
  const [tab, setTab] = useState<InspectorTab>('overview')

  useEffect(() => {
    setTab('overview')
  }, [step.stateKey])

  const tabs: Array<{ key: InspectorTab; label: string }> = [
    { key: 'overview', label: 'Overview' },
    { key: 'inputs', label: 'Inputs' },
    { key: 'outputs', label: 'Outputs' },
    { key: 'evidence', label: 'Evidence' },
    { key: 'transition', label: 'Transition' },
  ]

  return (
    <Panel title="Step Inspector" testId="workflow-step-inspector">
      <div>
        <div className="font-mono text-lg font-semibold text-[color:var(--ops-text-title)]">{step.stateKey}</div>
        <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{step.actorLabel} · {step.atomKey || step.atomType}</div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {tabs.map((item) => (
          <button
            key={item.key}
            type="button"
            className={[
              'rounded-lg px-3 py-1.5 text-xs font-medium',
              tab === item.key ? 'bg-[color:var(--ops-text-title)] text-white' : 'bg-slate-100 text-slate-600',
            ].join(' ')}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="mt-4">
        {tab === 'overview' ? (
          <div className="space-y-4 text-sm text-[color:var(--ops-text-muted)]">
            <p className="leading-7">{step.purpose}</p>
            <InspectorSection title="Success Signals" values={step.successSignals} />
            <InspectorSection title="Failure Signals" values={step.failureSignals} />
            <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-50 p-3 text-xs">
              Status: {step.status} · Duration: {step.invocation?.duration_ms ?? 0}ms
            </div>
          </div>
        ) : null}
        {tab === 'inputs' ? <JsonBlock value={step.inputs} /> : null}
        {tab === 'outputs' ? <JsonBlock value={step.outputs} /> : null}
        {tab === 'evidence' ? (
          <div className="space-y-3">
            <InspectorSection title="Expected Evidence" values={step.evidenceHints} />
            {step.evidenceArtifacts.map((artifact) => (
              <details key={artifact.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] p-3">
                <summary className="cursor-pointer text-sm font-semibold text-[color:var(--ops-text-title)]">{artifactDisplayTitle(artifact)}</summary>
                <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">{artifact.content_summary || '-'}</div>
                <div className="mt-3">
                  <JsonBlock value={artifact.payload} maxHeight="max-h-[220px]" />
                </div>
              </details>
            ))}
            {!step.evidenceArtifacts.length ? <div className="text-sm text-[color:var(--ops-text-muted)]">No evidence artifacts linked to this step.</div> : null}
          </div>
        ) : null}
        {tab === 'transition' ? (
          <div className="space-y-3">
            <MiniFact label="Matched Condition" value={step.matchedTransition || '-'} />
            <MiniFact label="Next State" value={step.nextState || '-'} />
            <MiniFact label="Output Key" value={step.definitionState?.output_key || '-'} />
            <JsonBlock value={step.definitionState?.transitions || []} maxHeight="max-h-[220px]" />
          </div>
        ) : null}
      </div>
    </Panel>
  )
}

function InspectorSection({ title, values }: Readonly<{ title: string; values: string[] }>) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">{title}</div>
      <ul className="mt-2 space-y-1">
        {values.length ? values.map((value) => (
          <li key={value} className="rounded-xl bg-slate-50 px-3 py-2 text-sm text-[color:var(--ops-text-muted)]">{value}</li>
        )) : <li className="text-sm text-[color:var(--ops-text-caption)]">-</li>}
      </ul>
    </div>
  )
}

function EvidenceMap({ steps }: Readonly<{ steps: StepViewModel[] }>) {
  return (
    <Panel title="Evidence Map" testId="workflow-evidence-map">
      <div className="space-y-4">
        {steps.map((step) => (
          <div key={step.stateKey} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="font-mono text-sm font-semibold text-[color:var(--ops-text-title)]">{step.stateKey}</div>
                <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{step.evidenceArtifacts.length} evidence artifacts</div>
              </div>
              <span className={['rounded-full border px-3 py-1 text-xs', statusClass(step.status)].join(' ')}>{step.status}</span>
            </div>
            <div className="mt-3 space-y-2">
              {step.evidenceArtifacts.map((artifact) => (
                <details key={artifact.id} className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-slate-50 px-3 py-2">
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

function GateDeliveryPanel({
  detail,
  busyGateId,
  onDecide,
}: Readonly<{
  detail: DeclarativeWorkflowRunDetail
  busyGateId: number | null
  onDecide: (gate: DeclarativeHumanGate, decision: string) => void
}>) {
  const pr = (detail.blackboard.pr || {}) as Record<string, unknown>
  const vcs = (pr.vcs || {}) as Record<string, unknown>
  const sync = (pr.sync || {}) as Record<string, unknown>
  const notifications = detail.notifications || []
  return (
    <div className="space-y-5" data-testid="workflow-gates-delivery">
      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
      <Panel title="Human Gates">
        <div className="space-y-3">
          {detail.human_gates.map((gate) => (
            <div key={gate.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-semibold text-[color:var(--ops-text-title)]">{gate.gate_type} · {gate.state_key}</div>
                  <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{gate.reason}</div>
                  <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">risk {gate.risk_level} · {gate.status} · {formatTime(gate.created_at)}</div>
                </div>
                {gate.status === 'pending' ? (
                  <div className="flex flex-wrap gap-2">
                    {['approve', 'reject', 'continue_retry'].map((decision) => (
                      <button
                        key={decision}
                        type="button"
                        className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-50"
                        disabled={busyGateId === gate.id}
                        onClick={() => onDecide(gate, decision)}
                      >
                        {decision}
                      </button>
                    ))}
                  </div>
                ) : (
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-600">{gate.decision || gate.status}</span>
                )}
              </div>
            </div>
          ))}
          {detail.human_gates.length === 0 ? <div className="text-sm text-[color:var(--ops-text-muted)]">暂无人工门禁。</div> : null}
        </div>
      </Panel>

      <Panel title="PR Delivery" testId="workflow-pr-delivery">
        <div className="grid gap-3 md:grid-cols-2">
          <MiniFact label="PR Status" value={String(pr.pr_status || sync.pr_status || pr.status || '-')} />
          <MiniFact label="Branch" value={String(pr.branch_name || sync.branch_name || vcs.branch_name || '-')} />
          <MiniFact label="Base" value={String(pr.base_branch || sync.base_branch || vcs.base_branch || '-')} />
          <MiniFact label="VCS" value={String(vcs.status || '-')} />
        </div>
        {pr.url ? (
          <a className="mt-4 inline-flex rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white" href={String(pr.url)} target="_blank" rel="noreferrer">
            Open GitHub PR
          </a>
        ) : null}
        {pr.compare_url ? (
          <a className="ml-2 mt-4 inline-flex rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" href={String(pr.compare_url)} target="_blank" rel="noreferrer">
            Compare
          </a>
        ) : null}
        {Array.isArray(pr.blockers) && pr.blockers.length ? (
          <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            {pr.blockers.map((blocker) => String(blocker)).join('; ')}
          </div>
        ) : null}
      </Panel>
      </div>

      <Panel title="Lark Notifications" testId="workflow-lark-notifications">
        <div className="space-y-3">
          {notifications.map((delivery) => (
            <div key={delivery.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className={['rounded-full border px-3 py-1 text-xs', statusClass(delivery.status)].join(' ')}>{delivery.status}</span>
                <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-600">{delivery.channel}</span>
                <span className="font-mono text-xs text-[color:var(--ops-text-caption)]">{delivery.event_type}</span>
              </div>
              <div className="mt-3 text-sm font-medium text-[color:var(--ops-text-title)]">{String(delivery.payload?.summary || delivery.event_key)}</div>
              <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">
                {formatTime(delivery.delivered_at || delivery.created_at)} · {delivery.response_excerpt || 'no response excerpt'}
              </div>
              {delivery.fingerprint_key ? (
                <div className="mt-3 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-800">
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
      </Panel>
    </div>
  )
}

function DebugPanel({ detail }: Readonly<{ detail: DeclarativeWorkflowRunDetail }>) {
  return (
    <div className="grid gap-5 xl:grid-cols-2" data-testid="workflow-debug-panel">
      <Panel title="Raw Blackboard JSON">
        <JsonBlock value={detail.blackboard} maxHeight="max-h-[620px]" />
      </Panel>
      <Panel title="Raw Artifacts">
        <div className="space-y-3">
          {detail.artifacts.map((artifact) => (
            <details key={artifact.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] p-4">
              <summary className="cursor-pointer font-semibold text-[color:var(--ops-text-title)]">{artifact.artifact_type} #{artifact.id}</summary>
              <div className="mt-3">
                <JsonBlock value={artifact.payload} maxHeight="max-h-[320px]" />
              </div>
            </details>
          ))}
        </div>
      </Panel>
      <Panel title="Raw Transition Events">
        <JsonBlock value={detail.events} maxHeight="max-h-[520px]" />
      </Panel>
      <Panel title="Raw Atom Invocations">
        <JsonBlock value={detail.atom_invocations} maxHeight="max-h-[520px]" />
      </Panel>
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
  const [busyGateId, setBusyGateId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<WorkflowTab>('overview')
  const [selectedStepKey, setSelectedStepKey] = useState<string>('')

  async function load() {
    if (!Number.isFinite(workflowRunId)) return
    setLoading(true)
    setError(null)
    try {
      const nextDetail = await api.getWorkflowRun(workflowRunId)
      setDetail(nextDetail)
      setSelectedStepKey((current) => current || nextDetail.current_state)
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

  async function decideGate(gate: DeclarativeHumanGate, decision: string) {
    if (!detail) return
    setBusyGateId(gate.id)
    setError(null)
    try {
      setDetail(await api.decideWorkflowHumanGate(detail.id, gate.id, {
        decision,
        reviewer: 'operator',
        comment: `Operator ${decision} from workflow detail`,
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : '门禁决策失败')
    } finally {
      setBusyGateId(null)
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

  useEffect(() => {
    load().catch(() => {})
  }, [workflowRunId])

  useEffect(() => {
    const tab = new URLSearchParams(location.search).get('tab')
    if (tab === 'delivery') {
      setActiveTab('gates')
    } else if (tab && WORKFLOW_TABS.some((item) => item.key === tab)) {
      setActiveTab(tab as WorkflowTab)
    }
  }, [location.search])

  const steps = useMemo(() => detail ? buildStepViewModels(detail, definition) : [], [detail, definition])
  const selectedStep = steps.find((step) => step.stateKey === selectedStepKey) || steps[0]
  const nextAction = detail ? buildNextAction(detail) : null

  const selectStep = (stepKey: string) => {
    setSelectedStepKey(stepKey)
    setActiveTab('steps')
  }

  if (loading && !detail) {
    return <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white p-6 text-sm text-[color:var(--ops-text-muted)]">加载工作流中…</div>
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
        onSetTab={setActiveTab}
      />

      <WorkflowRunTabs activeTab={activeTab} onChange={setActiveTab} />

      {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}

      {activeTab === 'overview' ? (
        <div className="space-y-5" data-testid="workflow-overview-tab">
          <RunBriefPanel detail={detail} nextAction={nextAction} />
          <CompletionArchivePanel detail={detail} onArchive={() => archiveRun().catch(() => {})} onCreateFollowup={() => createFollowup().catch(() => {})} />
          <CorrectnessPanel detail={detail} />
          <CompactStepRail steps={steps} selectedStepKey={selectedStep?.stateKey || ''} onSelect={selectStep} />
        </div>
      ) : null}

      {activeTab === 'steps' && selectedStep ? (
        <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]" data-testid="workflow-steps-tab">
          <Panel title="Step Explorer">
            <StepExplorer steps={steps} selectedStepKey={selectedStep.stateKey} onSelect={setSelectedStepKey} />
          </Panel>
          <StepInspector step={selectedStep} />
        </div>
      ) : null}

      {activeTab === 'evidence' ? <EvidenceMap steps={steps} /> : null}

      {activeTab === 'gates' ? (
        <GateDeliveryPanel detail={detail} busyGateId={busyGateId} onDecide={(gate, decision) => { decideGate(gate, decision).catch(() => {}) }} />
      ) : null}

      {activeTab === 'debug' ? <DebugPanel detail={detail} /> : null}
    </div>
  )
}
