import { useCallback, useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { api, Requirement, RequirementDetail } from '../api'

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  ready: '已规划',
  in_progress: '执行中',
  done: '已完成',
  needs_revision: '需修订',
  blocked: '阻塞',
}

const STATUS_CLASS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  ready: 'bg-sky-100 text-sky-700',
  in_progress: 'bg-blue-100 text-blue-700',
  done: 'bg-green-100 text-green-700',
  needs_revision: 'bg-amber-100 text-amber-700',
  blocked: 'bg-red-100 text-red-700',
}

const STEP_STATUS_CLASS: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-700',
  running: 'bg-blue-100 text-blue-700',
  waiting_approval: 'bg-yellow-100 text-yellow-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
}

function Md({ children }: Readonly<{ children: string }>) {
  return (
    <div className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-headings:mb-2">
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  )
}

function formatTime(value: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

export default function RequirementPool() {
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<RequirementDetail | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState({ title: '', description_markdown: '', priority: 'normal' })

  const loadRequirements = useCallback(async () => {
    const data = await api.getRequirements(statusFilter || undefined)
    setRequirements(data)
    if (data.length === 0) {
      setSelectedId(null)
      setDetail(null)
      return
    }
    if (selectedId == null || !data.some((item) => item.id === selectedId)) {
      setSelectedId(data[0].id)
    }
  }, [statusFilter, selectedId])

  const loadDetail = useCallback(async (requirementId: number) => {
    const data = await api.getRequirement(requirementId)
    setDetail(data)
  }, [])

  useEffect(() => {
    loadRequirements().catch(() => {})
  }, [loadRequirements])

  useEffect(() => {
    if (selectedId == null) return
    loadDetail(selectedId).catch(() => {})
  }, [selectedId, loadDetail])

  useEffect(() => {
    if (!requirements.some((item) => item.status === 'in_progress')) return
    const timer = setInterval(() => {
      loadRequirements().catch(() => {})
      if (selectedId != null) {
        loadDetail(selectedId).catch(() => {})
      }
    }, 2500)
    return () => clearInterval(timer)
  }, [requirements, selectedId, loadRequirements, loadDetail])

  const selectedRequirement = useMemo(
    () => requirements.find((item) => item.id === selectedId) || detail?.requirement || null,
    [requirements, selectedId, detail],
  )

  const handleCreate = async () => {
    if (!form.title.trim() || !form.description_markdown.trim()) return
    setSubmitting(true)
    try {
      const created = await api.createRequirement({
        title: form.title.trim(),
        description_markdown: form.description_markdown.trim(),
        priority: form.priority,
      })
      setShowCreate(false)
      setForm({ title: '', description_markdown: '', priority: 'normal' })
      await loadRequirements()
      setSelectedId(created.requirement.id)
      setDetail(created)
    } finally {
      setSubmitting(false)
    }
  }

  const handlePlan = async () => {
    if (selectedId == null) return
    const data = await api.planRequirement(selectedId)
    setDetail(data)
    await loadRequirements()
  }

  const handleStart = async () => {
    if (selectedId == null) return
    const data = await api.startRequirement(selectedId)
    setDetail(data)
    await loadRequirements()
  }

  return (
    <div data-testid="requirements-page" className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">需求池</h2>
          <p className="text-sm text-gray-500">Requirement-first workflow orchestration with validation and bugfix loop.</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            data-testid="requirement-status-filter"
            className="rounded border px-3 py-2 text-sm"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="">全部状态</option>
            <option value="draft">草稿</option>
            <option value="ready">已规划</option>
            <option value="in_progress">执行中</option>
            <option value="done">已完成</option>
          </select>
          <button
            data-testid="create-requirement-btn"
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            onClick={() => setShowCreate((value) => !value)}
          >
            新建需求
          </button>
        </div>
      </div>

      {showCreate && (
        <div data-testid="requirement-create-form" className="rounded-xl border bg-white p-5 shadow-sm space-y-3">
          <input
            data-testid="requirement-title"
            className="w-full rounded border px-3 py-2"
            placeholder="需求标题"
            value={form.title}
            onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
          />
          <textarea
            data-testid="requirement-description"
            className="min-h-32 w-full rounded border px-3 py-2"
            placeholder="用 Markdown 描述需求、目标和约束"
            value={form.description_markdown}
            onChange={(event) => setForm((prev) => ({ ...prev, description_markdown: event.target.value }))}
          />
          <div className="flex items-center justify-between">
            <select
              data-testid="requirement-priority"
              className="rounded border px-3 py-2 text-sm"
              value={form.priority}
              onChange={(event) => setForm((prev) => ({ ...prev, priority: event.target.value }))}
            >
              <option value="low">low</option>
              <option value="normal">normal</option>
              <option value="high">high</option>
            </select>
            <button
              data-testid="submit-requirement-btn"
              className="rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-50"
              disabled={submitting}
              onClick={() => { handleCreate().catch(() => {}) }}
            >
              创建并保存
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-3">
          {requirements.length === 0 && (
            <div data-testid="requirements-empty" className="rounded-xl border border-dashed bg-white p-6 text-sm text-gray-500">
              还没有 requirement。先创建一条需求，再规划和启动 workflow。
            </div>
          )}
          {requirements.map((requirement) => (
            <button
              key={requirement.id}
              data-testid={`requirement-card-${requirement.id}`}
              className={`w-full rounded-xl border bg-white p-4 text-left shadow-sm transition ${selectedId === requirement.id ? 'border-blue-500 ring-2 ring-blue-100' : 'hover:border-gray-300'}`}
              onClick={() => setSelectedId(requirement.id)}
            >
              <div className="mb-2 flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-gray-900">{requirement.title}</div>
                  <div className="mt-1 text-xs text-gray-500">Plan v{requirement.current_plan_version || 0}</div>
                </div>
                <span className={`rounded-full px-2 py-1 text-xs font-medium ${STATUS_CLASS[requirement.status] || STATUS_CLASS.draft}`}>
                  {STATUS_LABEL[requirement.status] || requirement.status}
                </span>
              </div>
              <div className="line-clamp-3 text-xs text-gray-600">{requirement.description_markdown}</div>
              <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
                <span>优先级: {requirement.priority}</span>
                <span>{formatTime(requirement.updated_at)}</span>
              </div>
            </button>
          ))}
        </div>

        <div>
          {!selectedRequirement || !detail ? (
            <div className="rounded-xl border bg-white p-8 text-sm text-gray-500">选择左侧需求查看详情。</div>
          ) : (
            <div data-testid="requirement-detail" className="rounded-2xl border bg-white p-6 shadow-sm space-y-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-xl font-bold">{detail.requirement.title}</h3>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                    <span className={`rounded-full px-2 py-1 font-medium ${STATUS_CLASS[detail.requirement.status] || STATUS_CLASS.draft}`}>
                      {STATUS_LABEL[detail.requirement.status] || detail.requirement.status}
                    </span>
                    <span>Priority: {detail.requirement.priority}</span>
                    <span>Plan v{detail.requirement.current_plan_version}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    data-testid="plan-requirement-btn"
                    className="rounded border px-3 py-2 text-sm hover:bg-gray-50"
                    onClick={() => { handlePlan().catch(() => {}) }}
                  >
                    生成计划
                  </button>
                  <button
                    data-testid="start-requirement-btn"
                    className="rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
                    onClick={() => { handleStart().catch(() => {}) }}
                  >
                    启动执行
                  </button>
                </div>
              </div>

              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_320px]">
                <div className="space-y-4">
                  <section className="rounded-xl border bg-slate-50 p-4">
                    <div className="mb-2 text-sm font-semibold">需求说明</div>
                    <Md>{detail.requirement.description_markdown}</Md>
                  </section>

                  <section className="rounded-xl border p-4" data-testid="workflow-steps-panel">
                    <div className="mb-3 flex items-center justify-between">
                      <div className="text-sm font-semibold">Workflow Steps</div>
                      <div className="text-xs text-gray-500">Run #{detail.workflow_run?.id ?? '-'}</div>
                    </div>
                    <div className="space-y-3">
                      {(detail.workflow_run?.steps || []).map((step) => (
                        <div key={step.id} data-testid={`workflow-step-${step.id}`} className="rounded-lg border p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-sm font-medium">{step.title}</div>
                              <div className="mt-1 text-xs text-gray-500">
                                {step.step_type} · {step.assigned_workflow_role || '-'} · agent {step.assigned_agent_id || '-'}
                              </div>
                            </div>
                            <span className={`rounded-full px-2 py-1 text-xs font-medium ${STEP_STATUS_CLASS[step.status] || STEP_STATUS_CLASS.pending}`}>
                              {step.status}
                            </span>
                          </div>
                          {step.branch_from_step_id != null && (
                            <div className="mt-2 text-xs text-amber-600">Bugfix branch from step #{step.branch_from_step_id}</div>
                          )}
                          <div className="mt-2 text-xs text-gray-600">{step.done_when_markdown}</div>
                        </div>
                      ))}
                    </div>
                  </section>
                </div>

                <div className="space-y-4">
                  <section className="rounded-xl border p-4" data-testid="acceptance-checks-panel">
                    <div className="mb-3 text-sm font-semibold">Acceptance Checks</div>
                    <div className="space-y-2">
                      {detail.acceptance_checks.map((check) => (
                        <div key={check.id} className="rounded-lg bg-gray-50 p-3 text-xs">
                          <div className="font-medium text-gray-900">{check.check_key}</div>
                          <div className="mt-1 text-gray-600">{check.description}</div>
                          <div className="mt-2 flex items-center justify-between text-gray-500">
                            <span>{check.owner_role}</span>
                            <span>{check.status}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>

                  <section className="rounded-xl border p-4" data-testid="artifacts-panel">
                    <div className="mb-3 text-sm font-semibold">Artifacts</div>
                    <div className="space-y-2">
                      {detail.artifacts.slice().reverse().slice(0, 8).map((artifact) => (
                        <div key={artifact.id} className="rounded-lg bg-gray-50 p-3 text-xs">
                          <div className="font-medium text-gray-900">{artifact.artifact_type}</div>
                          <div className="mt-1 text-gray-600">{artifact.content_summary || '-'}</div>
                        </div>
                      ))}
                    </div>
                  </section>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}