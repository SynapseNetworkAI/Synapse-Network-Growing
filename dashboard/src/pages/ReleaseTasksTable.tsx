import { ReleaseTask } from '../api'
import { EmptyPane, StateBadge } from '../components/workbench'
import {
  ReleaseTaskCompactFailure,
  ReleaseTaskFailureSnippet,
  ReleaseTaskPrGate,
  releaseTaskFailureSummary,
  shouldShowReleaseTaskFailure,
} from './ReleaseTaskDetailPanel'
import { STATUS_LABEL, releaseTone } from './releaseListUi'

const SOURCE_LABEL: Record<string, string> = {
  manual: '人工创建',
  requirement_flow: '需求流转',
}

export type GateRequestState = {
  status: 'idle' | 'loading' | 'ready' | 'error'
  gate?: ReleaseTask['pr_gate']
  error?: string
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function CompactListText({ value }: Readonly<{ value: string | null | undefined }>) {
  const summary = releaseTaskFailureSummary(value, 180)
  if (!summary.text) return <span>-</span>
  return (
    <div>
      <div className="line-clamp-2">{summary.text}</div>
      {summary.truncated ? <div className="mt-1 text-[11px] text-[color:var(--ops-text-caption)]">详情查看完整内容</div> : null}
    </div>
  )
}

function shortDigest(value: string) {
  const match = value.match(/sha256:([0-9a-f]{64})/i)
  return match ? `sha256:${match[1].slice(0, 12)}…` : value.slice(0, 24)
}

function shortSha(value: unknown) {
  const text = typeof value === 'string' ? value.trim() : ''
  return text ? `${text.slice(0, 12)}${text.length > 12 ? '…' : ''}` : ''
}

function isFrontendPrebuiltCandidate(task: ReleaseTask) {
  return task.environment === 'staging'
    && task.project_key === 'synapse-network'
    && task.status === 'requested'
    && ['admin-front', 'user-front', 'docs-front'].includes(task.service_key || '')
}

export function ReleaseTasksTable({
  tasks,
  total,
  limit,
  offset,
  loading,
  busyAction,
  gateStatusByTaskId,
  onUpdateStatus,
  onCreatePr,
  onDeployStaging,
  onDeployProduction,
  onRefreshGate,
  onRefresh,
  onOpenDetails,
  onPage,
}: Readonly<{
  tasks: ReleaseTask[]
  total: number
  limit: number
  offset: number
  loading: boolean
  busyAction: string | null
  gateStatusByTaskId: Record<number, GateRequestState>
  onUpdateStatus: (task: ReleaseTask, status: 'completed' | 'failed' | 'cancelled') => void
  onCreatePr: (task: ReleaseTask) => void
  onDeployStaging: (task: ReleaseTask) => void
  onDeployProduction: (task: ReleaseTask) => void
  onRefreshGate: (task: ReleaseTask) => void
  onRefresh: () => void
  onOpenDetails: (task: ReleaseTask) => void
  onPage: (offset: number) => void
}>) {
  const pageNumber = Math.floor(offset / limit) + 1
  const canPrev = offset > 0
  const canNext = offset + limit < total
  return (
    <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse">
          <thead className="bg-[color:var(--ops-panel-subtle)]">
            <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
              <th className="px-5 py-4 font-medium">来源</th>
              <th className="px-4 py-4 font-medium">项目 / 分支</th>
              <th className="px-4 py-4 font-medium">环境</th>
              <th className="px-4 py-4 font-medium">状态</th>
              <th className="px-4 py-4 font-medium">创建 / 执行</th>
              <th className="px-4 py-4 font-medium">备注</th>
              <th className="px-4 py-4 font-medium">更新时间</th>
              <th className="px-5 py-4 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => {
              const gateState = gateStatusByTaskId[task.id]
              const effectiveTask = gateState?.gate ? { ...task, pr_gate: gateState.gate } : task
              const effectiveGate = effectiveTask.pr_gate
              const taskMetadata = (task as ReleaseTask & { task_metadata?: Record<string, unknown> }).task_metadata || {}
              const prebuiltImageDigest = typeof taskMetadata.prebuiltImageDigest === 'string'
                ? taskMetadata.prebuiltImageDigest
                : ''
              const prebuiltCommit = shortSha(taskMetadata.sourceCommitSha)
              const gateLoading = gateState?.status === 'loading'
              const gateError = gateState?.status === 'error'
              const gateReady = gateState?.status === 'ready'
              const shouldCheckGate = task.status === 'requested' && ['staging', 'production'].includes(task.environment)
              return (
                <tr key={task.id} className="border-t border-[color:var(--ops-stroke-soft)] hover:bg-[color:var(--ops-panel-subtle)]">
                  <td className="px-5 py-4">
                    <StateBadge tone={task.source_type === 'requirement_flow' ? 'running' : 'muted'}>
                      {SOURCE_LABEL[task.source_type] || task.source_type}
                    </StateBadge>
                    {task.requirement_id ? <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">Requirement #{task.requirement_id}</div> : null}
                  </td>
                  <td className="px-4 py-4">
                    <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{task.project_display_name || task.project_key}</div>
                    {task.service_key ? <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">Service: {task.service_key}</div> : null}
                    <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-muted)]">{task.branch_name}</div>
                  </td>
                  <td className="px-4 py-4">
                    <StateBadge tone={task.environment === 'production' ? 'blocked' : 'ready'}>{task.environment}</StateBadge>
                  </td>
                  <td className="px-4 py-4">
                    <StateBadge tone={releaseTone(task.status)}>{STATUS_LABEL[task.status] || task.status}</StateBadge>
                    {task.deployment_status ? (
                      <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">
                        Deploy: {STATUS_LABEL[task.deployment_status] || task.deployment_status}
                      </div>
                    ) : null}
                    {task.status === 'deploying' && task.branch_name ? (
                      <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">
                        Deploy branch: <span className="font-mono">{task.branch_name}</span>
                      </div>
                    ) : null}
                    {prebuiltImageDigest ? (
                      <div className="mt-2 max-w-xs rounded-lg border border-[color:var(--ops-state-ready-border)] bg-[color:var(--ops-state-ready-bg)] px-2 py-1 text-xs text-[color:var(--ops-state-ready-text)]">
                        <div>Prebuilt image attached · {shortDigest(prebuiltImageDigest)}</div>
                        {prebuiltCommit ? <div className="mt-1 font-mono text-[11px]">commit {prebuiltCommit}</div> : null}
                      </div>
                    ) : isFrontendPrebuiltCandidate(task) ? (
                      <div className="mt-2 max-w-xs rounded-lg border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-2 py-1 text-xs text-[color:var(--ops-text-caption)]">
                        未绑定 Prebuilt image；发布将走 Cloud Build，预计多约 5 分钟。
                      </div>
                    ) : null}
                    {task.deployment_health_status ? <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">Health: {STATUS_LABEL[task.deployment_health_status] || task.deployment_health_status}</div> : null}
                    {shouldShowReleaseTaskFailure(task) && task.deployment_failure_summary ? (
                      <ReleaseTaskCompactFailure value={task.deployment_failure_summary} />
                    ) : null}
                    <ReleaseTaskFailureSnippet task={task} />
                    {shouldCheckGate ? (
                      <>
                        <ReleaseTaskPrGate task={effectiveTask} />
                        {gateLoading ? (
                          <div className="mt-2 text-xs text-[color:var(--ops-state-running-text)]">Gate: 检查中…</div>
                        ) : null}
                        {gateError ? (
                          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-[color:var(--ops-state-blocked-text)]">
                            <span title={gateState?.error}>检查失败</span>
                            <button
                              type="button"
                              className="rounded-md border border-[color:var(--ops-state-blocked-border)] px-2 py-1"
                              onClick={() => onRefreshGate(task)}
                            >
                              重新检查
                            </button>
                          </div>
                        ) : null}
                      </>
                    ) : null}
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                    <div>创建：{task.actor || '-'}</div>
                    <div className="mt-1">执行：{task.operator || '-'}</div>
                  </td>
                  <td className="max-w-xs px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                    <CompactListText value={task.note} />
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(task.updated_at || task.created_at)}</td>
                  <td className="px-5 py-4">
                    {busyAction?.startsWith(`release-task-${task.id}-`) ? (
                      <div className="mb-2 rounded-lg border border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] px-3 py-2 text-xs font-semibold text-[color:var(--ops-state-running-text)]">
                        正在更新发布任务…
                      </div>
                    ) : null}
                    {task.status === 'requested' ? (
                      <div className="flex flex-wrap justify-end gap-2">
                        <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => onOpenDetails(task)}>
                          详情
                        </button>
                        {task.environment === 'staging' && effectiveGate?.can_create_pr ? (
                          <button type="button" className="rounded-lg border border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] px-3 py-2 text-sm font-semibold text-[color:var(--ops-state-running-text)] disabled:opacity-50" disabled={Boolean(busyAction)} onClick={() => onCreatePr(task)}>
                            {busyAction === `release-task-${task.id}-create-pr` ? '提交中…' : '提交 PR'}
                          </button>
                        ) : null}
                        {task.environment === 'staging' && effectiveGate?.pr_url ? (
                          <a className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" href={effectiveGate.pr_url} target="_blank" rel="noreferrer">
                            查看 PR
                          </a>
                        ) : null}
                        {task.environment === 'staging' && shouldCheckGate && !gateReady ? (
                          <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" disabled={Boolean(busyAction) || gateLoading} onClick={() => onRefreshGate(task)}>
                            {gateLoading ? '检查中…' : gateError ? '重新检查' : '先检查 Gate'}
                          </button>
                        ) : null}
                        {task.environment === 'staging' && !task.deployment_record_id && gateReady && effectiveGate?.can_deploy_staging ? (
                          <button type="button" className="rounded-lg border border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] px-3 py-2 text-sm font-semibold text-[color:var(--ops-state-running-text)] disabled:opacity-50" disabled={Boolean(busyAction)} onClick={() => onDeployStaging(task)}>
                            {busyAction === `release-task-${task.id}-deploy-staging` ? '发布中…' : '发布到 staging'}
                          </button>
                        ) : null}
                        {task.environment === 'staging' && gateReady && effectiveGate?.pr_exists && effectiveGate?.checks_status === 'success' && !effectiveGate?.can_deploy_staging ? (
                          <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm text-[color:var(--ops-text-caption)] opacity-70" disabled title={effectiveGate.blocked_reason || 'PR gate 尚未允许 staging 发布'}>
                            发布到 staging
                          </button>
                        ) : null}
                        {task.environment === 'production' && gateReady && effectiveGate?.can_deploy_production && !task.deployment_record_id ? (
                          <button type="button" className="rounded-lg border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] px-3 py-2 text-sm font-semibold text-[color:var(--ops-state-blocked-text)] disabled:opacity-50" disabled={Boolean(busyAction)} onClick={() => onDeployProduction(task)}>
                            {busyAction === `release-task-${task.id}-deploy-production` ? '发布中…' : '发布到 production'}
                          </button>
                        ) : task.environment === 'production' && shouldCheckGate && !gateReady ? (
                          <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" disabled={Boolean(busyAction) || gateLoading} onClick={() => onRefreshGate(task)}>
                            {gateLoading ? '检查中…' : gateError ? '重新检查' : '先检查 Gate'}
                          </button>
                        ) : task.environment === 'production' ? (
                          <span className="rounded-lg border border-[color:var(--ops-state-blocked-border)] px-3 py-2 text-sm text-[color:var(--ops-state-blocked-text)]" title={effectiveGate?.blocked_reason || undefined}>
                            {effectiveGate?.blocked_reason || 'Production 需 Human Gate'}
                          </span>
                        ) : null}
                        <button type="button" className="rounded-lg border border-[color:var(--ops-state-ready-border)] px-3 py-2 text-sm text-[color:var(--ops-state-ready-text)] disabled:opacity-50" disabled={Boolean(busyAction)} onClick={() => onUpdateStatus(task, 'completed')}>
                          {busyAction === `release-task-${task.id}-completed` ? '处理中…' : '标记为已完成'}
                        </button>
                        <button type="button" className="rounded-lg border border-[color:var(--ops-state-blocked-border)] px-3 py-2 text-sm text-[color:var(--ops-state-blocked-text)] disabled:opacity-50" disabled={Boolean(busyAction)} onClick={() => onUpdateStatus(task, 'failed')}>
                          {busyAction === `release-task-${task.id}-failed` ? '处理中…' : '标记为失败'}
                        </button>
                        <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-50" disabled={Boolean(busyAction)} onClick={() => onUpdateStatus(task, 'cancelled')}>
                          {busyAction === `release-task-${task.id}-cancelled` ? '处理中…' : '取消'}
                        </button>
                      </div>
                    ) : (
                      <div className="flex flex-wrap justify-end gap-2">
                        <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => onOpenDetails(task)}>
                          详情
                        </button>
                        {task.status === 'deploying' && task.deployment_external_url ? <a className="rounded-lg border border-[color:var(--ops-state-running-border)] px-3 py-2 text-sm text-[color:var(--ops-state-running-text)]" href={task.deployment_external_url} target="_blank" rel="noreferrer">GitHub Actions</a> : null}
                        {task.status === 'deploying' ? (
                          <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" disabled={Boolean(busyAction)} onClick={onRefresh}>
                            同步状态
                          </button>
                        ) : null}
                      </div>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {!loading && tasks.length === 0 ? (
        <div className="p-6">
          <EmptyPane>暂无发布任务。点击“新建发布任务”记录一次人工分支发布。</EmptyPane>
        </div>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4 text-sm text-[color:var(--ops-text-muted)]">
        <span>第 {pageNumber} 页 · 共 {total} 条发布任务</span>
        <div className="flex gap-2">
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-2 disabled:opacity-40" disabled={!canPrev || loading} onClick={() => onPage(Math.max(0, offset - limit))}>
            上一页
          </button>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-2 disabled:opacity-40" disabled={!canNext || loading} onClick={() => onPage(offset + limit)}>
            下一页
          </button>
        </div>
      </div>
    </section>
  )
}
