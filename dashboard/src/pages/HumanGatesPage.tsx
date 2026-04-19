import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, DeclarativeWorkflowRunSummary } from '../api'
import { ActionButton, AgentReasoningCard, CockpitPanel, EmptyCockpitState, MetricTile } from '../components/controlPlane'
import { StateBadge, useToast } from '../components/workbench'

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function gateTone(item: DeclarativeWorkflowRunSummary) {
  if (['critical', 'high'].includes(item.risk_level)) return 'danger'
  if (item.pending_human_gate_count > 0 || item.needs_human) return 'warning'
  return 'info'
}

export default function HumanGatesPage() {
  const [items, setItems] = useState<DeclarativeWorkflowRunSummary[]>([])
  const [failed, setFailed] = useState<DeclarativeWorkflowRunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const toast = useToast()
  const navigate = useNavigate()

  const load = () => {
    setLoading(true)
    setError(null)
    Promise.all([
      api.getWorkflowRunsPage({ tab: 'needs_human', page_size: 80 }),
      api.getWorkflowRunsPage({ tab: 'failed', page_size: 40 }),
    ])
      .then(([needsHuman, failedRuns]) => {
        setItems(needsHuman.items)
        setFailed(failedRuns.items)
      })
      .catch((err) => setError(err.message || String(err)))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  return (
    <div className="space-y-6">
      <CockpitPanel
        eyebrow="Human Oracle"
        title="门禁与审批"
        description="所有高风险动作、证据不足、发布/资金/生产相关决策都必须在这里由人类放行。Agent 只提交证据，不自己越权。"
        actions={<ActionButton onClick={load}>刷新</ActionButton>}
      >
        <div className="grid gap-4 md:grid-cols-4">
          <MetricTile label="Pending Gates" value={items.length} detail="等待你处理的 workflow" tone={items.length ? 'warning' : 'muted'} />
          <MetricTile label="High Risk" value={items.filter((item) => ['critical', 'high'].includes(item.risk_level)).length} detail="资金/发布/生产等高风险" tone="danger" />
          <MetricTile label="Failed Runs" value={failed.length} detail="重试耗尽或证据不足" tone={failed.length ? 'danger' : 'muted'} />
          <MetricTile label="Release Blockers" value={items.filter((item) => item.release_status && item.release_status !== 'done').length} detail="PR / deploy / observing 阻塞" tone="info" />
        </div>
      </CockpitPanel>

      {error ? <AgentReasoningCard title="Gate queue failed to load" tone="danger" summary={error} /> : null}

      <CockpitPanel eyebrow="Pending Approvals" title="需要人工判断的工作流" description="点击 Review Gate 进入 Run Explorer，在 Gates & Delivery 中查看证据并做决定。">
        {loading ? (
          <div className="text-sm text-[color:var(--ops-text-muted)]">Loading human gates...</div>
        ) : items.length ? (
          <div className="grid gap-3">
            {items.map((item) => (
              <div key={item.id} className="rounded-3xl border border-white/10 bg-white/[0.035] px-5 py-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="machine-label text-[color:var(--ops-text-caption)]">Workflow Run #{item.id}</div>
                    <h3 className="mt-2 text-lg font-semibold text-[color:var(--ops-text-title)]">{item.workflow_key}</h3>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
                      Requirement #{item.requirement_id} {item.requirement_title || ''} 当前停在 `{item.current_state}`。{item.pending_human_gate_count || 0} 个 gate 等待处理。
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <StateBadge tone={gateTone(item) === 'danger' ? 'blocked' : 'validating'}>{item.risk_level}</StateBadge>
                      <StateBadge tone="validating">{item.outcome_label || item.status}</StateBadge>
                      {item.simulated_delivery ? <StateBadge tone="validating">simulated delivery</StateBadge> : null}
                      {item.evidence_complete === false ? <StateBadge tone="validating">evidence incomplete</StateBadge> : null}
                    </div>
                  </div>
                  <div className="flex flex-wrap justify-end gap-2">
                    <ActionButton onClick={() => navigate(`/workflows/${item.id}?tab=gates`)} tone="primary">Review Gate</ActionButton>
                    <ActionButton onClick={() => navigate(`/requirements/${item.requirement_id}`)}>Requirement</ActionButton>
                  </div>
                </div>
                <div className="mt-4 grid gap-3 border-t border-white/8 pt-4 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-4">
                  <div>last atom: <span className="font-mono text-cyan-100">{item.last_atom || '-'}</span></div>
                  <div>artifacts: {item.artifact_count ?? 0}</div>
                  <div>updated: {formatTime(item.updated_at)}</div>
                  <div>goal: {item.goal_key || '-'}</div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyCockpitState
            title="没有待处理门禁"
            description="当前没有 pending human gate。高风险动作仍会在 workflow risk gate 处被拦截，并出现在这里。"
            actions={<ActionButton href="/workflows">查看 Workflow Runs</ActionButton>}
          />
        )}
      </CockpitPanel>

      <CockpitPanel eyebrow="Failed & Blocked" title="失败与阻断" description="这些 workflow 不一定都需要立即审批，但通常需要 operator 检查最后一次失败证据。">
        {failed.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {failed.slice(0, 8).map((item) => (
              <AgentReasoningCard
                key={item.id}
                title={`${item.workflow_key} · #${item.id}`}
                tone="danger"
                summary={<span>{item.requirement_title || `Requirement #${item.requirement_id}`} · state {item.current_state} · {item.resolution || item.status}</span>}
                metadata={<Link className="text-cyan-200 hover:text-cyan-100" to={`/workflows/${item.id}`}>Inspect failure evidence</Link>}
              />
            ))}
          </div>
        ) : (
          <div className="text-sm text-[color:var(--ops-text-muted)]">No failed workflows in the current view.</div>
        )}
      </CockpitPanel>
    </div>
  )
}
