import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, OptimizationSignal } from '../api'

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

const severityClass: Record<string, string> = {
  high: 'bg-red-100 text-red-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-slate-100 text-slate-700',
}

export default function OptimizationSignals() {
  const navigate = useNavigate()
  const [signals, setSignals] = useState<OptimizationSignal[]>([])
  const [status, setStatus] = useState('open')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [actioningId, setActioningId] = useState<number | null>(null)
  const [autoIntaking, setAutoIntaking] = useState(false)

  const load = async (refresh = false) => {
    if (refresh) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    setError('')
    try {
      const data = refresh
        ? await api.refreshOptimizationSignals()
        : await api.getOptimizationSignals(status || undefined)
      setSignals(status ? data.filter((signal) => signal.status === status) : data)
    } catch (error) {
      const message = error instanceof Error ? error.message : '无法加载优化信号'
      setSignals([])
      setError(message)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [status])

  if (loading) {
    return <div data-testid="optimization-signals-loading" className="rounded-xl border bg-white p-6 text-sm text-gray-500">正在加载优化信号…</div>
  }

  return (
    <div data-testid="optimization-signals-page" className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">优化信号</h2>
          <p className="text-sm text-gray-500">把 bug report、manual override 和 delivery blocker 沉淀成真正可转需求的优化信号。</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            data-testid="optimization-signal-filter"
            className="rounded border px-3 py-2 text-sm"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="open">open</option>
            <option value="converted">converted</option>
            <option value="dismissed">dismissed</option>
            <option value="resolved">resolved</option>
            <option value="">all</option>
          </select>
          <button
            data-testid="optimization-signal-refresh"
            className="rounded border px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            disabled={refreshing}
            onClick={() => load(true).catch(() => {})}
          >
            {refreshing ? '刷新中…' : '刷新信号'}
          </button>
          <button
            data-testid="optimization-signal-auto-intake"
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            disabled={autoIntaking}
            onClick={async () => {
              setAutoIntaking(true)
              try {
                const result = await api.autoIntakeOptimizationSignals({ max_created: 1 })
                await load()
                if (result.created[0]) {
                  navigate(`/requirements/${result.created[0].requirement_id}`)
                }
              } finally {
                setAutoIntaking(false)
              }
            }}
          >
            {autoIntaking ? '自动 intake 中…' : '自动转高价值信号'}
          </button>
        </div>
      </div>

      {error && (
        <div data-testid="optimization-signals-error" className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
          {error}
        </div>
      )}

      {signals.length === 0 && (
        <div className="rounded-xl border bg-white p-6 text-sm text-gray-500">当前没有可见优化信号。</div>
      )}

      <div className="grid gap-4">
        {signals.map((signal) => (
          <div key={signal.id} data-testid={`optimization-signal-card-${signal.id}`} className="rounded-xl border bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-semibold text-gray-900">{signal.title}</h3>
                  <span className={`rounded-full px-2 py-0.5 text-xs ${severityClass[signal.severity] || severityClass.low}`}>
                    {signal.severity}
                  </span>
                  <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs text-sky-700">
                    score {Number(signal.score_breakdown?.total || 0).toFixed(1)}
                  </span>
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  {signal.signal_type} · {signal.source_kind} · status={signal.status} · {signal.intake_recommendation || 'observe'}
                </div>
              </div>
              <div className="text-right text-xs text-gray-500">
                <div>occurrences: {signal.occurrence_count}</div>
                <div>confidence: {signal.confidence.toFixed(2)}</div>
              </div>
            </div>

            <p className="mt-3 text-sm text-gray-700">{signal.summary}</p>

            <div className="mt-3 grid gap-2 text-xs text-gray-500 md:grid-cols-2">
              <div>项目: {signal.project_key || 'org-ops'}</div>
              <div>路径: {signal.routing_target_path || signal.project_root_path || '-'}</div>
              <div>最近证据: {formatTime(signal.latest_evidence_at)}</div>
              <div>推荐优先级: {signal.recommended_priority || '-'}</div>
              <div>Impact: {signal.score_breakdown?.impact ?? '-'}</div>
              <div>Risk: {signal.score_breakdown?.risk ?? '-'}</div>
              <div>Urgency: {signal.score_breakdown?.urgency ?? '-'}</div>
              <div>实现成本: {signal.score_breakdown?.implementation_cost ?? '-'}</div>
              <div>已转需求: {signal.converted_requirement_id || '-'}</div>
            </div>

            {signal.evidence.length > 0 && (
              <div className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-700">
                <div className="font-medium">Recent Evidence</div>
                <div className="mt-2 space-y-1">
                  {signal.evidence.slice(0, 3).map((item, index) => (
                    <div key={`${signal.id}-${index}`} className="break-all">{JSON.stringify(item)}</div>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-4 flex gap-2">
              <button
                data-testid={`optimization-signal-create-${signal.id}`}
                className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                disabled={actioningId === signal.id || signal.converted_requirement_id !== null}
                onClick={async () => {
                  setActioningId(signal.id)
                  try {
                    const detail = await api.createRequirementFromSignal(signal.id, {})
                    await load()
                    navigate(`/requirements/${detail.requirement.id}`)
                  } finally {
                    setActioningId(null)
                  }
                }}
              >
                {signal.converted_requirement_id ? '已转需求' : (signal.auto_intake_eligible ? '立即 intake' : '转为需求')}
              </button>
              <button
                data-testid={`optimization-signal-dismiss-${signal.id}`}
                className="rounded-lg border px-4 py-2 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                disabled={actioningId === signal.id || signal.status === 'dismissed'}
                onClick={async () => {
                  setActioningId(signal.id)
                  try {
                    await api.dismissOptimizationSignal(signal.id)
                    await load()
                  } finally {
                    setActioningId(null)
                  }
                }}
              >
                dismiss
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
