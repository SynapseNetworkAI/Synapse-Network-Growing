import { Link } from 'react-router-dom'
import { MissionBoard, MissionBoardItem } from '../api'
import { ActionButton, EmptyCockpitState } from './controlPlane'

const laneMeta = {
  product_planner: {
    title: 'Product Planner',
    description: '发现产品缺口，提出 Goal / Product Opportunity。',
    action: 'Open Planning',
    href: '/planning?tab=opportunities',
  },
  growth_lead: {
    title: 'Growth Lead',
    description: '把目标转成内容、趋势、回帖和转发候选。',
    action: 'Open Publishing',
    href: '/publishing',
  },
  software_engineer: {
    title: 'Software Engineer',
    description: '把确认要做的能力变成 Requirement / Workflow / Release。',
    action: 'Open Engineering Queue',
    href: '/planning?tab=engineering',
  },
}

function badgeClass(status: string) {
  if (['failed', 'blocked'].includes(status)) return 'border-rose-300/30 bg-rose-400/[0.10] text-rose-100'
  if (['awaiting_operator', 'needs_review', 'pending', 'proposed'].includes(status)) return 'border-amber-300/30 bg-amber-300/[0.10] text-amber-100'
  if (['running', 'approved', 'candidate', 'requested'].includes(status)) return 'border-cyan-300/25 bg-cyan-300/[0.08] text-cyan-100'
  return 'border-white/10 bg-white/[0.04] text-[color:var(--ops-text-muted)]'
}

function itemTypeLabel(type: string) {
  return type.replace(/_/g, ' ')
}

function proofBadgeClass(status: string) {
  if (status === 'blocked') return 'border-rose-300/30 bg-rose-400/[0.10] text-rose-100'
  if (status === 'missing' || status === 'incomplete') return 'border-amber-300/30 bg-amber-300/[0.10] text-amber-100'
  return 'border-emerald-300/25 bg-emerald-300/[0.08] text-emerald-100'
}

export function MissionLaneItem({ item }: Readonly<{ item: MissionBoardItem }>) {
  const content = (
    <article className="rounded-2xl border border-white/8 bg-white/[0.035] px-4 py-4 transition hover:border-cyan-300/25 hover:bg-cyan-300/[0.05]">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)]">{itemTypeLabel(item.type)}</span>
        <span className={['rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em]', badgeClass(item.status)].join(' ')}>
          {item.status}
        </span>
      </div>
      <h4 className="mt-3 line-clamp-2 text-sm font-semibold text-[color:var(--ops-text-title)]">{item.title}</h4>
      <p className="mt-2 line-clamp-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">{item.next_action}</p>
      {item.evidence_label ? <div className="mt-3 truncate font-mono text-[11px] text-[color:var(--ops-text-caption)]">{item.evidence_label}</div> : null}
    </article>
  )
  if (item.deep_link) return <Link to={item.deep_link}>{content}</Link>
  return content
}

export function MissionBoardPanel({ board, compact = false }: Readonly<{ board: MissionBoard | null; compact?: boolean }>) {
  const goal = board?.active_goal
  return (
    <section className="space-y-5" data-testid="mission-board">
      <div className="rounded-[28px] border border-cyan-300/20 bg-[radial-gradient(circle_at_15%_20%,rgba(34,211,238,0.12),transparent_32%),rgba(255,255,255,0.035)] p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="machine-label text-cyan-200/70">Active Goal</div>
            {goal ? (
              <>
                <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-[color:var(--ops-text-title)]">{goal.title || goal.goal_key}</h2>
                <p className="mt-3 max-w-4xl text-sm leading-6 text-[color:var(--ops-text-muted)]">{goal.intent_excerpt || goal.success_metric || 'No active goal summary yet.'}</p>
                <div className="mt-4 flex flex-wrap gap-2 text-xs">
                  <span className="rounded-full border border-white/10 px-3 py-1 text-[color:var(--ops-text-muted)]">{goal.goal_key}</span>
                  <span className="rounded-full border border-white/10 px-3 py-1 text-[color:var(--ops-text-muted)]">{goal.domain}</span>
                  <span className="rounded-full border border-white/10 px-3 py-1 text-[color:var(--ops-text-muted)]">risk {goal.risk_level}</span>
                </div>
              </>
            ) : (
              <EmptyCockpitState title="No active goal" description="当前没有 active Goal。请在 Planning 中创建或恢复一个目标，让三条战线重新挂到同一条主线。" />
            )}
          </div>
          {board?.unassigned.count ? (
            <ActionButton href="/planning?tab=unassigned" tone="danger">Unassigned {board.unassigned.count}</ActionButton>
          ) : (
            <span className="rounded-full border border-emerald-300/25 bg-emerald-300/[0.08] px-3 py-2 text-xs font-semibold text-emerald-100">Lineage clean</span>
          )}
        </div>
      </div>

      {board?.traction_proof?.items?.length ? (
        <section className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5" data-testid="mission-traction-proof">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="machine-label text-[color:var(--ops-text-caption)]">Public Preview Traction Proof</div>
              <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">Evidence, not vibes</h3>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
                只读证明面板：缺失证据会显示为 missing / blocked，不会把目标自动染绿。
              </p>
            </div>
            <span className={['rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em]', proofBadgeClass(board.traction_proof.status)].join(' ')}>
              {board.traction_proof.status}
            </span>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {board.traction_proof.items.map((item) => (
              <Link key={item.key} to={item.deep_link || '/planning'} className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-4 transition hover:border-cyan-300/25">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{item.label}</div>
                  <span className={['rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em]', proofBadgeClass(item.status)].join(' ')}>
                    {item.status}
                  </span>
                </div>
                <div className="mt-2 truncate font-mono text-[11px] text-[color:var(--ops-text-caption)]">{item.evidence_label}</div>
                <p className="mt-2 line-clamp-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">{item.next_action}</p>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        {(Object.keys(laneMeta) as Array<keyof typeof laneMeta>).map((laneKey) => {
          const meta = laneMeta[laneKey]
          const items = board?.lanes[laneKey] || []
          const visibleItems = compact ? items.slice(0, 3) : items
          return (
            <section key={laneKey} className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5" data-testid={`mission-lane-${laneKey}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="machine-label text-[color:var(--ops-text-caption)]">{laneKey}</div>
                  <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">{meta.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{meta.description}</p>
                </div>
                <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-[color:var(--ops-text-muted)]">{items.length}</span>
              </div>
              <div className="mt-4 grid gap-3">
                {visibleItems.length ? visibleItems.map((item) => <MissionLaneItem key={item.id} item={item} />) : (
                  <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] px-4 py-6 text-sm text-[color:var(--ops-text-muted)]">
                    这条战线暂无待处理事项。
                  </div>
                )}
              </div>
              <div className="mt-4">
                <ActionButton href={meta.href}>{meta.action}</ActionButton>
              </div>
            </section>
          )
        })}
      </div>

      {board?.next_actions?.length ? (
        <section className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5" data-testid="mission-next-actions">
          <div className="machine-label text-[color:var(--ops-text-caption)]">Next Actions</div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {board.next_actions.map((action) => (
              <Link key={`${action.lane}:${action.title}`} to={action.deep_link || '/planning'} className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-4 transition hover:border-cyan-300/25">
                <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)]">{action.lane}</div>
                <div className="mt-2 text-sm font-semibold text-[color:var(--ops-text-title)]">{action.title}</div>
                <p className="mt-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">{action.next_action}</p>
              </Link>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  )
}
