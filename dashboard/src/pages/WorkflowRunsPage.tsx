import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, DeclarativeWorkflowRunSummary } from '../api'

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function statusTone(status: string) {
  if (['completed', 'done', 'passed'].includes(status)) return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  if (['running', 'paused', 'awaiting_human'].includes(status)) return 'border-blue-200 bg-blue-50 text-blue-700'
  if (['failed', 'error'].includes(status)) return 'border-rose-200 bg-rose-50 text-rose-700'
  return 'border-slate-200 bg-slate-50 text-slate-600'
}

export default function WorkflowRunsPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<DeclarativeWorkflowRunSummary[]>([])
  const [filters, setFilters] = useState({
    status: '',
    workflow_key: '',
    current_state: '',
    risk_level: '',
    pending_human_gate: '',
    requirement_id: '',
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setItems(await api.getWorkflowRuns({
        limit: 200,
        status: filters.status || undefined,
        workflow_key: filters.workflow_key || undefined,
        current_state: filters.current_state || undefined,
        risk_level: filters.risk_level || undefined,
        pending_human_gate: filters.pending_human_gate ? filters.pending_human_gate === 'yes' : undefined,
        requirement_id: filters.requirement_id ? Number(filters.requirement_id) : undefined,
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载工作流失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [filters.status, filters.workflow_key, filters.current_state, filters.risk_level, filters.pending_human_gate])

  const stats = {
    running: items.filter((item) => ['running', 'pending'].includes(item.status)).length,
    awaiting: items.filter((item) => item.status === 'awaiting_operator').length,
    failed: items.filter((item) => item.status === 'failed').length,
    succeeded: items.filter((item) => ['succeeded', 'completed', 'done'].includes(item.status)).length,
    gates: items.reduce((sum, item) => sum + (item.pending_human_gate_count || 0), 0),
  }

  return (
    <div className="space-y-5" data-testid="workflow-runs-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white px-5 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">State Machine Runs</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">工作流运行</h2>
            <p className="mt-2 text-sm text-[color:var(--ops-text-muted)]">Operator 管理面：查看状态机、atom、门禁和生成的运行任务。</p>
          </div>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>
            刷新
          </button>
        </div>
      </section>

      {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}

      <section className="grid gap-3 md:grid-cols-5" data-testid="workflow-run-stats">
        {[
          ['running', stats.running],
          ['awaiting_operator', stats.awaiting],
          ['failed', stats.failed],
          ['succeeded', stats.succeeded],
          ['pending human gate', stats.gates],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white px-4 py-4">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div>
            <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{value}</div>
          </div>
        ))}
      </section>

      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white px-5 py-4" data-testid="workflow-run-filters">
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}>
            <option value="">全部状态</option>
            <option value="running">running</option>
            <option value="awaiting_operator">awaiting_operator</option>
            <option value="failed">failed</option>
            <option value="succeeded">succeeded</option>
          </select>
          <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" value={filters.workflow_key} onChange={(event) => setFilters((current) => ({ ...current, workflow_key: event.target.value }))}>
            <option value="">全部 workflow</option>
            <option value="agent_self_repair">agent_self_repair</option>
            <option value="gateway_reliability_repair">gateway_reliability_repair</option>
          </select>
          <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" placeholder="current_state" value={filters.current_state} onChange={(event) => setFilters((current) => ({ ...current, current_state: event.target.value }))} />
          <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" value={filters.risk_level} onChange={(event) => setFilters((current) => ({ ...current, risk_level: event.target.value }))}>
            <option value="">全部风险</option>
            <option value="normal">normal</option>
            <option value="high">high</option>
            <option value="critical">critical</option>
          </select>
          <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" value={filters.pending_human_gate} onChange={(event) => setFilters((current) => ({ ...current, pending_human_gate: event.target.value }))}>
            <option value="">Human Gate</option>
            <option value="yes">pending only</option>
            <option value="no">no pending</option>
          </select>
          <div className="flex gap-2">
            <input className="min-w-0 flex-1 rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" placeholder="requirement id" value={filters.requirement_id} onChange={(event) => setFilters((current) => ({ ...current, requirement_id: event.target.value.replace(/[^0-9]/g, '') }))} />
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => load().catch(() => {})}>查</button>
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse">
            <thead className="bg-slate-50/90">
              <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                <th className="px-5 py-4 font-medium">Workflow</th>
                <th className="px-4 py-4 font-medium">需求</th>
                <th className="px-4 py-4 font-medium">状态</th>
                <th className="px-4 py-4 font-medium">当前节点</th>
                <th className="px-4 py-4 font-medium">风险</th>
                <th className="px-4 py-4 font-medium">Human Gate</th>
                <th className="px-4 py-4 font-medium">Last Atom</th>
                <th className="px-4 py-4 font-medium">更新时间</th>
                <th className="px-5 py-4 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t border-[color:var(--ops-stroke-soft)] transition hover:bg-slate-50/80">
                  <td className="px-5 py-4">
                    <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{item.workflow_key}</div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">#{item.id}</div>
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">#{item.requirement_id} {item.requirement_title || ''}</td>
                  <td className="px-4 py-4">
                    <span className={['rounded-full border px-3 py-1 text-xs font-medium', statusTone(item.status)].join(' ')}>{item.status}</span>
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-body)]">{item.current_state}</td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{item.risk_level}</td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{item.pending_human_gate_count ? `${item.pending_human_gate_count} pending` : '-'}</td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{item.last_atom || '-'}</td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(item.updated_at)}</td>
                  <td className="px-5 py-4 text-right">
                    <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/workflows/${item.id}`)}>
                      查看
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && items.length === 0 ? (
                <tr>
                  <td className="px-5 py-8 text-center text-sm text-[color:var(--ops-text-muted)]" colSpan={9}>暂无 declarative workflow run。</td>
                </tr>
              ) : null}
              {loading ? (
                <tr>
                  <td className="px-5 py-8 text-center text-sm text-[color:var(--ops-text-muted)]" colSpan={9}>加载中…</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
