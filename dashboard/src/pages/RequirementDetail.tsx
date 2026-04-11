import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { api, RequirementDetail as RequirementDetailType, Requirement } from '../api'

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
  blocked: 'bg-gray-200 text-gray-500',
}

function Md({ children }: Readonly<{ children: string }>) {
  return (
    <div className="prose-sm prose max-w-none prose-p:my-1 prose-ul:my-1 prose-headings:mb-2">
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  )
}

function formatTime(value: string | null) {
  if (!value) return '-'
  const d = new Date(value.endsWith('Z') ? value : value + 'Z')
  return d.toLocaleString('zh-CN')
}

export default function RequirementDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const requirementId = Number(id)

  const [detail, setDetail] = useState<RequirementDetailType | null>(null)
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [expandedStepId, setExpandedStepId] = useState<number | null>(null)
  const [showPlan, setShowPlan] = useState(true)
  const [showRevise, setShowRevise] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [revisionForm, setRevisionForm] = useState({
    title: '',
    description_markdown: '',
    revision_note: '',
    depends_on_requirement_ids: [] as number[],
  })

  const loadDetail = useCallback(async () => {
    const data = await api.getRequirement(requirementId)
    setDetail(data)
  }, [requirementId])

  useEffect(() => {
    loadDetail().catch(() => {})
    api.getRequirements().then(setRequirements).catch(() => {})
  }, [loadDetail])

  useEffect(() => {
    if (!detail) return
    setRevisionForm({
      title: detail.requirement.title,
      description_markdown: detail.requirement.description_markdown,
      revision_note: '',
      depends_on_requirement_ids: detail.dependencies.map((d) => d.depends_on_requirement_id),
    })
    setShowRevise(false)
  }, [detail])

  // Poll while in_progress
  useEffect(() => {
    if (!detail || detail.requirement.status !== 'in_progress') return
    const timer = setInterval(() => { loadDetail().catch(() => {}) }, 2500)
    return () => clearInterval(timer)
  }, [detail, loadDetail])

  const handlePlan = async () => {
    const data = await api.planRequirement(requirementId)
    setDetail(data)
  }

  const handleStart = async () => {
    const data = await api.startRequirement(requirementId)
    setDetail(data)
  }

  const handleRevise = async () => {
    if (!detail || !revisionForm.description_markdown.trim()) return
    setSubmitting(true)
    try {
      const data = await api.reviseRequirement(requirementId, {
        title: revisionForm.title.trim(),
        description_markdown: revisionForm.description_markdown.trim(),
        revision_note: revisionForm.revision_note.trim() || null,
        source_ref: detail.requirement.source_ref,
        depends_on_requirement_ids: revisionForm.depends_on_requirement_ids,
      })
      setShowRevise(false)
      setDetail(data)
    } finally {
      setSubmitting(false)
    }
  }

  const toggleDependency = (values: number[], rid: number) =>
    values.includes(rid) ? values.filter((v) => v !== rid) : [...values, rid]

  const revisionDependencyCandidates = requirements.filter((r) => r.id !== requirementId)

  if (!detail) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate('/requirements')} className="text-sm text-blue-600 hover:underline">← 返回需求池</button>
        <div className="p-8 text-sm text-gray-500 bg-white border rounded-xl">加载中…</div>
      </div>
    )
  }

  const req = detail.requirement

  return (
    <div data-testid="requirement-detail-page" className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Link to="/requirements" className="text-blue-600 hover:underline">需求池</Link>
        <span>/</span>
        <span className="font-medium text-gray-900">{req.title}</span>
      </div>

      {/* Header */}
      <div className="p-6 space-y-6 bg-white border shadow-sm rounded-2xl">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold">{req.title}</h2>
            <div className="flex flex-wrap items-center gap-2 mt-2 text-xs text-gray-500">
              <span className={`rounded-full px-2 py-1 font-medium ${STATUS_CLASS[req.status] || STATUS_CLASS.draft}`}>
                {STATUS_LABEL[req.status] || req.status}
              </span>
              <span>Priority: {req.priority}</span>
              <span>Plan v{req.current_plan_version}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              data-testid="plan-requirement-btn"
              className="px-3 py-2 text-sm border rounded hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={req.status === 'blocked' || req.status === 'in_progress'}
              onClick={() => { handlePlan().catch(() => {}) }}
            >
              生成计划
            </button>
            <button
              data-testid="start-requirement-btn"
              className="px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!detail.workflow_run || req.status === 'blocked' || req.status === 'done'}
              onClick={() => { handleStart().catch(() => {}) }}
            >
              启动执行
            </button>
            <button
              data-testid="toggle-revise-btn"
              className="px-3 py-2 text-sm border rounded hover:bg-gray-50"
              onClick={() => setShowRevise((v) => !v)}
            >
              提交修订
            </button>
          </div>
        </div>

        {req.blocked_by_count > 0 && (
          <div data-testid="blocked-banner" className="px-4 py-3 text-sm text-red-700 border border-red-200 rounded-xl bg-red-50">
            当前需求被 {req.blocked_by_count} 个未完成依赖阻塞，需等待上游 requirement 完成后再规划执行。
          </div>
        )}

        {showRevise && (
          <section data-testid="requirement-revision-form" className="p-4 space-y-3 border shadow-sm rounded-xl bg-amber-50">
            <div className="text-sm font-semibold">修订需求</div>
            <input
              data-testid="revise-title"
              className="w-full px-3 py-2 border rounded"
              value={revisionForm.title}
              onChange={(e) => setRevisionForm((prev) => ({ ...prev, title: e.target.value }))}
            />
            <textarea
              data-testid="revise-description"
              className="w-full px-3 py-2 border rounded min-h-32"
              value={revisionForm.description_markdown}
              onChange={(e) => setRevisionForm((prev) => ({ ...prev, description_markdown: e.target.value }))}
            />
            <textarea
              data-testid="revise-note"
              className="w-full px-3 py-2 border rounded min-h-20"
              placeholder="记录这次需求修订的原因"
              value={revisionForm.revision_note}
              onChange={(e) => setRevisionForm((prev) => ({ ...prev, revision_note: e.target.value }))}
            />
            <div data-testid="revise-dependencies" className="px-3 py-2 text-xs text-gray-600 bg-white border rounded">
              {revisionDependencyCandidates.length === 0 ? (
                <div>暂无可选依赖</div>
              ) : (
                revisionDependencyCandidates.map((r) => (
                  <label key={r.id} className="flex items-center gap-2 py-1">
                    <input
                      data-testid={`revise-dependency-${r.id}`}
                      type="checkbox"
                      checked={revisionForm.depends_on_requirement_ids.includes(r.id)}
                      onChange={() => setRevisionForm((prev) => ({
                        ...prev,
                        depends_on_requirement_ids: toggleDependency(prev.depends_on_requirement_ids, r.id),
                      }))}
                    />
                    <span>{r.title}</span>
                    <span className="text-gray-400">{STATUS_LABEL[r.status] || r.status}</span>
                  </label>
                ))
              )}
            </div>
            <div className="flex justify-end">
              <button
                data-testid="submit-revision-btn"
                className="px-4 py-2 text-sm font-medium text-white rounded bg-amber-600 hover:bg-amber-700 disabled:opacity-50"
                disabled={submitting}
                onClick={() => { handleRevise().catch(() => {}) }}
              >
                保存修订并重开流程
              </button>
            </div>
          </section>
        )}

        {/* Main content grid */}
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_320px]">
          <div className="space-y-4">
            <section className="p-4 border rounded-xl bg-slate-50">
              <div className="mb-2 text-sm font-semibold">需求说明</div>
              <Md>{req.description_markdown}</Md>
              {req.target_project_path && (
                <div className="mt-2 rounded bg-blue-50 px-3 py-1.5 text-xs text-blue-800" data-testid="target-project-path">
                  目标项目: {req.target_project_path}
                </div>
              )}
            </section>

            <section className="p-4 border rounded-xl" data-testid="dependencies-panel">
              <div className="mb-3 text-sm font-semibold">Dependencies</div>
              {detail.dependencies.length === 0 ? (
                <div className="text-xs text-gray-500">无依赖，可以直接规划执行。</div>
              ) : (
                <div className="space-y-2">
                  {detail.dependencies.map((dep) => (
                    <Link
                      key={dep.id}
                      to={`/requirements/${dep.depends_on_requirement_id}`}
                      data-testid={`dependency-${dep.depends_on_requirement_id}`}
                      className="block p-3 text-xs transition rounded-lg bg-gray-50 hover:bg-gray-100"
                    >
                      <div className="font-medium text-gray-900">{dep.depends_on_title}</div>
                      <div className="flex items-center justify-between mt-1 text-gray-500">
                        <span>#{dep.depends_on_requirement_id}</span>
                        <span>{STATUS_LABEL[dep.depends_on_status] || dep.depends_on_status}</span>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </section>

            {/* Plan section – implementation_plan artifact from the active run */}
            {(() => {
              const planArtifact = detail.artifacts
                .filter((a) => a.artifact_type === 'implementation_plan')
                .sort((a, b) => b.id - a.id)[0]
              if (!planArtifact) return null
              return (
                <section className="border rounded-xl" data-testid="plan-panel">
                  <button
                    className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold hover:bg-gray-50 rounded-xl"
                    onClick={() => setShowPlan((v) => !v)}
                  >
                    <span className="flex items-center gap-2">
                      执行计划
                      {detail.workflow_run && (
                        <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-normal text-blue-700">
                          Plan v{detail.workflow_run.plan_version}
                        </span>
                      )}
                    </span>
                    <span className="text-gray-400 text-xs">{showPlan ? '▲ 收起' : '▼ 展开'}</span>
                  </button>
                  {showPlan && (
                    <div className="border-t px-4 py-3">
                      {planArtifact.content_summary && (
                        <div className="mb-2 text-xs text-gray-500">{planArtifact.content_summary}</div>
                      )}
                      {planArtifact.human_readable_body ? (
                        <Md>{planArtifact.human_readable_body}</Md>
                      ) : (
                        <div className="text-xs text-gray-400">计划内容暂无。</div>
                      )}
                    </div>
                  )}
                </section>
              )
            })()}

            <section className="p-4 border rounded-xl" data-testid="workflow-steps-panel">
              <div className="flex items-center justify-between mb-3">
                <div className="text-sm font-semibold">Workflow Steps</div>
                <div className="text-xs text-gray-500">Run #{detail.workflow_run?.id ?? '-'}</div>
              </div>
              <div className="space-y-3">
                {(detail.workflow_run?.steps || []).map((step) => {
                  const taskId = step.compatibility_task_id
                  const inner = (
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium">{step.title}</div>
                        <div className="mt-1 text-xs text-gray-500">
                          {step.step_type} · {step.assigned_workflow_role || '-'} · agent {step.assigned_agent_id || '-'}
                          {taskId != null && <span className="ml-2 text-blue-600">Task #{taskId}</span>}
                        </div>
                      </div>
                      <span className={`rounded-full px-2 py-1 text-xs font-medium ${STEP_STATUS_CLASS[step.status] || STEP_STATUS_CLASS.pending}`}>
                        {step.status}
                      </span>
                    </div>
                  )

                  return taskId != null ? (
                    <Link
                      key={step.id}
                      to={`/tasks/${taskId}`}
                      data-testid={`workflow-step-${step.id}`}
                      className="block p-3 transition border rounded-lg cursor-pointer hover:bg-blue-50"
                    >
                      {inner}
                      {step.branch_from_step_id != null && (
                        <div className="mt-2 text-xs text-amber-600">Bugfix branch from step #{step.branch_from_step_id}</div>
                      )}
                      <div className="mt-2 text-xs text-gray-600">{step.done_when_markdown}</div>
                    </Link>
                  ) : (
                    <div
                      key={step.id}
                      data-testid={`workflow-step-${step.id}`}
                      className="p-3 transition border rounded-lg cursor-pointer hover:bg-gray-50"
                      onClick={() => setExpandedStepId(expandedStepId === step.id ? null : step.id)}
                    >
                      {inner}
                      {step.branch_from_step_id != null && (
                        <div className="mt-2 text-xs text-amber-600">Bugfix branch from step #{step.branch_from_step_id}</div>
                      )}
                      {expandedStepId === step.id ? (
                        <div className="mt-3 space-y-2">
                          {step.done_when_markdown && (
                            <div className="px-3 py-2 text-xs text-gray-700 border border-gray-100 rounded-md bg-gray-50">
                              <div className="mb-1 font-semibold text-gray-500 uppercase tracking-wide text-[10px]">验收标准 done_when</div>
                              <Md>{step.done_when_markdown}</Md>
                            </div>
                          )}
                          <div className="px-3 py-2 text-xs border rounded-md bg-amber-50 border-amber-100 text-amber-700">
                            Task 尚未分派 — 等待前置步骤完成后将自动调度执行
                          </div>
                        </div>
                      ) : (
                        <div className="mt-2 text-xs text-gray-400 line-clamp-1">{step.done_when_markdown}</div>
                      )}
                    </div>
                  )
                })}
                {(detail.workflow_run?.steps || []).length === 0 && (
                  <div className="text-xs text-gray-500">当前还没有 workflow run。先生成计划，再启动执行。</div>
                )}
              </div>
            </section>
          </div>

          <div className="space-y-4">
            <section className="p-4 border rounded-xl" data-testid="acceptance-checks-panel">
              <div className="mb-3 text-sm font-semibold">Acceptance Checks</div>
              <div className="space-y-2">
                {detail.acceptance_checks.map((check) => (
                  <div key={check.id} className="p-3 text-xs rounded-lg bg-gray-50">
                    <div className="font-medium text-gray-900">{check.check_key}</div>
                    <div className="mt-1 text-gray-600">{check.description}</div>
                    <div className="flex items-center justify-between mt-2 text-gray-500">
                      <span>{check.owner_role}</span>
                      <span>{check.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="p-4 border rounded-xl" data-testid="artifacts-panel">
              <div className="mb-3 text-sm font-semibold">Artifacts</div>
              <div className="space-y-2">
                {detail.artifacts.slice().reverse().slice(0, 8).map((artifact) => (
                  <div key={artifact.id} className="p-3 text-xs rounded-lg bg-gray-50">
                    <div className="font-medium text-gray-900">{artifact.artifact_type}</div>
                    <div className="mt-1 text-gray-600">{artifact.content_summary || '-'}</div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}
