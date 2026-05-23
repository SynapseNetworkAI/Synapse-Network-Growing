import { useEffect, useState } from 'react'
import { ReleaseTask } from '../api'
import { DeploymentEvent, getDeploymentEvents } from '../apiDeployments'
import { OverlayModal, StateBadge } from '../components/workbench'
import { STATUS_LABEL, releaseTone } from './releaseListUi'

const SOURCE_LABEL: Record<string, string> = {
  manual: '人工创建',
  requirement_flow: '需求流转',
}

const FAILURE_METADATA_KEYS = new Set([
  'deploymentSyncError',
  'deploymentSyncFailureKind',
  'deploymentSyncPendingReason',
  'githubFailureLogError',
  'githubFailureLogExcerpt',
  'githubFailureLogStatus',
  'githubFailureLogSyncedAt',
])

const COMPACT_FAILURE_LIMIT = 220

function metadataString(source: Record<string, unknown> | null | undefined, ...keys: string[]) {
  for (const key of keys) {
    const value = source?.[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return null
}

function compactWhitespace(value: string) {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function releaseTaskFailureSummary(value: string | null | undefined, maxLength = COMPACT_FAILURE_LIMIT) {
  const text = compactWhitespace(value || '')
  if (!text) return { text: '', truncated: false }
  if (text.length <= maxLength) return { text, truncated: false }
  return { text: `${text.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`, truncated: true }
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

export function releaseTaskFailureLogExcerpt(task: ReleaseTask) {
  return metadataString(task.deployment_metadata, 'githubFailureLogExcerpt')
}

export function releaseTaskFailureLogError(task: ReleaseTask) {
  return metadataString(task.deployment_metadata, 'githubFailureLogError')
}

export function shouldShowReleaseTaskFailure(task: ReleaseTask) {
  const statusTokens = [
    task.status,
    task.deployment_status,
    task.deployment_health_status,
  ].map((value) => String(value || '').toLowerCase())
  if (statusTokens.some((value) => ['completed', 'succeeded', 'passed', 'healthy'].includes(value))) {
    return false
  }
  return statusTokens.some((value) => ['failed', 'blocked', 'cancelled', 'timed_out', 'startup_failure', 'action_required'].includes(value))
}

function displayDeploymentMetadata(task: ReleaseTask) {
  const metadata = task.deployment_metadata || {}
  if (shouldShowReleaseTaskFailure(task)) return metadata
  return Object.fromEntries(
    Object.entries(metadata).filter(([key]) => !FAILURE_METADATA_KEYS.has(key)),
  )
}

function AgentApprovalGate({ metadata }: Readonly<{ metadata: Record<string, unknown> }>) {
  const approval = metadata.agent_approval || metadata.production_agent_approval
  if (!approval || typeof approval !== 'object') return null
  const gate = approval as Record<string, unknown>
  const blockedReasons = Array.isArray(gate.blocked_reasons)
    ? gate.blocked_reasons.map((item) => String(item))
    : []
  return (
    <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Agent Approval Gate</div>
        <StateBadge tone={blockedReasons.length ? 'blocked' : 'delivered'}>
          {String(gate.status || (blockedReasons.length ? 'agent_blocked' : 'passed'))}
        </StateBadge>
      </div>
      <div className="grid gap-2 text-xs text-[color:var(--ops-text-muted)] md:grid-cols-2">
        <span>reviewer: {String(gate.actor || 'agent_release_reviewer')}</span>
        <span>risk: {String(gate.risk_score ?? '-')}</span>
        <span>staging record: {String(gate.staging_record_id ?? '-')}</span>
        <span>rollback target: {String(gate.rollback_target_record_id ?? '-')}</span>
      </div>
      {blockedReasons.length ? (
        <div className="mt-2 text-xs text-[color:var(--ops-state-blocked-text)]">
          {blockedReasons.join(' · ')}
        </div>
      ) : null}
    </div>
  )
}

export function ReleaseTaskCompactFailure({
  value,
  mono = false,
}: Readonly<{
  value: string | null | undefined
  mono?: boolean
}>) {
  const summary = releaseTaskFailureSummary(value)
  if (!summary.text) return null
  return (
    <div className="mt-2 max-w-xs">
      <div className={`line-clamp-2 text-xs text-[color:var(--ops-state-blocked-text)] ${mono ? 'font-mono text-[11px]' : ''}`}>
        {summary.text}
      </div>
      {summary.truncated ? (
        <div className="mt-1 text-[11px] text-[color:var(--ops-text-caption)]">详情查看完整失败日志</div>
      ) : null}
    </div>
  )
}

export function ReleaseTaskFailureSnippet({ task }: Readonly<{ task: ReleaseTask }>) {
  if (!shouldShowReleaseTaskFailure(task)) return null
  const excerpt = releaseTaskFailureLogExcerpt(task)
  const error = releaseTaskFailureLogError(task)
  if (excerpt) {
    return (
      <div className="mt-2 max-w-xs rounded-lg bg-[color:var(--ops-panel)] p-2 font-mono text-[11px] text-[color:var(--ops-state-blocked-text)]">
        <ReleaseTaskCompactFailure value={excerpt} mono />
      </div>
    )
  }
  if (error) {
    return (
      <div className="mt-2 max-w-xs rounded-lg bg-[color:var(--ops-panel)] p-2 text-[11px] text-[color:var(--ops-text-caption)]">
        Actions 日志读取失败：
        <ReleaseTaskCompactFailure value={error} />
      </div>
    )
  }
  return null
}

export function ReleaseTaskDetailModal({
  task,
  onClose,
  onRefresh,
}: Readonly<{
  task: ReleaseTask | null
  onClose: () => void
  onRefresh: () => void
}>) {
  const [deploymentEvents, setDeploymentEvents] = useState<DeploymentEvent[]>([])
  useEffect(() => {
    let cancelled = false
    setDeploymentEvents([])
    if (!task?.deployment_record_id) return () => { cancelled = true }
    getDeploymentEvents(task.deployment_record_id)
      .then((events) => { if (!cancelled) setDeploymentEvents(events) })
      .catch(() => { if (!cancelled) setDeploymentEvents([]) })
    return () => { cancelled = true }
  }, [task?.deployment_record_id])
  if (!task) return null
  const hasDeployment = Boolean(task.deployment_record_id)
  const showFailure = shouldShowReleaseTaskFailure(task)
  const failureLogExcerpt = showFailure ? releaseTaskFailureLogExcerpt(task) : null
  const failureLogError = showFailure ? releaseTaskFailureLogError(task) : null
  const safeMetadata = displayDeploymentMetadata(task)
  return (
    <OverlayModal
      open={Boolean(task)}
      eyebrow="Release Task Detail"
      title={`发布任务 #${task.id}`}
      description="查看 PR gate、DeploymentRecord、GitHub Actions 链接、健康检查和失败摘要。"
      onClose={onClose}
    >
      <div className="space-y-5">
        <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">
                {task.project_display_name || task.project_key} · {task.service_key || 'service'}
              </div>
              <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-muted)]">{task.branch_name}</div>
            </div>
            <div className="flex flex-wrap gap-2">
              <StateBadge tone={task.environment === 'production' ? 'blocked' : 'ready'}>{task.environment}</StateBadge>
              <StateBadge tone={releaseTone(task.status)}>{STATUS_LABEL[task.status] || task.status}</StateBadge>
            </div>
          </div>
          <div className="mt-4 grid gap-3 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-2">
            <div>来源：{SOURCE_LABEL[task.source_type] || task.source_type}</div>
            <div>创建人：{task.actor || '-'}</div>
            <div>执行人：{task.operator || '-'}</div>
            <div>更新时间：{formatTime(task.updated_at || task.created_at)}</div>
          </div>
          {task.note ? <div className="mt-4 rounded-xl bg-[color:var(--ops-panel)] p-3 text-sm text-[color:var(--ops-text-muted)]">{task.note}</div> : null}
        </section>

        <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">PR Gate</h3>
            <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-1.5 text-xs" onClick={onRefresh}>
              刷新状态
            </button>
          </div>
          <ReleaseTaskPrGate task={task} />
          {task.pr_gate?.pr_url ? (
            <a className="mt-3 inline-flex rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" href={task.pr_gate.pr_url} target="_blank" rel="noreferrer">
              打开 PR #{task.pr_gate.pr_number || ''}
            </a>
          ) : null}
        </section>

        <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
          <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Deployment Record</h3>
          {hasDeployment ? (
            <div className="mt-3 space-y-3 text-sm text-[color:var(--ops-text-muted)]">
              <div className="flex flex-wrap gap-2">
                <StateBadge tone={releaseTone(task.deployment_status || task.status)}>
                  Deploy: {STATUS_LABEL[task.deployment_status || ''] || task.deployment_status || '-'}
                </StateBadge>
                {task.deployment_health_status ? (
                  <StateBadge tone={releaseTone(task.deployment_health_status)}>
                    Health: {STATUS_LABEL[task.deployment_health_status] || task.deployment_health_status}
                  </StateBadge>
                ) : null}
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div>Record ID：{task.deployment_record_id}</div>
                <div>Workflow：{task.deployment_workflow_file || '-'}</div>
                <div>Run ID：{task.deployment_external_run_id || '-'}</div>
                <div>Commit：{task.deployment_commit_sha || '-'}</div>
                <div>Started：{formatTime(task.deployment_started_at)}</div>
                <div>Finished：{formatTime(task.deployment_finished_at)}</div>
              </div>
              {task.deployment_external_url ? (
                <a className="inline-flex rounded-lg border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)]" href={task.deployment_external_url} target="_blank" rel="noreferrer">
                  打开 GitHub Actions 日志
                </a>
              ) : null}
              {showFailure && task.deployment_failure_summary ? (
                <div className="rounded-xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] p-3 text-[color:var(--ops-state-blocked-text)]">
                  {task.deployment_failure_summary}
                </div>
              ) : null}
              <AgentApprovalGate metadata={task.deployment_metadata || {}} />
              {failureLogExcerpt ? (
                <div className="rounded-xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-panel)] p-3">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-state-blocked-text)]">GitHub Actions failed step</div>
                  <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-xs text-[color:var(--ops-text-muted)]">{failureLogExcerpt}</pre>
                </div>
              ) : failureLogError ? (
                <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-3 text-sm text-[color:var(--ops-text-muted)]">
                  无法读取 GitHub Actions 失败日志：{failureLogError}
                  <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">
                    私有仓库需要后端运行环境的 GitHub token 拥有该 repo 的 Actions read / Contents read 权限；classic PAT 需要 repo + workflow scope。
                  </div>
                </div>
              ) : null}
              <details className="rounded-xl bg-[color:var(--ops-panel)] p-3">
                <summary className="cursor-pointer text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Deployment metadata</summary>
                <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap text-xs text-[color:var(--ops-text-muted)]">
                  {JSON.stringify(safeMetadata, null, 2)}
                </pre>
              </details>
            </div>
          ) : (
            <div className="mt-3 rounded-xl bg-[color:var(--ops-panel)] p-3 text-sm text-[color:var(--ops-text-muted)]">
              还没有 DeploymentRecord。只有点击“发布到 staging”并通过 PR gate 后，系统才会创建部署记录并写入 GitHub Actions 链接、健康检查和结果。
            </div>
          )}
        </section>

        {hasDeployment ? (
          <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
            <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Deployment Events</h3>
            {deploymentEvents.length ? (
              <div className="mt-3 space-y-2">
                {deploymentEvents.map((event) => (
                  <div key={event.id} className="rounded-xl bg-[color:var(--ops-panel)] p-3 text-sm text-[color:var(--ops-text-muted)]">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <b className="text-[color:var(--ops-text-title)]">{event.event_type}</b>
                      <span className="font-mono text-xs text-[color:var(--ops-text-caption)]">{formatTime(event.created_at)}</span>
                    </div>
                    <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">
                      {event.status_from || '-'} → {event.status_to || '-'} · {event.actor || 'system'}
                    </div>
                    {event.summary ? <div className="mt-2 text-xs">{event.summary}</div> : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-3 rounded-xl bg-[color:var(--ops-panel)] p-3 text-sm text-[color:var(--ops-text-caption)]">暂无 deployment_events。旧记录可能只包含 DeploymentRecord 字段。</div>
            )}
          </section>
        ) : null}
      </div>
    </OverlayModal>
  )
}

export function ReleaseTaskPrGate({ task }: Readonly<{ task: ReleaseTask }>) {
  const gate = task.pr_gate
  if (!gate) return null
  let label = gate.blocked_reason || 'PR gate 待同步'
  let tone: 'ready' | 'running' | 'blocked' | 'muted' | 'delivered' = 'muted'
  if (!gate.branch_exists) {
    label = '分支不存在'
    tone = 'blocked'
  } else if (task.pr_gate?.can_deploy_staging && !gate.pr_exists && task.branch_name === 'main') {
    label = 'main 可直接发布 staging'
    tone = 'delivered'
  } else if (!gate.pr_exists) {
    label = '未提交 PR'
    tone = 'running'
  } else if (gate.pr_state === 'draft') {
    label = 'PR 是 Draft'
    tone = 'blocked'
  } else if (gate.pr_state === 'merged' && gate.checks_status === 'success') {
    label = 'PR 已合并 / Checks 通过'
    tone = 'delivered'
  } else if (gate.checks_status === 'success') {
    label = 'Checks 通过'
    tone = 'delivered'
  } else if (gate.checks_status === 'failed') {
    label = 'Checks 失败'
    tone = 'blocked'
  } else if (gate.checks_status === 'pending') {
    label = 'Checks 运行中'
    tone = 'running'
  }
  return (
    <div className="mt-2 space-y-1">
      <StateBadge tone={tone}>PR Gate: {label}</StateBadge>
      {gate.checks_summary ? <div className="max-w-xs text-xs text-[color:var(--ops-text-caption)]">{gate.checks_summary}</div> : null}
      {gate.blocked_reason && label !== gate.blocked_reason ? (
        <div className="max-w-xs text-xs text-[color:var(--ops-state-blocked-text)]">{gate.blocked_reason}</div>
      ) : null}
    </div>
  )
}
