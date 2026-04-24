import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { DeployScope, ReleaseDetail, api } from '../api'
import { ActivityFeed, FieldLabel, InspectorRail, LoadingPane, SectionFrame, StateBadge } from '../components/workbench'

const STATUS_LABEL: Record<string, string> = {
  pending: '待交付',
  preparing_branch: '准备分支',
  pushing: '推送中',
  opening_pr: '打开 PR',
  repairing: '交付修复中',
  blocked: '阻塞',
  pr_open: 'PR 已打开',
  pr_opened: 'PR 已打开',
  pr_closed: 'PR 已关闭',
  ready_for_merge: '等待合并',
  merged: '已合并',
  abandoned: '已废弃',
  no_deploy: '无需部署',
}

function releaseTone(state: string | null | undefined) {
  if (state === 'merged') return 'delivered'
  if (state === 'pr_open' || state === 'pr_opened' || state === 'ready_for_merge') return 'ready'
  if (state === 'repairing' || state === 'pushing' || state === 'opening_pr' || state === 'preparing_branch') return 'running'
  if (state === 'blocked' || state === 'pr_closed' || state === 'abandoned') return 'blocked'
  if (state === 'pending') return 'ready'
  return 'muted'
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

export default function ReleaseDetailPage() {
  const { requirementId } = useParams<{ requirementId: string }>()
  const navigate = useNavigate()
  const id = Number(requirementId)
  const [detail, setDetail] = useState<ReleaseDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [deployScope, setDeployScope] = useState<DeployScope>('auto')

  const load = async () => {
    setLoading(true)
    try {
      setDetail(await api.getReleaseDetail(id))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [id])

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
    return <LoadingPane>正在加载发布详情…</LoadingPane>
  }

  const release = detail.release
  const releaseState = release?.status || release?.state || 'pending'
  const workflowRunId = detail.requirement.active_workflow_run_id ?? detail.requirement.active_workflow_run_summary?.id ?? null
  const workspaceBlocker = release?.workspace_blocker || null
  const isWorkspaceBlocked =
    release?.delivery_blocker_type === 'workspace_blocked' ||
    release?.blocker_kind === 'workspace_blocked'
  const plannedBranchName = release?.planned_branch_name || workspaceBlocker?.target_branch || release?.branch_name || null
  const actualBranchName = release?.actual_branch_name || release?.branch_name || null
  const deploymentSourceRef = actualBranchName || release?.commit_sha || ''

  return (
    <div className="space-y-[var(--ops-section-gap)]" data-testid="release-detail-page">
      <SectionFrame
        eyebrow="Release Record"
        title={`Requirement #${detail.requirement.id} 发布详情`}
        description="Release 面统一处理 prepare、PR、deploy 和 rollback，不回灌 requirement 细节编辑。"
        actions={
          <div className="flex flex-wrap gap-2">
            <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/requirements/${detail.requirement.id}`)}>
              查看需求
            </button>
            {workflowRunId && (
              <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/workflows/${workflowRunId}`)}>
                查看工作流
              </button>
            )}
          </div>
        }
      >
        <div className="flex flex-wrap gap-2">
          <StateBadge tone="muted">{detail.requirement.title}</StateBadge>
          {release?.project_display_name || detail.requirement.project_display_name ? (
            <StateBadge tone="muted">{release?.project_display_name || detail.requirement.project_display_name}</StateBadge>
          ) : null}
          <StateBadge tone={releaseTone(releaseState)}>{STATUS_LABEL[releaseState] || releaseState}</StateBadge>
          <StateBadge tone={detail.validation?.status === 'passed' ? 'delivered' : 'validating'}>
            {detail.validation?.status || 'pending_validation'}
          </StateBadge>
        </div>
        <div className="mt-4 grid gap-3 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-2 xl:grid-cols-4">
          <div>project: {release?.project_display_name || detail.requirement.project_display_name || detail.requirement.project_key || '-'}</div>
          <div>release state: {releaseState}</div>
          <div>delivery blocker: {release?.blocker_kind || release?.delivery_blocker_type || '-'}</div>
          <div>next action: {release?.next_action || '-'}</div>
          <div>validation: {detail.validation?.status || '-'}</div>
          <div>latest deploy: {detail.deployments[0]?.environment || '-'}</div>
          <div>repairability: {release?.repairability || '-'}</div>
          <div>workspace mode: {release?.workspace_mode || workspaceBlocker?.workspace_mode || 'shared_checkout'}</div>
        </div>
      </SectionFrame>

      <div className="grid gap-[var(--ops-section-gap)] xl:grid-cols-[minmax(0,1.4fr),minmax(300px,var(--ops-inspector-width))]">
        <SectionFrame eyebrow="Release Control" title="发布动作" description="只有 validate 通过后，才应该继续 prepare、open PR 和后续部署。">
          {isWorkspaceBlocked ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <div className="flex flex-wrap items-center gap-2">
                <StateBadge tone="blocked">workspace_blocked</StateBadge>
                <span>交付工作区阻塞，清理后可继续当前 release。</span>
              </div>
              <div className="mt-3 grid gap-2 text-xs md:grid-cols-2">
                <div>当前工作区分支：{workspaceBlocker?.current_branch || '-'}</div>
                <div>稳定目标分支：{plannedBranchName || '-'}</div>
                <div>实际交付分支：{actualBranchName || '-'}</div>
                <div>基线分支：{release?.base_branch || workspaceBlocker?.base_branch || '-'}</div>
                <div>dirty files：{workspaceBlocker?.dirty_file_count ?? '-'}</div>
                <div>next action：{release?.next_action || '-'}</div>
              </div>
              {workspaceBlocker?.dirty_files_preview?.length ? (
                <div className="mt-2 text-xs">脏文件预览：{workspaceBlocker.dirty_files_preview.join(' · ')}</div>
              ) : null}
              <div className="mt-2 text-xs">
                {workspaceBlocker?.recommended_operator_action ||
                  '如果这些改动属于当前需求，请先采纳到目标分支；否则清理工作区后点击“准备分支”。'}
              </div>
            </div>
          ) : null}

          <textarea
            className="mt-4 min-h-[120px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
            placeholder="记录本次 prepare / PR / deploy / rollback 备注"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />

          <div className="mt-4 flex flex-wrap gap-2">
            <label className="flex items-center gap-2 rounded-2xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm">
              <span className="text-[color:var(--ops-text-caption)]">Scope</span>
              <select className="bg-transparent text-[color:var(--ops-text-title)] outline-none" value={deployScope} onChange={(event) => setDeployScope(event.target.value as DeployScope)}>
                <option value="auto">auto</option>
                <option value="gateway">gateway</option>
                <option value="gateway-admin">gateway-admin</option>
                <option value="user-front">user-front</option>
                <option value="admin-front">admin-front</option>
                <option value="all">all</option>
              </select>
            </label>
            <button
              className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm disabled:opacity-60"
              disabled={busyAction === 'prepare' || detail.validation?.status !== 'passed'}
              onClick={() => runAction('prepare', () => api.prepareRelease(id, { actor: 'operator', note: note || null }))}
            >
              {isWorkspaceBlocked ? '重新准备分支' : '准备分支'}
            </button>
            <button
              className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2 text-sm text-white disabled:opacity-60"
              disabled={busyAction === 'open-pr' || detail.validation?.status !== 'passed'}
              onClick={() => runAction('open-pr', () => api.openReleasePr(id, { actor: 'operator', note: note || null }))}
            >
              {release?.status === 'branch_prepared' ? '打开 PR' : '继续打开 PR'}
            </button>
            <button
              className="rounded-2xl border border-[color:var(--ops-state-ready-border)] px-4 py-2 text-sm text-[color:var(--ops-state-ready-text)] disabled:opacity-60"
              disabled={busyAction === 'deploy-staging' || !deploymentSourceRef}
              onClick={() =>
                runAction('deploy-staging', () =>
                  api.deployReleaseToStaging(id, {
                    actor: 'operator',
                    note: note || null,
                    source_ref_type: actualBranchName ? 'branch' : 'commit',
                    source_ref: deploymentSourceRef,
                    deploy_scope: deployScope,
                  }),
                )
              }
            >
              部署分支到 Staging
            </button>
            <button
              className="rounded-2xl border border-[color:var(--ops-state-running-border)] px-4 py-2 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-60"
              disabled={busyAction === 'deploy-production' || !release?.commit_sha}
              onClick={() =>
                runAction('deploy-production', () =>
                  api.deployReleaseToProduction(id, {
                    actor: 'operator',
                    note: note || null,
                    source_ref_type: 'commit',
                    source_ref: release?.commit_sha || null,
                    deploy_scope: deployScope,
                  }),
                )
              }
            >
              部署到 Production
            </button>
            <button
              className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm disabled:opacity-60"
              disabled={busyAction === 'no-deploy' || !deploymentSourceRef}
              onClick={() =>
                runAction('no-deploy', () =>
                  api.markReleaseNoDeploy(id, {
                    actor: 'operator',
                    note: note || 'Manual no-deploy from release console',
                    source_ref_type: actualBranchName ? 'branch' : 'commit',
                    source_ref: deploymentSourceRef,
                    deploy_scope: deployScope,
                  }),
                )
              }
            >
              标记 No Deploy
            </button>
            <button
              className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] px-4 py-2 text-sm text-[color:var(--ops-state-blocked-text)] disabled:opacity-60"
              disabled={busyAction === 'rollback'}
              onClick={async () => {
                const sha = window.prompt('输入要回滚到的 commit SHA', release?.commit_sha || '')
                if (!sha?.trim()) return
                await runAction('rollback', () => api.rollbackRelease(id, { actor: 'operator', note: note || null, rollback_target_sha: sha.trim() }))
              }}
            >
              回滚
            </button>
          </div>
        </SectionFrame>

        <div className="space-y-[var(--ops-section-gap)]">
          <InspectorRail eyebrow="Current Release" title="当前发布记录">
          {release ? (
            <div className="space-y-3 text-sm text-[color:var(--ops-text-muted)]">
              <div>state: {release.state || release.status}</div>
              <div>stable target branch: {plannedBranchName || '-'}</div>
              <div>actual branch: {actualBranchName || '-'}</div>
              <div>branch reuse: {release.branch_reuse_status || '-'}</div>
              <div>base: {release.base_branch || '-'}</div>
              <div>current workspace branch: {workspaceBlocker?.current_branch || '-'}</div>
              <div>dirty files: {workspaceBlocker?.dirty_file_count ?? '-'}</div>
              <div>workspace mode: {release.workspace_mode || workspaceBlocker?.workspace_mode || 'shared_checkout'}</div>
              <div>sha: {release.commit_sha || '-'}</div>
              <div>deploy source: {actualBranchName ? `branch:${actualBranchName}` : release.commit_sha ? `commit:${release.commit_sha}` : '-'}</div>
              <div>prepared: {formatTime(release.prepared_at)}</div>
              <div>delivered: {formatTime(release.delivered_at)}</div>
              <div>updated: {formatTime(release.updated_at)}</div>
              <div>repairable: {release.repairable ? 'yes' : 'no'}</div>
              <div>repair attempts: {release.repair_attempt_count}</div>
              <div>next action: {release.next_action || '-'}</div>
              <div>GitHub PR state: {release.pr_status || '-'}</div>
              <div>PR synced: {formatTime(release.last_pr_status_synced_at)}</div>
              <div>merged at: {formatTime(release.merged_at)}</div>
              <div>merge commit: {release.merge_commit_sha || '-'}</div>
              {release.pr_sync_failure_summary ? <div>PR sync: {release.pr_sync_failure_summary}</div> : null}
              {release.delivery_failure_excerpt ? <div>failure: {release.delivery_failure_excerpt}</div> : null}
              {release.compare_url ? <a className="block text-blue-600 hover:underline" href={release.compare_url} target="_blank" rel="noreferrer">Compare</a> : null}
              {release.pr_url ? <a className="block text-blue-600 hover:underline" href={release.pr_url} target="_blank" rel="noreferrer">Pull Request</a> : null}
            </div>
          ) : (
            <div className="text-sm text-[color:var(--ops-text-muted)]">当前还没有 release record。</div>
          )}
          </InspectorRail>

          <InspectorRail eyebrow="Environment" title="发布门槛">
            <div>
              <FieldLabel>Validation</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">{detail.validation?.status || 'pending'}</div>
            </div>
            <div>
              <FieldLabel>Commit SHA</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">{release?.commit_sha || '-'}</div>
            </div>
            <div>
              <FieldLabel>Latest Deploy</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">{detail.deployments[0]?.environment || '-'}</div>
            </div>
          </InspectorRail>
        </div>
      </div>

      <ActivityFeed eyebrow="Deployment History" title="部署记录">
        <div className="mt-4 grid gap-4">
          {detail.deployments.map((record) => (
            <article key={record.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5 text-sm text-[color:var(--ops-text-muted)]">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="text-base font-semibold text-[color:var(--ops-text-title)]">{record.environment} · {record.action} · {record.status}</div>
                  <div className="mt-2">sha: {record.commit_sha || '-'} · health: {record.health_status || '-'}</div>
                  <div className="mt-1">source: {String(record.metadata?.sourceRefType || '-')}:{String(record.metadata?.sourceRef || record.branch_name || '-')}</div>
                  <div className="mt-1">scope: {Array.isArray(record.metadata?.deployScope) ? record.metadata.deployScope.join(', ') : String(record.metadata?.deployScope || '-')}</div>
                  {record.metadata?.evidenceUri ? <div className="mt-1">evidence: {String(record.metadata.evidenceUri)}</div> : null}
                </div>
                <div className="text-right text-xs text-[color:var(--ops-text-caption)]">
                  <div>started {formatTime(record.started_at)}</div>
                  <div>finished {formatTime(record.finished_at)}</div>
                </div>
              </div>
              {record.external_url ? <a className="mt-3 block text-blue-600 hover:underline" href={record.external_url} target="_blank" rel="noreferrer">Workflow run</a> : null}
            </article>
          ))}
          {detail.deployments.length === 0 && (
            <div className="rounded-3xl border border-dashed border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-8 text-sm text-[color:var(--ops-text-muted)]">
              当前没有 deployment record。
            </div>
          )}
        </div>
      </ActivityFeed>
    </div>
  )
}
