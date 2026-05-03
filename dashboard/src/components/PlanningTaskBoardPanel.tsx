import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, DeclarativeWorkflowRunDetail, PlanningTaskBoard, PlanningTaskBoardCard, PlanningTaskBoardColumnKey } from '../api'

const visibleColumns: PlanningTaskBoardColumnKey[] = ['backlog', 'todo', 'in_progress', 'human_review', 'rework', 'delivery', 'done']

function tone(status: string) {
  if (['completed', 'done', 'published', 'online', 'approved'].includes(status)) return 'border-emerald-300/30 bg-emerald-300/[0.08] text-emerald-100'
  if (['failed', 'blocked', 'validation_failed'].includes(status)) return 'border-rose-300/30 bg-rose-400/[0.10] text-rose-100'
  if (['awaiting_operator', 'needs_review'].includes(status)) return 'border-amber-300/30 bg-amber-300/[0.10] text-amber-100'
  if (['running', 'in_progress', 'executing'].includes(status)) return 'border-cyan-300/30 bg-cyan-300/[0.08] text-cyan-100'
  return 'border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-subtle)] text-[color:var(--ops-text-muted)]'
}

function formatLocal(value: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString()
}

function cardLabel(card: PlanningTaskBoardCard) {
  if (card.card_kind === 'intake') return card.intake_type === 'product_opportunity' ? 'Opportunity Intake' : 'Candidate Intake'
  return 'Requirement'
}

function TaskCard({ card, onOpen }: Readonly<{ card: PlanningTaskBoardCard; onOpen: (card: PlanningTaskBoardCard) => void }>) {
  return (
    <button
      type="button"
      onClick={() => onOpen(card)}
      className="w-full rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4 text-left transition hover:border-cyan-300/40 hover:bg-cyan-300/[0.035] focus:outline-none focus:ring-2 focus:ring-cyan-300/40"
      data-testid={`planning-task-card-${card.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{card.task_key} · {cardLabel(card)}</div>
          <div className="mt-2 line-clamp-2 text-sm font-semibold text-[color:var(--ops-text-title)]">{card.title}</div>
        </div>
        <span className={['shrink-0 rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em]', tone(card.status)].join(' ')}>
          {card.status}
        </span>
      </div>
      <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-[color:var(--ops-text-muted)]">{card.next_action}</p>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px] text-[color:var(--ops-text-caption)]">
        {card.goal_key ? <span>{card.goal_key}</span> : null}
        {card.project_key ? <span>{card.project_key}</span> : null}
        {card.delivery_label ? <span>{card.delivery_label}</span> : null}
      </div>
    </button>
  )
}

function WorkflowMiniDetail({ workflow }: Readonly<{ workflow: DeclarativeWorkflowRunDetail | null }>) {
  if (!workflow) return null
  const rootCause = workflow.operator_decision_summary?.root_cause || workflow.resolution || workflow.current_state
  return (
    <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Latest Workflow Run</div>
      <div className="mt-2 grid gap-3 md:grid-cols-3">
        <div><div className="text-[11px] text-[color:var(--ops-text-caption)]">Run</div><div className="font-semibold text-[color:var(--ops-text-title)]">#{workflow.id}</div></div>
        <div><div className="text-[11px] text-[color:var(--ops-text-caption)]">State</div><div className="font-semibold text-[color:var(--ops-text-title)]">{workflow.current_state}</div></div>
        <div><div className="text-[11px] text-[color:var(--ops-text-caption)]">Status</div><div className="font-semibold text-[color:var(--ops-text-title)]">{workflow.status}</div></div>
      </div>
      <p className="mt-3 text-sm text-[color:var(--ops-text-muted)]">{rootCause}</p>
    </section>
  )
}

function TaskDetailModal({ card, onClose }: Readonly<{ card: PlanningTaskBoardCard | null; onClose: () => void }>) {
  const [workflow, setWorkflow] = useState<DeclarativeWorkflowRunDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    setWorkflow(null)
    setError(null)
    if (!card?.latest_workflow_run_id) return undefined
    api.getWorkflowRun(card.latest_workflow_run_id)
      .then((detail) => { if (active) setWorkflow(detail) })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : 'Failed to load workflow run') })
    return () => { active = false }
  }, [card])
  if (!card) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 py-8" role="dialog" aria-modal="true" aria-label="Planning task detail">
      <div className="max-h-[90vh] w-full max-w-4xl overflow-auto rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-bg)] shadow-2xl">
        <header className="flex items-start justify-between gap-4 border-b border-[color:var(--ops-stroke-soft)] p-6">
          <div>
            <div className="font-mono text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">{cardLabel(card)} · {card.task_key}</div>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{card.title}</h2>
            <p className="mt-2 text-sm text-[color:var(--ops-text-muted)]">{card.next_action}</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm text-[color:var(--ops-text-body)] hover:bg-[color:var(--ops-panel-strong)]">关闭</button>
        </header>
        <main className="space-y-4 p-6">
          <div className="grid gap-3 md:grid-cols-4">
            {[
              ['Status', card.status],
              ['Column', card.column_key],
              ['Goal', card.goal_key || '-'],
              ['Updated', formatLocal(card.updated_at)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div>
                <div className="mt-2 text-sm font-semibold text-[color:var(--ops-text-title)]">{value}</div>
              </div>
            ))}
          </div>
          {card.description ? (
            <section className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Summary</div>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-[color:var(--ops-text-body)]">{card.description}</p>
            </section>
          ) : null}
          {error ? <div className="rounded-2xl border border-rose-300/30 bg-rose-400/[0.10] p-4 text-sm text-rose-100">{error}</div> : null}
          <WorkflowMiniDetail workflow={workflow} />
          <div className="flex flex-wrap gap-3">
            {card.deep_link ? <Link to={card.deep_link} className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white">打开关联页面</Link> : null}
            {card.latest_workflow_run_id ? <Link to={`/workflows/${card.latest_workflow_run_id}`} className="rounded-xl border border-cyan-300/30 px-4 py-2 text-sm font-semibold text-cyan-100">打开 Workflow</Link> : null}
          </div>
        </main>
      </div>
    </div>
  )
}

export function PlanningTaskBoardPanel({ board, focusedColumn }: Readonly<{ board: PlanningTaskBoard | null; focusedColumn?: string | null }>) {
  const [selected, setSelected] = useState<PlanningTaskBoardCard | null>(null)
  const columns = visibleColumns.map((key) => board?.columns.find((column) => column.key === key)).filter(Boolean)
  const hidden = board?.columns.find((column) => column.key === 'canceled')
  if (!board) {
    return <section className="rounded-[28px] border border-dashed border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-8 text-sm text-[color:var(--ops-text-muted)]">Task Board is loading.</section>
  }
  return (
    <main className="space-y-4" data-testid="planning-task-board-tab">
      <section className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="font-mono text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Requirement-first Task Board</div>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">任务看板</h2>
            <p className="mt-2 max-w-3xl text-sm text-[color:var(--ops-text-muted)]">Requirement 是交付任务主卡；WorkflowRun、PR 和 Release 只在详情里作为运行日志和证据展示。看板不可拖拽，状态由后端真实流程推进。</p>
          </div>
          <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] px-4 py-3 text-sm text-[color:var(--ops-text-muted)]">
            {board.summary.visible_total} visible · Done {board.summary.include_done_days}d
          </div>
        </div>
      </section>
      <section className="overflow-x-auto pb-3">
        <div className="grid min-w-[1480px] grid-cols-7 gap-3">
          {columns.map((column) => (
            <div key={column!.key} className={['min-h-[520px] rounded-[24px] border bg-[color:var(--ops-panel-subtle)]', focusedColumn === column!.key ? 'border-cyan-300/60' : 'border-[color:var(--ops-stroke-soft)]'].join(' ')} data-testid={`planning-task-board-column-${column!.key}`}>
              <div className="sticky top-0 z-10 rounded-t-[24px] border-b border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-4 py-3">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="font-semibold text-[color:var(--ops-text-title)]">{column!.title}</h3>
                  <span className="rounded-full bg-[color:var(--ops-panel-strong)] px-2 py-1 text-xs text-[color:var(--ops-text-muted)]">{column!.count}</span>
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-[color:var(--ops-text-caption)]">{column!.description}</p>
              </div>
              <div className="space-y-3 p-3">
                {column!.cards.length ? column!.cards.map((card) => <TaskCard key={card.id} card={card} onOpen={setSelected} />) : (
                  <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] p-4 text-xs text-[color:var(--ops-text-caption)]">No cards in this column.</div>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>
      {hidden && hidden.count > 0 ? (
        <details className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-4">
          <summary className="cursor-pointer text-sm font-semibold text-[color:var(--ops-text-title)]">Hidden column: Canceled · {hidden.count}</summary>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            {hidden.cards.map((card) => <TaskCard key={card.id} card={card} onOpen={setSelected} />)}
          </div>
        </details>
      ) : null}
      <TaskDetailModal card={selected} onClose={() => setSelected(null)} />
    </main>
  )
}
