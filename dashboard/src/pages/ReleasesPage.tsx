import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ReleaseCandidate, api } from '../api'
import { EmptyPane, StateBadge } from '../components/workbench'

const STATUS_LABEL: Record<string, string> = {
  pending: '待交付',
  preparing_branch: '准备分支',
  pushing: '推送中',
  opening_pr: '打开 PR',
  repairing: '交付修复中',
  blocked: '阻塞',
  pr_open: 'PR 已打开',
  merged: '已合并',
  abandoned: '已放弃',
}

function releaseTone(state: string | null | undefined) {
  if (state === 'pr_open' || state === 'merged') return 'delivered'
  if (state === 'repairing' || state === 'pushing' || state === 'opening_pr' || state === 'preparing_branch') return 'running'
  if (state === 'blocked') return 'blocked'
  if (state === 'pending') return 'ready'
  return 'muted'
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

export default function ReleasesPage() {
  const navigate = useNavigate()
  const [candidates, setCandidates] = useState<ReleaseCandidate[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      setCandidates(await api.getReleaseCandidates())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return candidates
    return candidates.filter((item) =>
      [
        String(item.requirement.id),
        item.requirement.title,
        item.requirement.project_display_name || '',
        item.requirement.project_key || '',
        item.release?.project_display_name || '',
        item.release?.status || '',
      ]
        .join('\n')
        .toLowerCase()
        .includes(needle),
    )
  }, [candidates, search])

  return (
    <div className="space-y-5" data-testid="releases-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white px-5 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Releases</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">发布列表</h2>
          </div>
          <div className="flex items-center gap-2">
            <input
              className="w-72 rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm"
              placeholder="搜索 requirement / project"
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
                <th className="px-5 py-4 font-medium">Requirement</th>
                <th className="px-4 py-4 font-medium">验证</th>
                <th className="px-4 py-4 font-medium">发布状态</th>
                <th className="px-4 py-4 font-medium">分支 / PR</th>
                <th className="px-4 py-4 font-medium">更新时间</th>
                <th className="px-5 py-4 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={item.requirement.id} className="border-t border-[color:var(--ops-stroke-soft)] hover:bg-slate-50/80">
                  <td className="px-5 py-4">
                    <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">
                      #{item.requirement.id} {item.requirement.title}
                    </div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">
                      {item.release?.project_display_name || item.requirement.project_display_name || item.requirement.project_key || '-'}
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <StateBadge tone={item.validation.status === 'passed' ? 'delivered' : 'validating'}>{item.validation.status}</StateBadge>
                  </td>
                  <td className="px-4 py-4">
                    <StateBadge tone={releaseTone(item.release?.state || item.release?.status)}>{STATUS_LABEL[item.release?.state || item.release?.status || 'pending'] || item.release?.state || item.release?.status || 'pending'}</StateBadge>
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                    {item.release?.branch_name || '-'} · PR {item.release?.pr_number || '-'}
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(item.release?.updated_at || item.validation.updated_at)}</td>
                  <td className="px-5 py-4">
                    <div className="flex flex-wrap justify-end gap-2">
                      <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/requirements/${item.requirement.id}`)}>
                        需求
                      </button>
                      <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/executions/${item.requirement.latest_execution_run_id}`)} disabled={!item.requirement.latest_execution_run_id}>
                        执行
                      </button>
                      <button type="button" className="rounded-lg bg-[color:var(--ops-text-title)] px-3 py-2 text-sm text-white" onClick={() => navigate(`/releases/${item.requirement.id}`)}>
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
            <EmptyPane>暂无发布候选。</EmptyPane>
          </div>
        )}
      </section>
    </div>
  )
}
