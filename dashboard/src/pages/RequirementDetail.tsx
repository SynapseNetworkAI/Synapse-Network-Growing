import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { AgentRequirementDetail, api } from '../api'
import { EmptyPane, FieldLabel, InspectorRail, LoadingPane, SectionFrame, StateBadge } from '../components/workbench'

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

function statusTone(status: string) {
  if (status === 'done' || status === 'delivery_ready') return 'delivered'
  if (status === 'running') return 'running'
  if (status === 'blocked' || status === 'needs_revision' || status === 'cancelled') return 'blocked'
  if (status === 'ready') return 'ready'
  return 'muted'
}

function approvalTone(status: string) {
  if (status === 'approved' || status === 'waived') return 'ready'
  if (status === 'rejected') return 'blocked'
  return 'validating'
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
    return <LoadingPane>正在加载需求…</LoadingPane>
  }

  const requirement = detail.requirement
  const approval = detail.approval

  return (
    <div className="space-y-[var(--ops-section-gap)]" data-testid="agent-first-requirement-detail">
      <SectionFrame
        eyebrow="Requirement"
        title={requirement.title}
        description="需求详情只展示意图、验收和治理摘要，不直接承担执行控制和发布控制。"
        actions={
          <div className="flex flex-wrap gap-2">
            {requirement.status === 'draft' && (
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
            {requirement.status === 'blocked' && approval.approval_status === 'pending_approval' && (
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
            {approval.pending_execution_start && detail.latest_execution_id && (
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
            {detail.latest_execution_id && (
              <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/executions/${detail.latest_execution_id}`)}>
                查看执行
              </button>
            )}
            {detail.latest_release_id && (
              <button className="rounded-2xl border border-[color:var(--ops-state-ready-border)] px-4 py-2 text-sm text-[color:var(--ops-state-ready-text)]" onClick={() => navigate(`/releases/${requirement.id}`)}>
                查看发布
              </button>
            )}
          </div>
        }
      >
        <div className="flex flex-wrap gap-2">
          <StateBadge tone={statusTone(requirement.status)}>{STATUS_LABEL[requirement.status] || requirement.status}</StateBadge>
          <StateBadge tone="muted">{requirement.priority}</StateBadge>
          <StateBadge tone="muted">{requirement.source}</StateBadge>
        </div>
        <div className="mt-4 grid gap-3 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-2 xl:grid-cols-3">
          <div>target: {requirement.target_projects.join(', ') || '-'}</div>
          <div>approval: {approval.approval_decision}</div>
          <div>latest execution: {detail.latest_execution_id ?? '-'}</div>
          <div>latest release: {detail.latest_release_id ?? '-'}</div>
          <div>created: {formatTime(requirement.created_at)}</div>
          <div>updated: {formatTime(requirement.updated_at)}</div>
        </div>
      </SectionFrame>

      <div className="grid gap-[var(--ops-section-gap)] xl:grid-cols-[minmax(0,1.45fr),minmax(300px,var(--ops-inspector-width))]">
        <div className="space-y-[var(--ops-section-gap)]">
          <SectionFrame eyebrow="Intent" title="需求意图">
            <Markdown value={requirement.description_markdown} />
          </SectionFrame>

          <SectionFrame eyebrow="Acceptance" title="验收标准">
            <Markdown value={requirement.acceptance_criteria_markdown} />
          </SectionFrame>

          <SectionFrame eyebrow="Edit" title="修订需求" description="需求面允许修订意图和约束，但不处理执行日志和发布决策。">
            <div className="grid gap-3">
              <div>
                <FieldLabel>标题</FieldLabel>
                <input className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
              </div>
              <div>
                <FieldLabel>目标项目路径</FieldLabel>
                <input className="mt-2 w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.target_project_path} onChange={(event) => setForm((current) => ({ ...current, target_project_path: event.target.value }))} />
              </div>
              <div>
                <FieldLabel>需求描述</FieldLabel>
                <textarea className="mt-2 min-h-[130px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.description_markdown} onChange={(event) => setForm((current) => ({ ...current, description_markdown: event.target.value }))} />
              </div>
              <div>
                <FieldLabel>验收标准</FieldLabel>
                <textarea className="mt-2 min-h-[110px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.acceptance_criteria_markdown} onChange={(event) => setForm((current) => ({ ...current, acceptance_criteria_markdown: event.target.value }))} />
              </div>
              <div>
                <FieldLabel>Revision Note</FieldLabel>
                <textarea className="mt-2 min-h-[90px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" placeholder="revision note" value={revisionNote} onChange={(event) => setRevisionNote(event.target.value)} />
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2 text-sm text-white disabled:opacity-50"
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
                  className="rounded-2xl border border-[color:var(--ops-state-validating-border)] px-4 py-2 text-sm text-[color:var(--ops-state-validating-text)] disabled:opacity-50"
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
                  className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] px-4 py-2 text-sm text-[color:var(--ops-state-blocked-text)] disabled:opacity-50"
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
          </SectionFrame>
        </div>

        <div className="space-y-[var(--ops-section-gap)]">
          <InspectorRail eyebrow="Approval" title="执行许可">
            <div className="flex flex-wrap gap-2">
              <StateBadge tone={approvalTone(approval.approval_status)}>{approval.approval_decision}</StateBadge>
              {approval.approval_source ? <StateBadge tone="muted">{approval.approval_source}</StateBadge> : null}
            </div>
            <div>
              <FieldLabel>Reason</FieldLabel>
              <div className="mt-2 leading-6 text-[color:var(--ops-text-muted)]">{approval.approval_reason || '当前没有审批说明。'}</div>
            </div>
            <div>
              <FieldLabel>Roles</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">{approval.required_approver_roles.join(', ') || '-'}</div>
            </div>
            <div>
              <FieldLabel>Risk Flags</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">{approval.risk_flags.join(', ') || 'none'}</div>
            </div>
            <div>
              <FieldLabel>Bridge</FieldLabel>
              <div className="mt-2 leading-6 text-[color:var(--ops-text-muted)]">
                submit 是 requirement 进入 execution 的唯一正式桥接点。低风险自动放行并自动启动，高风险停在这里等待人工批准。
              </div>
            </div>
          </InspectorRail>

          <InspectorRail eyebrow="Policy" title="策略摘要">
            {detail.policy_summary_markdown.trim() ? <Markdown value={detail.policy_summary_markdown} /> : <EmptyPane>当前没有策略摘要。</EmptyPane>}
          </InspectorRail>

          <InspectorRail eyebrow="Links" title="执行 / 发布跳转">
            <div>
              <FieldLabel>Execution</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">latest execution #{detail.latest_execution_id ?? '-'}</div>
            </div>
            <div>
              <FieldLabel>Release</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">latest release #{detail.latest_release_id ?? '-'}</div>
            </div>
            <div>
              <FieldLabel>治理边界</FieldLabel>
              <div className="mt-2 leading-6 text-[color:var(--ops-text-muted)]">
                Requirement 只关心 why / acceptance / policy。执行状态去 Execution，PR 和部署去 Release。
              </div>
            </div>
          </InspectorRail>
        </div>
      </div>
    </div>
  )
}
