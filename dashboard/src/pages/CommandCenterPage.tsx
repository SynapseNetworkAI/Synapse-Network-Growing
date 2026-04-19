import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, DashboardStats, PlanningMissionControl, RecurringWorkflowHealth, WorkflowRunsSummary } from '../api'
import { ActionButton, AgentReasoningCard, CockpitPanel, EmptyCockpitState, MetricTile } from '../components/controlPlane'
import { StateBadge } from '../components/workbench'

type LoadState = {
  stats: DashboardStats | null
  workflows: WorkflowRunsSummary | null
  planning: PlanningMissionControl | null
  health: RecurringWorkflowHealth | null
}

function numberValue(value: number | undefined | null) {
  return value == null ? 0 : value
}

function formatHealth(value: unknown) {
  if (!value || typeof value !== 'object') return 'unknown'
  const record = value as Record<string, unknown>
  return String(record.health_status || record.status || (record.running ? 'running' : 'unknown'))
}

export default function CommandCenterPage() {
  const [state, setState] = useState<LoadState>({ stats: null, workflows: null, planning: null, health: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.allSettled([
      api.getStats(),
      api.getWorkflowRunsSummary(),
      api.getPlanningMissionControl(),
      api.getRecurringWorkflowHealth(),
    ]).then((results) => {
      if (cancelled) return
      const [stats, workflows, planning, health] = results
      setState({
        stats: stats.status === 'fulfilled' ? stats.value : null,
        workflows: workflows.status === 'fulfilled' ? workflows.value : null,
        planning: planning.status === 'fulfilled' ? planning.value : null,
        health: health.status === 'fulfilled' ? health.value : null,
      })
      const rejected = results.find((result) => result.status === 'rejected')
      setError(rejected && rejected.status === 'rejected' ? String(rejected.reason?.message || rejected.reason) : null)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const activeGoals = useMemo(
    () => (state.planning?.goal_lanes || []).filter((lane) => String(lane.goal.status || 'active') === 'active'),
    [state.planning],
  )
  const blockers = numberValue(state.workflows?.needs_human) + numberValue(state.workflows?.failed)

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-[32px] border border-white/10 bg-[radial-gradient(circle_at_20%_20%,rgba(34,211,238,0.16),transparent_34%),linear-gradient(135deg,rgba(39,42,49,0.88),rgba(16,19,26,0.96))] px-6 py-7 shadow-[0_28px_90px_rgba(0,0,0,0.34)]">
        <div className="absolute right-6 top-6 h-24 w-24 rounded-full border border-cyan-300/20 bg-cyan-300/10 blur-2xl" />
        <div className="relative flex flex-wrap items-end justify-between gap-6">
          <div>
            <div className="machine-label text-cyan-200/70">Human-Agent Control Plane</div>
            <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-[-0.05em] text-[color:var(--ops-text-title)] md:text-5xl">
              Command Center
            </h1>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-[color:var(--ops-text-muted)]">
              这里不是 Jira，也不是日志墙。它只回答三件事：系统想达成什么、机器正在做什么、哪里需要你做决定。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <ActionButton href="/planning" tone="primary">调整目标</ActionButton>
            <ActionButton href="/gates">处理门禁</ActionButton>
            <ActionButton href="/workflows">查看运行</ActionButton>
          </div>
        </div>
      </section>

      {error ? (
        <AgentReasoningCard
          title="Partial data loaded"
          tone="warning"
          summary={`部分控制面数据拉取失败：${error}。页面保留可用数据，避免 operator 被空白页阻断。`}
        />
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <MetricTile label="Active Requirements" value={state.stats?.requirement_active ?? '-'} detail="正式需求池中仍需推进的事项" tone="info" />
        <MetricTile label="Running Workflows" value={state.stats?.workflow_running ?? state.workflows?.running ?? '-'} detail="状态机正在执行或等待下一步" tone="success" />
        <MetricTile label="Needs Human" value={state.stats?.human_gate_pending ?? state.workflows?.needs_human ?? '-'} detail="必须由 Human Oracle 决策" tone={blockers ? 'warning' : 'muted'} />
        <MetricTile label="Failed" value={state.stats?.workflow_failed ?? state.workflows?.failed ?? '-'} detail="失败、超预算或证据不足" tone={numberValue(state.workflows?.failed) ? 'danger' : 'muted'} />
        <MetricTile label="Completed Today" value={state.workflows?.completed_today ?? '-'} detail="今天真正完成的 workflow run" tone="success" />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <CockpitPanel
          eyebrow="Active Fronts"
          title="Goal Mission Lanes"
          description="从 Operating Manifest 聚合当前战线。Planner 只产生候选，正式执行仍由 Requirement 和 Workflow Run 承接。"
          actions={<ActionButton href="/planning">打开 Planning</ActionButton>}
        >
          {loading ? (
            <div className="text-sm text-[color:var(--ops-text-muted)]">Loading mission lanes...</div>
          ) : activeGoals.length ? (
            <div className="grid gap-3">
              {activeGoals.slice(0, 5).map((lane) => (
                <Link key={lane.goal_key} to="/planning" className="group rounded-2xl border border-white/8 bg-white/[0.035] px-4 py-4 transition hover:border-cyan-300/25 hover:bg-cyan-300/[0.06]">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="font-mono text-sm font-semibold text-cyan-100">{lane.goal_key}</div>
                      <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-body)]">{String(lane.goal.intent || lane.goal.title || 'No intent')}</div>
                    </div>
                    <StateBadge tone="running">{String(lane.goal.domain || 'ops')}</StateBadge>
                  </div>
                  <div className="mt-4 grid gap-2 text-xs text-[color:var(--ops-text-muted)] sm:grid-cols-4">
                    <span>candidates {Object.values(lane.rollup.candidate_status_counts || {}).reduce((a, b) => a + Number(b), 0)}</span>
                    <span>requirements {Object.values(lane.rollup.requirement_status_counts || {}).reduce((a, b) => a + Number(b), 0)}</span>
                    <span>workflows {Object.values(lane.rollup.workflow_status_counts || {}).reduce((a, b) => a + Number(b), 0)}</span>
                    <span>releases {Object.values(lane.rollup.release_status_counts || {}).reduce((a, b) => a + Number(b), 0)}</span>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyCockpitState title="No active goals" description="当前 active manifest 没有 active goal。请在 Planning 中创建或恢复一个经营目标。" actions={<ActionButton href="/planning" tone="primary">打开 Planning</ActionButton>} />
          )}
        </CockpitPanel>

        <CockpitPanel eyebrow="Blockers" title="Human Oracle Queue" description="真正需要人判断的地方集中在这里，不让 Agent 绕过风险门。">
          <div className="space-y-3">
            <AgentReasoningCard
              title={blockers ? `${blockers} blocker(s) require attention` : 'No operator blocker'}
              tone={blockers ? 'warning' : 'info'}
              summary={blockers ? '存在 awaiting_operator 或 failed workflow。优先进入 Oracle Gates 处理风险、证据或继续重试。' : '没有等待人工处理的 blocker。系统可以继续让 Runner 推进低风险任务。'}
              metadata={<ActionButton href="/gates" tone={blockers ? 'primary' : 'default'}>打开 Oracle Gates</ActionButton>}
            />
            <div className="rounded-2xl border border-white/8 bg-white/[0.025] px-4 py-4">
              <div className="machine-label text-[color:var(--ops-text-caption)]">Background Health</div>
              <div className="mt-3 grid gap-2 text-sm text-[color:var(--ops-text-body)]">
                <div>Bug Scheduler: {formatHealth(state.health?.bug_log_scheduler)}</div>
                <div>Notification Dispatcher: {formatHealth(state.health?.notification_dispatcher)}</div>
                <div>Recurring Registry: {formatHealth(state.health?.recurring_registry)}</div>
              </div>
            </div>
          </div>
        </CockpitPanel>
      </div>
    </div>
  )
}
