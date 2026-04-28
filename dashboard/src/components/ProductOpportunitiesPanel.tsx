import { useEffect, useState } from 'react'

type ProductOpportunity = {
  id: number
  title: string
  problem: string
  suggested_goal_key: string
  recommended_lane: string
  risk_level: string
  success_metric: string
  next_action: string
  status: string
}

async function planningRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(String(body.detail || `HTTP ${response.status}`))
  }
  return response.json()
}

function laneLabel(value: string) {
  if (value === 'growth_lead') return 'Growth'
  if (value === 'software_engineer') return 'Engineering'
  if (value === 'both') return 'Growth + Engineering'
  return value || 'Product'
}

export function ProductOpportunitiesPanel({ onChanged }: Readonly<{ onChanged?: () => void }>) {
  const [items, setItems] = useState<ProductOpportunity[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await planningRequest<{ items: ProductOpportunity[] }>('/planning/product-opportunities?limit=8')
      setItems(data.items || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Product opportunities failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [])

  async function decide(id: number, action: 'create-goal' | 'defer' | 'reject') {
    setBusy(`${action}:${id}`)
    setError(null)
    try {
      await planningRequest(`/planning/product-opportunities/${id}/${action}`, {
        method: 'POST',
        body: JSON.stringify({ operator: 'operator', reason: `operator_${action.replace('-', '_')}` }),
      })
      await load()
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : `${action} failed`)
    } finally {
      setBusy(null)
    }
  }

  const pending = items.filter((item) => item.status === 'proposed')
  return (
    <section className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5" data-testid="product-opportunities-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Product Opportunities</div>
          <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">产品机会 / Goal Proposals</h3>
          <p className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">Product planner 只提出公司目标和产品缺口；通过人审后才进入正式 Goal 或后续需求链路。</p>
        </div>
        <div className="rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.06] px-4 py-3 text-sm text-cyan-100">
          {pending.length} pending review
        </div>
      </div>
      {error ? <div className="mt-4 rounded-2xl border border-rose-300/25 bg-rose-400/[0.10] px-4 py-3 text-sm text-rose-100">{error}</div> : null}
      {loading ? <div className="mt-4 text-sm text-[color:var(--ops-text-muted)]">Loading product opportunities...</div> : null}
      {!loading && !items.length ? (
        <div className="mt-4 rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] px-4 py-6 text-sm text-[color:var(--ops-text-muted)]">
          暂无产品机会。可在定时任务中手动运行 product_planning_sweep 生成 proposal。
        </div>
      ) : null}
      <div className="mt-4 grid gap-3">
        {items.map((item) => (
          <article key={item.id} className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-[color:var(--ops-text-caption)]">#{item.id}</span>
                  <span className="rounded-full border border-cyan-300/25 bg-cyan-300/[0.08] px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-cyan-100">{laneLabel(item.recommended_lane)}</span>
                  <span className="rounded-full border border-white/10 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-[color:var(--ops-text-muted)]">{item.status}</span>
                </div>
                <h4 className="mt-2 font-semibold text-[color:var(--ops-text-title)]">{item.title}</h4>
                <p className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{item.problem}</p>
                <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">Metric: {item.success_metric || 'operator-defined'}</div>
              </div>
              {item.status === 'proposed' ? (
                <div className="flex flex-wrap gap-2">
                  <button className="rounded-xl bg-[color:var(--ops-accent)] px-3 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={busy === `create-goal:${item.id}`} onClick={() => decide(item.id, 'create-goal')}>Create Goal</button>
                  <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-60" disabled={busy === `defer:${item.id}`} onClick={() => decide(item.id, 'defer')}>Defer</button>
                  <button className="rounded-xl border border-rose-300/30 px-3 py-2 text-sm text-rose-100 disabled:opacity-60" disabled={busy === `reject:${item.id}`} onClick={() => decide(item.id, 'reject')}>Reject</button>
                </div>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
