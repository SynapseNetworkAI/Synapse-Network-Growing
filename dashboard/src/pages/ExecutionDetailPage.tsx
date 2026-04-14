import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { ExecutionDetail, api } from '../api'

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
    return <div className="rounded-3xl border border-slate-200 bg-white p-8 text-sm text-slate-500">正在加载执行详情…</div>
  }

  const execution = detail.execution

  return (
    <div className="space-y-6" data-testid="execution-detail-page">
      <section className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-slate-400">Execution Run</div>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Execution #{execution.id}</h2>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
              <span className="rounded-full bg-slate-100 px-3 py-1">{STATUS_LABEL[execution.status] || execution.status}</span>
              <span className="rounded-full bg-slate-100 px-3 py-1">{execution.execution_mode}</span>
              <span className="rounded-full bg-slate-100 px-3 py-1">{execution.complexity}</span>
              <span className="rounded-full bg-slate-100 px-3 py-1">{execution.validation_profile}</span>
            </div>
          </div>
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
                {execution.status === 'paused' ? '恢复执行' : '启动执行'}
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
                className="rounded-2xl bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-60"
                disabled={busyAction === 'validate'}
                onClick={() => runAction('validate', () => api.validateExecution(execution.id))}
              >
                进入验证
              </button>
            )}
          </div>
        </div>

        <div className="mt-4 grid gap-3 text-sm text-slate-600 md:grid-cols-2 xl:grid-cols-4">
          <div>requirement: #{execution.requirement_id}</div>
          <div>delivery: {execution.delivery_intent}</div>
          <div>approval: {execution.approval_required ? detail.requirement.approval_status : 'waived'}</div>
          <div>latest task: {execution.latest_task_id ?? '-'}</div>
          <div>targets: {execution.target_projects.join(', ') || '-'}</div>
          <div>started: {formatTime(execution.started_at)}</div>
          <div>updated: {formatTime(execution.updated_at)}</div>
          <div>completed: {formatTime(execution.completed_at)}</div>
        </div>

        <div className="mt-4 text-sm text-slate-600">
          <Markdown value={execution.planner_summary} />
        </div>
      </section>

      <section className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
        <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Execution Graph</div>
        <h3 className="mt-2 text-xl font-semibold text-slate-950">执行节点</h3>
        <div className="mt-4 grid gap-4">
          {detail.nodes.map((node) => (
            <article key={node.id} className="rounded-3xl border border-slate-200/80 bg-slate-50/80 p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-lg font-semibold text-slate-950">{node.title}</h4>
                    <span className="rounded-full bg-white px-3 py-1 text-xs text-slate-600">{STATUS_LABEL[node.status] || node.status}</span>
                    <span className="rounded-full bg-white px-3 py-1 text-xs text-slate-600">{node.node_key}</span>
                  </div>
                  <div className="mt-2 text-xs text-slate-500">
                    task #{node.task_id ?? '-'} · backend {node.runtime_backend || '-'} · model {node.runtime_model || '-'}
                  </div>
                </div>
                <div className="text-right text-xs text-slate-500">
                  <div>seq {node.sequence_no}</div>
                  <div>{formatTime(node.completed_at || node.started_at)}</div>
                </div>
              </div>
              <div className="mt-4 text-sm text-slate-600">
                <Markdown value={node.summary_markdown} />
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr,0.9fr]">
        <div className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
          <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Validation</div>
          <h3 className="mt-2 text-xl font-semibold text-slate-950">验证记录</h3>
          {detail.validation ? (
            <div className="mt-4 space-y-4">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                <div className="font-medium text-slate-900">{STATUS_LABEL[detail.validation.status] || detail.validation.status}</div>
                <div className="mt-2">{detail.validation.summary_markdown}</div>
              </div>
              <div className="space-y-3">
                {detail.validation.checks.map((check) => (
                  <div key={`${check.label}-${check.command || 'no-command'}`} className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
                    <div className="font-medium text-slate-900">{check.label}</div>
                    <div className="mt-1 text-xs text-slate-500">{check.command || 'manual evidence'} · {check.project_path || '-'}</div>
                    <div className="mt-2">{check.status}</div>
                    {check.output_excerpt ? <pre className="mt-3 overflow-x-auto rounded-xl bg-slate-950/95 p-3 text-xs text-slate-100">{check.output_excerpt}</pre> : null}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="mt-4 text-sm text-slate-500">当前还没有验证记录。</div>
          )}
        </div>

        <div className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
          <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Incidents</div>
          <h3 className="mt-2 text-xl font-semibold text-slate-950">恢复信号</h3>
          <div className="mt-4 space-y-3">
            {detail.incidents.length > 0 ? (
              detail.incidents.map((incident, index) => (
                <div key={`${String(incident.kind || 'incident')}-${index}`} className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                  <div className="font-medium">{String(incident.kind || 'incident')}</div>
                  <div className="mt-2">{String(incident.summary || '')}</div>
                </div>
              ))
            ) : (
              <div className="text-sm text-slate-500">当前没有 incident。</div>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
