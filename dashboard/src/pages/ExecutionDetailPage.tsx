import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { ExecutionDetail, ExecutionFilePreview, api } from '../api'
import { ActivityFeed, LoadingPane, OverlayModal, SectionFrame, StateBadge } from '../components/workbench'

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

function formatDuration(elapsedMs: number | null | undefined) {
  if (elapsedMs == null) return '-'
  const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`
  if (minutes > 0) return `${minutes}m ${seconds}s`
  return `${seconds}s`
}

function statusTone(status: string) {
  if (status === 'succeeded' || status === 'completed') return 'delivered'
  if (status === 'running') return 'running'
  if (status === 'blocked' || status === 'failed') return 'blocked'
  if (status === 'validating') return 'validating'
  if (status === 'queued') return 'ready'
  return 'muted'
}

function startLabel(detail: ExecutionDetail) {
  if (detail.execution.status === 'paused' || detail.blocking_reason_code === 'manual_pause') return '继续执行'
  if (detail.execution.status === 'blocked' && detail.recovery_mode === 'restart_current') return '再次启动'
  return '启动执行'
}

function Markdown({ value, empty = '暂无内容' }: Readonly<{ value: string | null | undefined; empty?: string }>) {
  if (!String(value || '').trim()) return <div className="text-sm text-slate-400">{empty}</div>
  return (
    <div className="prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2 prose-pre:rounded-2xl prose-pre:bg-slate-950 prose-pre:text-slate-100">
      <ReactMarkdown>{String(value)}</ReactMarkdown>
    </div>
  )
}

function Metric({
  label,
  value,
}: Readonly<{
  label: string
  value: string
}>) {
  return (
    <div className="min-w-[120px]">
      <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className="mt-2 text-sm font-medium text-[color:var(--ops-text-title)]">{value}</div>
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
  const [nowMs, setNowMs] = useState(Date.now())
  const [previewPath, setPreviewPath] = useState<string | null>(null)
  const [preview, setPreview] = useState<ExecutionFilePreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewTab, setPreviewTab] = useState<'diff' | 'content'>('diff')

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

  useEffect(() => {
    if (!detail || detail.execution.completed_at) return
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [detail])

  const runAction = async (key: string, action: () => Promise<unknown>) => {
    setBusyAction(key)
    try {
      await action()
      await load()
    } finally {
      setBusyAction(null)
    }
  }

  const openPreview = async (path: string) => {
    setPreviewPath(path)
    setPreviewLoading(true)
    try {
      const payload = await api.getExecutionFilePreview(executionId, path)
      setPreview(payload)
      setPreviewTab(payload.diff_patch ? 'diff' : 'content')
    } finally {
      setPreviewLoading(false)
    }
  }

  const closePreview = () => {
    setPreviewPath(null)
    setPreview(null)
    setPreviewLoading(false)
  }

  const liveElapsed = useMemo(() => {
    if (!detail?.execution.started_at) return null
    if (detail.execution.completed_at) return detail.execution.elapsed_ms
    const startedAt = new Date(detail.execution.started_at.endsWith('Z') ? detail.execution.started_at : `${detail.execution.started_at}Z`).getTime()
    return Math.max(0, nowMs - startedAt)
  }, [detail, nowMs])

  if (loading || !detail) {
    return <LoadingPane>正在加载执行详情…</LoadingPane>
  }

  const execution = detail.execution
  const runtimeSummary = detail.runtime_summary ?? {
    tokens_used_total: execution.tokens_used_total,
    elapsed_ms: execution.elapsed_ms,
    agent_id: execution.agent_id,
    agent_label: execution.agent_label,
    runtime_backend: execution.runtime_backend,
    runtime_provider: execution.runtime_provider,
    runtime_model: execution.runtime_model,
    current_branch: execution.current_branch,
  }
  const planMarkdown = String(detail.plan_summary?.summary_markdown || '').trim()
  const verification = detail.verification_result ?? detail.validation
  const verificationPlan = detail.verification_plan ?? verification?.verification_plan ?? null
  const detailAllowedActions = detail.allowed_actions ?? []

  return (
    <div className="space-y-6" data-testid="execution-detail-page">
      <SectionFrame
        eyebrow="Execution"
        title={`Execution #${execution.id}`}
        actions={
          <div className="flex flex-wrap gap-2">
            <button className="rounded-2xl border border-slate-200 px-4 py-2 text-sm" onClick={() => navigate(`/requirements/${execution.requirement_id}`)}>
              查看需求
            </button>
            {detail.delivery_summary?.pr_url ? (
              <a
                className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-700"
                href={detail.delivery_summary.pr_url}
                target="_blank"
                rel="noreferrer"
              >
                查看 PR
              </a>
            ) : null}
            {(detailAllowedActions.includes('start') || detailAllowedActions.includes('resume')) && (
              <button
                className="rounded-2xl bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-60"
                disabled={busyAction === 'start'}
                onClick={() => runAction('start', () => api.startExecution(execution.id))}
              >
                {startLabel(detail)}
              </button>
            )}
            {detailAllowedActions.includes('pause') && (
              <button
                className="rounded-2xl border border-amber-200 px-4 py-2 text-sm text-amber-700 disabled:opacity-60"
                disabled={busyAction === 'pause'}
                onClick={() => runAction('pause', () => api.pauseExecution(execution.id))}
              >
                暂停执行
              </button>
            )}
            {detailAllowedActions.includes('retry') && (
              <button
                className="rounded-2xl border border-rose-200 px-4 py-2 text-sm text-rose-700 disabled:opacity-60"
                disabled={busyAction === 'retry'}
                onClick={() => runAction('retry', () => api.retryExecution(execution.id))}
              >
                创建新 run 重试
              </button>
            )}
          </div>
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <StateBadge tone={statusTone(execution.status)}>{STATUS_LABEL[execution.status] || execution.status}</StateBadge>
          {detail.phase && detail.phase !== execution.status ? <StateBadge tone="muted">{detail.phase}</StateBadge> : null}
          {detail.recovery_status ? <StateBadge tone="blocked">恢复: {detail.recovery_status}</StateBadge> : null}
          {!detail.is_current_execution ? <StateBadge tone="muted">历史 run</StateBadge> : null}
          <StateBadge tone="muted">{execution.execution_mode}</StateBadge>
          <StateBadge tone="muted">{execution.execution_kind === 'delivery_repair' ? 'delivery_repair' : 'implementation'}</StateBadge>
          <StateBadge tone="muted">{execution.complexity}</StateBadge>
          <StateBadge tone="validating">{execution.validation_profile}</StateBadge>
          {runtimeSummary.current_branch ? <StateBadge tone="ready">{runtimeSummary.current_branch}</StateBadge> : null}
        </div>
        {detail.queue_reason ? <div className="mt-3 text-sm text-[color:var(--ops-text-muted)]">{detail.queue_reason}</div> : null}
        {detail.blocking_reason_message ? (
          <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            <div className="font-medium">阻塞原因</div>
            <div className="mt-1">
              {detail.blocking_reason_code ? `${detail.blocking_reason_code}: ` : ''}
              {detail.blocking_reason_message}
            </div>
            {detail.recovery_hint ? <div className="mt-2 text-xs text-rose-700/80">{detail.recovery_hint}</div> : null}
          </div>
        ) : null}
        {detail.workspace_blocker ? (
          <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <div className="font-medium">工作区阻塞详情</div>
            <div className="mt-2 grid gap-2 md:grid-cols-2">
              <div>仓库路径：{detail.workspace_blocker.repo_path}</div>
              <div>目标基线分支：{detail.workspace_blocker.base_branch || '-'}</div>
              <div>当前分支：{detail.workspace_blocker.current_branch || '-'}</div>
              <div>脏文件数量：{detail.workspace_blocker.dirty_file_count}</div>
            </div>
            {detail.workspace_blocker.dirty_files_preview.length ? (
              <div className="mt-3">
                <div className="text-xs uppercase tracking-[0.18em] text-amber-900/70">Dirty files preview</div>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                  {detail.workspace_blocker.dirty_files_preview.map((path) => (
                    <li key={path}>{path}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
        {detail.delivery_summary?.status === 'release_blocked' && detail.delivery_summary.delivery_failure_excerpt ? (
          <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <div className="font-medium">交付门禁阻塞</div>
            <div className="mt-1">
              {detail.delivery_summary.delivery_blocker_type ? `${detail.delivery_summary.delivery_blocker_type}: ` : ''}
              {detail.delivery_summary.delivery_failure_excerpt}
            </div>
            <div className="mt-2 text-xs text-amber-900/75">
              next action: {detail.delivery_summary.next_action || '-'} · repairable: {detail.delivery_summary.repairable ? 'yes' : 'no'} · attempts: {detail.delivery_summary.repair_attempt_count}
            </div>
          </div>
        ) : null}

        <div className="mt-5 grid gap-4 border-b border-[color:var(--ops-stroke-soft)] pb-5 md:grid-cols-3 xl:grid-cols-6">
          <Metric label="Requirement" value={`#${execution.requirement_id}`} />
          <Metric label="Agent" value={runtimeSummary.agent_label || runtimeSummary.agent_id || '-'} />
          <Metric label="Model" value={runtimeSummary.runtime_model || '-'} />
          <Metric label="Backend" value={runtimeSummary.runtime_backend || '-'} />
          <Metric label="Tokens" value={runtimeSummary.tokens_used_total != null ? String(runtimeSummary.tokens_used_total) : '-'} />
          <Metric label="Duration" value={formatDuration(liveElapsed)} />
        </div>

        <div className="mt-4 grid gap-3 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-2 xl:grid-cols-4">
          <div>delivery: {execution.delivery_intent}</div>
          <div>delivery status: {detail.delivery_summary?.status || '-'}</div>
          <div>execution kind: {execution.execution_kind}</div>
          <div>approval: {execution.approval_required ? `${detail.requirement.approval_status} · submit gated` : 'waived'}</div>
          <div>started: {formatTime(execution.started_at)}</div>
          <div>completed: {formatTime(execution.completed_at)}</div>
          <div>updated: {formatTime(execution.updated_at)}</div>
          <div>latest task: {execution.latest_task_id ?? '-'}</div>
          <div>runtime session: {execution.runtime_session_id || '-'}</div>
          <div>resume count: {execution.resume_count ?? '-'}</div>
          <div>targets: {execution.target_projects.join(', ') || '-'}</div>
          <div>delivery blocker: {detail.delivery_summary?.delivery_blocker_type || '-'}</div>
          <div>compare: {detail.delivery_summary?.compare_url ? <a className="text-blue-600 hover:underline" href={detail.delivery_summary.compare_url} target="_blank" rel="noreferrer">打开 Compare</a> : '-'}</div>
        </div>
      </SectionFrame>

      <SectionFrame eyebrow="Runtime" title="任务运行时">
        <div className="overflow-x-auto">
          <table className="min-w-full border-separate border-spacing-y-2 text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                <th className="pb-2 pr-4">节点</th>
                <th className="pb-2 pr-4">状态</th>
                <th className="pb-2 pr-4">Agent</th>
                <th className="pb-2 pr-4">Runtime</th>
                <th className="pb-2 pr-4">Tokens</th>
                <th className="pb-2 pr-4">时长</th>
                <th className="pb-2 pr-4">时间</th>
              </tr>
            </thead>
            <tbody>
              {detail.nodes.map((node) => (
                <tr key={node.id} className="rounded-2xl bg-[color:var(--ops-panel-subtle)] align-top">
                  <td className="rounded-l-2xl border-y border-l border-[color:var(--ops-stroke-soft)] px-4 py-4">
                    <div className="font-medium text-[color:var(--ops-text-title)]">{node.title}</div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">
                      {node.node_key} · task #{node.task_id ?? '-'}
                    </div>
                  </td>
                  <td className="border-y border-[color:var(--ops-stroke-soft)] px-4 py-4">
                    <StateBadge tone={statusTone(node.status)}>{STATUS_LABEL[node.status] || node.status}</StateBadge>
                  </td>
                  <td className="border-y border-[color:var(--ops-stroke-soft)] px-4 py-4 text-[color:var(--ops-text-body)]">
                    <div>{node.agent_label || node.agent_id || '-'}</div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{node.task_status || '-'}</div>
                  </td>
                  <td className="border-y border-[color:var(--ops-stroke-soft)] px-4 py-4 text-[color:var(--ops-text-body)]">
                    <div>{node.runtime_model || '-'}</div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">
                      {[node.runtime_backend, node.runtime_provider].filter(Boolean).join(' · ') || '-'}
                    </div>
                  </td>
                  <td className="border-y border-[color:var(--ops-stroke-soft)] px-4 py-4 text-[color:var(--ops-text-body)]">{node.tokens_used != null ? node.tokens_used : '-'}</td>
                  <td className="border-y border-[color:var(--ops-stroke-soft)] px-4 py-4 text-[color:var(--ops-text-body)]">{formatDuration(node.elapsed_ms)}</td>
                  <td className="rounded-r-2xl border-y border-r border-[color:var(--ops-stroke-soft)] px-4 py-4 text-[color:var(--ops-text-muted)]">
                    <div>{formatTime(node.started_at)}</div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{formatTime(node.completed_at)}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionFrame>

      <SectionFrame eyebrow="Plan" title="执行计划">
        <Markdown value={planMarkdown} empty="当前还没有执行计划。" />
      </SectionFrame>

      <SectionFrame eyebrow="Verification Plan" title="验证方案">
        {verificationPlan ? (
          <div className="space-y-4">
            <div className="rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] p-4">
              <div className="flex items-center gap-2">
                <StateBadge tone={verificationPlan.mode === 'command_checks' ? 'running' : verificationPlan.mode === 'none_required' ? 'muted' : 'validating'}>
                  {verificationPlan.mode}
                </StateBadge>
              </div>
              <div className="mt-3 text-sm text-[color:var(--ops-text-body)]">
                <Markdown value={verificationPlan.summary} />
              </div>
              {verificationPlan.why_no_verification ? (
                <div className="mt-3 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white p-4 text-sm text-[color:var(--ops-text-body)]">
                  <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Why No Verification</div>
                  <Markdown value={verificationPlan.why_no_verification} />
                </div>
              ) : null}
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white p-4">
                <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Checks</div>
                {verificationPlan.checks.length > 0 ? (
                  <ul className="list-disc space-y-2 pl-5 text-sm text-[color:var(--ops-text-body)]">
                    {verificationPlan.checks.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-sm text-[color:var(--ops-text-muted)]">当前验证方案没有额外命令检查。</div>
                )}
              </div>
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white p-4">
                <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Evidence Expectations</div>
                {verificationPlan.evidence_expectations.length > 0 ? (
                  <ul className="list-disc space-y-2 pl-5 text-sm text-[color:var(--ops-text-body)]">
                    {verificationPlan.evidence_expectations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-sm text-[color:var(--ops-text-muted)]">当前没有额外证据要求。</div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="text-sm text-[color:var(--ops-text-muted)]">verification agent 完成后会生成最终验证方案。</div>
        )}
      </SectionFrame>

      <SectionFrame eyebrow="Files" title="改动文件">
        {detail.changed_files.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full border-separate border-spacing-y-2 text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                  <th className="pb-2 pr-4">路径</th>
                  <th className="pb-2 pr-4">变更</th>
                  <th className="pb-2 pr-4">+ / -</th>
                  <th className="pb-2 pr-4">预览</th>
                </tr>
              </thead>
              <tbody>
                {detail.changed_files.map((file) => (
                  <tr key={file.path} className="rounded-2xl bg-[color:var(--ops-panel-subtle)]">
                    <td className="rounded-l-2xl border-y border-l border-[color:var(--ops-stroke-soft)] px-4 py-4 font-medium text-[color:var(--ops-text-title)]">
                      {file.path}
                    </td>
                    <td className="border-y border-[color:var(--ops-stroke-soft)] px-4 py-4 text-[color:var(--ops-text-body)]">
                      {file.change_type}
                    </td>
                    <td className="border-y border-[color:var(--ops-stroke-soft)] px-4 py-4 text-[color:var(--ops-text-body)]">
                      +{file.additions} / -{file.deletions}
                    </td>
                    <td className="rounded-r-2xl border-y border-r border-[color:var(--ops-stroke-soft)] px-4 py-4">
                      <button
                        className="rounded-2xl border border-slate-200 px-3 py-2 text-sm text-[color:var(--ops-text-body)] disabled:opacity-50"
                        disabled={!file.preview_available}
                        onClick={() => openPreview(file.path)}
                      >
                        预览
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-sm text-[color:var(--ops-text-muted)]">暂无文件改动。</div>
        )}
      </SectionFrame>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr),minmax(0,1fr)]">
      <SectionFrame eyebrow="Verification" title="验证结果">
          {verification ? (
            <div className="space-y-4">
              <div className="rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] p-4">
                <div className="flex items-center gap-2">
                  <StateBadge tone={statusTone(verification.status)}>{STATUS_LABEL[verification.status] || verification.status}</StateBadge>
                  <span className="text-sm text-[color:var(--ops-text-muted)]">{verification.profile}</span>
                  <span className="text-sm text-[color:var(--ops-text-muted)]">{verification.verification_agent_label || verification.verification_agent_id || 'Verification Agent'}</span>
                </div>
                <div className="mt-3 text-sm text-[color:var(--ops-text-body)]">
                  <Markdown value={verification.summary_markdown} />
                </div>
                {verification.reasoning_markdown ? (
                  <div className="mt-3 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white p-4 text-sm text-[color:var(--ops-text-body)]">
                    <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Reasoning</div>
                    <Markdown value={verification.reasoning_markdown} />
                  </div>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-3 text-xs text-[color:var(--ops-text-caption)]">
                  <span>next action: {verification.suggested_next_action || '-'}</span>
                  <span>resolution: {verification.resolution_path || verification.resolution_recommendation || '-'}</span>
                  <span>evidence: {verification.evidence_used.length > 0 ? verification.evidence_used.join(' · ') : '-'}</span>
                </div>
                {verification.resolution_reason ? (
                  <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">{verification.resolution_reason}</div>
                ) : null}
                {verification.followup_requirement_id ? (
                  <div className="mt-3">
                    <button
                      className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm"
                      onClick={() => navigate(`/requirements/${verification.followup_requirement_id}`)}
                    >
                      查看 follow-up requirement #{verification.followup_requirement_id}
                    </button>
                  </div>
                ) : null}
              </div>
              <div className="space-y-3">
                {verification.checks.map((check) => (
                  <article key={`${check.label}-${check.command || 'manual'}`} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white p-4">
                    <div className="font-medium text-[color:var(--ops-text-title)]">{check.label}</div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">
                      {check.command || 'verification evidence'} · {check.project_path || '-'}
                    </div>
                    <div className="mt-2 text-sm text-[color:var(--ops-text-body)]">{check.status}</div>
                    {check.output_excerpt ? <pre className="mt-3 overflow-x-auto rounded-xl bg-slate-950/95 p-3 text-xs text-slate-100">{check.output_excerpt}</pre> : null}
                  </article>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-sm text-[color:var(--ops-text-muted)]">验证 agent 结果生成后会显示在这里。</div>
          )}
        </SectionFrame>

        <ActivityFeed eyebrow="Activity" title="执行活动流">
          {detail.activity_stream.length > 0 ? (
            <div className="space-y-3">
              {detail.activity_stream.map((item, index) => (
                <div key={`${item.event}-${item.ts || index}`} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <StateBadge tone={statusTone(item.status || 'queued')}>{item.event}</StateBadge>
                      {item.status ? <span className="text-xs text-[color:var(--ops-text-caption)]">{item.status}</span> : null}
                    </div>
                    <div className="text-xs text-[color:var(--ops-text-caption)]">{formatTime(item.ts)}</div>
                  </div>
                  <div className="mt-2 text-sm text-[color:var(--ops-text-body)]">{item.message}</div>
                </div>
              ))}
              {detail.incidents.map((incident, index) => (
                <div key={`incident-${index}`} className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] p-4 text-sm text-[color:var(--ops-state-blocked-text)]">
                  <div className="font-medium">{String(incident.kind || 'incident')}</div>
                  <div className="mt-2">{String(incident.summary || '')}</div>
                </div>
              ))}
            </div>
          ) : detail.incidents.length > 0 ? (
            <div className="space-y-3">
              {detail.incidents.map((incident, index) => (
                <div key={`incident-${index}`} className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] p-4 text-sm text-[color:var(--ops-state-blocked-text)]">
                  <div className="font-medium">{String(incident.kind || 'incident')}</div>
                  <div className="mt-2">{String(incident.summary || '')}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-[color:var(--ops-text-muted)]">暂无活动事件。</div>
          )}
        </ActivityFeed>
      </div>

      <SectionFrame eyebrow="Agent Output" title="原始执行输出">
        {detail.raw_task_output ? (
          <div className="space-y-3">
            {detail.raw_task_output_truncated ? (
              <div className="rounded-2xl border border-[color:var(--ops-state-validating-border)] bg-[color:var(--ops-state-validating-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-validating-text)]">
                原始输出较长，当前为截断预览。
              </div>
            ) : null}
            <pre className="overflow-x-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">
              {detail.raw_task_output}
            </pre>
          </div>
        ) : (
          <div className="text-sm text-[color:var(--ops-text-muted)]">当前还没有原始执行输出。</div>
        )}
      </SectionFrame>

      <OverlayModal
        open={Boolean(previewPath)}
        eyebrow="File Preview"
        title={previewPath || '文件预览'}
        description="默认先看 diff，必要时再看当前文件内容。"
        onClose={closePreview}
        actions={
          preview ? (
            <div className="flex gap-2">
              <button
                type="button"
                className={`rounded-2xl px-3 py-2 text-sm ${previewTab === 'diff' ? 'bg-blue-600 text-white' : 'border border-[color:var(--ops-stroke-strong)] text-[color:var(--ops-text-body)]'}`}
                onClick={() => setPreviewTab('diff')}
                disabled={!preview.diff_patch}
              >
                Diff
              </button>
              <button
                type="button"
                className={`rounded-2xl px-3 py-2 text-sm ${previewTab === 'content' ? 'bg-blue-600 text-white' : 'border border-[color:var(--ops-stroke-strong)] text-[color:var(--ops-text-body)]'}`}
                onClick={() => setPreviewTab('content')}
                disabled={!preview.current_content}
              >
                当前内容
              </button>
            </div>
          ) : null
        }
      >
        {previewLoading ? (
          <LoadingPane>正在加载文件预览…</LoadingPane>
        ) : preview ? (
          <div className="space-y-3">
            {preview.truncated ? (
              <div className="rounded-2xl border border-[color:var(--ops-state-validating-border)] bg-[color:var(--ops-state-validating-bg)] px-4 py-3 text-sm text-[color:var(--ops-state-validating-text)]">
                预览内容较长，已截断显示。
              </div>
            ) : null}
            <pre className="overflow-x-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">
              {previewTab === 'diff' ? (preview.diff_patch || '暂无 diff。') : (preview.current_content || '暂无当前文件内容。')}
            </pre>
          </div>
        ) : (
          <div className="text-sm text-[color:var(--ops-text-muted)]">暂无文件预览。</div>
        )}
      </OverlayModal>
    </div>
  )
}
