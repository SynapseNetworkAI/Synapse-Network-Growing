import { useEffect, useState } from 'react'
import { api, CompanyOperatingReview, CompanyReviewBundleMaterializeResult, DashboardStats, OrgNode, OrgTree, RecurringWorkflow } from '../api'

/* ── Color mapping ──────────────────────────────────────────── */
const COLOR_MAP: Record<string, { bg: string; border: string; tag: string; tagText: string; lightBg: string }> = {
  amber:  { bg: 'bg-amber-50',  border: 'border-amber-300',  tag: 'bg-amber-100',  tagText: 'text-amber-700',  lightBg: 'bg-amber-50' },
  green:  { bg: 'bg-green-50',  border: 'border-green-300',  tag: 'bg-green-100',  tagText: 'text-green-700',  lightBg: 'bg-green-50' },
  blue:   { bg: 'bg-blue-50',   border: 'border-blue-300',   tag: 'bg-blue-100',   tagText: 'text-blue-700',   lightBg: 'bg-blue-50' },
  purple: { bg: 'bg-purple-50', border: 'border-purple-300', tag: 'bg-purple-100', tagText: 'text-purple-700', lightBg: 'bg-purple-50' },
  sky:    { bg: 'bg-sky-50',    border: 'border-sky-300',    tag: 'bg-sky-100',    tagText: 'text-sky-700',    lightBg: 'bg-sky-50' },
  rose:   { bg: 'bg-rose-50',   border: 'border-rose-300',   tag: 'bg-rose-100',   tagText: 'text-rose-700',   lightBg: 'bg-rose-50' },
  indigo: { bg: 'bg-indigo-50', border: 'border-indigo-300', tag: 'bg-indigo-100', tagText: 'text-indigo-700', lightBg: 'bg-indigo-50' },
  gray:   { bg: 'bg-gray-50',   border: 'border-gray-300',   tag: 'bg-gray-100',   tagText: 'text-gray-700',   lightBg: 'bg-gray-50' },
}

function getColor(color?: string) {
  return COLOR_MAP[color || 'gray'] || COLOR_MAP.gray
}

function severityTone(severity?: string) {
  switch (severity) {
    case 'critical':
      return 'bg-rose-200 text-rose-900'
    case 'high':
      return 'bg-rose-100 text-rose-800'
    case 'medium':
      return 'bg-amber-100 text-amber-800'
    default:
      return 'bg-slate-100 text-slate-700'
  }
}

function actionTone(action?: string) {
  switch (action) {
    case 'approval_required':
      return 'bg-amber-100 text-amber-800'
    case 'intake':
      return 'bg-emerald-100 text-emerald-800'
    case 'review':
      return 'bg-sky-100 text-sky-800'
    default:
      return 'bg-slate-100 text-slate-700'
  }
}

export default function OrgChart() {
  const [orgTree, setOrgTree] = useState<OrgTree | null>(null)
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [review, setReview] = useState<CompanyOperatingReview | null>(null)
  const [rituals, setRituals] = useState<RecurringWorkflow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [materializingBundle, setMaterializingBundle] = useState(false)
  const [bundleResult, setBundleResult] = useState<CompanyReviewBundleMaterializeResult | null>(null)
  const [ritualRunning, setRitualRunning] = useState<Record<string, boolean>>({})
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [expandedDomains, setExpandedDomains] = useState<Set<string>>(new Set())

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [tree, s, companyReview] = await Promise.all([
        api.getOrgTree(),
        api.getStats(),
        api.getCompanyOperatingReview(),
      ])
      const recurring = await api.getRecurringWorkflows()
      setOrgTree(tree)
      setStats(s)
      setReview(companyReview)
      setRituals(recurring)
      // Auto-expand all domains
      if (tree?.root?.children) {
        setExpandedDomains(new Set(tree.root.children.map(d => d.id)))
      }
    } catch {
      setError('无法连接后端，请启动 sh scripts/local/start.sh')
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const handleMaterializeBundle = async () => {
    if (!review) return
    setMaterializingBundle(true)
    try {
      const result = await api.materializeCompanyReviewBundle(review.id, {})
      setBundleResult(result)
    } finally {
      setMaterializingBundle(false)
    }
  }

  const handleRunRitual = async (workflowKey: string) => {
    setRitualRunning((prev) => ({ ...prev, [workflowKey]: true }))
    try {
      const result = await api.runRecurringWorkflow(workflowKey, {})
      setRituals((prev) => prev.map((item) => (
        item.workflow_key === workflowKey
          ? {
              ...item,
              last_run_at: result.run_started_at,
              last_result: result.result,
            }
          : item
      )))
      if (workflowKey === 'weekly_operating_review' || workflowKey === 'closeout_and_compact_sweep') {
        const companyReview = await api.getCompanyOperatingReview()
        setReview(companyReview)
      }
    } finally {
      setRitualRunning((prev) => ({ ...prev, [workflowKey]: false }))
    }
  }

  const toggleDomain = (id: string) => {
    setExpandedDomains(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectedDetail = selectedNode && orgTree
    ? findNode(orgTree.root, selectedNode) : null
  const ritualByKey = Object.fromEntries(rituals.map((item) => [item.workflow_key, item])) as Record<string, RecurringWorkflow>
  const priorityItems = review ? [
    ...review.incidents.slice(0, 2).map((item) => ({
      key: `incident-${item.item_key}`,
      tone: 'rose',
      title: item.title,
      summary: item.summary,
      meta: item.recovery_status || item.project_display_name || item.project_key || 'incident',
    })),
    ...review.next_cycle_recommendations.slice(0, 2).map((item) => ({
      key: `recommendation-${item.source_ref || item.title}`,
      tone: 'emerald',
      title: item.title,
      summary: item.rationale,
      meta: `${item.action} / ${item.project_display_name}`,
    })),
    ...review.human_gate_hotspots.slice(0, 1).map((item) => ({
      key: `gate-${item.gate_key}`,
      tone: 'violet',
      title: item.title,
      summary: item.summary,
      meta: `${item.pending_count} pending`,
    })),
  ].slice(0, 5) : []

  /* ── Loading skeleton ──────────────────────────────────────── */
  if (loading) {
    return (
      <div data-testid="orgchart-skeleton" className="space-y-6 animate-pulse">
        <div className="grid grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="h-20 bg-gray-200 rounded-lg" />)}
        </div>
        <div className="flex justify-center"><div className="w-40 h-16 bg-gray-200 rounded-lg" /></div>
        <div className="grid grid-cols-5 gap-4">
          {[1,2,3,4,5].map(i => <div key={i} className="h-32 bg-gray-100 rounded-lg" />)}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div data-testid="orgchart-error" className="py-20 text-center">
        <p className="mb-4 text-lg text-red-600">{error}</p>
        <button onClick={load} className="px-4 py-2 text-sm text-white bg-blue-600 rounded hover:bg-blue-700">重试</button>
      </div>
    )
  }

  if (!orgTree) {
    return (
      <div data-testid="orgchart-empty" className="py-20 text-center">
        <p className="mb-4 text-gray-500">暂无组织数据</p>
        <button onClick={() => { load().catch(() => {}) }} className="px-4 py-2 text-sm text-white bg-blue-600 rounded hover:bg-blue-700">重新加载</button>
      </div>
    )
  }

  const root = orgTree.root
  const groups = root.children || []

  return (
    <div data-testid="orgchart-page">
      {/* ── Stats bar ──────────────────────────────────────── */}
      {stats && (
        <div data-testid="stats-bar" className="grid grid-cols-4 gap-4 mb-6">
          {[
            { label: 'Agent 总数', value: stats.agent_count, cls: 'bg-blue-50 border-blue-200' },
            { label: '任务总数', value: stats.task_total, cls: 'bg-gray-50 border-gray-200' },
            { label: '已完成', value: stats.task_completed, cls: 'bg-green-50 border-green-200' },
            { label: '待审批', value: stats.approval_pending, cls: 'bg-yellow-50 border-yellow-200' },
          ].map((s) => (
            <div key={s.label} className={`border rounded-lg p-4 ${s.cls}`}>
              <div className="text-2xl font-bold" data-testid={`stat-${s.label}`}>{s.value}</div>
              <div className="text-sm text-gray-600">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* ── Header ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">全局组织架构</h2>
        <div className="text-sm text-slate-500">Roles 自动从 `roles/` 目录加载，Review 通过 ritual 运行更新。</div>
      </div>

      {review && (
        <section data-testid="company-review-panel" className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-xs uppercase tracking-wide text-slate-400">{review.cycle_label}</div>
              <h3 className="text-lg font-semibold text-slate-900">{review.title}</h3>
              <p className="mt-2 max-w-3xl whitespace-pre-line text-sm text-slate-600">{review.summary_markdown}</p>
            </div>
            <div className="text-right text-xs text-slate-400">
              <div>updated: {review.updated_at ? new Date(review.updated_at.endsWith('Z') ? review.updated_at : `${review.updated_at}Z`).toLocaleString('zh-CN') : '-'}</div>
              <div>review id: #{review.id}</div>
            </div>
          </div>

          {bundleResult && (
            <div data-testid="company-review-bundle-result" className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
              <div className="font-medium">
                Bundle materialized: created {bundleResult.created_requirement_ids.length}, reused {bundleResult.reused_requirement_ids.length}
              </div>
              <div className="mt-1 text-xs text-emerald-800">
                {bundleResult.items.map((item) => `${item.status}: ${item.title}`).join(' · ')}
              </div>
            </div>
          )}

          <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-6">
            {[
              ['active', review.portfolio_summary.active_requirements],
              ['completed', review.portfolio_summary.completed_requirements],
              ['completion %', review.portfolio_summary.completion_rate],
              ['signals', review.portfolio_summary.open_signals],
              ['approval', review.portfolio_summary.approval_required_decisions],
              ['rebalance', review.portfolio_summary.rebalance_opportunities],
              ['over budget', review.portfolio_summary.projects_over_budget],
              ['publish blocked', review.portfolio_summary.blocked_publish_projects],
              ['budget pts', review.portfolio_summary.budget_spent_points],
              ['cache saved', review.portfolio_summary.prompt_cache_saved_chars],
              ['escalations', review.portfolio_summary.escalations],
              ['downgrades', review.portfolio_summary.downgrades],
              ['human gates', review.portfolio_summary.human_gate_hotspots],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
                <div className="text-lg font-semibold text-slate-900">{value}</div>
                <div className="text-xs text-slate-500">{label}</div>
              </div>
            ))}
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
              <div className="font-medium text-slate-900">Tier Mix</div>
              <div className="mt-1">mini: {review.portfolio_summary.tier_mix.mini ?? 0}</div>
              <div>standard: {review.portfolio_summary.tier_mix.standard ?? 0}</div>
              <div>max: {review.portfolio_summary.tier_mix.max ?? 0}</div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
              <div className="font-medium text-slate-900">Prompt Cache</div>
              <div className="mt-1">saved chars: {review.portfolio_summary.prompt_cache_saved_chars}</div>
              <div>deduped bindings: {review.portfolio_summary.deduped_bindings}</div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
              <div className="font-medium text-slate-900">Budget</div>
              <div className="mt-1">spent points: {review.portfolio_summary.budget_spent_points}</div>
              <div>tokens used: {review.portfolio_summary.tokens_used}</div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
              <div className="font-medium text-slate-900">Adaptation Loop</div>
              <div className="mt-1">escalations: {review.portfolio_summary.escalations}</div>
              <div>downgrades: {review.portfolio_summary.downgrades}</div>
            </div>
          </div>

          <div className="mt-5 grid gap-4 xl:grid-cols-2">
            <div data-testid="next-cycle-bundle-panel" className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h4 className="text-sm font-semibold text-slate-900">Next Cycle Requirement Bundle</h4>
                  <p className="mt-1 text-xs text-slate-500">将公司级 review 转成下一周期的可执行 requirement 集。</p>
                </div>
                <button
                  data-testid="materialize-company-review-bundle"
                  onClick={() => { handleMaterializeBundle().catch(() => {}) }}
                  className="px-4 py-2 text-sm text-white bg-emerald-600 rounded hover:bg-emerald-700"
                >
                  {materializingBundle ? '生成中…' : '生成 Bundle'}
                </button>
              </div>
              <div className="mt-3 space-y-3">
                {review.next_cycle_requirement_bundle.map((item) => (
                  <div key={item.bundle_item_key} className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-800">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-medium text-slate-900">{item.title}</div>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] uppercase tracking-wide text-slate-600">{item.priority}</span>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">{item.materialization_mode}</span>
                      {item.approval_required && (
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] text-amber-700">approval required</span>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-slate-600">
                      {item.project_display_name} / {item.action} / score {item.score} / budget {item.budget_cost}
                    </div>
                    <div className="mt-2 text-xs text-slate-500">{item.rationale}</div>
                    {item.acceptance_checks.length > 0 && (
                      <div className="mt-2 text-xs text-slate-500">acceptance checks: {item.acceptance_checks.length}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div data-testid="operator-review-package-panel" className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <h4 className="text-sm font-semibold text-slate-900">{review.operator_review_package.title}</h4>
              <p className="mt-2 whitespace-pre-line text-sm text-slate-600">{review.operator_review_package.summary_markdown}</p>
              <div className="mt-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Checklist</div>
                <div className="mt-2 space-y-2">
                  {review.operator_review_package.checklist.map((item) => (
                    <div key={item} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700">
                      {item}
                    </div>
                  ))}
                </div>
              </div>
              <div className="mt-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Operator Decisions</div>
                <div className="mt-2 space-y-2">
                  {review.operator_review_package.decisions.map((item) => (
                    <div key={item.decision_key} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                      <div className="font-medium">{item.title}</div>
                      <div className="mt-1">{item.summary}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="mt-5 grid gap-4 xl:grid-cols-3">
            <div>
              <h4 className="text-sm font-semibold text-slate-900">Top Bottlenecks</h4>
              <div className="mt-3 space-y-2">
                {review.bottlenecks.map((item) => (
                  <div key={item.item_key} className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900">
                    <div className="font-medium">{item.title}</div>
                    <div className="mt-1 text-xs text-amber-800">{item.summary}</div>
                    {item.recommendation && <div className="mt-2 text-xs text-amber-700">建议: {item.recommendation}</div>}
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-slate-900">Incidents</h4>
              <div data-testid="company-review-incidents" className="mt-3 space-y-2">
                {review.incidents.map((item) => (
                  <div key={item.item_key} className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-900">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-medium">{item.title}</div>
                      <span className={`rounded-full px-2 py-0.5 text-[11px] uppercase tracking-wide ${severityTone(item.severity)}`}>{item.severity}</span>
                      {item.incident_family && (
                        <span className="rounded-full bg-white/70 px-2 py-0.5 text-[11px] text-rose-700">{item.incident_family}</span>
                      )}
                      {item.incident_code && (
                        <span className="rounded-full bg-white/70 px-2 py-0.5 font-mono text-[11px] text-rose-700">{item.incident_code}</span>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-rose-800">{item.summary}</div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-rose-700">
                      <span>{item.project_display_name || item.project_key || 'Org Ops'}</span>
                      {item.recovery_status && <span>recovery: {item.recovery_status}</span>}
                      {item.requirement_id && <span>requirement #{item.requirement_id}</span>}
                    </div>
                    {item.recommendation && <div className="mt-2 text-xs text-rose-700">建议: {item.recommendation}</div>}
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-slate-900">Next Cycle Recommendations</h4>
              <div data-testid="company-review-recommendations" className="mt-3 space-y-2">
                {review.next_cycle_recommendations.map((item) => (
                  <div key={`${item.source_ref || item.title}-${item.action}`} className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-900">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-medium">{item.title}</div>
                      <span className={`rounded-full px-2 py-0.5 text-[11px] uppercase tracking-wide ${actionTone(item.action)}`}>{item.action}</span>
                      <span className="rounded-full bg-white/70 px-2 py-0.5 text-[11px] text-emerald-800">{item.candidate_type}</span>
                      {item.incident_family && (
                        <span className="rounded-full bg-white/70 px-2 py-0.5 text-[11px] text-emerald-800">{item.incident_family}</span>
                      )}
                      {item.incident_code && (
                        <span className="rounded-full bg-white/70 px-2 py-0.5 font-mono text-[11px] text-emerald-800">{item.incident_code}</span>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-emerald-800">
                      {item.project_display_name} / {item.action} / score {item.score} / budget {item.budget_cost}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-emerald-700">
                      {item.recovery_status && <span>recovery: {item.recovery_status}</span>}
                      {item.approval_required && <span>needs operator approval</span>}
                      {item.requirement_id && <span>requirement #{item.requirement_id}</span>}
                    </div>
                    <div className="mt-1 text-xs text-emerald-700">{item.rationale}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="mt-5 grid gap-4 xl:grid-cols-2">
            <div>
              <h4 className="text-sm font-semibold text-slate-900">Human Gate Hotspots</h4>
              <div data-testid="company-review-human-gates" className="mt-3 space-y-2">
                {review.human_gate_hotspots.map((item) => (
                  <div key={item.gate_key} className="rounded-xl border border-violet-200 bg-violet-50 px-3 py-3 text-sm text-violet-900">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-medium">{item.title}</div>
                      <span className="rounded-full bg-white/70 px-2 py-0.5 text-[11px] uppercase tracking-wide text-violet-800">{item.approval_type}</span>
                      {item.approval_scope && (
                        <span className="rounded-full bg-white/70 px-2 py-0.5 text-[11px] text-violet-800">{item.approval_scope}</span>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-violet-800">{item.summary}</div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-violet-700">
                      <span>{item.project_display_name || item.project_key || 'Org Ops'}</span>
                      {item.step_type && <span>step: {item.step_type}</span>}
                      <span>count: {item.occurrence_count}</span>
                      <span>pending: {item.pending_count}</span>
                    </div>
                    {item.recommendation && <div className="mt-2 text-xs text-violet-700">建议: {item.recommendation}</div>}
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-slate-900">Automation Candidates</h4>
              <div data-testid="company-review-automation-candidates" className="mt-3 space-y-2">
                {review.automation_candidates.map((item) => (
                  <div key={item.candidate_key} className="rounded-xl border border-cyan-200 bg-cyan-50 px-3 py-3 text-sm text-cyan-900">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-medium">{item.title}</div>
                      <span className="rounded-full bg-white/70 px-2 py-0.5 text-[11px] uppercase tracking-wide text-cyan-800">{item.automation_type}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[11px] ${item.priority === 'high' ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-700'}`}>{item.priority}</span>
                    </div>
                    <div className="mt-1 text-xs text-cyan-800">{item.rationale}</div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-cyan-700">
                      <span>{item.project_display_name || item.project_key || 'Org Ops'}</span>
                      <span>occurrences: {item.occurrence_count}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="mt-5">
            <h4 className="text-sm font-semibold text-slate-900">Project Highlights</h4>
            <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {review.project_highlights.map((item) => (
                <div key={item.project_key} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-700">
                  <div className="font-medium text-slate-900">{item.display_name}</div>
                  <div className="mt-1">readiness: {item.readiness_status} ({item.readiness_score})</div>
                  <div>active / queued: {item.active_count} / {item.queued_count}</div>
                  <div>bug / blocked publish: {item.bug_report_count} / {item.blocked_publish_count}</div>
                  <div>autonomy: {item.autonomy_mode} / weight x{item.scheduler_weight}</div>
                  <div>budget used / remaining: {item.budget_used} / {item.budget_remaining}</div>
                  <div>completed requirements: {item.completed_requirements}</div>
                  <div>runtime budget spent: {item.budget_spent_points}</div>
                  <div>prompt cache saved: {item.prompt_cache_saved_chars}</div>
                  <div>adaptation up/down: {item.escalations} / {item.downgrades}</div>
                  <div>tier mix: mini {item.tier_mix.mini ?? 0} / std {item.tier_mix.standard ?? 0} / max {item.tier_mix.max ?? 0}</div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      <section data-testid="operator-rituals-panel" className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-400">Operator Rituals</div>
            <h3 className="text-lg font-semibold text-slate-900">Daily / Weekly Ritual Board</h3>
            <p className="mt-2 max-w-3xl text-sm text-slate-600">
              让 operator 像管理一家 AI 公司一样看 intake、dispatch、closeout 和 weekly COO review。
            </p>
          </div>
          <div className="text-xs text-slate-500">
            visible rituals: {rituals.length}
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[1.2fr,1fr]">
          <div data-testid="operator-priority-panel" className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <h4 className="text-sm font-semibold text-slate-900">Today Priorities</h4>
            <p className="mt-1 text-xs text-slate-500">来自 incident、next-cycle recommendation 和 human gate hotspot 的今日优先项。</p>
            <div className="mt-3 space-y-2">
              {priorityItems.length === 0 && (
                <div className="rounded-xl border border-dashed border-slate-300 bg-white px-3 py-3 text-sm text-slate-500">
                  当前没有优先事项，先运行 daily rituals。
                </div>
              )}
              {priorityItems.map((item) => (
                <div
                  key={item.key}
                  className={`rounded-xl border px-3 py-3 text-sm ${
                    item.tone === 'rose'
                      ? 'border-rose-200 bg-rose-50 text-rose-900'
                      : item.tone === 'violet'
                        ? 'border-violet-200 bg-violet-50 text-violet-900'
                        : 'border-emerald-200 bg-emerald-50 text-emerald-900'
                  }`}
                >
                  <div className="font-medium">{item.title}</div>
                  <div className="mt-1 text-xs opacity-90">{item.summary}</div>
                  <div className="mt-2 text-[11px] opacity-80">{item.meta}</div>
                </div>
              ))}
            </div>
          </div>

          <div data-testid="weekly-coo-package-panel" className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <h4 className="text-sm font-semibold text-slate-900">Weekly COO Review</h4>
            <p className="mt-1 text-xs text-slate-500">来自 weekly operating review 的 operator 包和 ritual 摘要。</p>
            {review ? (
              <>
                <div className="mt-3 whitespace-pre-line rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-700">
                  {review.operator_review_package.summary_markdown}
                </div>
                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700">
                    <div className="font-medium text-slate-900">Decisions</div>
                    <div className="mt-1">{review.operator_review_package.decisions.length}</div>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-xs text-slate-700">
                    <div className="font-medium text-slate-900">Recommended Bundle</div>
                    <div className="mt-1">{review.operator_review_package.recommended_bundle_item_keys.length}</div>
                  </div>
                </div>
              </>
            ) : (
              <div className="mt-3 rounded-xl border border-dashed border-slate-300 bg-white px-3 py-3 text-sm text-slate-500">
                暂无 weekly COO review。
              </div>
            )}
          </div>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[
            ritualByKey.morning_intake_sweep,
            ritualByKey.dispatcher_loop,
            ritualByKey.closeout_and_compact_sweep,
            ritualByKey.weekly_operating_review,
          ].filter(Boolean).map((ritual) => {
            const result = ritual.last_result || {}
            return (
              <div key={ritual.workflow_key} data-testid={`ritual-${ritual.workflow_key}`} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-900">{ritual.display_name}</div>
                    <div className="mt-1 text-xs text-slate-500">{ritual.owner_role} / {String(ritual.schedule?.cadence || ritual.trigger_type || 'scheduled')}</div>
                  </div>
                  <button
                    data-testid={`run-${ritual.workflow_key}`}
                    onClick={() => { handleRunRitual(ritual.workflow_key).catch(() => {}) }}
                    className="rounded-lg bg-slate-900 px-3 py-2 text-xs text-white hover:bg-slate-800"
                  >
                    {ritualRunning[ritual.workflow_key] ? '运行中…' : '运行'}
                  </button>
                </div>
                <div className="mt-3 text-xs text-slate-500">
                  last run: {ritual.last_run_at ? new Date(ritual.last_run_at.endsWith('Z') ? ritual.last_run_at : `${ritual.last_run_at}Z`).toLocaleString('zh-CN') : '-'}
                </div>
                <div className="mt-3 space-y-1 text-xs text-slate-700">
                  {ritual.workflow_key === 'morning_intake_sweep' && (
                    <>
                      <div>created: {Array.isArray(result.created_requirement_ids) ? result.created_requirement_ids.length : 0}</div>
                      <div>operator attention: {Array.isArray(result.operator_attention_items) ? result.operator_attention_items.length : 0}</div>
                    </>
                  )}
                  {ritual.workflow_key === 'dispatcher_loop' && (
                    <>
                      <div>started: {Array.isArray(result.started_ids) ? result.started_ids.length : 0}</div>
                      <div>follow-ups: {Array.isArray(result.follow_up_actions) ? result.follow_up_actions.length : 0}</div>
                    </>
                  )}
                  {ritual.workflow_key === 'closeout_and_compact_sweep' && (
                    <>
                      <div>acceptance: {Number(result.acceptance_candidates || 0)}</div>
                      <div>snapshots: {Array.isArray(result.review_snapshot_requirement_ids) ? result.review_snapshot_requirement_ids.length : 0}</div>
                    </>
                  )}
                  {ritual.workflow_key === 'weekly_operating_review' && (
                    <>
                      <div>bundle items: {Number(result.bundle_item_count || 0)}</div>
                      <div>automation: {Number(result.automation_candidate_count || 0)}</div>
                    </>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </section>

      <div data-testid="org-root" className="p-5 mb-6 border rounded-xl bg-slate-50">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-sm font-semibold text-slate-900">{root.display_name}</div>
            <div className="mt-1 text-sm text-slate-600">{root.goal}</div>
          </div>
          <button
            data-testid="root-detail-toggle"
            className="px-3 py-2 text-sm border rounded hover:bg-white"
            onClick={() => setSelectedNode(selectedNode === root.id ? null : root.id)}
          >
            查看详情
          </button>
        </div>
        <div className="mt-3 text-xs text-slate-500">
          动态分组: {groups.length} · 真实角色: {groups.reduce((count, group) => count + (group.children?.length || 0), 0)}
        </div>
      </div>

      <div data-testid="group-grid" className="grid gap-4 lg:grid-cols-2">
        {groups.map(group => {
          const c = getColor(group.color)
          const isExpanded = expandedDomains.has(group.id)
          const isSelected = selectedNode === group.id
          return (
            <section key={group.id} data-testid={`group-${group.id}`} className={`rounded-xl border-2 p-4 ${c.bg} ${c.border}`}>
              <div
                className={`rounded-lg border bg-white px-4 py-3 cursor-pointer transition-all duration-200
                  ${isSelected ? 'ring-2 ring-blue-500 scale-105 shadow-md' : 'hover:shadow-md hover:-translate-y-0.5'}`}
                onClick={() => {
                  toggleDomain(group.id)
                  setSelectedNode(isSelected ? null : group.id)
                }}
              >
                <div className="mt-1 text-sm font-bold">{group.display_name}</div>
                <div className="text-xs text-gray-500 mt-0.5">{group.children?.length || 0} 个角色</div>
                <div className="mt-1 text-xs">{isExpanded ? '▼' : '▶'}</div>
              </div>
              {isExpanded && (
                <div className="grid gap-3 mt-4 md:grid-cols-2">
                  {(group.children || []).map(agent => (
                    <div
                      key={agent.id}
                      data-testid={`node-${agent.id}`}
                      className={`bg-white rounded-md px-3 py-3 border cursor-pointer transition-all duration-200
                        ${selectedNode === agent.id ? 'ring-2 ring-blue-500 scale-[1.02] shadow-sm' : 'hover:shadow-sm'}`}
                      onClick={() => setSelectedNode(selectedNode === agent.id ? null : agent.id)}
                    >
                      <div className="text-sm font-medium">{agent.display_name}</div>
                      <div className="mt-1 text-xs text-gray-500 line-clamp-2">{agent.goal}</div>
                      {agent.skills && agent.skills.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {agent.skills.slice(0, 4).map(skill => (
                            <span key={skill} className={`text-[10px] px-1.5 py-0.5 rounded ${c.tag} ${c.tagText}`}>{skill}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </section>
          )
        })}
      </div>

      {/* ── Selected node detail ───────────────────────────── */}
      {selectedDetail && (
        <div data-testid="node-detail" className="p-5 mt-6 bg-white border rounded-lg shadow-sm">
          <h3 className="mb-2 text-lg font-bold">节点详情</h3>
          <NodeDetailView node={selectedDetail} />
        </div>
      )}
    </div>
  )
}

/* ── Node detail view ────────────────────────────────────────── */
function NodeDetailView({ node }: { node: OrgNode }) {
  const c = getColor(node.color)
  return (
    <div data-testid={`detail-${node.id}`}>
      <div className="flex items-center gap-3 mb-2">
        {node.icon && <span className="text-2xl">{node.icon}</span>}
        <div>
          <h4 className="text-lg font-bold">{node.display_name}</h4>
          <span className={`text-xs px-2 py-0.5 rounded ${c.tag} ${c.tagText}`}>{node.type}</span>
          <span className="ml-2 font-mono text-xs text-gray-400">{node.id}</span>
        </div>
      </div>
      <p className="mb-3 text-sm text-gray-600">{node.goal}</p>
      {node.project && (
        <p className="mb-2 text-xs text-gray-400">项目: <span className="font-mono">{node.project}</span></p>
      )}
      {node.skills && node.skills.length > 0 && (
        <div className="flex gap-1.5 flex-wrap mb-3">
          {node.skills.map(s => (
            <span key={s} className={`text-xs px-2 py-0.5 rounded ${c.tag} ${c.tagText}`}>{s}</span>
          ))}
        </div>
      )}
      {node.children && node.children.length > 0 && (
        <div className="text-xs text-gray-500">
          下级节点: {node.children.map(c => c.display_name).join(', ')}
        </div>
      )}
    </div>
  )
}

/* ── Helper: find node by id in tree ─────────────────────────── */
function findNode(node: OrgNode, id: string): OrgNode | null {
  if (node.id === id) return node
  for (const child of node.children || []) {
    const found = findNode(child, id)
    if (found) return found
  }
  return null
}
