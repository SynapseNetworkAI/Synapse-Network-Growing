import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ErrorFingerprint, api } from '../api'
import { EmptyPane, FieldLabel, InspectorRail, SectionFrame, StateBadge } from '../components/workbench'

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
      [
        item.fingerprint_key,
        item.service_name,
        item.summary,
        item.project_key || '',
        item.severity,
      ]
        .join('\n')
        .toLowerCase()
        .includes(needle),
    )
  }, [items, search])

  return (
    <div className="space-y-[var(--ops-section-gap)]" data-testid="errors-page">
      <SectionFrame
        eyebrow="Error Loop"
        title="错误日志"
        description="错误页是稳定性治理辅助面：聚合 fingerprint、关联 requirement / execution，并记录告警发送历史。"
        actions={
          <div className="flex items-center gap-3">
            <input
              className="w-72 rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm"
              placeholder="搜索 service / fingerprint / summary"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2.5 text-sm font-medium text-white" onClick={() => load().catch(() => {})}>
              刷新
            </button>
          </div>
        }
      >
        <div className="grid gap-4 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-3">
          <div>
            <FieldLabel>错误归并</FieldLabel>
            <div className="mt-2">同一 fingerprint 同时只允许一条未完成 requirement。</div>
          </div>
          <div>
            <FieldLabel>自动回流</FieldLabel>
            <div className="mt-2">新错误会创建或复用 requirement，并立即走 submit 与审批判定。</div>
          </div>
          <div>
            <FieldLabel>告警群</FieldLabel>
            <div className="mt-2">新错误事件与 execution failure 会统一走 alert channel。</div>
          </div>
        </div>
      </SectionFrame>

      <SectionFrame eyebrow="Fingerprints" title="错误指纹" description={loading ? '正在拉取错误数据…' : `${filtered.length} 条 fingerprint`}>
        <div className="grid gap-4">
          {filtered.map((item) => (
            <article key={item.fingerprint_key} className="border-b border-[color:var(--ops-stroke-soft)] pb-5 last:border-b-0 last:pb-0">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.7fr),320px]">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-lg font-semibold text-[color:var(--ops-text-title)]">{item.service_name}</h4>
                    <StateBadge tone={toneForSeverity(item.severity)}>{item.severity}</StateBadge>
                    <StateBadge tone="muted">{item.source_kind}</StateBadge>
                    <StateBadge tone="muted">{item.status}</StateBadge>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">{item.summary}</p>
                  <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">{item.fingerprint_key}</div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2 text-sm text-white" onClick={() => navigate(`/errors/${encodeURIComponent(item.fingerprint_key)}`)}>
                      查看错误详情
                    </button>
                    <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/requirements/${item.linked_requirement_id}`)} disabled={!item.linked_requirement_id}>
                      查看需求
                    </button>
                    <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/executions/${item.latest_execution_run_id}`)} disabled={!item.latest_execution_run_id}>
                      查看执行
                    </button>
                  </div>
                </div>
                <InspectorRail eyebrow={item.project_key || 'Error Fingerprint'} title="Stability Summary" className="bg-transparent shadow-none">
                  <div>
                    <FieldLabel>Occurrence Count</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{item.occurrence_count}</div>
                  </div>
                  <div>
                    <FieldLabel>Latest Seen</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{formatTime(item.latest_seen_at)}</div>
                  </div>
                  <div>
                    <FieldLabel>Linked Requirement</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{item.linked_requirement_id ? `#${item.linked_requirement_id}` : '-'}</div>
                  </div>
                  <div>
                    <FieldLabel>Latest Execution</FieldLabel>
                    <div className="mt-2 text-[color:var(--ops-text-muted)]">{item.latest_execution_run_id ? `#${item.latest_execution_run_id}` : '-'}</div>
                  </div>
                </InspectorRail>
              </div>
            </article>
          ))}

          {!loading && filtered.length === 0 && <EmptyPane>当前还没有错误 fingerprint。</EmptyPane>}
        </div>
      </SectionFrame>
    </div>
  )
}
