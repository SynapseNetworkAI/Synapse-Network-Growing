import { useEffect, useMemo, useState } from 'react'
import {
  api,
  DropGoalResult,
  PlannerSweep,
  PlanningManifest,
  PlanningManifestHistory,
  RequirementCandidate,
} from '../api'

type Goal = {
  goal_key?: string
  domain?: string
  status?: string
  intent?: string
  success_metric?: string
  weight?: number
}

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function badgeTone(status: string) {
  if (['active', 'approved', 'materialized', 'succeeded'].includes(status)) return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  if (['pending', 'draft'].includes(status)) return 'border-blue-200 bg-blue-50 text-blue-700'
  if (['dropped', 'cancelled', 'suppressed', 'rejected', 'failed'].includes(status)) return 'border-rose-200 bg-rose-50 text-rose-700'
  return 'border-slate-200 bg-slate-50 text-slate-600'
}

function goalsFrom(manifest: PlanningManifest | null): Goal[] {
  const goals = manifest?.payload?.goals
  return Array.isArray(goals) ? (goals as Goal[]) : []
}

function JsonBlock({ value }: Readonly<{ value: unknown }>) {
  return (
    <pre className="max-h-[420px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-relaxed text-slate-100">
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  )
}

export default function PlanningPage() {
  const [manifest, setManifest] = useState<PlanningManifest | null>(null)
  const [history, setHistory] = useState<PlanningManifestHistory | null>(null)
  const [candidates, setCandidates] = useState<RequirementCandidate[]>([])
  const [historyPage, setHistoryPage] = useState(1)
  const [historySearch, setHistorySearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [payloadDraft, setPayloadDraft] = useState('')
  const [dropGoal, setDropGoal] = useState<Goal | null>(null)
  const [dropReason, setDropReason] = useState('')
  const [dropResult, setDropResult] = useState<DropGoalResult | null>(null)
  const [lastSweep, setLastSweep] = useState<PlannerSweep | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const goals = useMemo(() => goalsFrom(manifest), [manifest])

  async function load(nextPage = historyPage) {
    setLoading(true)
    setError(null)
    try {
      const [active, nextHistory] = await Promise.all([
        api.getActivePlanningManifest(),
        api.getPlanningManifestHistory({ page: nextPage, page_size: 10, search: historySearch || undefined }),
      ])
      setManifest(active)
      setPayloadDraft(JSON.stringify(active.payload, null, 2))
      setHistory(nextHistory)
      const candidatePage = await api.getRequirementCandidates({ manifest_id: active.id, page_size: 30 })
      setCandidates(candidatePage.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载 Planning 数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(1).catch(() => {})
  }, [])

  async function saveManifest() {
    if (!manifest) return
    setBusy('save')
    setError(null)
    try {
      const payload = JSON.parse(payloadDraft) as Record<string, unknown>
      const next = await api.saveActivePlanningManifest({
        version_name: manifest.version_name,
        cycle_label: manifest.cycle_label,
        payload,
        operator: 'operator',
      })
      setManifest(next)
      setPayloadDraft(JSON.stringify(next.payload, null, 2))
      await load(historyPage)
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存 Manifest 失败')
    } finally {
      setBusy(null)
    }
  }

  async function runSweep(dryRun: boolean) {
    setBusy(dryRun ? 'dry_sweep' : 'sweep')
    setError(null)
    try {
      const sweep = await api.runPlannerSweep({ dry_run: dryRun, triggered_by: 'operator' })
      setLastSweep(sweep)
      await load(historyPage)
    } catch (err) {
      setError(err instanceof Error ? err.message : '运行 Planner Sweep 失败')
    } finally {
      setBusy(null)
    }
  }

  async function confirmDropGoal() {
    if (!manifest || !dropGoal?.goal_key) return
    setBusy('drop')
    setError(null)
    try {
      const result = await api.dropPlanningGoal(manifest.id, dropGoal.goal_key, {
        reason: dropReason,
        operator: 'operator',
        halt_mode: 'safe_halt',
      })
      setDropResult(result)
      setDropGoal(null)
      setDropReason('')
      await load(historyPage)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Drop Goal 失败')
    } finally {
      setBusy(null)
    }
  }

  async function actOnCandidate(candidate: RequirementCandidate, action: 'approve' | 'reject' | 'materialize') {
    setBusy(`${action}:${candidate.id}`)
    setError(null)
    try {
      if (action === 'approve') await api.approveRequirementCandidate(candidate.id, { operator: 'operator' })
      if (action === 'reject') await api.rejectRequirementCandidate(candidate.id, { operator: 'operator', reason: 'operator_rejected' })
      if (action === 'materialize') await api.materializeRequirementCandidate(candidate.id, { operator: 'operator' })
      await load(historyPage)
    } catch (err) {
      setError(err instanceof Error ? err.message : `${action} candidate failed`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-5" data-testid="planning-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white px-5 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Planning Control Plane</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">经营规划</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
              这里是 Agent-First 公司的上游：唯一活跃 Operating Manifest 定义当前目标，Planner Sweep 生成候选需求，Drop Goal 只停止未来投入和未交付链路，不自动回滚已发布产物。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => load(historyPage).catch(() => {})}>刷新</button>
            <button className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700" disabled={busy === 'dry_sweep'} onClick={() => runSweep(true)}>Dry Run Planner</button>
            <button className="rounded-xl bg-[color:var(--ops-accent)] px-4 py-2 text-sm font-semibold text-white" disabled={busy === 'sweep'} onClick={() => runSweep(false)}>Run Planner Sweep</button>
          </div>
        </div>
        {error && <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
        <div className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Active Manifest</div>
              <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">{manifest?.version_name || 'Manifest'}</h3>
              <p className="mt-1 text-sm text-[color:var(--ops-text-muted)]">revision {manifest?.revision ?? '-'} · {manifest?.cycle_label || '-'}</p>
            </div>
            <span className={['rounded-full border px-3 py-1 text-xs font-medium', badgeTone(manifest?.status || 'draft')].join(' ')}>{manifest?.status || '-'}</span>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {goals.map((goal) => (
              <div key={goal.goal_key} className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-slate-50/70 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-mono text-xs text-[color:var(--ops-text-caption)]">{goal.goal_key}</div>
                    <div className="mt-2 text-base font-semibold text-[color:var(--ops-text-title)]">{goal.domain || 'operations'}</div>
                  </div>
                  <span className={['rounded-full border px-3 py-1 text-xs font-medium', badgeTone(goal.status || 'active')].join(' ')}>{goal.status || 'active'}</span>
                </div>
                <p className="mt-3 text-sm leading-6 text-[color:var(--ops-text-body)]">{goal.intent || '-'}</p>
                <p className="mt-3 text-xs leading-5 text-[color:var(--ops-text-muted)]">Metric: {goal.success_metric || '-'}</p>
                {goal.status !== 'dropped' && (
                  <button
                    className="mt-4 rounded-xl border border-rose-200 bg-white px-3 py-2 text-xs font-medium text-rose-700"
                    onClick={() => setDropGoal(goal)}
                  >
                    Drop Goal
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white p-5">
          <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Manifest Editor</div>
          <textarea
            className="mt-4 h-[360px] w-full rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-100"
            value={payloadDraft}
            onChange={(event) => setPayloadDraft(event.target.value)}
            spellCheck={false}
          />
          <button className="mt-3 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white" disabled={busy === 'save'} onClick={() => saveManifest()}>保存 Minor Revision</button>
        </div>
      </section>

      {dropResult && (
        <section className="rounded-[var(--ops-radius-panel)] border border-amber-200 bg-amber-50 p-5">
          <div className="text-[11px] uppercase tracking-[0.22em] text-amber-700">Halt Summary</div>
          <div className="mt-2 text-lg font-semibold text-amber-950">Goal `{dropResult.goal_key}` 已停止未来投入</div>
          <p className="mt-2 text-sm text-amber-800">已发布产物保留；如需下线，请创建新的 decommission requirement，不会自动 rollback。</p>
          <div className="mt-4 grid gap-3 md:grid-cols-5">
            {Object.entries(dropResult.halt_summary).map(([key, value]) => (
              <div key={key} className="rounded-2xl bg-white/70 p-3">
                <div className="font-mono text-[10px] text-amber-700">{key}</div>
                <div className="mt-1 text-lg font-semibold text-amber-950">{String(value)}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Requirement Candidates</div>
              <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">候选需求</h3>
            </div>
            <span className="text-sm text-[color:var(--ops-text-muted)]">{candidates.length} shown</span>
          </div>
          <div className="mt-4 space-y-3">
            {candidates.map((candidate) => (
              <div key={candidate.id} className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-base font-semibold text-[color:var(--ops-text-title)]">{candidate.title}</div>
                    <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{candidate.goal_key} · {candidate.workflow_key}</div>
                  </div>
                  <span className={['rounded-full border px-3 py-1 text-xs font-medium', badgeTone(candidate.status)].join(' ')}>{candidate.status}</span>
                </div>
                <p className="mt-3 line-clamp-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">{candidate.description_markdown}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {candidate.status === 'pending' && <button className="rounded-xl border px-3 py-2 text-xs" onClick={() => actOnCandidate(candidate, 'approve')}>Approve</button>}
                  {candidate.status === 'approved' && <button className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700" onClick={() => actOnCandidate(candidate, 'materialize')}>Materialize Requirement</button>}
                  {['pending', 'approved'].includes(candidate.status) && <button className="rounded-xl border border-rose-200 px-3 py-2 text-xs text-rose-700" onClick={() => actOnCandidate(candidate, 'reject')}>Reject</button>}
                </div>
              </div>
            ))}
            {!candidates.length && <div className="rounded-3xl border border-dashed border-[color:var(--ops-stroke-soft)] p-6 text-sm text-[color:var(--ops-text-muted)]">暂无候选。运行 Planner Sweep 会基于 active goals 生成候选需求。</div>}
          </div>
        </div>

        <div className="space-y-5">
          <div className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Manifest History</div>
                <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">全部历史分页</h3>
              </div>
              <div className="flex gap-2">
                <input className="rounded-xl border px-3 py-2 text-sm" placeholder="Search goal / version" value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} />
                <button className="rounded-xl border px-3 py-2 text-sm" onClick={() => { setHistoryPage(1); load(1).catch(() => {}) }}>搜索</button>
              </div>
            </div>
            <div className="mt-4 overflow-hidden rounded-2xl border border-[color:var(--ops-stroke-soft)]">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">
                  <tr>
                    <th className="px-4 py-3">Cycle</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Goals</th>
                    <th className="px-4 py-3">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {(history?.items || []).map((item) => (
                    <tr key={item.id} className="border-t border-[color:var(--ops-stroke-soft)]">
                      <td className="px-4 py-3">
                        <div className="font-medium text-[color:var(--ops-text-title)]">{item.version_name || item.manifest_key}</div>
                        <div className="font-mono text-xs text-[color:var(--ops-text-caption)]">{item.cycle_label}</div>
                      </td>
                      <td className="px-4 py-3"><span className={['rounded-full border px-3 py-1 text-xs', badgeTone(item.status)].join(' ')}>{item.status}</span></td>
                      <td className="px-4 py-3 text-[color:var(--ops-text-muted)]">{item.active_goal_count} active · {item.dropped_goal_count} dropped</td>
                      <td className="px-4 py-3 text-[color:var(--ops-text-muted)]">{formatTime(item.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center justify-between text-sm text-[color:var(--ops-text-muted)]">
              <span>Page {history?.page || 1} / {history?.total_pages || 1} · total {history?.total || 0}</span>
              <div className="flex gap-2">
                <button className="rounded-lg border px-3 py-1" disabled={(history?.page || 1) <= 1} onClick={() => { const page = Math.max(1, historyPage - 1); setHistoryPage(page); load(page).catch(() => {}) }}>Prev</button>
                <button className="rounded-lg border px-3 py-1" disabled={(history?.page || 1) >= (history?.total_pages || 1)} onClick={() => { const page = historyPage + 1; setHistoryPage(page); load(page).catch(() => {}) }}>Next</button>
              </div>
            </div>
          </div>

          {lastSweep && (
            <div className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white p-5">
              <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Last Planner Sweep</div>
              <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">{lastSweep.status}</h3>
              <div className="mt-3 text-sm text-[color:var(--ops-text-muted)]">created: {lastSweep.created_candidate_ids.length} · suppressed: {lastSweep.suppressed_items.length}</div>
              <div className="mt-4"><JsonBlock value={lastSweep} /></div>
            </div>
          )}
        </div>
      </section>

      {dropGoal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-xl rounded-[var(--ops-radius-panel)] bg-white p-6 shadow-2xl">
            <div className="text-[11px] uppercase tracking-[0.22em] text-rose-600">Danger Zone</div>
            <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">Drop Goal: {dropGoal.goal_key}</h3>
            <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
              会取消 pending candidates、取消未开始 requirements、暂停/阻断 running workflows，并保留已发布产物。不会自动 rollback、revert、删除数据库变更或撤回已发布内容。
            </div>
            <label className="mt-4 block text-sm font-medium text-[color:var(--ops-text-title)]">Reason required</label>
            <textarea className="mt-2 h-28 w-full rounded-2xl border border-[color:var(--ops-stroke-soft)] p-3 text-sm" value={dropReason} onChange={(event) => setDropReason(event.target.value)} />
            <div className="mt-5 flex justify-end gap-2">
              <button className="rounded-xl border px-4 py-2 text-sm" onClick={() => setDropGoal(null)}>Cancel</button>
              <button className="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white" disabled={!dropReason.trim() || busy === 'drop'} onClick={() => confirmDropGoal()}>Confirm Safe Halt</button>
            </div>
          </div>
        </div>
      )}

      {loading && <div className="text-sm text-[color:var(--ops-text-muted)]">Loading planning control plane...</div>}
    </div>
  )
}

