import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ExecutionRun, api } from '../api'

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
      [String(item.id), String(item.requirement_id), item.execution_mode, item.complexity, item.planner_summary || '', item.target_projects.join('\n')]
        .join('\n')
        .toLowerCase()
        .includes(needle),
    )
  }, [executions, search])

  return (
    <div className="space-y-6" data-testid="executions-page">
      <section className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-slate-400">Execution</div>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">执行面</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              只看 agent 如何执行、跑了哪些节点、什么时候进入 validate，以及哪里发生了 blocked / failed incident。
            </p>
          </div>
          <div className="flex items-center gap-3">
            <input
              className="w-72 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm"
              placeholder="搜索 execution / requirement / target"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button className="rounded-2xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white" onClick={() => load().catch(() => {})}>
              刷新
            </button>
          </div>
        </div>
      </section>

      <section className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Runs</div>
            <h3 className="mt-2 text-xl font-semibold text-slate-950">执行队列</h3>
          </div>
          <div className="text-sm text-slate-500">{loading ? '加载中…' : `${filtered.length} 个 execution run`}</div>
        </div>

        <div className="mt-4 grid gap-4">
          {filtered.map((item) => (
            <article key={item.id} className="rounded-3xl border border-slate-200/80 bg-slate-50/80 p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-lg font-semibold text-slate-950">Execution #{item.id}</h4>
                    <span className="rounded-full bg-white px-3 py-1 text-xs text-slate-600">{STATUS_LABEL[item.status] || item.status}</span>
                    <span className="rounded-full bg-white px-3 py-1 text-xs text-slate-600">{item.execution_mode}</span>
                    <span className="rounded-full bg-white px-3 py-1 text-xs text-slate-600">{item.complexity}</span>
                  </div>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{item.planner_summary || 'No planner summary'}</p>
                </div>
                <div className="text-right text-xs text-slate-500">
                  <div>requirement #{item.requirement_id}</div>
                  <div>{formatTime(item.updated_at)}</div>
                </div>
              </div>

              <div className="mt-4 grid gap-2 text-xs text-slate-500 md:grid-cols-2 xl:grid-cols-4">
                <div>targets: {item.target_projects.join(', ') || '-'}</div>
                <div>validation: {item.validation_profile}</div>
                <div>delivery: {item.delivery_intent}</div>
                <div>approval: {item.approval_required ? 'required' : 'waived'}</div>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <button className="rounded-2xl border border-slate-200 px-4 py-2 text-sm" onClick={() => navigate(`/requirements/${item.requirement_id}`)}>
                  查看需求
                </button>
                <button className="rounded-2xl bg-slate-900 px-4 py-2 text-sm text-white" onClick={() => navigate(`/executions/${item.id}`)}>
                  打开执行面
                </button>
                {(item.status === 'queued' || item.status === 'paused' || item.status === 'blocked') && (
                  <button
                    className="rounded-2xl border border-blue-200 px-4 py-2 text-sm text-blue-700"
                    onClick={async () => {
                      await api.startExecution(item.id)
                      await load()
                    }}
                  >
                    {item.status === 'paused' ? '恢复执行' : '启动执行'}
                  </button>
                )}
              </div>
            </article>
          ))}

          {!loading && filtered.length === 0 && (
            <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 p-8 text-sm text-slate-500">
              当前没有 execution run。
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
