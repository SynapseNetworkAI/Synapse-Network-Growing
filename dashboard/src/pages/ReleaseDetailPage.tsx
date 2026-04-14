import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ReleaseDetail, api } from '../api'

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
    return <div className="rounded-3xl border border-slate-200 bg-white p-8 text-sm text-slate-500">正在加载发布详情…</div>
  }

  const release = detail.release

  return (
    <div className="space-y-6" data-testid="release-detail-page">
      <section className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-slate-400">Release Record</div>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Requirement #{detail.requirement.id} 发布详情</h2>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
              <span className="rounded-full bg-slate-100 px-3 py-1">{detail.requirement.title}</span>
              <span className="rounded-full bg-slate-100 px-3 py-1">{release?.status || 'not_ready'}</span>
              <span className="rounded-full bg-slate-100 px-3 py-1">{detail.validation?.status || 'pending_validation'}</span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="rounded-2xl border border-slate-200 px-4 py-2 text-sm" onClick={() => navigate(`/requirements/${detail.requirement.id}`)}>
              查看需求
            </button>
            {detail.requirement.latest_execution_run_id && (
              <button className="rounded-2xl border border-slate-200 px-4 py-2 text-sm" onClick={() => navigate(`/executions/${detail.requirement.latest_execution_run_id}`)}>
                查看执行
              </button>
            )}
          </div>
        </div>

        <div className="mt-4 grid gap-3 text-sm text-slate-600 md:grid-cols-2 xl:grid-cols-4">
          <div>target: {detail.requirement.target_projects.join(', ') || '-'}</div>
          <div>release status: {release?.status || '-'}</div>
          <div>validation: {detail.validation?.status || '-'}</div>
          <div>latest deploy: {detail.deployments[0]?.environment || '-'}</div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr,0.92fr]">
        <div className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
          <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Release Control</div>
          <h3 className="mt-2 text-xl font-semibold text-slate-950">发布动作</h3>

          <textarea
            className="mt-4 min-h-[120px] w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm"
            placeholder="记录本次 prepare / PR / deploy / rollback 备注"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              className="rounded-2xl border border-slate-200 px-4 py-2 text-sm disabled:opacity-60"
              disabled={busyAction === 'prepare' || detail.validation?.status !== 'passed'}
              onClick={() => runAction('prepare', () => api.prepareRelease(id, { actor: 'operator', note: note || null }))}
            >
              准备分支
            </button>
            <button
              className="rounded-2xl bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-60"
              disabled={busyAction === 'open-pr' || detail.validation?.status !== 'passed'}
              onClick={() => runAction('open-pr', () => api.openReleasePr(id, { actor: 'operator', note: note || null }))}
            >
              打开 PR
            </button>
            <button
              className="rounded-2xl border border-emerald-200 px-4 py-2 text-sm text-emerald-700 disabled:opacity-60"
              disabled={busyAction === 'deploy-staging' || !release?.commit_sha}
              onClick={() => runAction('deploy-staging', () => api.deployReleaseToStaging(id, { actor: 'operator', note: note || null }))}
            >
              部署到 Staging
            </button>
            <button
              className="rounded-2xl border border-blue-200 px-4 py-2 text-sm text-blue-700 disabled:opacity-60"
              disabled={busyAction === 'deploy-production' || !release?.commit_sha}
              onClick={() => runAction('deploy-production', () => api.deployReleaseToProduction(id, { actor: 'operator', note: note || null }))}
            >
              部署到 Production
            </button>
            <button
              className="rounded-2xl border border-rose-200 px-4 py-2 text-sm text-rose-700 disabled:opacity-60"
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
        </div>

        <div className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
          <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Current Release</div>
          <h3 className="mt-2 text-xl font-semibold text-slate-950">当前发布记录</h3>
          {release ? (
            <div className="mt-4 space-y-3 text-sm text-slate-600">
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
            <div className="mt-4 text-sm text-slate-500">当前还没有 release record。</div>
          )}
        </div>
      </section>

      <section className="rounded-[28px] border border-slate-200/70 bg-white/80 p-6 shadow-[0_18px_60px_rgba(15,23,42,0.08)]">
        <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Deployment History</div>
        <h3 className="mt-2 text-xl font-semibold text-slate-950">部署记录</h3>
        <div className="mt-4 grid gap-4">
          {detail.deployments.map((record) => (
            <article key={record.id} className="rounded-3xl border border-slate-200/80 bg-slate-50/80 p-5 text-sm text-slate-600">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="text-base font-semibold text-slate-950">{record.environment} · {record.action} · {record.status}</div>
                  <div className="mt-2">sha: {record.commit_sha || '-'} · health: {record.health_status || '-'}</div>
                </div>
                <div className="text-right text-xs text-slate-500">
                  <div>started {formatTime(record.started_at)}</div>
                  <div>finished {formatTime(record.finished_at)}</div>
                </div>
              </div>
              {record.external_url ? <a className="mt-3 block text-blue-600 hover:underline" href={record.external_url} target="_blank" rel="noreferrer">Workflow run</a> : null}
            </article>
          ))}
          {detail.deployments.length === 0 && (
            <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 p-8 text-sm text-slate-500">
              当前没有 deployment record。
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
