import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { ExecutionDetail, api } from '../api'
import { ActivityFeed, FieldLabel, InspectorRail, LoadingPane, SectionFrame, StateBadge } from '../components/workbench'

const STATUS_LABEL: Record<string, string> = {
  queued: '排队中',
  running: '执行中',
  paused: '已暂停',
  blocked: '阻塞',
  validating: '验证中',
  failed: '失败',
  succeeded: '成功',
  completed: '已完成',
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function statusTone(status: string) {
  if (status === 'succeeded' || status === 'completed') return 'delivered'
  if (status === 'running') return 'running'
  if (status === 'blocked' || status === 'failed') return 'blocked'
  if (status === 'validating') return 'validating'
  if (status === 'queued') return 'ready'
  return 'muted'
}

function Markdown({ value }: Readonly<{ value: string | null | undefined }>) {
  if (!String(value || '').trim()) return <div className="text-sm text-slate-400">暂无内容</div>
  return (
    <div className="prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2">
      <ReactMarkdown>{String(value)}</ReactMarkdown>
    </div>
  )
}

export default function ExecutionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const executionId = Number(id)
  const [detail, setDetail] = useState<ExecutionDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyAction, setBusyAction] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      setDetail(await api.getExecution(executionId))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [executionId])

  const runAction = async (key: string, action: () => Promise<unknown>) => {
    setBusyAction(key)
    try {
      await action()
      await load()
    } finally {
      setBusyAction(null)
    }
  }

  if (loading || !detail) {
    return <LoadingPane>正在加载执行详情…</LoadingPane>
  }

  const execution = detail.execution

  return (
    <div className="space-y-[var(--ops-section-gap)]" data-testid="execution-detail-page">
      <SectionFrame
        eyebrow="Execution Run"
        title={`Execution #${execution.id}`}
        description="执行面承载 agent 当前工作状态、验证结果与恢复动作。"
        actions={
          <div className="flex flex-wrap gap-2">
            <button className="rounded-2xl border border-slate-200 px-4 py-2 text-sm" onClick={() => navigate(`/requirements/${execution.requirement_id}`)}>
              查看需求
            </button>
            {(execution.status === 'queued' || execution.status === 'paused' || execution.status === 'blocked') && (
              <button
                className="rounded-2xl bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-60"
                disabled={busyAction === 'start'}
                onClick={() => runAction('start', () => api.startExecution(execution.id))}
              >
                {execution.status === 'paused' ? '恢复执行' : '恢复/重启执行'}
              </button>
            )}
            {execution.status === 'running' && (
              <button
                className="rounded-2xl border border-amber-200 px-4 py-2 text-sm text-amber-700 disabled:opacity-60"
                disabled={busyAction === 'pause'}
                onClick={() => runAction('pause', () => api.pauseExecution(execution.id))}
              >
                暂停执行
              </button>
            )}
            {(execution.status === 'failed' || execution.status === 'blocked') && (
              <button
                className="rounded-2xl border border-rose-200 px-4 py-2 text-sm text-rose-700 disabled:opacity-60"
                disabled={busyAction === 'retry'}
                onClick={() => runAction('retry', () => api.retryExecution(execution.id))}
              >
                重试
              </button>
            )}
            {detail.nodes.length > 0 && detail.nodes.every((node) => node.status === 'completed') && (
              <button
                className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2 text-sm text-white disabled:opacity-60"
                disabled={busyAction === 'validate'}
                onClick={() => runAction('validate', () => api.validateExecution(execution.id))}
              >
                进入验证
              </button>
            )}
          </div>
        }
      >
        <div className="flex flex-wrap gap-2">
          <StateBadge tone={statusTone(execution.status)}>{STATUS_LABEL[execution.status] || execution.status}</StateBadge>
          <StateBadge tone="muted">{execution.execution_mode}</StateBadge>
          <StateBadge tone="muted">{execution.complexity}</StateBadge>
          <StateBadge tone="validating">{execution.validation_profile}</StateBadge>
        </div>

        <div className="mt-4 grid gap-3 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-2 xl:grid-cols-4">
          <div>requirement: #{execution.requirement_id}</div>
          <div>delivery: {execution.delivery_intent}</div>
          <div>approval: {execution.approval_required ? `${detail.requirement.approval_status} · submit gated` : 'waived'}</div>
          <div>latest task: {execution.latest_task_id ?? '-'}</div>
          <div>targets: {execution.target_projects.join(', ') || '-'}</div>
          <div>started: {formatTime(execution.started_at)}</div>
          <div>updated: {formatTime(execution.updated_at)}</div>
          <div>completed: {formatTime(execution.completed_at)}</div>
        </div>

        <div className="mt-4 text-sm text-[color:var(--ops-text-muted)]">
          <Markdown value={execution.planner_summary} />
        </div>
      </SectionFrame>

      <SectionFrame eyebrow="Execution Graph" title="执行节点" description="复杂任务会在这里展开节点图；简单任务一般只会有一个 execute 节点。">
        <div className="mt-4 grid gap-4">
          {detail.nodes.map((node) => (
            <article key={node.id} className="border-b border-[color:var(--ops-stroke-soft)] pb-5 last:border-b-0 last:pb-0">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-lg font-semibold text-[color:var(--ops-text-title)]">{node.title}</h4>
                    <StateBadge tone={statusTone(node.status)}>{STATUS_LABEL[node.status] || node.status}</StateBadge>
                    <StateBadge tone="muted">{node.node_key}</StateBadge>
                  </div>
                  <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">
                    task #{node.task_id ?? '-'} · backend {node.runtime_backend || '-'} · model {node.runtime_model || '-'}
                  </div>
                </div>
                <div className="text-right text-xs text-[color:var(--ops-text-caption)]">
                  <div>seq {node.sequence_no}</div>
                  <div>{formatTime(node.completed_at || node.started_at)}</div>
                </div>
              </div>
              <div className="mt-4 text-sm text-[color:var(--ops-text-muted)]">
                <Markdown value={node.summary_markdown} />
              </div>
            </article>
          ))}
        </div>
      </SectionFrame>

      <div className="grid gap-[var(--ops-section-gap)] xl:grid-cols-[minmax(0,1.45fr),minmax(300px,var(--ops-inspector-width))]">
        <SectionFrame eyebrow="Validation" title="验证记录" description="validate 永远独立于 execute，execution 不能自证正确。">
          {detail.validation ? (
            <div className="mt-4 space-y-4">
              <div className="rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-workspace-bg)] p-4 text-sm text-[color:var(--ops-text-muted)]">
                <div className="font-medium text-[color:var(--ops-text-title)]">{STATUS_LABEL[detail.validation.status] || detail.validation.status}</div>
                <div className="mt-2">{detail.validation.summary_markdown}</div>
              </div>
              <div className="space-y-3">
                {detail.validation.checks.map((check) => (
                  <div key={`${check.label}-${check.command || 'no-command'}`} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/74 p-4 text-sm text-[color:var(--ops-text-muted)]">
                    <div className="font-medium text-[color:var(--ops-text-title)]">{check.label}</div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{check.command || 'manual evidence'} · {check.project_path || '-'}</div>
                    <div className="mt-2">{check.status}</div>
                    {check.output_excerpt ? <pre className="mt-3 overflow-x-auto rounded-xl bg-slate-950/95 p-3 text-xs text-slate-100">{check.output_excerpt}</pre> : null}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="mt-4 text-sm text-[color:var(--ops-text-muted)]">当前还没有验证记录。</div>
          )}
        </SectionFrame>

        <div className="space-y-[var(--ops-section-gap)]">
          <InspectorRail eyebrow="Inspector" title="执行摘要">
            <div>
              <FieldLabel>Requirement</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">#{execution.requirement_id}</div>
            </div>
            <div>
              <FieldLabel>Targets</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">{execution.target_projects.join(', ') || '-'}</div>
            </div>
            <div>
              <FieldLabel>Latest Task</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">{execution.latest_task_id ?? '-'}</div>
            </div>
            <div>
              <FieldLabel>Delivery Intent</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">{execution.delivery_intent}</div>
            </div>
          </InspectorRail>

          <ActivityFeed eyebrow="Incidents" title="恢复信号">
            {detail.incidents.length > 0 ? (
              detail.incidents.map((incident, index) => (
                <div key={`${String(incident.kind || 'incident')}-${index}`} className="rounded-2xl border border-[color:var(--ops-state-validating-border)] bg-[color:var(--ops-state-validating-bg)] p-4 text-sm text-[color:var(--ops-state-validating-text)]">
                  <div className="font-medium">{String(incident.kind || 'incident')}</div>
                  <div className="mt-2">{String(incident.summary || '')}</div>
                </div>
              ))
            ) : (
              <div className="text-sm text-[color:var(--ops-text-muted)]">当前没有 incident。</div>
            )}
          </ActivityFeed>
        </div>
      </div>
    </div>
  )
}
