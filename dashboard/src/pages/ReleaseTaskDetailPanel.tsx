import { useState } from 'react'
import { ReleaseTask } from '../api'
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
  onAttachPrebuiltImage,
}: Readonly<{
  task: ReleaseTask | null
  onClose: () => void
  onRefresh: () => void
  onAttachPrebuiltImage?: (
    task: ReleaseTask,
    payload: { image_digest: string; source_commit_sha: string },
  ) => Promise<void>
}>) {
  const [prebuiltDigest, setPrebuiltDigest] = useState('')
  const [prebuiltCommit, setPrebuiltCommit] = useState('')
  const [prebuiltBusy, setPrebuiltBusy] = useState(false)
  if (!task) return null
  const hasDeployment = Boolean(task.deployment_record_id)
  const showFailure = shouldShowReleaseTaskFailure(task)
  const failureLogExcerpt = showFailure ? releaseTaskFailureLogExcerpt(task) : null
  const failureLogError = showFailure ? releaseTaskFailureLogError(task) : null
  const safeMetadata = displayDeploymentMetadata(task)
  const taskMetadata = (task as ReleaseTask & { task_metadata?: Record<string, unknown> }).task_metadata || {}
  const attachedPrebuiltImage = metadataString(taskMetadata, 'prebuiltImageDigest')
  const attachedPrebuiltCommit = metadataString(taskMetadata, 'sourceCommitSha')
  const isPrebuiltFrontendTask = task.environment === 'staging'
    && task.project_key === 'synapse-network'
    && ['admin-front', 'user-front', 'docs-front'].includes(task.service_key || '')
  const canAttachPrebuiltImage = task.environment === 'staging'
    && isPrebuiltFrontendTask
    && task.status === 'requested'
    && !task.deployment_record_id
    && Boolean(onAttachPrebuiltImage)
  const submitPrebuiltImage = async () => {
    if (!task || !onAttachPrebuiltImage) return
    setPrebuiltBusy(true)
    try {
      await onAttachPrebuiltImage(task, {
        image_digest: prebuiltDigest.trim(),
        source_commit_sha: prebuiltCommit.trim(),
      })
      setPrebuiltDigest('')
      setPrebuiltCommit('')
    } finally {
      setPrebuiltBusy(false)
    }
  }
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

        {isPrebuiltFrontendTask ? (
          <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
            <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Prebuilt Image</h3>
            {attachedPrebuiltImage ? (
              <div className="mt-3 space-y-2 rounded-xl border border-[color:var(--ops-state-ready-border)] bg-[color:var(--ops-state-ready-bg)] p-3 text-sm text-[color:var(--ops-state-ready-text)]">
                <div>Prebuilt image attached. Staging frontend workflow will deploy by immutable digest and skip Cloud Build.</div>
                <div className="break-all font-mono text-xs">{attachedPrebuiltImage}</div>
                {attachedPrebuiltCommit ? <div className="font-mono text-xs">commit {attachedPrebuiltCommit}</div> : null}
              </div>
            ) : (
              <div className="mt-3 rounded-xl bg-[color:var(--ops-panel)] p-3 text-sm text-[color:var(--ops-text-muted)]">
                可选：先用本地 ephemeral worktree 构建并推送镜像，再把 immutable digest 绑定到此任务。发布时 Actions 会校验 digest 并直接部署。
              </div>
            )}
            {canAttachPrebuiltImage ? (
              <div className="mt-4 grid gap-3 md:grid-cols-[1.5fr_1fr_auto]">
                <label className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                  image@sha256 digest
                  <input
                    className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-3 py-2 font-mono text-xs text-[color:var(--ops-text-title)]"
                    value={prebuiltDigest}
                    onChange={(event) => setPrebuiltDigest(event.target.value)}
                    placeholder={`us-central1-docker.pkg.dev/.../${task.service_key}@sha256:...`}
                  />
                </label>
                <label className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                  source commit
                  <input
                    className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-3 py-2 font-mono text-xs text-[color:var(--ops-text-title)]"
                    value={prebuiltCommit}
                    onChange={(event) => setPrebuiltCommit(event.target.value)}
                    placeholder="40-char sha"
                  />
                </label>
                <button
                  type="button"
                  className="self-end rounded-xl border border-[color:var(--ops-state-running-border)] px-4 py-2 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-50"
                  disabled={prebuiltBusy || !prebuiltDigest.trim() || !prebuiltCommit.trim()}
                  onClick={submitPrebuiltImage}
                >
                  {prebuiltBusy ? '绑定中…' : '绑定镜像'}
                </button>
              </div>
            ) : null}
          </section>
        ) : null}

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
      </div>
    </OverlayModal>
  )
}

export function ReleaseTaskPrGate({ task }: Readonly<{ task: ReleaseTask }>) {
  const gate = task.pr_gate
  if (!gate) return null
  if (task.environment === 'production') {
    const ready = Boolean(gate.can_deploy_production)
    return (
      <div className="mt-2 space-y-1">
        <StateBadge tone={ready ? 'delivered' : 'blocked'}>Production Gate: {ready ? '已满足' : gate.blocked_reason || '待满足'}</StateBadge>
        {gate.environment_gate_summary ? <div className="max-w-xs text-xs text-[color:var(--ops-text-caption)]">{gate.environment_gate_summary}</div> : null}
        {gate.resolved_commit_sha ? <div className="max-w-xs font-mono text-xs text-[color:var(--ops-text-caption)]">main {gate.resolved_commit_sha.slice(0, 12)}</div> : null}
        {gate.staging_deployment_record_id ? <div className="max-w-xs text-xs text-[color:var(--ops-text-caption)]">staging deployment #{gate.staging_deployment_record_id}</div> : null}
      </div>
    )
  }
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
