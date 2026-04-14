import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ReleaseDetail, api } from '../api'
import { ActivityFeed, FieldLabel, InspectorRail, LoadingPane, SectionFrame, StateBadge } from '../components/workbench'

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
            {detail.requirement.latest_execution_run_id && (
              <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/executions/${detail.requirement.latest_execution_run_id}`)}>
                查看执行
              </button>
            )}
          </div>
        }
      >
        <div className="flex flex-wrap gap-2">
          <StateBadge tone="muted">{detail.requirement.title}</StateBadge>
          <StateBadge tone={release?.status ? 'ready' : 'muted'}>{release?.status || 'not_ready'}</StateBadge>
          <StateBadge tone={detail.validation?.status === 'passed' ? 'delivered' : 'validating'}>
            {detail.validation?.status || 'pending_validation'}
          </StateBadge>
        </div>
        <div className="mt-4 grid gap-3 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-2 xl:grid-cols-4">
          <div>target: {detail.requirement.target_projects.join(', ') || '-'}</div>
          <div>release status: {release?.status || '-'}</div>
          <div>validation: {detail.validation?.status || '-'}</div>
          <div>latest deploy: {detail.deployments[0]?.environment || '-'}</div>
        </div>
      </SectionFrame>

      <div className="grid gap-[var(--ops-section-gap)] xl:grid-cols-[minmax(0,1.4fr),minmax(300px,var(--ops-inspector-width))]">
        <SectionFrame eyebrow="Release Control" title="发布动作" description="只有 validate 通过后，才应该继续 prepare、open PR 和后续部署。">

          <textarea
            className="mt-4 min-h-[120px] w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
            placeholder="记录本次 prepare / PR / deploy / rollback 备注"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm disabled:opacity-60"
              disabled={busyAction === 'prepare' || detail.validation?.status !== 'passed'}
              onClick={() => runAction('prepare', () => api.prepareRelease(id, { actor: 'operator', note: note || null }))}
            >
              准备分支
            </button>
            <button
              className="rounded-2xl bg-[color:var(--ops-shell-bg)] px-4 py-2 text-sm text-white disabled:opacity-60"
              disabled={busyAction === 'open-pr' || detail.validation?.status !== 'passed'}
              onClick={() => runAction('open-pr', () => api.openReleasePr(id, { actor: 'operator', note: note || null }))}
            >
              打开 PR
            </button>
            <button
              className="rounded-2xl border border-[color:var(--ops-state-ready-border)] px-4 py-2 text-sm text-[color:var(--ops-state-ready-text)] disabled:opacity-60"
              disabled={busyAction === 'deploy-staging' || !release?.commit_sha}
              onClick={() => runAction('deploy-staging', () => api.deployReleaseToStaging(id, { actor: 'operator', note: note || null }))}
            >
              部署到 Staging
            </button>
            <button
              className="rounded-2xl border border-[color:var(--ops-state-running-border)] px-4 py-2 text-sm text-[color:var(--ops-state-running-text)] disabled:opacity-60"
              disabled={busyAction === 'deploy-production' || !release?.commit_sha}
              onClick={() => runAction('deploy-production', () => api.deployReleaseToProduction(id, { actor: 'operator', note: note || null }))}
            >
              部署到 Production
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
              <div>status: {release.status}</div>
              <div>branch: {release.branch_name || '-'}</div>
              <div>base: {release.base_branch || '-'}</div>
              <div>sha: {release.commit_sha || '-'}</div>
              <div>prepared: {formatTime(release.prepared_at)}</div>
              <div>delivered: {formatTime(release.delivered_at)}</div>
              <div>updated: {formatTime(release.updated_at)}</div>
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
            <article key={record.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/76 p-5 text-sm text-[color:var(--ops-text-muted)]">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="text-base font-semibold text-[color:var(--ops-text-title)]">{record.environment} · {record.action} · {record.status}</div>
                  <div className="mt-2">sha: {record.commit_sha || '-'} · health: {record.health_status || '-'}</div>
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
