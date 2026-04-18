import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, DeclarativeWorkflowRunDetail, DeclarativeHumanGate } from '../api'

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
  if (['completed', 'done', 'passed'].includes(status)) return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  if (['failed', 'error', 'rejected'].includes(status)) return 'border-rose-200 bg-rose-50 text-rose-700'
  if (['pending', 'awaiting_operator', 'awaiting_human'].includes(status)) return 'border-amber-200 bg-amber-50 text-amber-700'
  return 'border-blue-200 bg-blue-50 text-blue-700'
}

function Panel({ title, children, testId }: { title: string; children: ReactNode; testId?: string }) {
  return (
    <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white p-5" data-testid={testId}>
      <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{title}</h3>
      <div className="mt-4">{children}</div>
    </section>
  )
}

export default function WorkflowRunDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const workflowRunId = Number(id)
  const [detail, setDetail] = useState<DeclarativeWorkflowRunDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyGateId, setBusyGateId] = useState<number | null>(null)

  async function load() {
    if (!Number.isFinite(workflowRunId)) return
    setLoading(true)
    setError(null)
    try {
      setDetail(await api.getWorkflowRun(workflowRunId))
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

  useEffect(() => {
    load().catch(() => {})
  }, [workflowRunId])

  if (loading && !detail) {
    return <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white p-6 text-sm text-[color:var(--ops-text-muted)]">加载工作流中…</div>
  }

  if (!detail) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
        {error || '工作流不存在'}
      </div>
    )
  }

  return (
    <div className="space-y-5" data-testid="workflow-run-detail-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white px-5 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Declarative Workflow</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">{detail.workflow_key}</h2>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <span className={['rounded-full border px-3 py-1 font-medium', statusClass(detail.status)].join(' ')}>{detail.status}</span>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-600">state: {detail.current_state}</span>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-600">risk: {detail.risk_level}</span>
              {detail.resolution ? <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-emerald-700">resolution: {detail.resolution}</span> : null}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => navigate(`/requirements/${detail.requirement_id}`)}>
              查看需求
            </button>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>
              刷新
            </button>
          </div>
        </div>
      </section>

      {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}

      <div className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
        <Panel title="State Timeline" testId="workflow-state-timeline">
          <div className="space-y-3">
            {detail.events.map((event) => (
              <div key={event.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-50/70 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-mono text-sm text-[color:var(--ops-text-title)]">
                    {event.from_state || 'start'} → {event.to_state}
                  </div>
                  <div className="text-xs text-[color:var(--ops-text-caption)]">{formatTime(event.created_at)}</div>
                </div>
                <div className="mt-2 text-xs text-[color:var(--ops-text-muted)]">{event.event_type}{event.condition ? ` · ${event.condition}` : ''}</div>
              </div>
            ))}
            {detail.events.length === 0 ? <div className="text-sm text-[color:var(--ops-text-muted)]">暂无状态事件。</div> : null}
          </div>
        </Panel>

        <Panel title="Blackboard" testId="workflow-blackboard">
          <pre className="max-h-[420px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{prettyJson(detail.blackboard)}</pre>
        </Panel>
      </div>

      <Panel title="Human Gates" testId="workflow-human-gates">
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
                        onClick={() => decideGate(gate, decision)}
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

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Atom Invocations" testId="workflow-atom-invocations">
          <div className="space-y-3">
            {detail.atom_invocations.map((item) => (
              <div key={item.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-semibold text-[color:var(--ops-text-title)]">{item.atom_key}</div>
                  <span className={['rounded-full border px-3 py-1 text-xs', statusClass(item.status)].join(' ')}>{item.status}</span>
                </div>
                <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{item.state_key} · {item.atom_type} · {item.duration_ms}ms</div>
                <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">{item.output_summary || item.error_excerpt || '-'}</div>
              </div>
            ))}
            {detail.atom_invocations.length === 0 ? <div className="text-sm text-[color:var(--ops-text-muted)]">暂无 atom 调用。</div> : null}
          </div>
        </Panel>

        <Panel title="Artifacts" testId="workflow-artifacts">
          <div className="space-y-3">
            {detail.artifacts.map((artifact) => (
              <details key={artifact.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] p-4">
                <summary className="cursor-pointer font-semibold text-[color:var(--ops-text-title)]">
                  {artifact.artifact_type} #{artifact.id}
                </summary>
                <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">{artifact.state_key || '-'} · {artifact.atom_key || '-'} · {formatTime(artifact.created_at)}</div>
                <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">{artifact.content_summary || '-'}</div>
                <pre className="mt-3 max-h-[260px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{prettyJson(artifact.payload)}</pre>
              </details>
            ))}
            {detail.artifacts.length === 0 ? <div className="text-sm text-[color:var(--ops-text-muted)]">暂无 artifacts。</div> : null}
          </div>
        </Panel>
      </div>
    </div>
  )
}
