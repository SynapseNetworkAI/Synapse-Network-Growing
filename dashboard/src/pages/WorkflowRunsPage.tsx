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
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setItems(await api.getWorkflowRuns())
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载工作流失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [])

  return (
    <div className="space-y-5" data-testid="workflow-runs-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white px-5 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">State Machine Runs</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">工作流运行</h2>
            <p className="mt-2 text-sm text-[color:var(--ops-text-muted)]">Declarative Workflow Factory 的状态机运行列表。</p>
          </div>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>
            刷新
          </button>
        </div>
      </section>

      {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}

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
                  <td className="px-5 py-8 text-center text-sm text-[color:var(--ops-text-muted)]" colSpan={8}>暂无 declarative workflow run。</td>
                </tr>
              ) : null}
              {loading ? (
                <tr>
                  <td className="px-5 py-8 text-center text-sm text-[color:var(--ops-text-muted)]" colSpan={8}>加载中…</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
