import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ExecutionRun, api } from '../api'
import { EmptyPane, StateBadge } from '../components/workbench'

const STATUS_LABEL: Record<string, string> = {
  queued: '排队中',
  running: '执行中',
  paused: '已暂停',
  blocked: '阻塞',
  validating: '验证中',
  failed: '失败',
  succeeded: '成功',
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function formatRecoveryCountdown(seconds: number | null) {
  if (seconds == null) return null
  if (seconds <= 0) return '恢复窗口已到期'
  if (seconds < 60) return `恢复窗口剩余 ${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remain = seconds % 60
  return `恢复窗口剩余 ${minutes}m ${remain}s`
}

function statusTone(status: string) {
  if (status === 'succeeded') return 'delivered'
  if (status === 'running') return 'running'
  if (status === 'blocked' || status === 'failed') return 'blocked'
  if (status === 'validating') return 'validating'
  if (status === 'queued') return 'ready'
  return 'muted'
}

function startLabel(item: ExecutionRun) {
  if (item.status === 'paused' || item.blocking_reason_code === 'manual_pause') return '继续'
  if (item.status === 'blocked' && item.recovery_mode === 'restart_current') return '再次启动'
  return '启动'
}

export default function ExecutionsPage() {
  const navigate = useNavigate()
  const [executions, setExecutions] = useState<ExecutionRun[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      setExecutions(await api.getExecutions())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return executions
    return executions.filter((item) =>
      [
        String(item.id),
        String(item.requirement_id),
        item.requirement_title ?? '',
        item.execution_mode,
        item.complexity,
        item.target_projects.join('\n'),
      ]
        .join('\n')
        .toLowerCase()
        .includes(needle),
    )
  }, [executions, search])

  return (
    <div className="space-y-5" data-testid="executions-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white px-5 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Executions</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">执行列表</h2>
          </div>
          <div className="flex items-center gap-2">
            <input
              className="w-72 rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm"
              placeholder="搜索 execution / requirement"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>
              刷新
            </button>
          </div>
        </div>
        <div className="mt-4 rounded-xl border border-sky-100 bg-sky-50 px-4 py-3 text-sm text-sky-800">
          恢复中的 execution 只影响当前需求，不会阻塞其他需求执行。
        </div>
      </section>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse">
            <thead className="bg-slate-50/90">
              <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                <th className="px-5 py-4 font-medium">Execution</th>
                <th className="px-4 py-4 font-medium">状态</th>
                <th className="px-4 py-4 font-medium">模式</th>
                <th className="px-4 py-4 font-medium">复杂度</th>
                <th className="px-4 py-4 font-medium">验证</th>
                <th className="px-4 py-4 font-medium">更新时间</th>
                <th className="px-5 py-4 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={item.id} className="border-t border-[color:var(--ops-stroke-soft)] hover:bg-slate-50/80">
                  <td className="px-5 py-4">
                    <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">Execution #{item.id}</div>
                    {item.requirement_title ? (
                      <div className="mt-1 text-sm text-[color:var(--ops-text-body)]">需求：{item.requirement_title}</div>
                    ) : null}
                    <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">Requirement #{item.requirement_id}</div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{item.execution_kind === 'delivery_repair' ? 'delivery repair' : 'implementation'}</div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex flex-wrap gap-2">
                      <StateBadge tone={statusTone(item.status)}>{STATUS_LABEL[item.status] || item.status}</StateBadge>
                      {item.phase && item.phase !== item.status ? <StateBadge tone="muted">{item.phase}</StateBadge> : null}
                      {item.recovery_status ? <StateBadge tone="blocked">恢复: {item.recovery_status}</StateBadge> : null}
                      {item.recovery_scope ? <StateBadge tone="muted">仅影响当前需求</StateBadge> : null}
                      {!item.is_current_execution ? <StateBadge tone="muted">历史 run</StateBadge> : null}
                    </div>
                    {item.queue_reason ? <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">{item.queue_reason}</div> : null}
                    {item.blocking_reason_message ? (
                      <div className="mt-2 text-xs text-rose-600">
                        {item.blocking_reason_code ? `${item.blocking_reason_code}: ` : ''}
                        {item.blocking_reason_message}
                      </div>
                    ) : null}
                    {item.recovery_hint ? <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">{item.recovery_hint}</div> : null}
                    {item.recovery_deadline_at ? (
                      <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">
                        恢复截止：{formatTime(item.recovery_deadline_at)}
                        {item.time_remaining_seconds != null ? ` · ${formatRecoveryCountdown(item.time_remaining_seconds)}` : ''}
                      </div>
                    ) : null}
                    {item.recovery_timeout_status === 'timed_out' ? (
                      <div className="mt-2 text-xs text-rose-700">恢复超时，需人工介入。</div>
                    ) : null}
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-body)]">{item.execution_mode}</td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-body)]">{item.complexity}</td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{item.validation_profile}</td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(item.updated_at)}</td>
                  <td className="px-5 py-4">
                    <div className="flex flex-wrap justify-end gap-2">
                      {(() => {
                        const allowedActions = item.allowed_actions ?? []
                        return (
                          <>
                      <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/requirements/${item.requirement_id}`)}>
                        需求
                      </button>
                      <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/executions/${item.id}`)}>
                        查看
                      </button>
                      {(allowedActions.includes('start') || allowedActions.includes('resume')) && (
                        <button
                          type="button"
                          className="rounded-lg bg-[color:var(--ops-text-title)] px-3 py-2 text-sm text-white"
                          onClick={async () => {
                            await api.startExecution(item.id)
                            await load()
                          }}
                        >
                          {startLabel(item)}
                        </button>
                      )}
                      {allowedActions.includes('retry') && (
                        <button
                          type="button"
                          className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm"
                          onClick={async () => {
                            await api.retryExecution(item.id)
                            await load()
                          }}
                        >
                          创建新 run 重试
                        </button>
                      )}
                          </>
                        )
                      })()}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!loading && filtered.length === 0 && (
          <div className="p-6">
            <EmptyPane>暂无 execution。</EmptyPane>
          </div>
        )}
      </section>
    </div>
  )
}
