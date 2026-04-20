import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { AcceptanceContract, AgentRequirementDetail, ExecutionPlan, Project, api } from '../api'
import { ConfirmDialog, FieldLabel, LoadingPane, SectionFrame, StateBadge, useToast } from '../components/workbench'

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  planning: '规划中',
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
  cancelled: '已关闭',
  deleted: '已删除',
}

function statusTone(status: string) {
  if (status === 'completed' || status === 'done' || status === 'ready_for_merge' || status === 'delivery_ready') return 'delivered'
  if (status === 'executing' || status === 'running' || status === 'delivering') return 'running'
  if (status === 'awaiting_operator' || status === 'blocked' || status === 'needs_revision' || status === 'cancelled') return 'blocked'
  if (status === 'failed') return 'blocked'
  if (status === 'ready') return 'ready'
  return 'muted'
}

function assetsTone(status: string) {
  if (status === 'ready') return 'ready'
  if (status === 'failed') return 'blocked'
  return 'running'
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function extractWorkspaceBranch(text: string | null | undefined) {
  const value = String(text || '')
  const match = value.match(/dirty worktree on `([^`]+)`/i)
  return match?.[1] || null
}

function releaseBlockerText(release: AgentRequirementDetail['latest_release']) {
  if (!release) return ''
  return [
    release.delivery_failure_excerpt,
    release.notes,
    release.delivery_failure_raw_output,
  ]
    .map((item) => String(item || '').trim())
    .find(Boolean) || ''
}

const LIFECYCLE_STEPS = [
  { key: 'created', label: '创建' },
  { key: 'planning', label: '规划' },
  { key: 'ready', label: '待工作流' },
  { key: 'execution', label: '工作流' },
  { key: 'delivery', label: '交付' },
  { key: 'merge', label: '待合并' },
  { key: 'done', label: '完成' },
]

const LIFECYCLE_STATE_INDEX: Record<string, number> = {
  draft: 0,
  planning: 1,
  ready: 2,
  executing: 3,
  running: 3,
  delivering: 4,
  delivery_ready: 4,
  ready_for_merge: 5,
  completed: 6,
  done: 6,
  cancelled: 2,
  deleted: 2,
}

function lifecycleIndex(detail: AgentRequirementDetail, state: string) {
  if (state in LIFECYCLE_STATE_INDEX) return LIFECYCLE_STATE_INDEX[state]
  if (state === 'failed' || state === 'cancelled' || state === 'deleted' || state === 'awaiting_operator') {
    if (detail.latest_release_id || detail.latest_release) return 5
    if (detail.active_workflow_run_id || detail.requirement.active_workflow_run_id) return 4
    return 2
  }
  return 0
}

function lifecycleDescription(detail: AgentRequirementDetail, state: string) {
  const releaseState = detail.latest_release?.state || detail.latest_release?.status || ''
  if (state === 'failed') return detail.failure_reason ? `自动主链已终止：${detail.failure_reason}` : '自动主链已终止，需要人工介入'
  if (state === 'cancelled') return '需求已关闭，不会继续自动推进'
  if (state === 'deleted') return '需求已删除，不能再提交、启动 workflow 或进入人工门禁'
  if (state === 'awaiting_operator') return detail.attention_reason ? `需要人工处理：${detail.attention_reason}` : '需要人工处理后才能继续'
  if (state === 'planning' || detail.assets_status === 'pending') return '验收标准与状态机计划正在生成'
  if (state === 'ready') return '需求已就绪，可以创建状态机工作流'
  if (state === 'executing' || state === 'running') return '状态机正在驱动 agent atom 和 deterministic atom'
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
  return 'border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] text-[color:var(--ops-text-caption)]'
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
  const isTerminal = state === 'failed' || state === 'cancelled' || state === 'deleted'
  const description = lifecycleDescription(detail, state)
  const currentStep = LIFECYCLE_STEPS[currentIndex] || LIFECYCLE_STEPS[0]
  return (
    <div data-testid="requirement-lifecycle" className="mb-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-4 py-4">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <StateBadge tone={isTerminal ? 'blocked' : statusTone(state)}>{isTerminal ? (state === 'failed' ? '需求失败' : state === 'deleted' ? '需求已删除' : '需求已关闭') : `当前：${currentStep.label}`}</StateBadge>
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
    <div className="prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2 prose-headings:text-[color:var(--ops-text-title)] prose-p:text-[color:var(--ops-text-body)] prose-li:text-[color:var(--ops-text-body)] prose-strong:text-[color:var(--ops-text-title)]">
      <ReactMarkdown>{value}</ReactMarkdown>
    </div>
  )
}

function AcceptanceStepCards({ steps }: Readonly<{ steps: NonNullable<AgentRequirementDetail['acceptance_contract']['execution_acceptance_steps']> }>) {
  if (!steps.length) return null
  return (
    <div className="mb-5 space-y-3" data-testid="requirement-acceptance-steps">
      <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Planner-Generated Execution Steps</div>
      {steps.map((step, index) => (
        <div key={step.step_key || index} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{step.title || step.step_key || `Step ${index + 1}`}</div>
              <div className="mt-1 text-sm leading-6 text-[color:var(--ops-text-muted)]">{step.expected_result || 'No expected result recorded.'}</div>
            </div>
            <span className="rounded-full border border-cyan-300/25 bg-cyan-300/[0.08] px-3 py-1 font-mono text-xs text-cyan-100">{step.step_key || `step_${index + 1}`}</span>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-3 py-2 text-xs text-[color:var(--ops-text-muted)]">
              <div className="mb-1 uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Commands</div>
              {(step.required_commands || []).join('; ') || 'none'}
            </div>
            <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-3 py-2 text-xs text-[color:var(--ops-text-muted)]">
              <div className="mb-1 uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Evidence</div>
              {(step.required_evidence_types || []).join('; ') || 'none'}
            </div>
            <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-3 py-2 text-xs text-[color:var(--ops-text-muted)]">
              <div className="mb-1 uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">DB Lineage</div>
              {(step.required_db_lineage || []).join('; ') || 'none'}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function workflowReadinessCopy(detail: AgentRequirementDetail) {
  const readiness = detail.workflow_readiness
  const activeRunId = readiness?.active_workflow_run_id ?? detail.active_workflow_run_id ?? detail.requirement.active_workflow_run_id
  if (activeRunId) {
    return {
      title: 'Workflow 已生成',
      body: `当前 declarative workflow run #${activeRunId} 已绑定到该需求。`,
      tone: 'ready' as const,
    }
  }
  if (detail.assets_status === 'failed' || readiness?.blocking_reason === 'asset_generation_failed') {
    return {
      title: 'Workflow Assets 生成失败',
      body: detail.assets_error_message || 'Acceptance / plan / workflow blackboard 生成失败，需要重新生成。',
      tone: 'blocked' as const,
    }
  }
  if (detail.assets_status === 'pending' || readiness?.blocking_reason === 'acceptance_or_plan_pending') {
    return {
      title: 'Workflow 未生成',
      body: '当前状态：planning / assets pending。下一步：生成 workflow spec 与初始化 blackboard 后，系统会创建 declarative workflow run。',
      tone: 'running' as const,
    }
  }
  return {
    title: 'Workflow 可启动',
    body: 'Acceptance 与计划已就绪，可以创建 declarative workflow run 并进入状态机。',
    tone: 'ready' as const,
  }
}

function fallbackRequirementAllowedActions(detail: AgentRequirementDetail): string[] {
  const requirement = detail.requirement
  const actions = new Set<string>(['view'])
  const state = requirement.state || requirement.status
  const latestRelease = detail.latest_release
  if (state === 'cancelled' || state === 'deleted') {
    return [...actions]
  }
  if (detail.active_workflow_run_id != null || requirement.active_workflow_run_id != null) actions.add('view_workflow')
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
  if (requirement.active_workflow_run_id == null && ['draft', 'planning'].includes(state)) {
    actions.add('delete')
    actions.add('cancel')
  }
  if (latestRelease?.status === 'branch_prepared') {
    actions.add('open_pr')
  }
  if (
    latestRelease?.status === 'release_blocked' &&
    latestRelease.next_action === 'restart_current' &&
    (latestRelease.delivery_blocker_type === 'workspace_blocked' || latestRelease.blocker_kind === 'workspace_blocked')
  ) {
    actions.add('prepare_release')
    actions.add('open_pr')
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
  const [releaseActionBusy, setReleaseActionBusy] = useState<string | null>(null)
  const [workflowActionBusy, setWorkflowActionBusy] = useState<string | null>(null)
  const [lifecycleActionBusy, setLifecycleActionBusy] = useState<string | null>(null)
  const [confirmLifecycleAction, setConfirmLifecycleAction] = useState<'cancel' | 'delete' | null>(null)
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

  const runReleaseAction = async (key: string, action: () => Promise<unknown>, successMessage: string) => {
    setReleaseActionBusy(key)
    try {
      await action()
      toast.success(successMessage)
      await load()
    } catch (error) {
      const message = error instanceof Error ? error.message : '发布动作失败，请重试'
      toast.error(message)
    } finally {
      setReleaseActionBusy(null)
    }
  }

  const runWorkflowAction = async (key: string, action: () => Promise<void>) => {
    setWorkflowActionBusy(key)
    try {
      await action()
    } catch (error) {
      const message = error instanceof Error ? error.message : '工作流动作失败，请重试'
      toast.error(message)
    } finally {
      setWorkflowActionBusy(null)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [requirementId])

  if (loading || !detail) {
    return <LoadingPane>正在加载需求…</LoadingPane>
  }

  const requirement = detail.requirement
  const requirementAllowedActions = requirement.allowed_actions ?? fallbackRequirementAllowedActions(detail)
  const canEdit = requirementAllowedActions.includes('edit')
  const currentProject = detail.project
  const latestRelease = detail.latest_release
  const workspaceBlocker = latestRelease?.workspace_blocker || null
  const plannedBranchName = latestRelease?.planned_branch_name || workspaceBlocker?.target_branch || latestRelease?.branch_name || null
  const actualBranchName = latestRelease?.actual_branch_name || latestRelease?.branch_name || null
  const releaseBlocker = releaseBlockerText(latestRelease)
  const currentWorkspaceBranch = workspaceBlocker?.current_branch || extractWorkspaceBranch(releaseBlocker)
  const isWorkspaceBlocked =
    latestRelease?.delivery_blocker_type === 'workspace_blocked' ||
    latestRelease?.blocker_kind === 'workspace_blocked' ||
    /dirty worktree|automatic execution branch preparation/i.test(releaseBlocker)
  const assetsReady = detail.assets_status === 'ready'
  const requirementState = requirement.state || detail.state || requirement.status
  const activeWorkflowRunId = detail.active_workflow_run_id ?? requirement.active_workflow_run_id ?? detail.active_workflow_run_summary?.id ?? requirement.active_workflow_run_summary?.id ?? null
  const readiness = detail.workflow_readiness
  const readinessCopy = workflowReadinessCopy(detail)
  const autoSubmitPending =
    !activeWorkflowRunId &&
    assetsReady &&
    ((detail.pending_operations ?? []).includes('auto_submit') || requirementAllowedActions.includes('submit'))

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
                className={
                  autoSubmitPending
                    ? 'rounded-2xl border border-[color:var(--ops-state-ready-border)] px-4 py-2 text-sm text-[color:var(--ops-state-ready-text)] disabled:opacity-50'
                    : 'rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2 text-sm text-white disabled:opacity-50'
                }
                disabled={!assetsReady || !requirementAllowedActions.includes('submit')}
                onClick={async () => {
                  try {
                    const next = await api.submitRequirement(requirement.id)
                    setDetail(next)
                    const workflowRunId = next.active_workflow_run_id ?? next.requirement.active_workflow_run_id
                    if (workflowRunId) {
                      navigate(`/workflows/${workflowRunId}`)
                    }
                  } catch (error) {
                    const message = error instanceof Error ? error.message : '提交失败，请重试'
                    toast.error(message)
                  }
                }}
              >
                {detail.assets_status === 'pending'
                  ? '生成计划中…'
                  : detail.assets_status === 'failed'
                    ? '计划生成失败'
                    : autoSubmitPending
                      ? '创建工作流'
                      : '提交'}
              </button>
            ) : null}
            {!isEditing && requirementAllowedActions.includes('cancel') ? (
              <button
                className="rounded-2xl border border-[color:var(--ops-state-validating-border)] px-4 py-2 text-sm text-[color:var(--ops-state-validating-text)] disabled:opacity-50"
                disabled={lifecycleActionBusy === 'cancel'}
                onClick={() => setConfirmLifecycleAction('cancel')}
              >
                {lifecycleActionBusy === 'cancel' ? '关闭中…' : '关闭需求'}
              </button>
            ) : null}
            {!isEditing && requirementAllowedActions.includes('delete') ? (
              <button
                className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] px-4 py-2 text-sm text-[color:var(--ops-state-blocked-text)] disabled:opacity-50"
                disabled={lifecycleActionBusy === 'delete'}
                onClick={() => setConfirmLifecycleAction('delete')}
              >
                {lifecycleActionBusy === 'delete' ? '删除中…' : '删除需求'}
              </button>
            ) : null}
            {!isEditing && detail.assets_status === 'failed' && requirementAllowedActions.includes('regenerate_assets') ? (
              <button
                className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] px-4 py-2 text-sm text-[color:var(--ops-state-blocked-text)]"
                onClick={async () => {
                  try {
                    const next = await api.regenerateRequirementAssets(requirement.id)
                    setDetail(next)
                    toast.success('已重新开始生成验收标准与状态机计划')
                  } catch (error) {
                    const message = error instanceof Error ? error.message : '重新生成失败，请重试'
                    toast.error(message)
                  }
                }}
              >
                重新生成计划
              </button>
            ) : null}
            {!isEditing && activeWorkflowRunId ? (
              <button className="rounded-2xl border border-[color:var(--ops-state-running-border)] px-4 py-2 text-sm text-[color:var(--ops-state-running-text)]" onClick={() => navigate(`/workflows/${activeWorkflowRunId}`)}>
                查看工作流
              </button>
            ) : null}
            {!isEditing && detail.latest_release_id ? (
              <button className="rounded-2xl border border-[color:var(--ops-state-ready-border)] px-4 py-2 text-sm text-[color:var(--ops-state-ready-text)]" onClick={() => navigate(`/releases/${requirement.id}`)}>
                查看发布
              </button>
            ) : null}
            {!isEditing && requirementAllowedActions.includes('prepare_release') ? (
              <button
                className="rounded-2xl border border-[color:var(--ops-state-running-border)] px-4 py-2 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-50"
                disabled={releaseActionBusy === 'prepare_release'}
                onClick={() =>
                  runReleaseAction(
                    'prepare_release',
                    () => api.prepareRelease(requirement.id, { actor: 'operator', note: 'Restart release branch preparation from requirement detail' }),
                    '已重新准备交付分支',
                  )
                }
              >
                {releaseActionBusy === 'prepare_release' ? '准备中…' : '重新准备分支'}
              </button>
            ) : null}
            {!isEditing && requirementAllowedActions.includes('open_pr') ? (
              <button
                className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2 text-sm text-white disabled:opacity-50"
                disabled={releaseActionBusy === 'open_pr'}
                onClick={() =>
                  runReleaseAction(
                    'open_pr',
                    () => api.openReleasePr(requirement.id, { actor: 'operator', note: 'Resume release delivery from requirement detail' }),
                    '已触发 PR 交付',
                  )
                }
              >
                {releaseActionBusy === 'open_pr' ? '交付中…' : latestRelease?.status === 'branch_prepared' ? '打开 PR' : '继续打开 PR'}
              </button>
            ) : null}
          </div>
        }
      >
        {!isEditing ? <RequirementLifecycleStepper detail={detail} /> : null}

        {!isEditing ? (
          <div
            data-testid="workflow-readiness-panel"
            className="mb-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-4 py-4 text-sm text-[color:var(--ops-text-body)]"
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <StateBadge tone={readinessCopy.tone}>{readinessCopy.title}</StateBadge>
                  <span>assets: {readiness?.assets_status || detail.assets_status}</span>
                  <span>workflow: {activeWorkflowRunId ? `#${activeWorkflowRunId}` : '未生成'}</span>
                  {readiness?.recommended_workflow_key ? <span>recommended: {readiness.recommended_workflow_key}</span> : null}
                </div>
                <div className="mt-2 text-[color:var(--ops-text-muted)]">{readinessCopy.body}</div>
                <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">
                  blocking reason: {readiness?.blocking_reason || '-'} · next action: {readiness?.next_action || '-'}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {activeWorkflowRunId ? (
                  <button
                    type="button"
                    className="rounded-xl border border-[color:var(--ops-state-running-border)] px-4 py-2 text-sm text-[color:var(--ops-state-running-text)]"
                    onClick={() => navigate(`/workflows/${activeWorkflowRunId}`)}
                  >
                    查看工作流
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      data-testid="generate-workflow-assets-btn"
                      className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm disabled:opacity-50"
                      disabled={workflowActionBusy !== null}
                      onClick={() =>
                        runWorkflowAction('generate', async () => {
                          const next = await api.generateRequirementWorkflow(requirement.id)
                          setDetail(next)
                          toast.success('Workflow assets 已重新生成')
                        })
                      }
                    >
                      {workflowActionBusy === 'generate' ? '生成中…' : '重新生成 Workflow Assets'}
                    </button>
                    <button
                      type="button"
                      data-testid="start-workflow-btn"
                      className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                      disabled={workflowActionBusy !== null || readiness?.can_start_workflow === false}
                      onClick={() =>
                        runWorkflowAction('start', async () => {
                          const run = await api.startRequirementWorkflow(requirement.id, {
                            workflow_key: readiness?.recommended_workflow_key || undefined,
                            run_immediately: true,
                            triggered_by: 'operator',
                          })
                          toast.success('Workflow 已生成并启动')
                          navigate(`/workflows/${run.id}`)
                        })
                      }
                    >
                      {workflowActionBusy === 'start' ? '启动中…' : '生成并启动 Workflow'}
                    </button>
                    <button
                      type="button"
                      className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm"
                      onClick={() => navigate('/workflows')}
                    >
                      查看生成日志
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        ) : null}

        {!isEditing && autoSubmitPending ? (
          <div className="mb-5 rounded-2xl border border-[color:var(--ops-state-ready-border)] bg-[color:var(--ops-state-ready-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-ready-text)]">
            <div className="flex flex-wrap items-center gap-2">
              <StateBadge tone="ready">自动工作流</StateBadge>
              <span>Assets 已就绪，系统会创建 declarative workflow run 并由状态机推进。</span>
            </div>
            <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">
              如果后台触发还未完成，可以用右上角“创建工作流”重新触发 workflow asset generation / start workflow；高风险动作会在 workflow human gate 中处理。
            </div>
          </div>
        ) : null}

        {!isEditing && (detail.active_workflow_run_summary || requirement.active_workflow_run_summary) ? (
          <div className="mb-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-sm text-[color:var(--ops-text-body)]" data-testid="active-workflow-summary">
            {(() => {
              const summary = detail.active_workflow_run_summary || requirement.active_workflow_run_summary
              if (!summary) return null
              return (
                <div className="flex flex-wrap items-center gap-2">
                  <StateBadge tone={statusTone(summary.status)}>{summary.status}</StateBadge>
                  <span>{summary.workflow_key}</span>
                  <span>state: {summary.current_state}</span>
                  <span>risk: {summary.risk_level}</span>
                  {summary.pending_human_gate_count ? <span>human gate: {summary.pending_human_gate_count}</span> : null}
                  {summary.awaiting_business_confirmation ? <StateBadge tone="validating">技术完成，等待人工业务确认</StateBadge> : null}
                  {summary.business_outcome_status === 'confirmed' ? <StateBadge tone="delivered">业务已确认</StateBadge> : null}
                </div>
              )
            })()}
          </div>
        ) : null}

        {!isEditing && (detail.resolution_path || detail.followup_requirement_id) ? (
          <div className="mb-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-sm text-[color:var(--ops-text-body)]">
            <div className="flex flex-wrap items-center gap-2">
              <StateBadge tone="muted">{detail.resolution_path || 'resolution'}</StateBadge>
              {detail.followup_requirement_id ? <span>已转派修复需求 #{detail.followup_requirement_id}</span> : null}
            </div>
          </div>
        ) : null}

        {!isEditing && latestRelease?.status === 'release_blocked' ? (
          <div className="mb-5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <div className="flex flex-wrap items-center gap-2">
              <StateBadge tone="blocked">{latestRelease.delivery_blocker_type || (isWorkspaceBlocked ? 'workspace_blocked' : 'release_blocked')}</StateBadge>
              {latestRelease.failed_gate_name ? <span>gate: {latestRelease.failed_gate_name}</span> : null}
              <span>next action: {latestRelease.next_action || '-'}</span>
              <span>repairable: {latestRelease.repairable ? 'yes' : 'no'}</span>
            </div>
            {isWorkspaceBlocked ? (
              <div className="mt-3 rounded-2xl border border-amber-200 bg-[color:var(--ops-panel)] px-4 py-3">
                <div className="font-medium">交付工作区阻塞，清理后可继续当前 release。</div>
                <div className="mt-2 grid gap-2 text-xs md:grid-cols-2">
                  <div>当前工作区分支：{currentWorkspaceBranch || '-'}</div>
                  <div>稳定目标分支：{plannedBranchName || '-'}</div>
                  <div>实际交付分支：{actualBranchName || '-'}</div>
                  <div>工作区模式：{workspaceBlocker?.workspace_mode || latestRelease?.workspace_mode || 'shared_checkout'}</div>
                  <div>dirty files：{workspaceBlocker?.dirty_file_count ?? '-'}</div>
                  <div>next action：{latestRelease.next_action || '-'}</div>
                </div>
                {workspaceBlocker?.dirty_files_preview?.length ? (
                  <div className="mt-2 text-xs">
                    脏文件预览：{workspaceBlocker.dirty_files_preview.join(' · ')}
                  </div>
                ) : null}
                <div className="mt-2 text-xs text-amber-800">
                  {workspaceBlocker?.recommended_operator_action ||
                    '如果这些改动属于当前需求，请先采纳到目标分支；否则清理工作区后点击“重新准备分支”。'}
                </div>
              </div>
            ) : null}
            {releaseBlocker ? <div className="mt-2">阻塞原因：{releaseBlocker}</div> : null}
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
          <div className="mb-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-sm text-[color:var(--ops-text-muted)]">
            <div className="flex flex-wrap items-center gap-2">
              <StateBadge tone={assetsTone(detail.assets_status)}>
                {detail.assets_status === 'failed' ? '计划生成失败' : '正在生成计划'}
              </StateBadge>
              <span>
                {detail.assets_status === 'failed'
                  ? detail.assets_error_message || 'plan agent 未生成有效状态机计划，需求不会创建工作流。'
                  : '验收标准与状态机计划正在生成，完成前不能提交。'}
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
            <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-4">
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
              {plannedBranchName ? <StateBadge tone="ready">稳定目标分支：{plannedBranchName}</StateBadge> : null}
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
                <div>稳定目标分支：{plannedBranchName || '-'}</div>
                <div>实际交付分支：{actualBranchName || '-'}</div>
                <div>分支复用：{latestRelease.branch_reuse_status || '-'}</div>
                <div>基线分支：{latestRelease.base_branch || '-'}</div>
                <div>工作区模式：{latestRelease.workspace_mode || workspaceBlocker?.workspace_mode || 'shared_checkout'}</div>
                {workspaceBlocker?.dirty_file_count != null ? <div>dirty files：{workspaceBlocker.dirty_file_count}</div> : null}
                {currentWorkspaceBranch ? <div>当前工作区分支：{currentWorkspaceBranch}</div> : null}
                {isWorkspaceBlocked ? <div>状态说明：系统尚未切换到稳定目标分支</div> : null}
                <div>PR：{latestRelease.pr_url ? <a className="text-blue-600 hover:underline" href={latestRelease.pr_url} target="_blank" rel="noreferrer">查看 PR</a> : '-'}</div>
                {releaseBlocker ? <div className="basis-full">阻塞原因：{releaseBlocker}</div> : null}
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
                  className="overflow-hidden rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)]"
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
        {!isEditing && detail.requirement.source === 'planner_candidate' ? (
          <div className="mb-4 rounded-2xl border border-cyan-300/25 bg-cyan-300/[0.06] px-4 py-3 text-sm text-cyan-100">
            Generated by Planner Agent
            {detail.requirement.requirement_candidate_id ? ` · Candidate #${detail.requirement.requirement_candidate_id}` : ''}
            {detail.requirement.goal_key ? ` · Goal ${detail.requirement.goal_key}` : ''}
          </div>
        ) : null}
        {!isEditing ? <AcceptanceStepCards steps={detail.acceptance_contract.execution_acceptance_steps || []} /> : null}
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
              <div className="mb-2 text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Expected Evidence</div>
              <ul className="space-y-2 text-sm text-[color:var(--ops-text-body)]">
                {(detail.acceptance_contract.expected_evidence?.length
                  ? detail.acceptance_contract.expected_evidence
                  : (detail.acceptance_contract.verification_checks || []).map((item) => item.label)
                ).map((item) => (
                  <li key={item}>• {item}</li>
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

      <SectionFrame eyebrow="Plan" title="状态机计划">
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
      <ConfirmDialog
        open={confirmLifecycleAction !== null}
        title={confirmLifecycleAction === 'cancel' ? '关闭需求' : '删除需求'}
        description={
          confirmLifecycleAction === 'cancel'
            ? `关闭后，需求 #${requirement.id} 会进入 cancelled 状态，不会再提交、启动 workflow 或进入人工门禁。`
            : `删除后，需求 #${requirement.id} 会进入 deleted 状态；已删除需求不能再进入审批或 workflow。`
        }
        confirmLabel={confirmLifecycleAction === 'cancel' ? '确认关闭' : '确认删除'}
        cancelLabel="取消"
        tone="destructive"
        loading={lifecycleActionBusy !== null}
        onClose={() => {
          if (lifecycleActionBusy) return
          setConfirmLifecycleAction(null)
        }}
        onConfirm={() => {
          if (!confirmLifecycleAction) return
          const action = confirmLifecycleAction
          setLifecycleActionBusy(action)
          ;(async () => {
            try {
              const next = action === 'cancel'
                ? await api.cancelRequirement(requirement.id)
                : await api.deleteRequirement(requirement.id)
              setDetail(next)
              toast.success(action === 'cancel' ? '需求已关闭' : '需求已删除')
              setConfirmLifecycleAction(null)
            } catch (error) {
              const message = error instanceof Error ? error.message : (action === 'cancel' ? '关闭失败，请重试' : '删除失败，请重试')
              toast.error(message)
            } finally {
              setLifecycleActionBusy(null)
            }
          })().catch(() => {})
        }}
      />
    </div>
  )
}
