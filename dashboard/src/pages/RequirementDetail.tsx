import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { AcceptanceContract, AgentRequirementDetail, ExecutionPlan, Project, api } from '../api'
import { FieldLabel, LoadingPane, SectionFrame, StateBadge, useToast } from '../components/workbench'

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  planning: '规划中',
  awaiting_approval: '待审批',
  ready: '待执行',
  executing: '执行中',
  delivering: '交付中',
  ready_for_merge: '待合并',
  awaiting_operator: '待人工处理',
  completed: '已完成',
  failed: '失败',
  running: '执行中',
  blocked: '阻塞',
  needs_revision: '需修订',
  delivery_ready: '待发布',
  done: '已完成',
  cancelled: '已取消',
  deleted: '已删除',
}

function statusTone(status: string) {
  if (status === 'completed' || status === 'done' || status === 'ready_for_merge' || status === 'delivery_ready') return 'delivered'
  if (status === 'executing' || status === 'running' || status === 'delivering') return 'running'
  if (status === 'awaiting_operator' || status === 'blocked' || status === 'needs_revision' || status === 'cancelled') return 'blocked'
  if (status === 'failed') return 'blocked'
  if (status === 'ready' || status === 'awaiting_approval') return 'ready'
  return 'muted'
}

function assetsTone(status: string) {
  if (status === 'ready') return 'ready'
  if (status === 'failed') return 'blocked'
  return 'running'
}

const APPROVAL_STATUS_LABEL: Record<string, string> = {
  pending_manual_approval: '待人工审批',
  pending_approval: '待人工审批',
  pending: '待人工审批',
  approved: '已批准',
  waived: '已豁免',
  not_required: '已豁免',
  rejected: '已拒绝',
}

const FINAL_DECISION_SOURCE_LABEL: Record<string, string> = {
  human_required_by_policy: '结果来源：策略要求人工审批',
  auto_approved: '结果来源：系统自动批准',
  agent_approved: '结果来源：审批代理批准',
  waived: '结果来源：合同豁免',
  manual_decision: '结果来源：人工审批结论',
  manual_review_required: '结果来源：等待人工审批',
}

const RECOMMENDATION_LABEL: Record<string, string> = {
  approve: '批准',
  revise: '修订',
  route_to_human: '转人工',
  waive: '豁免',
}

const RECOMMENDATION_SOURCE_LABEL: Record<string, string> = {
  deterministic_policy: 'deterministic policy',
  approval_agent: 'approval agent',
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function approvalStatusLabel(detail: AgentRequirementDetail) {
  const state = detail.approval_decision?.state || detail.approval.approval_status
  return APPROVAL_STATUS_LABEL[state] || APPROVAL_STATUS_LABEL[detail.approval.approval_decision] || state
}

const LIFECYCLE_STEPS = [
  { key: 'created', label: '创建' },
  { key: 'planning', label: '规划' },
  { key: 'approval', label: '审批' },
  { key: 'ready', label: '待执行' },
  { key: 'execution', label: '执行' },
  { key: 'delivery', label: '交付' },
  { key: 'merge', label: '待合并' },
  { key: 'done', label: '完成' },
]

const LIFECYCLE_STATE_INDEX: Record<string, number> = {
  draft: 0,
  planning: 1,
  awaiting_approval: 2,
  ready: 3,
  executing: 4,
  running: 4,
  delivering: 5,
  delivery_ready: 5,
  ready_for_merge: 6,
  completed: 7,
  done: 7,
}

function lifecycleIndex(detail: AgentRequirementDetail, state: string) {
  if (state in LIFECYCLE_STATE_INDEX) return LIFECYCLE_STATE_INDEX[state]
  if (state === 'failed' || state === 'cancelled' || state === 'awaiting_operator') {
    if (detail.latest_release_id || detail.latest_release) return 5
    if (detail.latest_execution_id || detail.requirement.latest_execution_run_id) return 4
    if ((detail.approval_decision?.state || detail.approval.approval_status) === 'pending') return 2
    return 3
  }
  return 0
}

function lifecycleDescription(detail: AgentRequirementDetail, state: string) {
  const releaseState = detail.latest_release?.state || detail.latest_release?.status || ''
  if (state === 'failed') return detail.failure_reason ? `自动主链已终止：${detail.failure_reason}` : '自动主链已终止，需要人工介入'
  if (state === 'cancelled') return '需求已取消，不会继续自动推进'
  if (state === 'awaiting_operator') return detail.attention_reason ? `需要人工处理：${detail.attention_reason}` : '需要人工处理后才能继续'
  if (state === 'planning' || detail.assets_status === 'pending') return '验收标准与执行计划正在生成'
  if (state === 'awaiting_approval') return '等待审批结果，未通过前不会执行'
  if (state === 'ready') return '需求已就绪，可以启动执行'
  if (state === 'executing' || state === 'running') return 'agent 正在执行当前 attempt'
  if (state === 'delivering' || state === 'delivery_ready') {
    if (releaseState === 'repairing') return 'delivery repair 自动修复中'
    return '验证已过，正在 push / open PR / delivery repair'
  }
  if (state === 'ready_for_merge') return 'PR 已打开，等待最终 merge'
  if (state === 'completed' || state === 'done') return '需求生命周期已完成'
  return '需求已进入生命周期主线'
}

function lifecycleStepTone(stepStatus: 'done' | 'current' | 'upcoming' | 'terminal') {
  if (stepStatus === 'done') return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  if (stepStatus === 'terminal') return 'border-rose-200 bg-rose-50 text-rose-700'
  if (stepStatus === 'current') return 'border-blue-200 bg-blue-50 text-blue-700'
  return 'border-[color:var(--ops-stroke-soft)] bg-slate-50 text-[color:var(--ops-text-caption)]'
}

function lifecycleDotTone(stepStatus: 'done' | 'current' | 'upcoming' | 'terminal') {
  if (stepStatus === 'done') return 'bg-emerald-500'
  if (stepStatus === 'terminal') return 'bg-rose-500'
  if (stepStatus === 'current') return 'bg-blue-500'
  return 'bg-slate-300'
}

function RequirementLifecycleStepper({ detail }: Readonly<{ detail: AgentRequirementDetail }>) {
  const state = detail.requirement.state || detail.state || detail.requirement.status || 'draft'
  const currentIndex = lifecycleIndex(detail, state)
  const isTerminal = state === 'failed' || state === 'cancelled'
  const description = lifecycleDescription(detail, state)
  const currentStep = LIFECYCLE_STEPS[currentIndex] || LIFECYCLE_STEPS[0]
  return (
    <div data-testid="requirement-lifecycle" className="mb-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/75 px-4 py-4">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <StateBadge tone={isTerminal ? 'blocked' : statusTone(state)}>{isTerminal ? (state === 'failed' ? '需求失败' : '需求已取消') : `当前：${currentStep.label}`}</StateBadge>
        <span data-testid="requirement-lifecycle-current" className="text-sm text-[color:var(--ops-text-muted)]">
          {description}
        </span>
      </div>
      <div className="overflow-x-auto pb-1">
        <div className="flex min-w-max items-stretch gap-2">
          {LIFECYCLE_STEPS.map((step, index) => {
            const stepStatus = isTerminal && index === currentIndex ? 'terminal' : index < currentIndex ? 'done' : index === currentIndex ? 'current' : 'upcoming'
            return (
              <div key={step.key} className="flex items-center">
                <div
                  data-testid={`requirement-lifecycle-step-${step.key}`}
                  data-state={stepStatus}
                  className={`min-w-[112px] rounded-2xl border px-3 py-3 ${lifecycleStepTone(stepStatus)}`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${lifecycleDotTone(stepStatus)}`} />
                    <span className="text-xs font-semibold">{step.label}</span>
                  </div>
                  <div className="mt-1 text-[10px] uppercase tracking-[0.16em] opacity-70">{stepStatus}</div>
                </div>
                {index < LIFECYCLE_STEPS.length - 1 ? <div className="mx-2 h-px w-7 self-center bg-[color:var(--ops-stroke-soft)]" /> : null}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function Markdown({ value }: Readonly<{ value: string }>) {
  if (!value.trim()) return <div className="text-sm text-slate-400">暂无内容</div>
  return (
    <div className="prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2">
      <ReactMarkdown>{value}</ReactMarkdown>
    </div>
  )
}

function fallbackRequirementAllowedActions(detail: AgentRequirementDetail): string[] {
  const requirement = detail.requirement
  const actions = new Set<string>(['view'])
  const state = requirement.state || requirement.status
  if (detail.latest_execution_id != null) actions.add('view_execution')
  if (detail.latest_release_id != null) actions.add('view_release')
  if (state === 'draft' || state === 'planning' || state === 'ready' || state === 'awaiting_operator') {
    actions.add('edit')
  }
  if (detail.assets_status === 'ready' && (state === 'draft' || state === 'ready')) {
    actions.add('submit')
  }
  if (detail.assets_status === 'failed') {
    actions.add('regenerate_assets')
  }
  if ((detail.approval_decision?.state || detail.approval.approval_status) === 'pending') {
    actions.add('approve')
    actions.add('reject')
  }
  if (requirement.latest_execution_run_id == null && ['draft', 'planning', 'awaiting_approval'].includes(state)) {
    actions.add('delete')
  }
  return [...actions]
}

export default function RequirementDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const toast = useToast()
  const requirementId = Number(id)
  const [detail, setDetail] = useState<AgentRequirementDetail | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [form, setForm] = useState({
    title: '',
    description_markdown: '',
    acceptance_criteria_markdown: '',
    execution_plan_markdown: '',
    priority: 'normal',
    project_id: null as number | null,
    target_project_path_override: '',
  })

  const acceptanceMarkdown = (contract: AcceptanceContract, fallback: string) =>
    String(contract.markdown || '').trim() || fallback
  const planMarkdown = (plan: ExecutionPlan) => String(plan.summary_markdown || '').trim()

  const load = async () => {
    setLoading(true)
    try {
      const [data, projectRows] = await Promise.all([api.getRequirement(requirementId), api.getProjects()])
      setDetail(data)
      setProjects(projectRows)
      setForm({
        title: data.requirement.title,
        description_markdown: data.requirement.description_markdown,
        acceptance_criteria_markdown: data.requirement.acceptance_criteria_markdown,
        execution_plan_markdown: planMarkdown(data.execution_plan),
        priority: data.requirement.priority,
        project_id: data.requirement.project_id,
        target_project_path_override: data.requirement.target_project_path_override || '',
      })
      setShowAdvanced(Boolean(data.requirement.target_project_path_override))
      setIsEditing(false)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [requirementId])

  if (loading || !detail) {
    return <LoadingPane>正在加载需求…</LoadingPane>
  }

  const requirement = detail.requirement
  const approval = detail.approval
  const requirementAllowedActions = requirement.allowed_actions ?? fallbackRequirementAllowedActions(detail)
  const detailAllowedActions = detail.allowed_actions ?? requirementAllowedActions
  const canEdit = requirementAllowedActions.includes('edit')
  const finalApprovalState = detail.approval_decision?.state || approval.approval_status
  const showApprovalNotice =
    finalApprovalState === 'pending' ||
    finalApprovalState === 'rejected' ||
    Boolean(approval.approval_recommendation || approval.approval_reason)
  const currentProject = detail.project
  const latestRelease = detail.latest_release
  const assetsReady = detail.assets_status === 'ready'
  const requirementState = requirement.state || detail.state || requirement.status

  return (
    <div className="space-y-[var(--ops-section-gap)]" data-testid="agent-first-requirement-detail">
      <SectionFrame
        eyebrow="Requirement"
        title={requirement.title}
        actions={
          <div className="flex flex-wrap gap-2">
            {currentProject ? (
              <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/projects/${currentProject.id}`)}>
                查看项目
              </button>
            ) : null}
            {canEdit && !isEditing ? (
              <button
                data-testid="toggle-edit-requirement-btn"
                className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm"
                onClick={() => setIsEditing(true)}
              >
                编辑
              </button>
            ) : null}
            {isEditing ? (
              <>
                <button
                  className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm"
                  onClick={() => {
                      setForm({
                        title: requirement.title,
                        description_markdown: requirement.description_markdown,
                        acceptance_criteria_markdown: requirement.acceptance_criteria_markdown,
                        execution_plan_markdown: planMarkdown(detail.execution_plan),
                        priority: requirement.priority,
                        project_id: requirement.project_id,
                        target_project_path_override: requirement.target_project_path_override || '',
                    })
                    setShowAdvanced(Boolean(requirement.target_project_path_override))
                    setIsEditing(false)
                  }}
                >
                  取消
                </button>
                <button
                  data-testid="save-requirement-btn"
                  className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm text-white disabled:opacity-50"
                  disabled={saving || !form.project_id}
                  onClick={async () => {
                    setSaving(true)
                    try {
                      await api.updateRequirement(requirement.id, {
                        title: form.title,
                        description_markdown: form.description_markdown,
                        acceptance_criteria_markdown: form.acceptance_criteria_markdown,
                        execution_plan: { ...detail.execution_plan, summary_markdown: form.execution_plan_markdown },
                        priority: form.priority,
                        project_id: form.project_id ?? undefined,
                        target_project_path_override: form.target_project_path_override || undefined,
                      })
                      toast.success('需求已更新')
                      await load()
                    } catch {
                      toast.error('保存失败，请重试')
                    } finally {
                      setSaving(false)
                    }
                  }}
                >
                  保存
                </button>
              </>
            ) : null}
            {!isEditing && requirementAllowedActions.includes('submit') ? (
              <button
                className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2 text-sm text-white disabled:opacity-50"
                disabled={!assetsReady || !requirementAllowedActions.includes('submit')}
                onClick={async () => {
                  try {
                    const next = await api.submitRequirement(requirement.id)
                    setDetail(next)
                    if (next.approval.auto_started && next.approval.execution_run_id) {
                      navigate(`/executions/${next.approval.execution_run_id}`)
                    }
                  } catch (error) {
                    const message = error instanceof Error ? error.message : '提交失败，请重试'
                    toast.error(message)
                  }
                }}
              >
                {detail.assets_status === 'pending' ? '生成计划中…' : detail.assets_status === 'failed' ? '计划生成失败' : '提交'}
              </button>
            ) : null}
            {!isEditing && detail.assets_status === 'failed' && requirementAllowedActions.includes('regenerate_assets') ? (
              <button
                className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] px-4 py-2 text-sm text-[color:var(--ops-state-blocked-text)]"
                onClick={async () => {
                  try {
                    const next = await api.regenerateRequirementAssets(requirement.id)
                    setDetail(next)
                    toast.success('已重新开始生成验收标准与执行计划')
                  } catch (error) {
                    const message = error instanceof Error ? error.message : '重新生成失败，请重试'
                    toast.error(message)
                  }
                }}
              >
                重新生成计划
              </button>
            ) : null}
            {!isEditing && requirementAllowedActions.includes('approve') && (detail.approval_decision?.state || approval.approval_status) === 'pending' ? (
              <>
                <button
                  className="rounded-2xl bg-[color:var(--ops-state-running-text)] px-4 py-2 text-sm text-white"
                  onClick={async () => {
                    const next = await api.approveRequirement(requirement.id, {
                      reviewer: 'operator',
                      comment: approval.approval_recommendation_reason || approval.approval_reason || 'Approve and auto-start execution',
                    })
                    setDetail(next)
                    if (next.approval.execution_run_id) {
                      navigate(`/executions/${next.approval.execution_run_id}`)
                    }
                  }}
                >
                  批准并启动执行
                </button>
                <button
                  className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] px-4 py-2 text-sm text-[color:var(--ops-state-blocked-text)]"
                  onClick={async () => {
                    const next = await api.rejectRequirement(requirement.id, { reviewer: 'operator', comment: 'Need revision before execution can start' })
                    setDetail(next)
                  }}
                >
                  驳回
                </button>
              </>
            ) : null}
            {!isEditing && approval.pending_execution_start && detail.latest_execution_id && detailAllowedActions.includes('view_execution') ? (
              <button
                className="rounded-2xl bg-[color:var(--ops-state-running-text)] px-4 py-2 text-sm text-white"
                onClick={async () => {
                  const executionId = detail.latest_execution_id
                  if (!executionId) return
                  await api.startExecution(executionId)
                  navigate(`/executions/${executionId}`)
                }}
              >
                恢复启动执行
              </button>
            ) : null}
            {!isEditing && detail.latest_execution_id ? (
              <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/executions/${detail.latest_execution_id}`)}>
                查看执行
              </button>
            ) : null}
            {!isEditing && detail.latest_release_id ? (
              <button className="rounded-2xl border border-[color:var(--ops-state-ready-border)] px-4 py-2 text-sm text-[color:var(--ops-state-ready-text)]" onClick={() => navigate(`/releases/${requirement.id}`)}>
                查看发布
              </button>
            ) : null}
          </div>
        }
      >
        {!isEditing ? <RequirementLifecycleStepper detail={detail} /> : null}

        {showApprovalNotice ? (
          <div
            data-testid="requirement-approval-notice"
            className="mb-5 rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-blocked-text)]"
          >
            <div className="flex flex-wrap items-center gap-2">
              <StateBadge tone={finalApprovalState === 'approved' || finalApprovalState === 'waived' ? 'ready' : 'blocked'}>
                {approvalStatusLabel(detail)}
              </StateBadge>
              {approval.required_approver_roles.length ? <span>需要角色：{approval.required_approver_roles.join(' / ')}</span> : null}
            </div>
            {approval.approval_reason ? <div className="mt-2">审批状态原因：{approval.approval_reason}</div> : null}
            {(approval.final_decision_source || detail.approval_decision?.source) ? (
              <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">
                {FINAL_DECISION_SOURCE_LABEL[approval.final_decision_source || detail.approval_decision?.source || ''] ||
                  `结果来源：${approval.final_decision_source || detail.approval_decision?.source}`}
              </div>
            ) : null}
            {approval.approval_recommendation ? (
              <div className="mt-3 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/70 px-3 py-2 text-xs text-[color:var(--ops-text-caption)]">
                <div>
                  系统推荐：{RECOMMENDATION_LABEL[approval.approval_recommendation] || approval.approval_recommendation}
                  {approval.approval_confidence != null ? ` · 置信度 ${approval.approval_confidence}` : ''}
                </div>
                {approval.recommendation_source ? (
                  <div className="mt-1">
                    推荐来源：{RECOMMENDATION_SOURCE_LABEL[approval.recommendation_source] || approval.recommendation_source}
                  </div>
                ) : null}
                {approval.approval_recommendation_reason ? <div className="mt-1">推荐理由：{approval.approval_recommendation_reason}</div> : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {!isEditing && (detail.resolution_path || detail.followup_requirement_id) ? (
          <div className="mb-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-50/90 px-4 py-3 text-sm text-[color:var(--ops-text-body)]">
            <div className="flex flex-wrap items-center gap-2">
              <StateBadge tone="muted">{detail.resolution_path || 'resolution'}</StateBadge>
              {detail.followup_requirement_id ? <span>已转派修复需求 #{detail.followup_requirement_id}</span> : null}
            </div>
          </div>
        ) : null}

        {!isEditing && latestRelease?.status === 'release_blocked' ? (
          <div className="mb-5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <div className="flex flex-wrap items-center gap-2">
              <StateBadge tone="blocked">{latestRelease.delivery_blocker_type || 'release_blocked'}</StateBadge>
              {latestRelease.failed_gate_name ? <span>gate: {latestRelease.failed_gate_name}</span> : null}
              <span>next action: {latestRelease.next_action || '-'}</span>
              <span>repairable: {latestRelease.repairable ? 'yes' : 'no'}</span>
              <span>repair attempts: {requirement.delivery_repair_attempt_count ?? 0}</span>
            </div>
            {latestRelease.delivery_failure_excerpt ? <div className="mt-2">{latestRelease.delivery_failure_excerpt}</div> : null}
          </div>
        ) : null}

        {!isEditing && detail.failure_reason ? (
          <div className="mb-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            <div className="flex flex-wrap items-center gap-2">
              <StateBadge tone="blocked">主任务失败</StateBadge>
              <span>failure reason: {detail.failure_reason}</span>
            </div>
          </div>
        ) : null}

        {!isEditing && detail.assets_status !== 'ready' ? (
          <div className="mb-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-50/90 px-4 py-3 text-sm text-[color:var(--ops-text-muted)]">
            <div className="flex flex-wrap items-center gap-2">
              <StateBadge tone={assetsTone(detail.assets_status)}>
                {detail.assets_status === 'failed' ? '计划生成失败' : '正在生成计划'}
              </StateBadge>
              <span>
                {detail.assets_status === 'failed'
                  ? detail.assets_error_message || '验收标准与执行计划生成失败，请重新生成。'
                  : '验收标准与执行计划正在生成，完成前不能提交。'}
              </span>
            </div>
          </div>
        ) : null}

        {isEditing ? (
          <div className="grid gap-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <FieldLabel>标题</FieldLabel>
                <input
                  data-testid="edit-requirement-title"
                  className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
                  value={form.title}
                  onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                />
              </div>
              <div>
                <FieldLabel>所属项目</FieldLabel>
                <select
                  data-testid="edit-requirement-project"
                  className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
                  value={form.project_id ?? ''}
                  onChange={(event) => setForm((current) => ({ ...current, project_id: event.target.value ? Number(event.target.value) : null }))}
                >
                  <option value="">选择项目</option>
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.display_name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="md:max-w-[220px]">
              <FieldLabel>优先级</FieldLabel>
              <select
                data-testid="edit-requirement-priority"
                className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
                value={form.priority}
                onChange={(event) => setForm((current) => ({ ...current, priority: event.target.value }))}
              >
                <option value="low">low</option>
                <option value="normal">normal</option>
                <option value="high">high</option>
              </select>
            </div>
            <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-50/70 px-4 py-4">
              <button type="button" className="text-sm font-medium text-[color:var(--ops-text-title)]" onClick={() => setShowAdvanced((current) => !current)}>
                {showAdvanced ? '隐藏高级设置' : '显示高级设置'}
              </button>
              {showAdvanced ? (
                <div className="mt-4">
                  <FieldLabel>路径覆盖（可选）</FieldLabel>
                  <input
                    data-testid="edit-requirement-path-override"
                    className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
                    value={form.target_project_path_override}
                    onChange={(event) => setForm((current) => ({ ...current, target_project_path_override: event.target.value }))}
                  />
                </div>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <StateBadge tone={statusTone(requirementState)}>{STATUS_LABEL[requirementState] || requirementState}</StateBadge>
              {detail.phase && detail.phase !== requirementState ? <StateBadge tone="muted">{detail.phase}</StateBadge> : null}
              {detail.recovery_status ? <StateBadge tone="blocked">恢复: {detail.recovery_status}</StateBadge> : null}
              {detail.recovery_scope ? <StateBadge tone="muted">仅影响当前需求</StateBadge> : null}
              <StateBadge tone="muted">{requirement.priority}</StateBadge>
              {(requirement.project?.project_display_name || requirement.project_display_name) ? <StateBadge tone="muted">{requirement.project?.project_display_name || requirement.project_display_name}</StateBadge> : null}
              {requirement.target_project_path_override ? <StateBadge tone="muted">路径已覆盖</StateBadge> : null}
              {latestRelease?.branch_name ? <StateBadge tone="ready">{latestRelease.branch_name}</StateBadge> : null}
            </div>
            {(requirement.project?.project_display_name || requirement.project_display_name || requirement.project?.project_key || requirement.project_key || requirement.project?.target_project_path || requirement.target_project_path) ? (
              <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-[color:var(--ops-text-muted)]">
                <div>项目：{requirement.project?.project_display_name || requirement.project_display_name || '-'}</div>
                <div>project key：{requirement.project?.project_key || requirement.project_key || '-'}</div>
                <div>目标路径：{requirement.project?.target_project_path || requirement.target_project_path || '-'}</div>
                {requirement.target_project_path_override ? <div>路径覆盖：{requirement.target_project_path_override}</div> : null}
              </div>
            ) : null}
            {latestRelease ? (
              <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-[color:var(--ops-text-muted)]">
                <div>交付状态：{latestRelease.state || latestRelease.status}</div>
                <div>repair 次数：{requirement.delivery_repair_attempt_count ?? 0}</div>
                <div>基线分支：{latestRelease.base_branch || '-'}</div>
                <div>PR：{latestRelease.pr_url ? <a className="text-blue-600 hover:underline" href={latestRelease.pr_url} target="_blank" rel="noreferrer">查看 PR</a> : '-'}</div>
                {detail.recovery_deadline_at ? <div>恢复截止：{formatTime(detail.recovery_deadline_at)}</div> : null}
                {detail.recovery_timeout_status ? <div>恢复状态：{detail.recovery_timeout_status}</div> : null}
              </div>
            ) : null}
            {requirement.requirement_plan_summary ? (
              <div className="text-sm text-[color:var(--ops-text-muted)]">主计划摘要：{requirement.requirement_plan_summary}</div>
            ) : null}
            {detail.recovery_timeout_status === 'timed_out' ? (
              <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">恢复超时，需人工介入；不会阻塞其他需求执行。</div>
            ) : null}
          </div>
        )}
      </SectionFrame>

      <SectionFrame eyebrow="Intent" title="需求意图">
        {isEditing ? (
          <textarea
            data-testid="edit-requirement-description"
            className="min-h-[240px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
            value={form.description_markdown}
            onChange={(event) => setForm((current) => ({ ...current, description_markdown: event.target.value }))}
          />
        ) : (
          <Markdown value={requirement.description_markdown} />
        )}
      </SectionFrame>

      {detail.attachments.length ? (
        <SectionFrame eyebrow="Attachments" title="附件">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid="requirement-attachments">
            {detail.attachments.map((attachment) => {
              const href = `/api/requirements/${requirement.id}/attachments/${attachment.id}`
              return (
                <a
                  key={attachment.id}
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  className="overflow-hidden rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-50/80"
                >
                  {attachment.attachment_kind === 'image' ? (
                    <img src={href} alt={attachment.file_name} className="h-44 w-full object-cover" />
                  ) : null}
                  <div className="space-y-2 px-4 py-4">
                    <div className="text-sm font-medium text-[color:var(--ops-text-title)]">{attachment.file_name}</div>
                    <div className="text-xs text-[color:var(--ops-text-caption)]">
                      {attachment.attachment_kind === 'image' ? '图片' : '文件'} · {attachment.content_type} · {Math.max(1, Math.round(attachment.size_bytes / 1024))} KB
                    </div>
                    <div className="text-xs text-[color:var(--ops-text-caption)]">{attachment.stored_path}</div>
                  </div>
                </a>
              )
            })}
          </div>
        </SectionFrame>
      ) : null}

      <SectionFrame eyebrow="Acceptance" title="验收标准">
        {!isEditing && detail.acceptance_contract.done_criteria?.length ? (
          <div className="mb-5 grid gap-4 md:grid-cols-2">
            <div>
              <div className="mb-2 text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Done Criteria</div>
              <ul className="space-y-2 text-sm text-[color:var(--ops-text-body)]">
                {detail.acceptance_contract.done_criteria.map((item) => (
                  <li key={item}>• {item}</li>
                ))}
              </ul>
            </div>
            <div>
              <div className="mb-2 text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Verification Checks</div>
              <ul className="space-y-2 text-sm text-[color:var(--ops-text-body)]">
                {(detail.acceptance_contract.verification_checks || []).map((item) => (
                  <li key={`${item.label}-${item.command || 'manual'}`}>
                    • {item.label}
                    {item.command ? <span className="text-[color:var(--ops-text-caption)]"> (`{item.command}`)</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : null}
        {isEditing ? (
          <textarea
            data-testid="edit-requirement-acceptance"
            className="min-h-[180px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
            value={form.acceptance_criteria_markdown}
            onChange={(event) => setForm((current) => ({ ...current, acceptance_criteria_markdown: event.target.value }))}
          />
        ) : (
          <Markdown value={acceptanceMarkdown(detail.acceptance_contract, requirement.acceptance_criteria_markdown)} />
        )}
      </SectionFrame>

      <SectionFrame eyebrow="Plan" title="执行计划">
        {isEditing ? (
          <textarea
            data-testid="edit-requirement-plan"
            className="min-h-[220px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
            value={form.execution_plan_markdown}
            onChange={(event) => setForm((current) => ({ ...current, execution_plan_markdown: event.target.value }))}
          />
        ) : (
          <Markdown value={planMarkdown(detail.execution_plan)} />
        )}
      </SectionFrame>
    </div>
  )
}
