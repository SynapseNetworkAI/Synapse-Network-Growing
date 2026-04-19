import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  api,
  DeclarativeWorkflowDefinition,
  DeclarativeWorkflowRunSummary,
  WorkflowRunsSummary,
} from '../api'
import { StateBadge, useToast } from '../components/workbench'

type WorkflowTab = 'active' | 'needs_human' | 'failed' | 'completed' | 'archived' | 'definitions'

const TABS: Array<{ key: WorkflowTab; label: string; helper: string }> = [
  { key: 'active', label: 'Active', helper: '正在推进或暂停中的状态机' },
  { key: 'needs_human', label: 'Needs Human', helper: '等待人工门禁决策' },
  { key: 'failed', label: 'Failed', helper: '失败、超预算或需要修复' },
  { key: 'completed', label: 'Completed', helper: '已完成的工作流档案' },
  { key: 'archived', label: 'Archived', helper: '已隐藏但可追溯的历史' },
  { key: 'definitions', label: 'Definitions', helper: '只读 workflow 轨道管理' },
]

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function formatDuration(value: number | null | undefined) {
  if (!value) return '-'
  if (value < 1000) return `${value}ms`
  const seconds = Math.round(value / 1000)
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

function statusTone(status: string) {
  if (['succeeded', 'completed', 'done'].includes(status)) return 'delivered'
  if (['running', 'pending', 'paused'].includes(status)) return 'running'
  if (['failed', 'error', 'cancelled'].includes(status)) return 'blocked'
  if (status === 'awaiting_operator') return 'validating'
  return 'muted'
}

function workflowOutcome(item: DeclarativeWorkflowRunSummary) {
  if (item.needs_human || item.pending_human_gate_count > 0 || item.status === 'awaiting_operator') return '等待人工门禁'
  if (item.status === 'failed') return item.resolution || '失败'
  if (item.completed_truthfully || item.is_truly_completed) return item.pr_url ? '已完成，PR 可查看' : '已完成'
  if (['succeeded', 'completed', 'done'].includes(item.status)) return '终态但证据/门禁未完全收口'
  if (item.status === 'paused') return '已暂停'
  return '执行中'
}

function workflowNextAction(item: DeclarativeWorkflowRunSummary) {
  if (item.needs_human || item.pending_human_gate_count > 0 || item.status === 'awaiting_operator') return '处理 Human Gate'
  if (item.status === 'failed') return '查看失败原因'
  if (item.pr_url) return '打开 PR'
  if (item.completed_truthfully || item.is_truly_completed || ['succeeded', 'completed', 'done'].includes(item.status)) return '查看完成证据'
  return '查看运行详情'
}

function SummaryCard({ label, value, detail }: Readonly<{ label: string; value: number | string; detail: string }>) {
  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-4 py-4">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{value}</div>
      <div className="mt-2 text-xs text-[color:var(--ops-text-muted)]">{detail}</div>
    </div>
  )
}

function EmptyWorkflowState({
  summary,
  onOpenDefinitions,
}: Readonly<{
  summary: WorkflowRunsSummary | null
  onOpenDefinitions: () => void
}>) {
  const navigate = useNavigate()
  const count = summary?.pending_candidate_count ?? 0
  return (
    <div className="rounded-[var(--ops-radius-panel)] border border-dashed border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-6 py-10">
      <div className="max-w-3xl">
        <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">No Workflow Runs Yet</div>
        <h3 className="mt-3 text-xl font-semibold text-[color:var(--ops-text-title)]">还没有工作流运行记录</h3>
        <p className="mt-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">
          当前工作流列表为空，不代表系统没有发现事情。它表示候选需求还没有 materialize 成正式 Requirement，或者 Requirement 还没有提交并启动 declarative workflow run。
          {count > 0 ? ` 当前已有 ${count} 个 pending / approved RequirementCandidate 等待进入正式需求。` : ' 当前没有等待处理的候选需求。'}
        </p>
        {summary?.recent_candidates?.length ? (
          <div className="mt-5 grid gap-2">
            {summary.recent_candidates.map((candidate) => (
              <div key={candidate.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-sm">
                <div className="font-medium text-[color:var(--ops-text-title)]">#{candidate.id} {candidate.title}</div>
                <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{candidate.goal_key || '-'} · {candidate.workflow_key || 'workflow TBD'} · {candidate.status}</div>
              </div>
            ))}
          </div>
        ) : null}
        <div className="mt-6 flex flex-wrap gap-2">
          <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2.5 text-sm font-medium text-white" onClick={() => navigate('/planning')}>
            打开 Planning
          </button>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => navigate('/requirements')}>
            新建 Requirement
          </button>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={onOpenDefinitions}>
            查看 Workflow Definitions
          </button>
        </div>
      </div>
    </div>
  )
}

function WorkflowRunsTable({
  items,
  tab,
  onArchive,
  onCreateFollowup,
}: Readonly<{
  items: DeclarativeWorkflowRunSummary[]
  tab: WorkflowTab
  onArchive: (item: DeclarativeWorkflowRunSummary) => void
  onCreateFollowup: (item: DeclarativeWorkflowRunSummary) => void
}>) {
  const navigate = useNavigate()
  return (
    <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse">
          <thead className="bg-[color:var(--ops-panel-subtle)]">
            <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
              <th className="px-5 py-4 font-medium">Workflow</th>
              <th className="px-4 py-4 font-medium">Requirement</th>
              <th className="px-4 py-4 font-medium">Outcome</th>
              <th className="px-4 py-4 font-medium">Evidence</th>
              <th className="px-4 py-4 font-medium">Next Action</th>
              <th className="px-4 py-4 font-medium">Completed</th>
              <th className="px-5 py-4 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className="border-t border-[color:var(--ops-stroke-soft)] transition hover:bg-[color:var(--ops-panel-subtle)]">
                <td className="px-5 py-4">
                  <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{item.workflow_key}</div>
                  <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">run #{item.id} · {item.current_state}</div>
                  {item.goal_key ? <div className="mt-1 text-xs text-[color:var(--ops-text-muted)]">goal: {item.goal_key}</div> : null}
                </td>
                <td className="px-4 py-4">
                  <button type="button" className="text-left text-sm font-medium text-[color:var(--ops-text-body)]" onClick={() => navigate(`/requirements/${item.requirement_id}`)}>
                    #{item.requirement_id} {item.requirement_title || 'Untitled'}
                  </button>
                </td>
                <td className="px-4 py-4">
                  <StateBadge tone={statusTone(item.needs_human ? 'awaiting_operator' : item.status)}>{item.outcome_label || item.status}</StateBadge>
                  <div className="mt-2 text-xs text-[color:var(--ops-text-muted)]">{workflowOutcome(item)}</div>
                  {item.resolution ? <div className="mt-1 font-mono text-[11px] text-[color:var(--ops-text-caption)]">{item.resolution}</div> : null}
                  {item.simulated_delivery ? <div className="mt-1 text-xs text-amber-700">Simulated PR</div> : null}
                  {item.evidence_complete === false ? <div className="mt-1 text-xs text-amber-700">Evidence incomplete</div> : null}
                </td>
                <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                  <div>{item.atom_count ?? 0} atoms · {item.artifact_count ?? 0} artifacts</div>
                  <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{item.last_atom || 'no atom yet'}</div>
                  <div className="mt-1">{item.pending_human_gate_count ? `${item.pending_human_gate_count} gate pending` : item.last_human_gate_decision ? `gate: ${item.last_human_gate_decision}` : 'no pending gate'}</div>
                  <div className="mt-1">duration: {formatDuration(item.duration_ms)}</div>
                </td>
                <td className="px-4 py-4 text-sm text-[color:var(--ops-text-body)]">
                  {workflowNextAction(item)}
                  {item.pr_url ? (
                    <a className="mt-1 block text-xs text-[color:var(--ops-accent-strong)]" href={item.pr_url} target="_blank" rel="noreferrer">
                      PR / delivery
                    </a>
                  ) : null}
                </td>
                <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                  {formatTime(item.completed_at || item.updated_at)}
                  {item.archived_at ? <div className="mt-1 text-xs">archived: {formatTime(item.archived_at)}</div> : null}
                </td>
                <td className="px-5 py-4">
                  <div className="flex flex-wrap justify-end gap-2">
                    <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/workflows/${item.id}`)}>
                      查看
                    </button>
                    <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => onCreateFollowup(item)}>
                      Follow-up
                    </button>
                    {tab !== 'archived' ? (
                      <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => onArchive(item)}>
                        归档
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function DefinitionsPanel({ definitions }: Readonly<{ definitions: DeclarativeWorkflowDefinition[] }>) {
  const navigate = useNavigate()
  return (
    <section className="grid gap-3 lg:grid-cols-2" data-testid="workflow-definitions-panel">
      {definitions.map((definition) => {
        const atomCount = definition.states.filter((state) => state.atom_key).length
        const humanGateRequired = JSON.stringify(definition.risk_policy || {}).toLowerCase().includes('human')
        return (
          <div key={definition.workflow_key} className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{definition.workflow_key}</div>
                <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{definition.title || definition.description}</div>
              </div>
              <StateBadge tone={definition.status === 'active' ? 'ready' : 'muted'}>{definition.status}</StateBadge>
            </div>
            <div className="mt-4 grid gap-3 text-sm text-[color:var(--ops-text-muted)] sm:grid-cols-3">
              <div>
                <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Initial</div>
                <div className="mt-1 font-mono text-xs">{definition.initial_state}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">States</div>
                <div className="mt-1">{definition.states.length} states · {atomCount} atoms</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Gate</div>
                <div className="mt-1">{humanGateRequired ? 'human gate policy' : 'policy by states'}</div>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/workflows?definition=${definition.workflow_key}`)}>
                查看最近运行
              </button>
              <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigator.clipboard?.writeText(JSON.stringify(definition.spec, null, 2))}>
                Copy Spec
              </button>
            </div>
          </div>
        )
      })}
    </section>
  )
}

export default function WorkflowRunsPage() {
  const [items, setItems] = useState<DeclarativeWorkflowRunSummary[]>([])
  const [definitions, setDefinitions] = useState<DeclarativeWorkflowDefinition[]>([])
  const [summary, setSummary] = useState<WorkflowRunsSummary | null>(null)
  const [tab, setTab] = useState<WorkflowTab>('active')
  const [filters, setFilters] = useState({
    workflow_key: '',
    current_state: '',
    risk_level: '',
    requirement_id: '',
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const toast = useToast()

  const activeTab = useMemo(() => TABS.find((item) => item.key === tab) || TABS[0], [tab])

  async function load(nextTab = tab) {
    setLoading(true)
    setError(null)
    try {
      const [nextSummary, nextDefinitions] = await Promise.all([
        api.getWorkflowRunsSummary(),
        api.getWorkflowDefinitions(),
      ])
      setSummary(nextSummary)
      setDefinitions(nextDefinitions)
      if (nextTab === 'definitions') {
        setItems([])
      } else {
        const page = await api.getWorkflowRunsPage({
          page: 1,
          page_size: 100,
          tab: nextTab,
          include_archived: nextTab === 'archived',
          workflow_key: filters.workflow_key || undefined,
          current_state: filters.current_state || undefined,
          risk_level: filters.risk_level || undefined,
          requirement_id: filters.requirement_id ? Number(filters.requirement_id) : undefined,
        })
        setItems(page.items)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载工作流失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(tab).catch(() => {})
  }, [tab, filters.workflow_key, filters.current_state, filters.risk_level])

  async function archiveRun(item: DeclarativeWorkflowRunSummary) {
    try {
      await api.archiveWorkflowRun(item.id, { archived_by: 'operator', reason: `Archived from ${tab} view` })
      toast.success(`Workflow #${item.id} 已归档`)
      await load(tab)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '归档失败')
    }
  }

  async function createFollowup(item: DeclarativeWorkflowRunSummary) {
    try {
      const payload = await api.createWorkflowFollowup(item.id, {
        title: `Follow-up: ${item.requirement_title || item.workflow_key}`,
        operator: 'operator',
      })
      toast.success(`已创建 follow-up requirement #${payload.requirement_id}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '创建 follow-up 失败')
    }
  }

  const hasNoRuns = !loading && tab !== 'definitions' && items.length === 0

  return (
    <div className="space-y-5" data-testid="workflow-runs-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Workflow Operations Center</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">工作流运行与完成档案</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
              Workflow Run 是完成任务的主台账：Requirement 进入状态机后，所有 atom、证据、human gate、PR 与完成结果都在这里追踪。
            </p>
          </div>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load(tab).catch(() => {})}>
            刷新
          </button>
        </div>
      </section>

      {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}

      <section className="grid gap-3 md:grid-cols-3 xl:grid-cols-6" data-testid="workflow-run-stats">
        <SummaryCard label="Running" value={summary?.running ?? 0} detail="pending / running / paused" />
        <SummaryCard label="Needs Human" value={summary?.needs_human ?? 0} detail="等待 operator 决策" />
        <SummaryCard label="Failed" value={summary?.failed ?? 0} detail="需要修复或人工接管" />
        <SummaryCard label="Completed Today" value={summary?.completed_today ?? 0} detail={`${summary?.completed ?? 0} total completed`} />
        <SummaryCard label="Avg Duration" value={formatDuration(summary?.average_duration_ms)} detail="已完成 run 平均耗时" />
        <SummaryCard label="Pending Release" value={summary?.pending_release ?? 0} detail="PR / release 待处理" />
      </section>

      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-4 py-4">
        <div className="flex flex-wrap gap-2">
          {TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              className={[
                'rounded-2xl px-4 py-3 text-left text-sm transition',
                tab === item.key
                  ? 'bg-cyan-300/15 text-cyan-100 shadow-[0_0_0_1px_rgba(103,232,249,0.32)]'
                  : 'border border-[color:var(--ops-stroke-soft)] text-[color:var(--ops-text-body)] hover:bg-[color:var(--ops-panel-subtle)]',
              ].join(' ')}
              onClick={() => setTab(item.key)}
            >
              <span className="block font-semibold">{item.label}</span>
              <span className={tab === item.key ? 'text-cyan-100/70' : 'text-[color:var(--ops-text-caption)]'}>{item.helper}</span>
            </button>
          ))}
        </div>
      </section>

      {tab !== 'definitions' ? (
        <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-4" data-testid="workflow-run-filters">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" value={filters.workflow_key} onChange={(event) => setFilters((current) => ({ ...current, workflow_key: event.target.value }))}>
              <option value="">全部 workflow</option>
              {definitions.map((definition) => (
                <option key={definition.workflow_key} value={definition.workflow_key}>{definition.workflow_key}</option>
              ))}
            </select>
            <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" placeholder="current_state" value={filters.current_state} onChange={(event) => setFilters((current) => ({ ...current, current_state: event.target.value }))} />
            <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" value={filters.risk_level} onChange={(event) => setFilters((current) => ({ ...current, risk_level: event.target.value }))}>
              <option value="">全部风险</option>
              <option value="normal">normal</option>
              <option value="high">high</option>
              <option value="critical">critical</option>
            </select>
            <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" placeholder="requirement id" value={filters.requirement_id} onChange={(event) => setFilters((current) => ({ ...current, requirement_id: event.target.value.replace(/[^0-9]/g, '') }))} />
            <div className="flex items-center text-xs text-[color:var(--ops-text-caption)]">{activeTab.helper}</div>
          </div>
        </section>
      ) : null}

      {tab === 'definitions' ? <DefinitionsPanel definitions={definitions} /> : null}
      {hasNoRuns ? <EmptyWorkflowState summary={summary} onOpenDefinitions={() => setTab('definitions')} /> : null}
      {!loading && tab !== 'definitions' && items.length > 0 ? (
        <WorkflowRunsTable items={items} tab={tab} onArchive={archiveRun} onCreateFollowup={createFollowup} />
      ) : null}
      {loading ? (
        <div className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-8 text-center text-sm text-[color:var(--ops-text-muted)]">
          加载工作流运行台账…
        </div>
      ) : null}
    </div>
  )
}
