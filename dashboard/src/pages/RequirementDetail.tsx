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
    <div className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-headings:mb-2">
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
        <div className="rounded-xl border bg-white p-8 text-sm text-gray-500">加载中…</div>
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
        <span className="text-gray-900 font-medium">{req.title}</span>
      </div>

      {/* Header */}
      <div className="rounded-2xl border bg-white p-6 shadow-sm space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold">{req.title}</h2>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-500">
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
              className="rounded border px-3 py-2 text-sm hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={req.status === 'blocked' || req.status === 'in_progress'}
              onClick={() => { handlePlan().catch(() => {}) }}
            >
              生成计划
            </button>
            <button
              data-testid="start-requirement-btn"
              className="rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!detail.workflow_run || req.status === 'blocked' || req.status === 'done'}
              onClick={() => { handleStart().catch(() => {}) }}
            >
              启动执行
            </button>
            <button
              data-testid="toggle-revise-btn"
              className="rounded border px-3 py-2 text-sm hover:bg-gray-50"
              onClick={() => setShowRevise((v) => !v)}
            >
              提交修订
            </button>
          </div>
        </div>

        {req.blocked_by_count > 0 && (
          <div data-testid="blocked-banner" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            当前需求被 {req.blocked_by_count} 个未完成依赖阻塞，需等待上游 requirement 完成后再规划执行。
          </div>
        )}

        {showRevise && (
          <section data-testid="requirement-revision-form" className="rounded-xl border bg-amber-50 p-4 shadow-sm space-y-3">
            <div className="text-sm font-semibold">修订需求</div>
            <input
              data-testid="revise-title"
              className="w-full rounded border px-3 py-2"
              value={revisionForm.title}
              onChange={(e) => setRevisionForm((prev) => ({ ...prev, title: e.target.value }))}
            />
            <textarea
              data-testid="revise-description"
              className="min-h-32 w-full rounded border px-3 py-2"
              value={revisionForm.description_markdown}
              onChange={(e) => setRevisionForm((prev) => ({ ...prev, description_markdown: e.target.value }))}
            />
            <textarea
              data-testid="revise-note"
              className="min-h-20 w-full rounded border px-3 py-2"
              placeholder="记录这次需求修订的原因"
              value={revisionForm.revision_note}
              onChange={(e) => setRevisionForm((prev) => ({ ...prev, revision_note: e.target.value }))}
            />
            <div data-testid="revise-dependencies" className="rounded border bg-white px-3 py-2 text-xs text-gray-600">
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
                className="rounded bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
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
            <section className="rounded-xl border bg-slate-50 p-4">
              <div className="mb-2 text-sm font-semibold">需求说明</div>
              <Md>{req.description_markdown}</Md>
              {req.target_project_path && (
                <div className="mt-2 rounded bg-blue-50 px-3 py-1.5 text-xs text-blue-800" data-testid="target-project-path">
                  目标项目: {req.target_project_path}
                </div>
              )}
            </section>

            <section className="rounded-xl border p-4" data-testid="dependencies-panel">
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
                      className="block rounded-lg bg-gray-50 p-3 text-xs hover:bg-gray-100 transition"
                    >
                      <div className="font-medium text-gray-900">{dep.depends_on_title}</div>
                      <div className="mt-1 flex items-center justify-between text-gray-500">
                        <span>#{dep.depends_on_requirement_id}</span>
                        <span>{STATUS_LABEL[dep.depends_on_status] || dep.depends_on_status}</span>
                      </div>
                    </Link>
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
                      className="block rounded-lg border p-3 hover:bg-blue-50 transition cursor-pointer"
                    >
                      {inner}
                      {step.branch_from_step_id != null && (
                        <div className="mt-2 text-xs text-amber-600">Bugfix branch from step #{step.branch_from_step_id}</div>
                      )}
                      <div className="mt-2 text-xs text-gray-600">{step.done_when_markdown}</div>
                    </Link>
                  ) : (
                    <div key={step.id} data-testid={`workflow-step-${step.id}`} className="rounded-lg border p-3">
                      {inner}
                      {step.branch_from_step_id != null && (
                        <div className="mt-2 text-xs text-amber-600">Bugfix branch from step #{step.branch_from_step_id}</div>
                      )}
                      <div className="mt-2 text-xs text-gray-600">{step.done_when_markdown}</div>
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
    </div>
  )
}
