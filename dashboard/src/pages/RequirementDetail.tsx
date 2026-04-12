import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { api, RequirementDetail as RequirementDetailType, Requirement } from '../api'

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  planning: '规划中',
  plan_failed: '规划失败',
  ready: '已规划',
  paused: '已暂停',
  in_progress: '执行中',
  done: '已完成',
  needs_revision: '需修订',
  blocked: '阻塞',
  deleted: '已删除',
}

const STATUS_CLASS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  planning: 'bg-indigo-100 text-indigo-700',
  plan_failed: 'bg-rose-100 text-rose-700',
  ready: 'bg-sky-100 text-sky-700',
  paused: 'bg-slate-200 text-slate-700',
  in_progress: 'bg-blue-100 text-blue-700',
  done: 'bg-green-100 text-green-700',
  needs_revision: 'bg-amber-100 text-amber-700',
  blocked: 'bg-red-100 text-red-700',
  deleted: 'bg-zinc-200 text-zinc-700',
}

const APPROVAL_LABEL: Record<string, string> = {
  pending_approval: '待审批',
  approved: '已批准',
  rejected: '已拒绝',
  waived: '已豁免',
}

const APPROVAL_CLASS: Record<string, string> = {
  pending_approval: 'bg-yellow-100 text-yellow-700',
  approved: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
  waived: 'bg-slate-200 text-slate-700',
}

const STEP_STATUS_CLASS: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-700',
  ready: 'bg-sky-50 text-sky-700',
  running: 'bg-blue-100 text-blue-700',
  paused: 'bg-slate-200 text-slate-700',
  waiting_approval: 'bg-yellow-100 text-yellow-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  blocked: 'bg-gray-200 text-gray-500',
  deleted: 'bg-zinc-200 text-zinc-700',
}

function getRequirementDisplayState(requirement: Requirement) {
  return {
    label: STATUS_LABEL[requirement.status] || requirement.status,
    className: STATUS_CLASS[requirement.status] || STATUS_CLASS.draft,
  }
}

function Md({ children }: Readonly<{ children: string }>) {
  return (
    <div className="prose-sm prose max-w-none prose-p:my-1 prose-ul:my-1 prose-headings:mb-2">
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  )
}

function getTargetProjectPaths(value: string | null) {
  if (!value) return []
  return value.split('\n').map((item) => item.trim()).filter(Boolean)
}

function parsePayload(raw: string | null) {
  if (!raw) return null
  try {
    return JSON.parse(raw) as Record<string, unknown>
  } catch {
    return null
  }
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
  const [publishing, setPublishing] = useState(false)
  const [decidingApproval, setDecidingApproval] = useState(false)
  const [approvalComment, setApprovalComment] = useState('')
  const [revisionForm, setRevisionForm] = useState({
    title: '',
    description_markdown: '',
    revision_note: '',
    depends_on_requirement_ids: [] as number[],
  })
  const [publishChecks, setPublishChecks] = useState<string[]>([])
  const [publishNote, setPublishNote] = useState('')

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
    setPublishChecks(detail.delivery_state?.confirmed_checks || [])
    setPublishNote(detail.delivery_state?.publish_note || '')
  }, [detail])

  // Poll while planning or in_progress
  useEffect(() => {
    if (!detail || !['planning', 'in_progress'].includes(detail.requirement.status)) return
    const timer = setInterval(() => { loadDetail().catch(() => {}) }, 2500)
    return () => clearInterval(timer)
  }, [detail, loadDetail])

  const handleStart = async () => {
    const data = await api.startRequirement(requirementId)
    setDetail(data)
  }

  const handlePause = async () => {
    const data = await api.pauseRequirement(requirementId)
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

  const togglePublishCheck = (check: string) => {
    setPublishChecks((prev) => prev.includes(check) ? prev.filter((item) => item !== check) : [...prev, check])
  }

  const handlePublish = async () => {
    setPublishing(true)
    try {
      const data = await api.publishRequirement(requirementId, {
        completed_checks: publishChecks,
        note: publishNote.trim() || null,
      })
      setDetail(data)
    } finally {
      setPublishing(false)
    }
  }

  const handleApprovalDecision = async (action: 'approve' | 'reject' | 'waive') => {
    setDecidingApproval(true)
    try {
      const data = await api.decideRequirementApproval(requirementId, {
        action,
        reviewer: 'cto',
        comment: approvalComment.trim() || null,
      })
      setApprovalComment('')
      setDetail(data)
    } finally {
      setDecidingApproval(false)
    }
  }

  const toggleDependency = (values: number[], rid: number) =>
    values.includes(rid) ? values.filter((v) => v !== rid) : [...values, rid]

  const revisionDependencyCandidates = requirements.filter((r) => r.id !== requirementId && r.status !== 'deleted')

  if (!detail) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate('/requirements')} className="text-sm text-blue-600 hover:underline">← 返回需求池</button>
        <div className="p-8 text-sm text-gray-500 bg-white border rounded-xl">加载中…</div>
      </div>
    )
  }

  const req = detail.requirement
  const displayState = getRequirementDisplayState(req)
  const approvalLabel = APPROVAL_LABEL[req.approval_status] || req.approval_status
  const approvalClass = APPROVAL_CLASS[req.approval_status] || APPROVAL_CLASS.pending_approval
  const deliveryState = detail.delivery_state
  const targetProjectPaths = getTargetProjectPaths(req.target_project_path)
  const planArtifact = detail.artifacts
    .filter((a) => a.artifact_type === 'implementation_plan')
    .sort((a, b) => b.id - a.id)[0]
  const validationPlanArtifact = detail.artifacts
    .filter((a) => a.artifact_type === 'validation_plan')
    .sort((a, b) => b.id - a.id)[0]
  const validationPlan = parsePayload(validationPlanArtifact?.machine_readable_payload ?? null)
  const validationSummary = typeof validationPlan?.summary_markdown === 'string' ? validationPlan.summary_markdown : ''
  const validationGates = Array.isArray(validationPlan?.gates) ? validationPlan.gates : []
  const manualChecks = Array.isArray(validationPlan?.manual_checks) ? validationPlan.manual_checks : []
  const automatedChecks = Array.isArray(validationPlan?.automated_checks) ? validationPlan.automated_checks : []
  const bugfixOwner = typeof validationPlan?.bugfix_owner_role === 'string' ? validationPlan.bugfix_owner_role : ''
  const closeoutOwner = typeof validationPlan?.closeout_owner_role === 'string' ? validationPlan.closeout_owner_role : ''
  const bugReports = detail.artifacts
    .filter((artifact) => artifact.artifact_type === 'bug_report')
    .sort((a, b) => b.id - a.id)
    .slice(0, 3)
  const latestContextCompaction = detail.artifacts
    .filter((artifact) => artifact.artifact_type === 'context_compaction')
    .sort((a, b) => b.id - a.id)[0]
  const latestPromptCacheProfile = detail.artifacts
    .filter((artifact) => artifact.artifact_type === 'prompt_cache_profile')
    .sort((a, b) => b.id - a.id)[0]
  const latestStaleMemoryVerification = detail.artifacts
    .filter((artifact) => artifact.artifact_type === 'stale_memory_verification')
    .sort((a, b) => b.id - a.id)[0]
  const latestRuntimeLifecycle = detail.artifacts
    .filter((artifact) => artifact.artifact_type === 'runtime_lifecycle')
    .sort((a, b) => b.id - a.id)[0]
  const latestRuntimeTelemetry = detail.artifacts
    .filter((artifact) => artifact.artifact_type === 'runtime_telemetry')
    .sort((a, b) => b.id - a.id)[0]
  const promptCachePayload = parsePayload(latestPromptCacheProfile?.machine_readable_payload ?? null)
  const contextCompactionPayload = parsePayload(latestContextCompaction?.machine_readable_payload ?? null)
  const staleMemoryPayload = parsePayload(latestStaleMemoryVerification?.machine_readable_payload ?? null)
  const runtimeLifecyclePayload = parsePayload(latestRuntimeLifecycle?.machine_readable_payload ?? null)
  const runtimeTelemetryPayload = parsePayload(latestRuntimeTelemetry?.machine_readable_payload ?? null)
  const activeContextStep = (detail.workflow_run?.steps || []).find((step) => step.status !== 'completed' && step.status !== 'deleted')
    || detail.workflow_run?.steps?.[0]
  const activeContextPolicy = parsePayload(activeContextStep?.context_policy_json ?? null)
  const activeExecutionProfile = parsePayload(activeContextStep?.execution_profile_json ?? null)

  const canStartRequirement = !['blocked', 'done', 'deleted', 'planning', 'plan_failed'].includes(req.status)
    && ['approved', 'waived'].includes(req.approval_status)

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
              <span className={`rounded-full px-2 py-1 font-medium ${displayState.className}`}>
                {displayState.label}
              </span>
              <span data-testid="requirement-approval-badge" className={`rounded-full px-2 py-1 font-medium ${approvalClass}`}>
                审批: {approvalLabel}
              </span>
              <span>Priority: {req.priority}</span>
              <span>Plan v{req.current_plan_version}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              data-testid="start-requirement-btn"
              className="px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!canStartRequirement && req.status !== 'in_progress'}
              title={!canStartRequirement && req.status !== 'in_progress' ? `当前审批状态为 ${approvalLabel}，需审批通过后才能自动执行` : undefined}
              onClick={() => {
                if (req.status === 'in_progress') {
                  handlePause().catch(() => {})
                  return
                }
                handleStart().catch(() => {})
              }}
            >
              {req.status === 'in_progress' ? '暂停执行' : '启动执行'}
            </button>
            <button
              data-testid="toggle-revise-btn"
              className="px-3 py-2 text-sm border rounded hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={req.status === 'deleted'}
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

        {req.status === 'planning' && (
          <div data-testid="planning-banner" className="px-4 py-3 text-sm text-sky-700 border border-sky-200 rounded-xl bg-sky-50">
            当前需求正在自动生成 workflow plan。规划完成后会自动进入可执行状态。
          </div>
        )}

        {req.status === 'plan_failed' && (
          <div data-testid="plan-failed-banner" className="px-4 py-3 text-sm text-rose-700 border border-rose-200 rounded-xl bg-rose-50">
            workflow 规划失败。请修订需求后重试，或等待后续补充“重新规划”入口。
          </div>
        )}

        {!['approved', 'waived'].includes(req.approval_status) && (
          <div data-testid="approval-banner" className="rounded-xl border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
            当前需求审批状态为 {approvalLabel}。审批通过或豁免后，系统会自动生成计划，再进入自动执行。
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
              {targetProjectPaths.length > 0 && (
                <div className="mt-2 rounded bg-blue-50 px-3 py-2 text-xs text-blue-800" data-testid="target-project-path">
                  <div className="mb-1 font-medium">目标项目:</div>
                  <div className="space-y-1 font-mono">
                    {targetProjectPaths.map((projectPath) => (
                      <div key={projectPath} className="break-all">{projectPath}</div>
                    ))}
                  </div>
                </div>
              )}
            </section>

            <section className="p-4 border rounded-xl bg-slate-50" data-testid="requirement-approval-panel">
              <div className="mb-3 text-sm font-semibold">Execution Approval</div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border bg-white p-3 text-xs text-gray-600">
                  <div className="mb-2 font-medium text-gray-900">Approval Status</div>
                  <div>status: {approvalLabel}</div>
                  <div>mode: {String(req.approval_contract?.approval_mode || '-')}</div>
                  <div>requested at: {req.approval_requested_at || '-'}</div>
                  <div>approved at: {req.approved_at || '-'}</div>
                </div>
                <div className="rounded-lg border bg-white p-3 text-xs text-gray-600">
                  <div className="mb-2 font-medium text-gray-900">Required Roles</div>
                  {Array.isArray(req.approval_contract?.required_approver_roles) && req.approval_contract.required_approver_roles.length > 0 ? (
                    <div className="space-y-1">
                      {(req.approval_contract.required_approver_roles as string[]).map((role) => (
                        <div key={role}>{role}</div>
                      ))}
                    </div>
                  ) : (
                    <div>-</div>
                  )}
                </div>
              </div>
              {req.approval_status === 'pending_approval' && (
                <div className="mt-3 rounded-lg border bg-white p-3">
                  <input
                    data-testid="requirement-approval-comment"
                    className="mb-2 w-full rounded border px-3 py-2 text-sm"
                    placeholder="审批意见（可选）"
                    value={approvalComment}
                    onChange={(e) => setApprovalComment(e.target.value)}
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      data-testid="approve-requirement-btn"
                      className="rounded bg-green-600 px-4 py-2 text-xs text-white hover:bg-green-700 disabled:opacity-50"
                      disabled={decidingApproval}
                      onClick={() => { handleApprovalDecision('approve').catch(() => {}) }}
                    >
                      批准执行
                    </button>
                    <button
                      data-testid="waive-requirement-btn"
                      className="rounded bg-slate-700 px-4 py-2 text-xs text-white hover:bg-slate-800 disabled:opacity-50"
                      disabled={decidingApproval}
                      onClick={() => { handleApprovalDecision('waive').catch(() => {}) }}
                    >
                      豁免审批
                    </button>
                    <button
                      data-testid="reject-requirement-btn"
                      className="rounded bg-red-600 px-4 py-2 text-xs text-white hover:bg-red-700 disabled:opacity-50"
                      disabled={decidingApproval}
                      onClick={() => { handleApprovalDecision('reject').catch(() => {}) }}
                    >
                      拒绝
                    </button>
                  </div>
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
            {planArtifact && (
              <section className="border rounded-xl" data-testid="plan-panel">
                <button
                  className="flex items-center justify-between w-full px-4 py-3 text-sm font-semibold hover:bg-gray-50 rounded-xl"
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
                  <span className="text-xs text-gray-400">{showPlan ? '▲ 收起' : '▼ 展开'}</span>
                </button>
                {showPlan && (
                  <div className="px-4 py-3 border-t">
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
            )}

            <section className="p-4 border rounded-xl" data-testid="workflow-steps-panel">
              <div className="flex items-center justify-between mb-3">
                <div className="text-sm font-semibold">Workflow Steps</div>
                <div className="text-xs text-gray-500">Run #{detail.workflow_run?.id ?? '-'}</div>
              </div>
              <div className="space-y-3">
                {(detail.workflow_run?.steps || []).map((step) => {
                  const taskId = step.compatibility_task_id
                  const executionProfile = parsePayload(step.execution_profile_json ?? null)
                  const budgetCap = executionProfile?.budget_cap as Record<string, unknown> | undefined
                  const complexityTier = typeof executionProfile?.complexity_tier === 'string'
                    ? executionProfile.complexity_tier
                    : ''
                  const inner = (
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium">{step.title}</div>
                        <div className="mt-1 text-xs text-gray-500">
                          {step.step_type} · {step.assigned_workflow_role || '-'} · agent {step.assigned_agent_id || '-'}
                          {taskId != null && <span className="ml-2 text-blue-600">Task #{taskId}</span>}
                        </div>
                        {complexityTier && (
                          <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-600">
                            <span className="rounded-full bg-indigo-50 px-2 py-1 text-indigo-700">
                              tier {complexityTier}
                            </span>
                            <span>in≤{String(budgetCap?.max_input_tokens ?? '-')}</span>
                            <span>out≤{String(budgetCap?.max_output_tokens ?? '-')}</span>
                          </div>
                        )}
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
                  <div className="text-xs text-gray-500">计划正在生成中，请稍候…</div>
                )}
              </div>
            </section>
          </div>

          <div className="space-y-4">
            {deliveryState && (
              <section className="p-4 border rounded-xl bg-amber-50" data-testid="delivery-state-panel">
                <div className="mb-3 text-sm font-semibold">Delivery Gate</div>
                <div className="grid gap-3 text-xs sm:grid-cols-2">
                  <div className="p-3 border rounded-lg bg-white">
                    <div className="mb-2 font-medium text-gray-900">Branch</div>
                    <div className="space-y-1 text-gray-600">
                      <div>{deliveryState.branch_name || '-'}</div>
                      <div>base: {deliveryState.base_branch || '-'}</div>
                      <div>strategy: {deliveryState.branch_strategy || '-'}</div>
                    </div>
                  </div>
                  <div className="p-3 border rounded-lg bg-white">
                    <div className="mb-2 font-medium text-gray-900">Release State</div>
                    <div className="space-y-1 text-gray-600">
                      <div>review: {deliveryState.review_status}</div>
                      <div>publish: {deliveryState.publish_status}</div>
                      <div>mode: {deliveryState.release_mode || '-'}</div>
                    </div>
                  </div>
                </div>
                {deliveryState.review_surface_summary && (
                  <div className="mt-3 text-xs text-gray-700">{deliveryState.review_surface_summary}</div>
                )}
                {deliveryState.required_checks.length > 0 && (
                  <div className="mt-3 p-3 text-xs border rounded-lg bg-white">
                    <div className="mb-2 font-medium text-gray-900">Required Checks Before Publish</div>
                    <div className="space-y-2">
                      {deliveryState.required_checks.map((check) => (
                        <label key={check} className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={publishChecks.includes(check)}
                            onChange={() => togglePublishCheck(check)}
                          />
                          <span>{check}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
                {deliveryState.publish_blockers.length > 0 && (
                  <div className="mt-3 p-3 text-xs border rounded-lg bg-rose-50 border-rose-100 text-rose-700">
                    <div className="mb-1 font-medium">Publish Blockers</div>
                    <div className="space-y-1">
                      {deliveryState.publish_blockers.map((item) => (
                        <div key={item}>{item}</div>
                      ))}
                    </div>
                  </div>
                )}
                {deliveryState.rollback_hint_markdown && (
                  <div className="mt-3 p-3 text-xs border rounded-lg bg-white">
                    <div className="mb-2 font-medium text-gray-900">Rollback Hint</div>
                    <Md>{deliveryState.rollback_hint_markdown}</Md>
                  </div>
                )}
                <div className="mt-3 space-y-2">
                  <textarea
                    data-testid="publish-note"
                    className="w-full px-3 py-2 text-xs border rounded min-h-20"
                    placeholder="记录这次 publish decision 的说明"
                    value={publishNote}
                    onChange={(e) => setPublishNote(e.target.value)}
                  />
                  <div className="flex justify-end">
                    <button
                      data-testid="publish-requirement-btn"
                      className="px-3 py-2 text-sm font-medium text-white bg-emerald-600 rounded hover:bg-emerald-700 disabled:opacity-50"
                      disabled={publishing || deliveryState.publish_status === 'published' || deliveryState.release_mode === 'disabled'}
                      onClick={() => { handlePublish().catch(() => {}) }}
                    >
                      {deliveryState.publish_status === 'published' ? '已发布' : 'Promote To Publish'}
                    </button>
                  </div>
                </div>
              </section>
            )}

            {validationPlanArtifact && (
              <section className="p-4 border rounded-xl bg-slate-50" data-testid="validation-contract-panel">
                <div className="mb-3 text-sm font-semibold">Validation Contract</div>
                {validationSummary ? <Md>{validationSummary}</Md> : <div className="text-xs text-gray-500">暂无验证摘要。</div>}
                <div className="grid gap-3 mt-3 sm:grid-cols-2">
                  <div className="p-3 text-xs border rounded-lg bg-white">
                    <div className="mb-2 font-medium text-gray-900">Manual Checks</div>
                    {manualChecks.length === 0 ? (
                      <div className="text-gray-500">无</div>
                    ) : (
                      <div className="space-y-2">
                        {manualChecks.map((check, idx) => {
                          const item = check as Record<string, unknown>
                          return (
                            <div key={`${String(item.check_key)}-${idx}`}>
                              <div className="font-medium text-gray-800">{String(item.check_key || '-')}</div>
                              <div className="text-gray-500">{String(item.owner_role || '-')} · {String(item.method || '-')}</div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                  <div className="p-3 text-xs border rounded-lg bg-white">
                    <div className="mb-2 font-medium text-gray-900">Automated Checks</div>
                    {automatedChecks.length === 0 ? (
                      <div className="text-gray-500">无</div>
                    ) : (
                      <div className="space-y-2">
                        {automatedChecks.map((check, idx) => {
                          const item = check as Record<string, unknown>
                          return (
                            <div key={`${String(item.check_key)}-${idx}`}>
                              <div className="font-medium text-gray-800">{String(item.check_key || '-')}</div>
                              <div className="text-gray-500">{String(item.owner_role || '-')} · {String(item.method || '-')}</div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                </div>
                <div className="grid gap-3 mt-3 sm:grid-cols-2">
                  <div className="p-3 text-xs border rounded-lg bg-white">
                    <div className="mb-2 font-medium text-gray-900">Close Gates</div>
                    <div className="space-y-1 text-gray-600">
                      {validationGates.length === 0 ? (
                        <div>暂无</div>
                      ) : (
                        validationGates.map((gate, idx) => <div key={`${String(gate)}-${idx}`}>{String(gate)}</div>)
                      )}
                    </div>
                  </div>
                  <div className="p-3 text-xs border rounded-lg bg-white">
                    <div className="mb-2 font-medium text-gray-900">Ownership</div>
                    <div className="space-y-1 text-gray-600">
                      <div>Bugfix: {bugfixOwner || '-'}</div>
                      <div>Closeout: {closeoutOwner || '-'}</div>
                    </div>
                  </div>
                </div>
              </section>
            )}

            {(latestContextCompaction || latestPromptCacheProfile || latestStaleMemoryVerification || activeContextPolicy || activeExecutionProfile) && (
              <section className="p-4 border rounded-xl bg-slate-50" data-testid="context-governance-panel">
                <div className="mb-3 text-sm font-semibold">Context Governance</div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {activeExecutionProfile && (
                    <div className="p-3 text-xs border rounded-lg bg-white">
                      <div className="mb-2 font-medium text-gray-900">Execution Profile</div>
                      <div className="space-y-1 text-gray-600">
                        <div>tier: {String(activeExecutionProfile.complexity_tier ?? '-')}</div>
                        <div>allow escalation: {String(activeExecutionProfile.allow_escalation ?? '-')}</div>
                        <div>next tier: {String((activeExecutionProfile.escalation_rule as Record<string, unknown> | undefined)?.next_tier ?? '-')}</div>
                        <div>input tokens: {String((activeExecutionProfile.budget_cap as Record<string, unknown> | undefined)?.max_input_tokens ?? '-')}</div>
                        <div>output tokens: {String((activeExecutionProfile.budget_cap as Record<string, unknown> | undefined)?.max_output_tokens ?? '-')}</div>
                      </div>
                    </div>
                  )}
                  {activeContextPolicy && (
                    <div className="p-3 text-xs border rounded-lg bg-white">
                      <div className="mb-2 font-medium text-gray-900">Step Context Policy</div>
                      <div className="space-y-1 text-gray-600">
                        <div>max prompt: {String(activeContextPolicy.max_prompt_chars ?? '-')}</div>
                        <div>compact after: {String(activeContextPolicy.compact_after_chars ?? '-')}</div>
                        <div>artifact chars: {String(activeContextPolicy.max_artifact_body_chars ?? '-')}</div>
                        <div>handoff chars: {String(activeContextPolicy.max_handoff_chars ?? '-')}</div>
                        <div>stale after: {String(activeContextPolicy.stale_after_minutes ?? '-')} min</div>
                      </div>
                    </div>
                  )}
                  {latestContextCompaction && (
                    <div className="p-3 text-xs border rounded-lg bg-white">
                      <div className="mb-2 font-medium text-gray-900">Latest Compaction</div>
                      <div className="space-y-1 text-gray-600">
                        <div>raw chars: {String(contextCompactionPayload?.raw_chars ?? '-')}</div>
                        <div>final chars: {String(contextCompactionPayload?.final_chars ?? '-')}</div>
                        <div>sections: {String(contextCompactionPayload?.section_count ?? '-')}</div>
                        <div>compacted: {String(contextCompactionPayload?.compacted ?? true)}</div>
                      </div>
                    </div>
                  )}
                  {latestPromptCacheProfile && (
                    <div className="p-3 text-xs border rounded-lg bg-white">
                      <div className="mb-2 font-medium text-gray-900">Prompt Cache</div>
                      <div className="space-y-1 text-gray-600">
                        <div>cache key: {String(promptCachePayload?.cache_key ?? '-')}</div>
                        <div>applied: {String(promptCachePayload?.cache_applied ?? false)}</div>
                        <div>saved chars: {String(promptCachePayload?.cached_chars_saved ?? '-')}</div>
                        <div>deduped bindings: {String(promptCachePayload?.deduped_binding_count ?? '-')}</div>
                      </div>
                    </div>
                  )}
                </div>
                {latestStaleMemoryVerification && (
                  <div className="mt-3 p-3 text-xs border rounded-lg bg-white">
                    <div className="mb-2 font-medium text-gray-900">Stale Memory Verification</div>
                    <div className="text-gray-600">
                      status: {String(staleMemoryPayload?.verification_status ?? 'unknown')}
                    </div>
                    {Array.isArray(staleMemoryPayload?.stale_findings) && staleMemoryPayload.stale_findings.length > 0 && (
                      <div className="mt-2 space-y-1 text-amber-700">
                        {staleMemoryPayload.stale_findings.map((item, idx) => (
                          <div key={`${String(item)}-${idx}`}>{String(item)}</div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </section>
            )}

            {(latestRuntimeLifecycle || latestRuntimeTelemetry) && (
              <section className="p-4 border rounded-xl bg-slate-50" data-testid="runtime-lifecycle-panel">
                <div className="mb-3 text-sm font-semibold">Runtime Lifecycle</div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {latestRuntimeLifecycle && (
                    <div className="p-3 text-xs border rounded-lg bg-white">
                      <div className="mb-2 font-medium text-gray-900">Latest Lifecycle Snapshot</div>
                      <div className="space-y-1 text-gray-600">
                        <div>phase: {String(runtimeLifecyclePayload?.phase ?? '-')}</div>
                        <div>task status: {String(runtimeLifecyclePayload?.task_status ?? '-')}</div>
                        <div>step status: {String(runtimeLifecyclePayload?.step_status ?? '-')}</div>
                        <div>backend: {String(runtimeLifecyclePayload?.runtime_backend ?? '-')}</div>
                        <div>session: {String(runtimeLifecyclePayload?.runtime_session_id ?? '-')}</div>
                        <div>selected agent: {String(runtimeLifecyclePayload?.runtime_selected_agent ?? '-')}</div>
                      </div>
                    </div>
                  )}
                  {latestRuntimeTelemetry && (
                    <div className="p-3 text-xs border rounded-lg bg-white">
                      <div className="mb-2 font-medium text-gray-900">Telemetry Summary</div>
                      <div className="space-y-1 text-gray-600">
                        <div>cursor: {String(runtimeTelemetryPayload?.runtime_event_cursor ?? '-')}</div>
                        <div>transcript: {String(runtimeTelemetryPayload?.transcript_available ?? false)}</div>
                        <div>
                          subagents:
                          {' '}
                          selected {String((runtimeTelemetryPayload?.subagent_counts as Record<string, unknown> | undefined)?.selected ?? 0)}
                          {' / '}
                          started {String((runtimeTelemetryPayload?.subagent_counts as Record<string, unknown> | undefined)?.started ?? 0)}
                          {' / '}
                          completed {String((runtimeTelemetryPayload?.subagent_counts as Record<string, unknown> | undefined)?.completed ?? 0)}
                          {' / '}
                          failed {String((runtimeTelemetryPayload?.subagent_counts as Record<string, unknown> | undefined)?.failed ?? 0)}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
                {Array.isArray(runtimeTelemetryPayload?.recent_events) && runtimeTelemetryPayload.recent_events.length > 0 && (
                  <div className="mt-3 p-3 text-xs border rounded-lg bg-white">
                    <div className="mb-2 font-medium text-gray-900">Recent Runtime Events</div>
                    <div className="space-y-1 text-gray-600">
                      {runtimeTelemetryPayload.recent_events.map((item, idx) => {
                        const event = item as Record<string, unknown>
                        return (
                          <div key={`${String(event.event_type)}-${idx}`}>
                            <span className="font-medium text-gray-800">{String(event.event_type || '-')}</span>
                            {event.detail ? ` · ${String(event.detail)}` : ''}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </section>
            )}

            <section className="p-4 border rounded-xl" data-testid="acceptance-checks-panel">
              <div className="mb-3 text-sm font-semibold">Acceptance Checks</div>
              <div className="space-y-2">
                {detail.acceptance_checks.map((check) => (
                  <div key={check.id} className="p-3 text-xs rounded-lg bg-gray-50">
                    <div className="font-medium text-gray-900">{check.check_key}</div>
                    <div className="mt-1 text-gray-600">{check.description}</div>
                    <div className="flex items-center justify-between mt-2 text-gray-500">
                      <span>{check.owner_role} · {check.check_type}</span>
                      <span>{check.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {detail.incidents.length > 0 && (
              <section className="p-4 border rounded-xl bg-rose-50" data-testid="incident-panel">
                <div className="mb-3 text-sm font-semibold">Recovery Narrative & Incidents</div>
                <div className="space-y-3">
                  {detail.incidents.map((incident) => (
                    <div key={incident.incident_key} className="rounded-lg border border-rose-100 bg-white p-3 text-xs">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="font-medium text-gray-900">{incident.title}</div>
                        <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] text-rose-700">
                          {incident.severity}
                        </span>
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">
                          {incident.incident_family} / {incident.incident_code}
                        </span>
                      </div>
                      <div className="mt-2 text-gray-700">{incident.summary}</div>
                      <div className="mt-2 text-gray-500">
                        recovery: {incident.recovery_status} · source: {incident.source_artifact_type} #{incident.source_artifact_id}
                      </div>
                      <div className="mt-2 text-rose-700">
                        Recommended action: {incident.recommended_action}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {bugReports.length > 0 && (
              <section className="p-4 border rounded-xl" data-testid="bug-reports-panel">
                <div className="mb-3 text-sm font-semibold">Recent Bug Reports</div>
                <div className="space-y-2">
                  {bugReports.map((artifact) => {
                    const payload = parsePayload(artifact.machine_readable_payload)
                    const failedChecks = Array.isArray(payload?.failed_checks) ? payload.failed_checks : []
                    return (
                      <div key={artifact.id} className="p-3 text-xs rounded-lg bg-rose-50 border border-rose-100">
                        <div className="font-medium text-gray-900">{artifact.content_summary || `Bug #${artifact.id}`}</div>
                        <div className="mt-1 text-gray-600">
                          {typeof payload?.step_type === 'string' ? `${payload.step_type} · ` : ''}
                          {typeof payload?.verification_type === 'string' ? `${payload.verification_type} verification` : 'verification failure'}
                        </div>
                        {failedChecks.length > 0 && (
                          <div className="mt-2 text-rose-700">
                            Failed checks: {failedChecks.map((item) => String((item as Record<string, unknown>).check_key || '-')).join(', ')}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </section>
            )}

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
