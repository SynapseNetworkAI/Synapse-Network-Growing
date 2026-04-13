import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, DeploymentOverview, DeploymentRequirementCandidate } from '../api'

function formatIsoTime(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN')
}

function requirementTone(status: string) {
  if (status === 'done') return 'bg-emerald-50 text-emerald-700 border-emerald-200'
  if (status === 'blocked') return 'bg-rose-50 text-rose-700 border-rose-200'
  if (status === 'in_progress') return 'bg-sky-50 text-sky-700 border-sky-200'
  return 'bg-slate-50 text-slate-700 border-slate-200'
}

export default function DeploymentsPage() {
  const [searchParams] = useSearchParams()
  const highlightedRequirementId = Number(searchParams.get('requirement') || '')
  const [overview, setOverview] = useState<DeploymentOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [deployNote, setDeployNote] = useState<Record<number, string>>({})
  const [publishNote, setPublishNote] = useState<Record<number, string>>({})

  const loadOverview = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getDeploymentOverview()
      setOverview(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载发布中心失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadOverview().catch(() => {})
  }, [loadOverview])

  const sortedCandidates = useMemo(() => {
    const items = [...(overview?.release_candidates || [])]
    if (!highlightedRequirementId) return items
    return items.sort((a, b) => {
      if (a.requirement_id === highlightedRequirementId) return -1
      if (b.requirement_id === highlightedRequirementId) return 1
      return 0
    })
  }, [overview, highlightedRequirementId])

  const runAction = async (key: string, action: () => Promise<unknown>) => {
    setBusyKey(key)
    try {
      await action()
      await loadOverview()
    } finally {
      setBusyKey(null)
    }
  }

  const handleRollback = async (candidate: DeploymentRequirementCandidate) => {
    const fallbackSha = candidate.delivery_state?.last_deployed_sha || ''
    const rollbackTarget = window.prompt('输入要回滚到的 commit SHA', fallbackSha)
    if (!rollbackTarget?.trim()) return
    await runAction(`rollback-${candidate.requirement_id}`, () =>
      api.rollbackRequirementDeployment(candidate.requirement_id, {
        actor: 'operator',
        note: deployNote[candidate.requirement_id]?.trim() || null,
        rollback_target_sha: rollbackTarget.trim(),
      }),
    )
  }

  if (loading) {
    return <div data-testid="deployments-loading" className="rounded-xl border bg-white p-6 text-sm text-gray-500">正在加载发布中心…</div>
  }

  if (error) {
    return <div data-testid="deployments-error" className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">{error}</div>
  }

  return (
    <div data-testid="deployments-page" className="space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-[linear-gradient(135deg,rgba(14,165,233,0.08),rgba(59,130,246,0.03))] p-5">
        <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Release Center</div>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">环境与发布总览</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          这里负责 staging / production 环境状态、发布候选、部署记录和回滚动作。需求页只保留需求执行与验证，不再直接承载发布控制。
        </p>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-900">环境面板</div>
            <div className="text-xs text-slate-500">按项目查看 staging / production 当前版本、健康状态和最近一次发布。</div>
          </div>
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          {(overview?.project_overviews || []).map((project) => (
            <article key={project.project_policy_id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4" data-testid={`deployment-project-${project.project_key}`}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-sm font-semibold text-slate-900">{project.display_name}</div>
                  <div className="mt-1 text-xs text-slate-500">{project.deploy_repo_full_name || '未配置 deploy repo'}</div>
                </div>
                <div className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${project.deploy_trigger_enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'}`}>
                  {project.deploy_trigger_enabled ? 'trigger enabled' : 'trigger disabled'}
                </div>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {project.environment_statuses.map((env) => (
                  <div key={`${project.project_key}-${env.environment}`} className="rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-600">
                    <div className="mb-2 font-medium text-slate-900">{env.environment === 'production' ? 'Production' : 'Staging'}</div>
                    <div>host: {env.host_label || '-'}</div>
                    <div>sha: {env.current_commit_sha || '-'}</div>
                    <div>branch: {env.current_branch || '-'}</div>
                    <div>health: {env.health_status || '-'}</div>
                    <div>last success: {formatIsoTime(env.last_success_at)}</div>
                    {env.last_external_url ? (
                      <a href={env.last_external_url} target="_blank" rel="noreferrer" className="mt-2 block font-medium text-blue-600 hover:underline">
                        Run workflow
                      </a>
                    ) : null}
                  </div>
                ))}
              </div>
              {project.recent_records.length > 0 && (
                <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-600">
                  <div className="mb-2 font-medium text-slate-900">Recent Deployments</div>
                  <div className="space-y-2">
                    {project.recent_records.map((record) => (
                      <div key={record.id} className="rounded-lg border border-slate-200 p-2">
                        <div className="font-medium text-slate-900">
                          {record.environment} · {record.action} · {record.status}
                        </div>
                        <div className="mt-1">sha: {record.commit_sha || '-'} · started: {formatIsoTime(record.started_at)}</div>
                        {record.external_url ? (
                          <a href={record.external_url} target="_blank" rel="noreferrer" className="mt-1 block font-medium text-blue-600 hover:underline">
                            Workflow run
                          </a>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4">
        <div className="mb-3">
          <div className="text-sm font-semibold text-slate-900">发布候选</div>
          <div className="text-xs text-slate-500">从 requirement 切换到发布视角，集中处理 review PR、publish、部署和回滚。</div>
        </div>
        <div className="space-y-4">
          {sortedCandidates.map((candidate) => {
            const deliveryState = candidate.delivery_state
            const blockers = Array.isArray(deliveryState?.deploy_readiness?.blockers)
              ? (deliveryState?.deploy_readiness?.blockers as unknown[]).map((item) => String(item))
              : []
            const highlighted = highlightedRequirementId === candidate.requirement_id
            return (
              <article
                key={candidate.requirement_id}
                data-testid={`deployment-candidate-${candidate.requirement_id}`}
                className={`rounded-2xl border p-4 ${highlighted ? 'border-sky-300 bg-sky-50/60' : 'border-slate-200 bg-slate-50'}`}
              >
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link to={`/requirements/${candidate.requirement_id}`} className="text-base font-semibold text-slate-900 hover:text-blue-600">
                        #{candidate.requirement_id} {candidate.title}
                      </Link>
                      <span className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${requirementTone(candidate.status)}`}>
                        {candidate.status}
                      </span>
                    </div>
                    <div className="mt-2 text-xs text-slate-500">
                      {candidate.project_display_name || candidate.project_key || '未映射项目'} · priority {candidate.priority} · updated {formatIsoTime(candidate.updated_at)}
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4 text-xs text-slate-600">
                      <div className="rounded-xl border border-slate-200 bg-white p-3">
                        <div className="mb-1 font-medium text-slate-900">Review / Publish</div>
                        <div>review: {deliveryState?.review_status || '-'}</div>
                        <div>publish: {deliveryState?.publish_status || '-'}</div>
                        <div>mode: {deliveryState?.release_mode || '-'}</div>
                        <div>pr: {deliveryState?.pr_status || '-'}</div>
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-white p-3">
                        <div className="mb-1 font-medium text-slate-900">Branch / SHA</div>
                        <div>branch: {deliveryState?.branch_name || '-'}</div>
                        <div>head: {deliveryState?.head_branch || deliveryState?.branch_name || '-'}</div>
                        <div>sha: {deliveryState?.latest_remote_sha || deliveryState?.latest_commit_sha || '-'}</div>
                        <div>pushed: {formatIsoTime(deliveryState?.last_pushed_at)}</div>
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-white p-3">
                        <div className="mb-1 font-medium text-slate-900">Deploy Readiness</div>
                        <div>repo: {String((deliveryState?.deploy_readiness as Record<string, unknown> | null)?.deploy_repo_full_name || '-')}</div>
                        <div>sha: {String((deliveryState?.deploy_readiness as Record<string, unknown> | null)?.deliverable_commit_sha || '-')}</div>
                        <div>last deployed: {deliveryState?.last_deployed_sha || '-'}</div>
                        <div>at: {formatIsoTime(deliveryState?.last_deployed_at)}</div>
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-white p-3">
                        <div className="mb-1 font-medium text-slate-900">Links</div>
                        {deliveryState?.compare_url ? <a href={deliveryState.compare_url} target="_blank" rel="noreferrer" className="block text-blue-600 hover:underline">Compare</a> : <div>-</div>}
                        {deliveryState?.pr_url ? <a href={deliveryState.pr_url} target="_blank" rel="noreferrer" className="block text-blue-600 hover:underline">Pull Request</a> : <div>-</div>}
                      </div>
                    </div>
                    {blockers.length > 0 && (
                      <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                        <div className="mb-1 font-medium">Deploy Blockers</div>
                        <div className="space-y-1">
                          {blockers.map((item) => (
                            <div key={item}>{item}</div>
                          ))}
                        </div>
                      </div>
                    )}
                    {deliveryState?.promotion_checklist?.length ? (
                      <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-600">
                        <div className="mb-2 font-medium text-slate-900">Promotion Checklist</div>
                        <div className="space-y-2">
                          {deliveryState.promotion_checklist.map((item, idx) => {
                            const entry = item as Record<string, unknown>
                            return (
                              <div key={`${String(entry.key || 'check')}-${idx}`}>
                                <div className="font-medium text-slate-900">{String(entry.label || entry.key || 'check')}</div>
                                <div>{String(entry.detail || '')}</div>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    ) : null}
                  </div>

                  <div className="w-full max-w-md space-y-2 lg:w-[340px]">
                    <textarea
                      className="min-h-16 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs"
                      placeholder="记录本次发布 / 回滚说明"
                      value={deployNote[candidate.requirement_id] || ''}
                      onChange={(e) => setDeployNote((prev) => ({ ...prev, [candidate.requirement_id]: e.target.value }))}
                    />
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="rounded border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                        disabled={busyKey === `sync-${candidate.requirement_id}` || !deliveryState?.branch_name}
                        onClick={() => runAction(`sync-${candidate.requirement_id}`, () => api.syncRequirementReviewPr(candidate.requirement_id))}
                      >
                        {busyKey === `sync-${candidate.requirement_id}` ? 'Syncing…' : 'Create/Sync Review PR'}
                      </button>
                      <button
                        type="button"
                        className="rounded border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
                        disabled={busyKey === `publish-${candidate.requirement_id}` || deliveryState?.publish_status === 'published' || deliveryState?.release_mode === 'disabled'}
                        onClick={() => runAction(`publish-${candidate.requirement_id}`, () => api.publishRequirement(candidate.requirement_id, {
                          completed_checks: deliveryState?.required_checks || [],
                          note: publishNote[candidate.requirement_id]?.trim() || null,
                        }))}
                      >
                        {busyKey === `publish-${candidate.requirement_id}` ? 'Publishing…' : 'Promote To Publish'}
                      </button>
                      <button
                        type="button"
                        className="rounded border border-sky-300 bg-sky-50 px-3 py-2 text-xs font-medium text-sky-700 hover:bg-sky-100 disabled:opacity-50"
                        disabled={busyKey === `staging-${candidate.requirement_id}` || blockers.length > 0}
                        onClick={() => runAction(`staging-${candidate.requirement_id}`, () => api.deployRequirementToStaging(candidate.requirement_id, {
                          actor: 'operator',
                          note: deployNote[candidate.requirement_id]?.trim() || null,
                        }))}
                      >
                        {busyKey === `staging-${candidate.requirement_id}` ? 'Deploying…' : 'Deploy To Staging'}
                      </button>
                      <button
                        type="button"
                        className="rounded border border-violet-300 bg-violet-50 px-3 py-2 text-xs font-medium text-violet-700 hover:bg-violet-100 disabled:opacity-50"
                        disabled={busyKey === `production-${candidate.requirement_id}` || !deliveryState?.staging_status?.current_commit_sha}
                        onClick={() => runAction(`production-${candidate.requirement_id}`, () => api.promoteRequirementToProduction(candidate.requirement_id, {
                          actor: 'operator',
                          note: deployNote[candidate.requirement_id]?.trim() || null,
                        }))}
                      >
                        {busyKey === `production-${candidate.requirement_id}` ? 'Promoting…' : 'Promote To Production'}
                      </button>
                      <button
                        type="button"
                        className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-50"
                        disabled={busyKey === `rollback-${candidate.requirement_id}`}
                        onClick={() => { handleRollback(candidate).catch(() => {}) }}
                      >
                        {busyKey === `rollback-${candidate.requirement_id}` ? 'Rolling Back…' : 'Rollback'}
                      </button>
                    </div>
                    <textarea
                      className="min-h-20 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs"
                      placeholder="记录 publish decision 说明"
                      value={publishNote[candidate.requirement_id] || ''}
                      onChange={(e) => setPublishNote((prev) => ({ ...prev, [candidate.requirement_id]: e.target.value }))}
                    />
                  </div>
                </div>

                {candidate.deployment_records.length > 0 && (
                  <div className="mt-4 rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-600">
                    <div className="mb-2 font-medium text-slate-900">Deploy History</div>
                    <div className="space-y-2">
                      {candidate.deployment_records.map((record) => (
                        <div key={record.id} className="rounded-lg border border-slate-200 p-2">
                          <div className="font-medium text-slate-900">
                            {record.environment} · {record.action} · {record.status}
                          </div>
                          <div className="mt-1">sha: {record.commit_sha || '-'} · actor: {record.actor || '-'} · started: {formatIsoTime(record.started_at)}</div>
                          {record.external_url ? (
                            <a href={record.external_url} target="_blank" rel="noreferrer" className="mt-1 block text-blue-600 hover:underline">
                              {record.external_url}
                            </a>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </article>
            )
          })}
          {sortedCandidates.length === 0 && (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-6 text-sm text-slate-500">
              当前没有可显示的发布候选。先让 requirement 走到交付 closeout，或为项目配置 deploy governance。
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
