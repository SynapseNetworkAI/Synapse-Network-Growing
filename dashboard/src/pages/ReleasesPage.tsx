import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ReleaseCandidate, api } from '../api'

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
      [String(item.requirement.id), item.requirement.title, item.requirement.target_projects.join('\n'), item.release?.status || '', item.validation.summary_markdown]
        .join('\n')
        .toLowerCase()
        .includes(needle),
    )
  }, [candidates, search])

  return (
    <div className="space-y-6" data-testid="releases-page">
      <section className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-slate-400">Release</div>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">发布面</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              这里只接收 validate 成功后的 requirement，统一处理 branch、PR、staging / production promotion 与 rollback。
            </p>
          </div>
          <div className="flex items-center gap-3">
            <input
              className="w-72 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm"
              placeholder="搜索 requirement / project / release status"
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
            <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Candidates</div>
            <h3 className="mt-2 text-xl font-semibold text-slate-950">发布候选</h3>
          </div>
          <div className="text-sm text-slate-500">{loading ? '加载中…' : `${filtered.length} 个候选`}</div>
        </div>

        <div className="mt-4 grid gap-4">
          {filtered.map((item) => (
            <article key={item.requirement.id} className="rounded-3xl border border-slate-200/80 bg-slate-50/80 p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-lg font-semibold text-slate-950">#{item.requirement.id} {item.requirement.title}</h4>
                    <span className="rounded-full bg-white px-3 py-1 text-xs text-slate-600">{item.requirement.status}</span>
                    <span className="rounded-full bg-white px-3 py-1 text-xs text-slate-600">{item.release?.status || 'ready'}</span>
                  </div>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{item.validation.summary_markdown}</p>
                </div>
                <div className="text-right text-xs text-slate-500">
                  <div>{item.requirement.target_projects.join(', ') || '-'}</div>
                  <div>{formatTime(item.release?.updated_at || item.validation.updated_at)}</div>
                </div>
              </div>

              <div className="mt-4 grid gap-2 text-xs text-slate-500 md:grid-cols-2 xl:grid-cols-4">
                <div>validation: {item.validation.status}</div>
                <div>branch: {item.release?.branch_name || '-'}</div>
                <div>sha: {item.release?.commit_sha || '-'}</div>
                <div>pr: {item.release?.pr_number || '-'}</div>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <button className="rounded-2xl border border-slate-200 px-4 py-2 text-sm" onClick={() => navigate(`/requirements/${item.requirement.id}`)}>
                  查看需求
                </button>
                <button className="rounded-2xl border border-slate-200 px-4 py-2 text-sm" onClick={() => navigate(`/executions/${item.requirement.latest_execution_run_id}`)} disabled={!item.requirement.latest_execution_run_id}>
                  查看执行
                </button>
                <button className="rounded-2xl bg-slate-900 px-4 py-2 text-sm text-white" onClick={() => navigate(`/releases/${item.requirement.id}`)}>
                  打开发布面
                </button>
              </div>
            </article>
          ))}

          {!loading && filtered.length === 0 && (
            <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 p-8 text-sm text-slate-500">
              当前没有 validate 成功的 release candidate。
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
