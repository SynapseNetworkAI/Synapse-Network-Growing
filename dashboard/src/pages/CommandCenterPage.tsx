import { useEffect, useState } from 'react'
import { api, DashboardStats, MissionBoard, PlanningTaskBoard, WorkflowRunsSummary } from '../api'
import { ActionButton, AgentReasoningCard, CockpitPanel, MetricTile } from '../components/controlPlane'
import { MissionBoardPanel } from '../components/MissionBoardPanel'

type LoadState = {
  stats: DashboardStats | null
  workflows: WorkflowRunsSummary | null
  board: MissionBoard | null
  taskBoard: PlanningTaskBoard | null
}

function numberValue(value: number | undefined | null) {
  return value == null ? 0 : value
}

export default function CommandCenterPage() {
  const [state, setState] = useState<LoadState>({ stats: null, workflows: null, board: null, taskBoard: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.allSettled([
      api.getStats(),
      api.getWorkflowRunsSummary(),
      api.getPlanningMissionBoard(),
      api.getPlanningTaskBoard(),
    ]).then((results) => {
      if (cancelled) return
      const [stats, workflows, board, taskBoard] = results
      setState({
        stats: stats.status === 'fulfilled' ? stats.value : null,
        workflows: workflows.status === 'fulfilled' ? workflows.value : null,
        board: board.status === 'fulfilled' ? board.value : null,
        taskBoard: taskBoard.status === 'fulfilled' ? taskBoard.value : null,
      })
      const rejected = results.find((result) => result.status === 'rejected')
      setError(rejected && rejected.status === 'rejected' ? String(rejected.reason?.message || rejected.reason) : null)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const blockers = numberValue(state.workflows?.pending_gate_count ?? state.workflows?.needs_human) + numberValue(state.workflows?.failed_count ?? state.workflows?.failed)
  const board = state.board
  const taskColumns = (state.taskBoard?.columns || []).filter((column) => !column.hidden)

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
              只读驾驶舱：一个公司目标，三条核心战线，所有未归属任务都会亮红灯。复杂处理动作统一回到 Planning / Publishing / Releases。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <ActionButton href="/planning" tone="primary">Open Planning</ActionButton>
            <ActionButton href="/publishing">Open Publishing</ActionButton>
            <ActionButton href="/releases">Open Releases</ActionButton>
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
        <MetricTile label="Needs Human" value={state.workflows?.needs_human ?? state.workflows?.pending_gate_count ?? state.stats?.human_gate_pending ?? '-'} detail="Human Gate 或人工业务确认" tone={numberValue(state.workflows?.needs_human ?? state.workflows?.pending_gate_count) ? 'warning' : 'muted'} />
        <MetricTile label="Failed" value={state.workflows?.failed_count ?? state.workflows?.failed ?? state.stats?.workflow_failed ?? '-'} detail="失败、超预算或证据不足" tone={numberValue(state.workflows?.failed_count ?? state.workflows?.failed) ? 'danger' : 'muted'} />
        <MetricTile label="Unassigned" value={board?.unassigned.count ?? '-'} detail="缺失 goal_key 的 active 数据" tone={board?.unassigned.count ? 'danger' : 'muted'} />
      </div>

      <CockpitPanel eyebrow="Task Board" title="Delivery flow by Requirement status" description="Command Center 只展示列计数；具体卡片和详情统一进入 Planning Task Board。">
        <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-7">
          {taskColumns.map((column) => (
            <a
              key={column.key}
              href={`/planning?tab=board&column=${column.key}`}
              className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4 transition hover:border-cyan-300/40 hover:bg-cyan-300/[0.04]"
            >
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{column.title}</div>
              <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{column.count}</div>
            </a>
          ))}
        </div>
      </CockpitPanel>

      {loading ? (
        <CockpitPanel eyebrow="Mission Board" title="Loading mission board" description="正在汇总 active goal、三条 mission lane 和未归属事项。">
          <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] px-5 py-8 text-sm text-[color:var(--ops-text-muted)]">
            Mission Board loading...
          </div>
        </CockpitPanel>
      ) : (
        <MissionBoardPanel board={board} compact />
      )}

      <CockpitPanel eyebrow="Human Oracle" title="Blockers stay actionable" description="Command Center 不处理业务动作，只把你带到正确处理面。">
        <AgentReasoningCard
          title={blockers ? `${blockers} blocker(s) require attention` : 'No operator blocker'}
          tone={blockers ? 'warning' : 'info'}
          summary={blockers ? '存在 pending Human Gate、人工业务确认或 failed workflow。优先处理证据、风险或业务验收。' : '没有等待人工处理的 blocker。系统当前主线没有需要你立即介入的红灯。'}
          metadata={<ActionButton href="/gates" tone={blockers ? 'primary' : 'default'}>Open Needs Human</ActionButton>}
        />
      </CockpitPanel>
    </div>
  )
}
