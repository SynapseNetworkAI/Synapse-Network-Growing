import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AgentRequirement, api } from '../api'

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  ready: '待执行',
  running: '执行中',
  blocked: '阻塞',
  needs_revision: '需修订',
  delivery_ready: '待发布',
  done: '已完成',
  cancelled: '已取消',
  deleted: '已删除',
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

export default function RequirementPool() {
  const navigate = useNavigate()
  const [requirements, setRequirements] = useState<AgentRequirement[]>([])
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [submittingId, setSubmittingId] = useState<number | null>(null)
  const [form, setForm] = useState({
    title: '',
    description_markdown: '',
    acceptance_criteria_markdown: '',
    priority: 'normal',
    target_project_path: '',
  })

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getRequirements(status || undefined, undefined, search || undefined)
      setRequirements(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [status])

  const filtered = useMemo(() => {
    if (!search.trim()) return requirements
    const needle = search.trim().toLowerCase()
    return requirements.filter((item) =>
      [item.title, item.description_markdown, item.source_ref || '', item.target_project_path || '', String(item.id)]
        .join('\n')
        .toLowerCase()
        .includes(needle),
    )
  }, [requirements, search])

  return (
    <div className="space-y-6" data-testid="agent-first-requirements-page">
      <section className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-slate-400">Requirement</div>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">需求面</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              这里只管理为什么做、要做到什么、作用在哪个项目。执行和发布分别进入独立的 Execution / Release 页面。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <select className="rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">全部状态</option>
              <option value="draft">草稿</option>
              <option value="ready">待执行</option>
              <option value="running">执行中</option>
              <option value="blocked">阻塞</option>
              <option value="needs_revision">需修订</option>
              <option value="delivery_ready">待发布</option>
              <option value="done">已完成</option>
            </select>
            <input
              className="w-72 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm"
              placeholder="搜索标题 / 项目 / source_ref / ID"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button
              className="rounded-2xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white"
              onClick={() => load().catch(() => {})}
            >
              刷新
            </button>
          </div>
        </div>
      </section>

      <section className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-xs uppercase tracking-[0.22em] text-slate-400">New Requirement</div>
            <h3 className="mt-2 text-xl font-semibold text-slate-950">新建需求</h3>
          </div>
          <button
            className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-700"
            onClick={() => setForm({ title: '', description_markdown: '', acceptance_criteria_markdown: '', priority: 'normal', target_project_path: '' })}
          >
            清空
          </button>
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <input
            className="rounded-2xl border border-slate-200 px-4 py-3 text-sm"
            placeholder="标题"
            value={form.title}
            onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
          />
          <input
            className="rounded-2xl border border-slate-200 px-4 py-3 text-sm"
            placeholder="目标项目路径，可换行写多个"
            value={form.target_project_path}
            onChange={(event) => setForm((current) => ({ ...current, target_project_path: event.target.value }))}
          />
          <textarea
            className="min-h-[160px] rounded-2xl border border-slate-200 px-4 py-3 text-sm lg:col-span-2"
            placeholder="需求描述"
            value={form.description_markdown}
            onChange={(event) => setForm((current) => ({ ...current, description_markdown: event.target.value }))}
          />
          <textarea
            className="min-h-[120px] rounded-2xl border border-slate-200 px-4 py-3 text-sm lg:col-span-2"
            placeholder="验收标准"
            value={form.acceptance_criteria_markdown}
            onChange={(event) => setForm((current) => ({ ...current, acceptance_criteria_markdown: event.target.value }))}
          />
          <select
            className="rounded-2xl border border-slate-200 px-4 py-3 text-sm"
            value={form.priority}
            onChange={(event) => setForm((current) => ({ ...current, priority: event.target.value }))}
          >
            <option value="low">low</option>
            <option value="normal">normal</option>
            <option value="high">high</option>
          </select>
          <div className="flex items-center justify-end">
            <button
              className="rounded-2xl bg-blue-600 px-5 py-3 text-sm font-medium text-white disabled:opacity-60"
              disabled={creating || !form.title.trim() || !form.description_markdown.trim()}
              onClick={async () => {
                setCreating(true)
                try {
                  const detail = await api.createRequirement(form)
                  await load()
                  navigate(`/requirements/${detail.requirement.id}`)
                } finally {
                  setCreating(false)
                }
              }}
            >
              {creating ? '创建中…' : '创建需求'}
            </button>
          </div>
        </div>
      </section>

      <section className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Queue</div>
            <h3 className="mt-2 text-xl font-semibold text-slate-950">需求列表</h3>
          </div>
          <div className="text-sm text-slate-500">{loading ? '加载中…' : `${filtered.length} 条需求`}</div>
        </div>
        <div className="mt-4 grid gap-4">
          {filtered.map((item) => (
            <article key={item.id} className="rounded-3xl border border-slate-200/80 bg-slate-50/80 p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-lg font-semibold text-slate-950">{item.title}</h4>
                    <span className="rounded-full bg-white px-3 py-1 text-xs text-slate-600">{STATUS_LABEL[item.status] || item.status}</span>
                    <span className="rounded-full bg-white px-3 py-1 text-xs text-slate-600">{item.priority}</span>
                  </div>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 line-clamp-3">{item.description_markdown}</p>
                </div>
                <div className="text-right text-xs text-slate-500">
                  <div>#{item.id}</div>
                  <div>{formatTime(item.updated_at)}</div>
                </div>
              </div>
              <div className="mt-4 grid gap-2 text-xs text-slate-500 md:grid-cols-2">
                <div>target: {item.target_projects.join(', ') || '-'}</div>
                <div>approval: {item.approval_required ? item.approval_status : 'waived'}</div>
                <div>active execution: {item.active_execution_run_id ?? '-'}</div>
                <div>latest release: {item.latest_release_status ?? '-'}</div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button className="rounded-2xl border border-slate-200 px-4 py-2 text-sm" onClick={() => navigate(`/requirements/${item.id}`)}>
                  查看需求
                </button>
                <button
                  className="rounded-2xl bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
                  disabled={submittingId === item.id || item.status !== 'draft'}
                  onClick={async () => {
                    setSubmittingId(item.id)
                    try {
                      await api.submitRequirement(item.id)
                      await load()
                    } finally {
                      setSubmittingId(null)
                    }
                  }}
                >
                  提交到执行
                </button>
                <button
                  className="rounded-2xl border border-blue-200 px-4 py-2 text-sm text-blue-700 disabled:opacity-50"
                  disabled={item.status !== 'ready' && item.status !== 'needs_revision'}
                  onClick={async () => {
                    const detail = await api.createExecution({ requirement_id: item.id })
                    navigate(`/executions/${detail.execution.id}`)
                  }}
                >
                  创建执行
                </button>
                {item.latest_release_status && (
                  <button className="rounded-2xl border border-emerald-200 px-4 py-2 text-sm text-emerald-700" onClick={() => navigate(`/releases/${item.id}`)}>
                    查看发布
                  </button>
                )}
              </div>
            </article>
          ))}
          {!loading && filtered.length === 0 && (
            <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 p-8 text-sm text-slate-500">
              当前没有符合条件的 requirement。
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
