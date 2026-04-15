import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ErrorFingerprint, api } from '../api'
import { EmptyPane, StateBadge } from '../components/workbench'

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function toneForSeverity(value: string) {
  if (value === 'critical' || value === 'high') return 'blocked'
  if (value === 'normal') return 'running'
  return 'muted'
}

export default function ErrorsPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<ErrorFingerprint[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      setItems(await api.getErrors())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return items
    return items.filter((item) =>
      [item.fingerprint_key, item.service_name, item.summary, item.project_key || '', item.severity].join('\n').toLowerCase().includes(needle),
    )
  }, [items, search])

  return (
    <div className="space-y-5" data-testid="errors-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white px-5 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Errors</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">错误列表</h2>
          </div>
          <div className="flex items-center gap-2">
            <input
              className="w-72 rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm"
              placeholder="搜索 service / fingerprint"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>
              刷新
            </button>
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse">
            <thead className="bg-slate-50/90">
              <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                <th className="px-5 py-4 font-medium">服务</th>
                <th className="px-4 py-4 font-medium">严重级别</th>
                <th className="px-4 py-4 font-medium">来源</th>
                <th className="px-4 py-4 font-medium">发现策略</th>
                <th className="px-4 py-4 font-medium">需求 / 执行</th>
                <th className="px-4 py-4 font-medium">最后出现</th>
                <th className="px-5 py-4 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={item.fingerprint_key} className="border-t border-[color:var(--ops-stroke-soft)] hover:bg-slate-50/80">
                  <td className="px-5 py-4">
                    <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{item.service_name}</div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{item.fingerprint_key}</div>
                  </td>
                  <td className="px-4 py-4">
                    <StateBadge tone={toneForSeverity(item.severity)}>{item.severity}</StateBadge>
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{item.source_kind}</td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                    {item.discovery_recommendation?.discovery_action || item.discovery_status || '-'}
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                    #{item.linked_requirement_id || '-'} · #{item.latest_execution_run_id || '-'}
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(item.latest_seen_at)}</td>
                  <td className="px-5 py-4">
                    <div className="flex flex-wrap justify-end gap-2">
                      <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/requirements/${item.linked_requirement_id}`)} disabled={!item.linked_requirement_id}>
                        需求
                      </button>
                      <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/executions/${item.latest_execution_run_id}`)} disabled={!item.latest_execution_run_id}>
                        执行
                      </button>
                      <button type="button" className="rounded-lg bg-[color:var(--ops-text-title)] px-3 py-2 text-sm text-white" onClick={() => navigate(`/errors/${encodeURIComponent(item.fingerprint_key)}`)}>
                        查看
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!loading && filtered.length === 0 && (
          <div className="p-6">
            <EmptyPane>暂无错误记录。</EmptyPane>
          </div>
        )}
      </section>
    </div>
  )
}
