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
  if (!value) return '-'
  // Backend sends UTC timestamps without 'Z' suffix; append it so Date parses as UTC.
  const d = new Date(value.endsWith('Z') ? value : value + 'Z')
  return d.toLocaleString('zh-CN')
}

export default function RequirementPool() {
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<RequirementDetail | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [showRevise, setShowRevise] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState({
    title: '',
    description_markdown: '',
    priority: 'normal',
    depends_on_requirement_ids: [] as number[],
    auto_start: true,
  })
  const [revisionForm, setRevisionForm] = useState({
    title: '',
    description_markdown: '',
    revision_note: '',
    depends_on_requirement_ids: [] as number[],
  })

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
    if (!detail) return
    setRevisionForm({
      title: detail.requirement.title,
      description_markdown: detail.requirement.description_markdown,
      revision_note: '',
      depends_on_requirement_ids: detail.dependencies.map((dependency) => dependency.depends_on_requirement_id),
    })
    setShowRevise(false)
  }, [detail])

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
        depends_on_requirement_ids: form.depends_on_requirement_ids,
        auto_start: form.auto_start,
      })
      setShowCreate(false)
      setForm({ title: '', description_markdown: '', priority: 'normal', depends_on_requirement_ids: [], auto_start: true })
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

  const handleRevise = async () => {
    if (selectedId == null || !detail) return
    if (!revisionForm.description_markdown.trim()) return
    setSubmitting(true)
    try {
      const data = await api.reviseRequirement(selectedId, {
        title: revisionForm.title.trim(),
        description_markdown: revisionForm.description_markdown.trim(),
        revision_note: revisionForm.revision_note.trim() || null,
        source_ref: detail.requirement.source_ref,
        depends_on_requirement_ids: revisionForm.depends_on_requirement_ids,
      })
      setShowRevise(false)
      setDetail(data)
      await loadRequirements()
    } finally {
      setSubmitting(false)
    }
  }

  const toggleDependency = (values: number[], requirementId: number) => {
    if (values.includes(requirementId)) {
      return values.filter((value) => value !== requirementId)
    }
    return [...values, requirementId]
  }

  const createDependencyCandidates = requirements
  const revisionDependencyCandidates = requirements.filter((requirement) => requirement.id !== selectedId)

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
            <option value="blocked">阻塞</option>
            <option value="needs_revision">需修订</option>
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
            <div data-testid="create-dependencies" className="max-h-28 flex-1 overflow-auto rounded border px-3 py-2 text-xs text-gray-600">
              {createDependencyCandidates.length === 0 ? (
                <div>暂无可选依赖</div>
              ) : (
                createDependencyCandidates.map((requirement) => (
                  <label key={requirement.id} className="flex items-center gap-2 py-1">
                    <input
                      data-testid={`create-dependency-${requirement.id}`}
                      type="checkbox"
                      checked={form.depends_on_requirement_ids.includes(requirement.id)}
                      onChange={() => setForm((prev) => ({
                        ...prev,
                        depends_on_requirement_ids: toggleDependency(prev.depends_on_requirement_ids, requirement.id),
                      }))}
                    />
                    <span>{requirement.title}</span>
                    <span className="text-gray-400">{STATUS_LABEL[requirement.status] || requirement.status}</span>
                  </label>
                ))
              )}
            </div>
            <label className="flex items-center gap-2 py-2">
              <input
                data-testid="auto-start-checkbox"
                type="checkbox"
                checked={form.auto_start}
                onChange={() => setForm((prev) => ({ ...prev, auto_start: !prev.auto_start }))}
              />
              <span className="text-sm">创建后自动生成计划并启动执行</span>
            </label>
            <button
              data-testid="submit-requirement-btn"
              className="rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-50"
              disabled={submitting}
              onClick={() => { handleCreate().catch(() => {}) }}
            >
              {form.auto_start ? '创建并启动' : '创建并保存'}
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
                <span>阻塞: {requirement.blocked_by_count}</span>
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
                    className="rounded border px-3 py-2 text-sm hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={detail.requirement.status === 'blocked' || detail.requirement.status === 'in_progress'}
                    onClick={() => { handlePlan().catch(() => {}) }}
                  >
                    生成计划
                  </button>
                  <button
                    data-testid="start-requirement-btn"
                    className="rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!detail.workflow_run || detail.requirement.status === 'blocked' || detail.requirement.status === 'done'}
                    onClick={() => { handleStart().catch(() => {}) }}
                  >
                    启动执行
                  </button>
                  <button
                    data-testid="toggle-revise-btn"
                    className="rounded border px-3 py-2 text-sm hover:bg-gray-50"
                    onClick={() => setShowRevise((value) => !value)}
                  >
                    提交修订
                  </button>
                </div>
              </div>

              {detail.requirement.blocked_by_count > 0 && (
                <div data-testid="blocked-banner" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  当前需求被 {detail.requirement.blocked_by_count} 个未完成依赖阻塞，需等待上游 requirement 完成后再规划执行。
                </div>
              )}

              {showRevise && (
                <section data-testid="requirement-revision-form" className="rounded-xl border bg-amber-50 p-4 shadow-sm space-y-3">
                  <div className="text-sm font-semibold">修订需求</div>
                  <input
                    data-testid="revise-title"
                    className="w-full rounded border px-3 py-2"
                    value={revisionForm.title}
                    onChange={(event) => setRevisionForm((prev) => ({ ...prev, title: event.target.value }))}
                  />
                  <textarea
                    data-testid="revise-description"
                    className="min-h-32 w-full rounded border px-3 py-2"
                    value={revisionForm.description_markdown}
                    onChange={(event) => setRevisionForm((prev) => ({ ...prev, description_markdown: event.target.value }))}
                  />
                  <textarea
                    data-testid="revise-note"
                    className="min-h-20 w-full rounded border px-3 py-2"
                    placeholder="记录这次需求修订的原因"
                    value={revisionForm.revision_note}
                    onChange={(event) => setRevisionForm((prev) => ({ ...prev, revision_note: event.target.value }))}
                  />
                  <div data-testid="revise-dependencies" className="rounded border bg-white px-3 py-2 text-xs text-gray-600">
                    {revisionDependencyCandidates.length === 0 ? (
                      <div>暂无可选依赖</div>
                    ) : (
                      revisionDependencyCandidates.map((requirement) => (
                        <label key={requirement.id} className="flex items-center gap-2 py-1">
                          <input
                            data-testid={`revise-dependency-${requirement.id}`}
                            type="checkbox"
                            checked={revisionForm.depends_on_requirement_ids.includes(requirement.id)}
                            onChange={() => setRevisionForm((prev) => ({
                              ...prev,
                              depends_on_requirement_ids: toggleDependency(prev.depends_on_requirement_ids, requirement.id),
                            }))}
                          />
                          <span>{requirement.title}</span>
                          <span className="text-gray-400">{STATUS_LABEL[requirement.status] || requirement.status}</span>
                        </label>
                      ))
                    )}
                  </div>
                  <div className="flex justify-end">
                    <button
                      data-testid="submit-revision-btn"
                      className="rounded bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
                      disabled={submitting}
                      onClick={() => { handleRevise().catch(() => {}) }}
                    >
                      保存修订并重开流程
                    </button>
                  </div>
                </section>
              )}

              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_320px]">
                <div className="space-y-4">
                  <section className="rounded-xl border bg-slate-50 p-4">
                    <div className="mb-2 text-sm font-semibold">需求说明</div>
                    <Md>{detail.requirement.description_markdown}</Md>
                  </section>

                  <section className="rounded-xl border p-4" data-testid="dependencies-panel">
                    <div className="mb-3 text-sm font-semibold">Dependencies</div>
                    {detail.dependencies.length === 0 ? (
                      <div className="text-xs text-gray-500">无依赖，可以直接规划执行。</div>
                    ) : (
                      <div className="space-y-2">
                        {detail.dependencies.map((dependency) => (
                          <div key={dependency.id} data-testid={`dependency-${dependency.depends_on_requirement_id}`} className="rounded-lg bg-gray-50 p-3 text-xs">
                            <div className="font-medium text-gray-900">{dependency.depends_on_title}</div>
                            <div className="mt-1 flex items-center justify-between text-gray-500">
                              <span>#{dependency.depends_on_requirement_id}</span>
                              <span>{STATUS_LABEL[dependency.depends_on_status] || dependency.depends_on_status}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
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
                      {(detail.workflow_run?.steps || []).length === 0 && (
                        <div className="text-xs text-gray-500">当前还没有 workflow run。先生成计划，再启动执行。</div>
                      )}
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