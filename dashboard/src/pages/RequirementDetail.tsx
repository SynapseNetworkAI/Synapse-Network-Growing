import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { AgentRequirementDetail, api } from '../api'
import { FieldLabel, LoadingPane, SectionFrame, StateBadge } from '../components/workbench'

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
  const [isEditing, setIsEditing] = useState(false)
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
      const data = await api.getRequirement(requirementId)
      setDetail(data)
      setForm({
        title: data.requirement.title,
        description_markdown: data.requirement.description_markdown,
        acceptance_criteria_markdown: data.requirement.acceptance_criteria_markdown,
        priority: data.requirement.priority,
        target_project_path: data.requirement.target_project_path || '',
      })
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
  const canEdit = !detail.latest_execution_id && ['draft', 'ready', 'blocked', 'needs_revision'].includes(requirement.status)
  const showApprovalNotice = approval.approval_status === 'pending_approval' || approval.approval_status === 'rejected'

  return (
    <div className="space-y-[var(--ops-section-gap)]" data-testid="agent-first-requirement-detail">
      <SectionFrame
        eyebrow="Requirement"
        title={requirement.title}
        actions={
          <div className="flex flex-wrap gap-2">
            {canEdit && !isEditing && (
              <button
                data-testid="toggle-edit-requirement-btn"
                className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm"
                onClick={() => setIsEditing(true)}
              >
                编辑
              </button>
            )}
            {isEditing && (
              <>
                <button
                  className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm"
                  onClick={() => {
                    setForm({
                      title: requirement.title,
                      description_markdown: requirement.description_markdown,
                      acceptance_criteria_markdown: requirement.acceptance_criteria_markdown,
                      priority: requirement.priority,
                      target_project_path: requirement.target_project_path || '',
                    })
                    setIsEditing(false)
                  }}
                >
                  取消
                </button>
                <button
                  data-testid="save-requirement-btn"
                  className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm text-white disabled:opacity-50"
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
              </>
            )}
            {!isEditing && requirement.status === 'draft' && (
              <button
                className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2 text-sm text-white"
                onClick={async () => {
                  const next = await api.submitRequirement(requirement.id)
                  setDetail(next)
                  if (next.approval.auto_started && next.approval.execution_run_id) {
                    navigate(`/executions/${next.approval.execution_run_id}`)
                  }
                }}
              >
                提交
              </button>
            )}
            {!isEditing && requirement.status === 'blocked' && approval.approval_status === 'pending_approval' && (
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
            )}
            {!isEditing && approval.pending_execution_start && detail.latest_execution_id && (
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
            )}
            {!isEditing && detail.latest_execution_id && (
              <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/executions/${detail.latest_execution_id}`)}>
                查看执行
              </button>
            )}
            {!isEditing && detail.latest_release_id && (
              <button className="rounded-2xl border border-[color:var(--ops-state-ready-border)] px-4 py-2 text-sm text-[color:var(--ops-state-ready-text)]" onClick={() => navigate(`/releases/${requirement.id}`)}>
                查看发布
              </button>
            )}
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
          </div>
        ) : null}
        {isEditing ? (
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
              <FieldLabel>目标项目路径</FieldLabel>
              <input
                data-testid="edit-requirement-target-project-path"
                className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
                value={form.target_project_path}
                onChange={(event) => setForm((current) => ({ ...current, target_project_path: event.target.value }))}
              />
            </div>
            <div className="md:col-span-2">
              <FieldLabel>优先级</FieldLabel>
              <select
                data-testid="edit-requirement-priority"
                className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm md:max-w-[220px]"
                value={form.priority}
                onChange={(event) => setForm((current) => ({ ...current, priority: event.target.value }))}
              >
                <option value="low">low</option>
                <option value="normal">normal</option>
                <option value="high">high</option>
              </select>
            </div>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap gap-2">
              <StateBadge tone={statusTone(requirement.status)}>{STATUS_LABEL[requirement.status] || requirement.status}</StateBadge>
              <StateBadge tone="muted">{requirement.priority}</StateBadge>
              <StateBadge tone="muted">{requirement.source}</StateBadge>
              {requirement.target_projects.length ? <StateBadge tone="muted">{requirement.target_projects[0]}</StateBadge> : null}
            </div>
          </>
        )}
      </SectionFrame>

      <div className="space-y-[var(--ops-section-gap)]">
        <SectionFrame eyebrow="Intent" title="需求意图">
          {isEditing ? (
            <textarea
              data-testid="edit-requirement-description"
              className="min-h-[220px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
              value={form.description_markdown}
              onChange={(event) => setForm((current) => ({ ...current, description_markdown: event.target.value }))}
            />
          ) : (
            <Markdown value={requirement.description_markdown} />
          )}
        </SectionFrame>

        <SectionFrame eyebrow="Acceptance" title="验收标准">
          {isEditing ? (
            <textarea
              data-testid="edit-requirement-acceptance"
              className="min-h-[180px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
              value={form.acceptance_criteria_markdown}
              onChange={(event) => setForm((current) => ({ ...current, acceptance_criteria_markdown: event.target.value }))}
            />
          ) : (
            <Markdown value={requirement.acceptance_criteria_markdown} />
          )}
        </SectionFrame>
      </div>
    </div>
  )
}
