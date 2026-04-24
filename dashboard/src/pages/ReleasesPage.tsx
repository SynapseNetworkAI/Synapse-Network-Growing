import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ReleaseCandidate, api } from '../api'
import { EmptyPane, StateBadge, useToast } from '../components/workbench'

const STATUS_LABEL: Record<string, string> = {
  pending: '待交付',
  preparing_branch: '准备分支',
  pushing: '推送中',
  opening_pr: '打开 PR',
  repairing: '交付修复中',
  blocked: '阻塞',
  pr_open: 'PR 已打开',
  pr_opened: 'PR 已打开',
  pr_closed: 'PR 已关闭',
  ready_for_merge: '等待合并',
  merged: '已合并',
  abandoned: '已废弃',
  no_deploy: '无需部署',
}

function releaseTone(state: string | null | undefined) {
  if (state === 'merged') return 'delivered'
  if (state === 'pr_open' || state === 'pr_opened' || state === 'ready_for_merge') return 'ready'
  if (state === 'repairing' || state === 'pushing' || state === 'opening_pr' || state === 'preparing_branch') return 'running'
  if (state === 'blocked' || state === 'pr_closed' || state === 'abandoned') return 'blocked'
  if (state === 'pending') return 'ready'
  return 'muted'
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function releaseAction(item: ReleaseCandidate): { key: 'prepare' | 'open-pr' | 'repair-gate' | null; label: string } {
  const release = item.release
  if (!release) return { key: 'prepare', label: '准备分支' }
  if (release.status === 'release_blocked' && release.next_action === 'restart_current') return { key: 'prepare', label: '重新准备' }
  if (release.status === 'release_blocked' && release.next_action === 'repair_delivery' && release.repairable) return { key: 'repair-gate', label: '修复门禁' }
  if (release.status === 'branch_prepared' || release.status === 'ready') return { key: 'open-pr', label: '打开 PR' }
  if (release.state === 'pending') return { key: 'prepare', label: '准备分支' }
  return { key: null, label: '查看' }
}

function workflowRunIdFor(item: ReleaseCandidate) {
  return item.requirement.active_workflow_run_id ?? item.requirement.active_workflow_run_summary?.id ?? null
}

export default function ReleasesPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [candidates, setCandidates] = useState<ReleaseCandidate[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [syncBusy, setSyncBusy] = useState(false)

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
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
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
            <button
              type="button"
              className="rounded-xl border border-[color:var(--ops-state-running-border)] px-4 py-2.5 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-50"
              disabled={syncBusy}
              onClick={async () => {
                if (syncBusy) return
                setSyncBusy(true)
                try {
                  const response = await api.syncReleasePrStatuses()
                  const result = response.result || {}
                  const processed = Number(result.processed_count || 0)
                  const merged = Array.isArray(result.merged_ids) ? result.merged_ids.length : 0
                  const closed = Array.isArray(result.closed_ids) ? result.closed_ids.length : 0
                  const missing = Array.isArray(result.missing_ids) ? result.missing_ids.length : 0
                  toast.success(`PR 状态同步完成：处理 ${processed} 条，合并 ${merged} 条，关闭 ${closed + missing} 条`)
                  await load()
                } catch (error) {
                  const message = error instanceof Error ? error.message : '同步 PR 状态失败，请稍后重试'
                  toast.error(message)
                } finally {
                  setSyncBusy(false)
                }
              }}
            >
              {syncBusy ? '同步中…' : '同步 PR 状态'}
            </button>
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse">
            <thead className="bg-[color:var(--ops-panel-subtle)]">
              <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                <th className="px-5 py-4 font-medium">Requirement</th>
                <th className="px-4 py-4 font-medium">验证</th>
                <th className="px-4 py-4 font-medium">发布状态</th>
                <th className="px-4 py-4 font-medium">分支 / PR</th>
                <th className="px-4 py-4 font-medium">工作流</th>
                <th className="px-4 py-4 font-medium">更新时间</th>
                <th className="px-5 py-4 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={item.requirement.id} className="border-t border-[color:var(--ops-stroke-soft)] hover:bg-[color:var(--ops-panel-subtle)]">
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
                    <StateBadge tone={releaseTone(item.release?.status || item.release?.state)}>
                      {STATUS_LABEL[item.release?.status || item.release?.state || 'pending'] || item.release?.status || item.release?.state || 'pending'}
                    </StateBadge>
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                    <div>{item.release?.branch_name || '-'} · PR {item.release?.pr_number || '-'}</div>
                    {item.release?.pr_status || item.release?.last_pr_status_synced_at ? (
                      <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">
                        GitHub: {item.release?.pr_status || '-'} · synced {formatTime(item.release?.last_pr_status_synced_at || null)}
                      </div>
                    ) : null}
                    {item.release?.pr_sync_failure_summary ? (
                      <div className="mt-1 line-clamp-1 text-xs text-[color:var(--ops-state-blocked-text)]">{item.release.pr_sync_failure_summary}</div>
                    ) : null}
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                    {item.requirement.active_workflow_run_summary
                      ? `${item.requirement.active_workflow_run_summary.workflow_key} · ${item.requirement.active_workflow_run_summary.current_state}`
                      : '-'}
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(item.release?.updated_at || item.validation.updated_at)}</td>
                  <td className="px-5 py-4">
                    <div className="flex flex-wrap justify-end gap-2">
                      <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/requirements/${item.requirement.id}`)}>
                        需求
                      </button>
                      <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/workflows/${workflowRunIdFor(item)}`)} disabled={!workflowRunIdFor(item)}>
                        工作流
                      </button>
                      {(() => {
                        const action = releaseAction(item)
                        const busyKey = `${action.key}-${item.requirement.id}`
                        if (!action.key) return null
                        return (
                          <button
                            type="button"
                            className="rounded-lg border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-50"
                            disabled={busyAction === busyKey}
                            onClick={async () => {
                              if (action.key === 'repair-gate') {
                                navigate(`/releases/${item.requirement.id}`)
                                return
                              }
                              setBusyAction(busyKey)
                              try {
                                if (action.key === 'prepare') {
                                  await api.prepareRelease(item.requirement.id, { actor: 'operator', note: 'Release list branch preparation' })
                                  toast.success('已准备交付分支')
                                } else if (action.key === 'open-pr') {
                                  await api.openReleasePr(item.requirement.id, { actor: 'operator', note: 'Release list open PR' })
                                  toast.success('已触发 PR 交付')
                                }
                              } catch (error) {
                                const message = error instanceof Error ? error.message : '发布动作失败，请重试'
                                toast.error(message)
                              } finally {
                                await load()
                                setBusyAction(null)
                              }
                            }}
                          >
                            {busyAction === busyKey ? '处理中…' : action.label}
                          </button>
                        )
                      })()}
                      <button type="button" className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white" onClick={() => navigate(`/releases/${item.requirement.id}`)}>
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
