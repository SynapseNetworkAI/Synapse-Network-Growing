import { useEffect, useMemo, useState } from 'react'
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
  const outcomeLabel = detail.outcome_label || (hasPendingGate(detail) ? 'Needs Human' : isTrulyCompleted(detail) ? 'Completed' : detail.status)
  return (
    <section className="sticky top-0 z-10 rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5 shadow-sm backdrop-blur" data-testid="workflow-run-header">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Explainable Workflow Run</div>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">{detail.workflow_key}</h2>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <span className={['rounded-full border px-3 py-1 font-medium', statusClass(hasPendingGate(detail) ? 'awaiting_operator' : detail.status)].join(' ')}>{outcomeLabel}</span>
            <span className="rounded-full border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-subtle)] px-3 py-1 text-[color:var(--ops-text-muted)]">run #{detail.id}</span>
            <span className="rounded-full border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-subtle)] px-3 py-1 text-[color:var(--ops-text-muted)]">state: {detail.current_state}</span>
            <span className="rounded-full border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-subtle)] px-3 py-1 text-[color:var(--ops-text-muted)]">risk: {detail.risk_level}</span>
            {detail.simulated_delivery ? <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">Simulated PR</span> : null}
            {detail.evidence_complete === false ? <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">Evidence incomplete</span> : null}
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
              {command.timeout ? <span className="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-rose-700">timeout</span> : null}
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
                  <span className="rounded-full border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-subtle)] px-3 py-1 text-xs text-[color:var(--ops-text-muted)]">{gate.decision || gate.status}</span>
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
        {detail.delivery_summary?.simulated || detail.simulated_delivery ? (
          <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800">
            Simulated PR. This delivery did not create a real external GitHub PR.
          </div>
        ) : null}
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
  const [busyGateId, setBusyGateId] = useState<number | null>(null)
  const [businessOutcomeBusy, setBusinessOutcomeBusy] = useState(false)
  const [activeTab, setActiveTab] = useState<WorkflowTab>('overview')

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

  async function decideGate(gate: DeclarativeHumanGate, decision: string) {
    if (!detail) return
    setBusyGateId(gate.id)
    setError(null)
    try {
      const nextDetail = await api.decideWorkflowHumanGate(detail.id, gate.id, {
        decision,
        reviewer: 'operator',
        comment: `Operator ${decision} from workflow detail`,
      })
      setDetail(nextDetail)
      if (nextDetail.resume_status === 'failed') {
        toast.error('Gate decision saved, but runner resume failed. Inspect Timeline evidence.')
      } else if (nextDetail.resume_attempted) {
        toast.success(`Gate decision saved; runner ${nextDetail.resume_status || 'resumed'}.`)
      }
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
          <GateDeliveryPanel detail={detail} busyGateId={busyGateId} onDecide={(gate, decision) => { decideGate(gate, decision).catch(() => {}) }} />
        </div>
      ) : null}

      {activeTab === 'debug' ? <DebugPanel detail={detail} /> : null}
    </div>
  )
}
