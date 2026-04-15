import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { AcceptanceContract, AgentRequirementDetail, ExecutionPlan, Project, api } from '../api'
import { FieldLabel, LoadingPane, SectionFrame, StateBadge, useToast } from '../components/workbench'

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

function statusTone(status: string) {
  if (status === 'done' || status === 'delivery_ready') return 'delivered'
  if (status === 'running') return 'running'
  if (status === 'blocked' || status === 'needs_revision' || status === 'cancelled') return 'blocked'
  if (status === 'ready') return 'ready'
  return 'muted'
}

function assetsTone(status: string) {
  if (status === 'ready') return 'ready'
  if (status === 'failed') return 'blocked'
  return 'running'
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
  const status = requirement.status
  if (detail.latest_execution_id != null) actions.add('view_execution')
  if (detail.latest_release_id != null) actions.add('view_release')
  if (status === 'draft' || status === 'ready' || status === 'blocked' || status === 'needs_revision') {
    actions.add('edit')
  }
  if (detail.assets_status === 'ready' && (status === 'draft' || status === 'needs_revision')) {
    actions.add('submit')
  }
  if (detail.assets_status === 'failed') {
    actions.add('regenerate_assets')
  }
  if (detail.approval.approval_status === 'pending_approval') {
    actions.add('approve')
    actions.add('reject')
  }
  if (requirement.latest_execution_run_id == null && ['draft', 'planning', 'awaiting_execution_approval', 'needs_revision', 'blocked'].includes(requirement.phase || requirement.status)) {
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
  const showApprovalNotice = approval.approval_status === 'pending_approval' || approval.approval_status === 'rejected'
  const currentProject = detail.project
  const latestRelease = detail.latest_release
  const assetsReady = detail.assets_status === 'ready'

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
            {!isEditing && requirementAllowedActions.includes('approve') && approval.approval_status === 'pending_approval' ? (
              <>
                <button
                  className="rounded-2xl bg-[color:var(--ops-state-running-text)] px-4 py-2 text-sm text-white"
                  onClick={async () => {
                    const next = await api.approveRequirement(requirement.id, { reviewer: 'operator', comment: approval.approval_reason || 'Approve and auto-start execution' })
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
        {showApprovalNotice ? (
          <div
            data-testid="requirement-approval-notice"
            className="mb-5 rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-blocked-text)]"
          >
            <div className="flex flex-wrap items-center gap-2">
              <StateBadge tone="blocked">{approval.approval_decision}</StateBadge>
              {approval.required_approver_roles.length ? <span>需要角色：{approval.required_approver_roles.join(' / ')}</span> : null}
            </div>
            {approval.approval_reason ? <div className="mt-2">{approval.approval_reason}</div> : null}
            {approval.approval_recommendation ? (
              <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">
                approval agent: {approval.approval_recommendation}
                {approval.approval_confidence != null ? ` · confidence ${approval.approval_confidence}` : ''}
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
              <span>next action: {latestRelease.next_action || '-'}</span>
              <span>repairable: {latestRelease.repairable ? 'yes' : 'no'}</span>
            </div>
            {latestRelease.delivery_failure_excerpt ? <div className="mt-2">{latestRelease.delivery_failure_excerpt}</div> : null}
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
              <StateBadge tone={statusTone(requirement.status)}>{STATUS_LABEL[requirement.status] || requirement.status}</StateBadge>
              {detail.phase && detail.phase !== requirement.status ? <StateBadge tone="muted">{detail.phase}</StateBadge> : null}
              {detail.recovery_status ? <StateBadge tone="blocked">恢复: {detail.recovery_status}</StateBadge> : null}
              <StateBadge tone="muted">{requirement.priority}</StateBadge>
              {requirement.project_display_name ? <StateBadge tone="muted">{requirement.project_display_name}</StateBadge> : null}
              {requirement.target_project_path_override ? <StateBadge tone="muted">路径已覆盖</StateBadge> : null}
              {latestRelease?.branch_name ? <StateBadge tone="ready">{latestRelease.branch_name}</StateBadge> : null}
            </div>
            {latestRelease ? (
              <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-[color:var(--ops-text-muted)]">
                <div>交付状态：{latestRelease.status}</div>
                <div>基线分支：{latestRelease.base_branch || '-'}</div>
                <div>PR：{latestRelease.pr_url ? <a className="text-blue-600 hover:underline" href={latestRelease.pr_url} target="_blank" rel="noreferrer">查看 PR</a> : '-'}</div>
              </div>
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
