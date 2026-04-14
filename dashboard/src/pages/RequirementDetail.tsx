import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { AgentRequirementDetail, api } from '../api'

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

function Markdown({ value }: Readonly<{ value: string }>) {
  if (!value.trim()) return <div className="text-sm text-slate-400">暂无内容</div>
  return (
    <div className="prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2">
      <ReactMarkdown>{value}</ReactMarkdown>
    </div>
  )
}

export default function RequirementDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const requirementId = Number(id)
  const [detail, setDetail] = useState<AgentRequirementDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    title: '',
    description_markdown: '',
    acceptance_criteria_markdown: '',
    priority: 'normal',
    target_project_path: '',
  })
  const [revisionNote, setRevisionNote] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getRequirement(requirementId)
      setDetail(data)
      setForm({
        title: data.requirement.title,
        description_markdown: data.requirement.description_markdown,
        acceptance_criteria_markdown: data.requirement.acceptance_criteria_markdown,
        priority: data.requirement.priority,
        target_project_path: data.requirement.target_project_path || '',
      })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [requirementId])

  if (loading || !detail) {
    return <div className="rounded-3xl border border-slate-200 bg-white p-8 text-sm text-slate-500">正在加载需求…</div>
  }

  const requirement = detail.requirement

  return (
    <div className="space-y-6" data-testid="agent-first-requirement-detail">
      <section className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-slate-400">Requirement</div>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">{requirement.title}</h2>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
              <span className="rounded-full bg-slate-100 px-3 py-1">{STATUS_LABEL[requirement.status] || requirement.status}</span>
              <span className="rounded-full bg-slate-100 px-3 py-1">{requirement.priority}</span>
              <span className="rounded-full bg-slate-100 px-3 py-1">{requirement.source}</span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {requirement.status === 'draft' && (
              <button className="rounded-2xl bg-slate-900 px-4 py-2 text-sm text-white" onClick={async () => { await api.submitRequirement(requirement.id); await load() }}>
                提交
              </button>
            )}
            {(requirement.status === 'ready' || requirement.status === 'needs_revision') && (
              <button
                className="rounded-2xl bg-blue-600 px-4 py-2 text-sm text-white"
                onClick={async () => {
                  const execution = await api.createExecution({ requirement_id: requirement.id })
                  navigate(`/executions/${execution.execution.id}`)
                }}
              >
                创建执行
              </button>
            )}
            {detail.latest_execution_id && (
              <button className="rounded-2xl border border-slate-200 px-4 py-2 text-sm" onClick={() => navigate(`/executions/${detail.latest_execution_id}`)}>
                查看执行
              </button>
            )}
            {detail.latest_release_id && (
              <button className="rounded-2xl border border-emerald-200 px-4 py-2 text-sm text-emerald-700" onClick={() => navigate(`/releases/${requirement.id}`)}>
                查看发布
              </button>
            )}
          </div>
        </div>
        <div className="mt-4 grid gap-3 text-sm text-slate-600 md:grid-cols-2">
          <div>target: {requirement.target_projects.join(', ') || '-'}</div>
          <div>approval: {requirement.approval_required ? requirement.approval_status : 'waived'}</div>
          <div>latest execution: {detail.latest_execution_id ?? '-'}</div>
          <div>latest release: {detail.latest_release_id ?? '-'}</div>
          <div>created: {formatTime(requirement.created_at)}</div>
          <div>updated: {formatTime(requirement.updated_at)}</div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
        <div className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
          <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Intent</div>
          <h3 className="mt-2 text-xl font-semibold text-slate-950">需求意图</h3>
          <div className="mt-4">
            <Markdown value={requirement.description_markdown} />
          </div>
          <div className="mt-6 text-xs uppercase tracking-[0.22em] text-slate-400">Acceptance</div>
          <div className="mt-3">
            <Markdown value={requirement.acceptance_criteria_markdown} />
          </div>
        </div>

        <div className="space-y-6">
          <section className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
            <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Policy</div>
            <h3 className="mt-2 text-xl font-semibold text-slate-950">策略摘要</h3>
            <div className="mt-4 text-sm text-slate-600">
              <Markdown value={detail.policy_summary_markdown} />
            </div>
          </section>

          <section className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
            <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Edit</div>
            <h3 className="mt-2 text-xl font-semibold text-slate-950">修订需求</h3>
            <div className="mt-4 grid gap-3">
              <input className="rounded-2xl border border-slate-200 px-4 py-3 text-sm" value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
              <input className="rounded-2xl border border-slate-200 px-4 py-3 text-sm" value={form.target_project_path} onChange={(event) => setForm((current) => ({ ...current, target_project_path: event.target.value }))} />
              <textarea className="min-h-[130px] rounded-2xl border border-slate-200 px-4 py-3 text-sm" value={form.description_markdown} onChange={(event) => setForm((current) => ({ ...current, description_markdown: event.target.value }))} />
              <textarea className="min-h-[110px] rounded-2xl border border-slate-200 px-4 py-3 text-sm" value={form.acceptance_criteria_markdown} onChange={(event) => setForm((current) => ({ ...current, acceptance_criteria_markdown: event.target.value }))} />
              <textarea className="min-h-[90px] rounded-2xl border border-slate-200 px-4 py-3 text-sm" placeholder="revision note" value={revisionNote} onChange={(event) => setRevisionNote(event.target.value)} />
              <div className="flex flex-wrap gap-2">
                <button
                  className="rounded-2xl bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
                  disabled={saving}
                  onClick={async () => {
                    setSaving(true)
                    try {
                      await api.updateRequirement(requirement.id, form)
                      await load()
                    } finally {
                      setSaving(false)
                    }
                  }}
                >
                  保存
                </button>
                <button
                  className="rounded-2xl border border-amber-200 px-4 py-2 text-sm text-amber-700 disabled:opacity-50"
                  disabled={saving}
                  onClick={async () => {
                    setSaving(true)
                    try {
                      await api.reviseRequirement(requirement.id, {
                        title: form.title,
                        description_markdown: form.description_markdown,
                        acceptance_criteria_markdown: form.acceptance_criteria_markdown,
                        revision_note: revisionNote || null,
                      })
                      await load()
                    } finally {
                      setSaving(false)
                    }
                  }}
                >
                  标记修订并回到待执行
                </button>
                <button
                  className="rounded-2xl border border-rose-200 px-4 py-2 text-sm text-rose-700 disabled:opacity-50"
                  disabled={saving}
                  onClick={async () => {
                    setSaving(true)
                    try {
                      await api.cancelRequirement(requirement.id)
                      await load()
                    } finally {
                      setSaving(false)
                    }
                  }}
                >
                  取消需求
                </button>
              </div>
            </div>
          </section>
        </div>
      </section>
    </div>
  )
}
