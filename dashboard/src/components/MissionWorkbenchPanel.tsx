import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { MissionWorkbench, MissionWorkbenchNode, MissionWorkbenchStage } from '../api'

const stageLabels: Array<[MissionWorkbenchStage, string]> = [
  ['opportunity', 'Opportunity'],
  ['candidate', 'Candidate'],
  ['requirement', 'Requirement'],
  ['workflow', 'Workflow'],
  ['pr', 'PR'],
  ['release', 'Release'],
  ['online_record', 'Online'],
]

function statusBadgeClass(status: string) {
  if (['blocked', 'failed', 'validation_failed'].includes(status)) return 'border-rose-300/30 bg-rose-400/[0.10] text-rose-100'
  if (['waiting', 'pending', 'proposed', 'needs_review', 'awaiting_operator', 'approved'].includes(status)) return 'border-amber-300/30 bg-amber-300/[0.10] text-amber-100'
  if (['running', 'active', 'candidate', 'requested'].includes(status)) return 'border-cyan-300/25 bg-cyan-300/[0.08] text-cyan-100'
  if (['completed', 'succeeded', 'done', 'published'].includes(status)) return 'border-emerald-300/25 bg-emerald-300/[0.08] text-emerald-100'
  return 'border-white/10 bg-white/[0.04] text-[color:var(--ops-text-muted)]'
}

function stageDotClass(status: string) {
  if (status === 'blocked') return 'border-rose-300/40 bg-rose-400/60 shadow-[0_0_0_3px_rgba(251,113,133,0.12)]'
  if (status === 'running') return 'border-cyan-300/40 bg-cyan-300/60 shadow-[0_0_0_3px_rgba(34,211,238,0.12)]'
  if (status === 'waiting' || status === 'active') return 'border-amber-300/40 bg-amber-300/60 shadow-[0_0_0_3px_rgba(252,211,77,0.10)]'
  if (status === 'completed') return 'border-emerald-300/40 bg-emerald-300/70 shadow-[0_0_0_3px_rgba(52,211,153,0.10)]'
  return 'border-white/12 bg-white/[0.06]'
}

function collectDefaultExpanded(root: MissionWorkbenchNode | null) {
  const ids = new Set<string>()
  const walk = (node: MissionWorkbenchNode) => {
    if (node.level <= 2 || ['blocked', 'running', 'awaiting_operator'].includes(node.status)) ids.add(node.id)
    node.children.forEach(walk)
  }
  if (root) walk(root)
  return ids
}

function flattenTree(root: MissionWorkbenchNode | null, expanded: Set<string>) {
  const rows: MissionWorkbenchNode[] = []
  const walk = (node: MissionWorkbenchNode) => {
    rows.push(node)
    if (!expanded.has(node.id)) return
    node.children.forEach(walk)
  }
  if (root) walk(root)
  return rows
}

function StageRail({ node }: Readonly<{ node: MissionWorkbenchNode }>) {
  const stages = node.process_stages?.length
    ? node.process_stages
    : stageLabels.map(([key, label]) => ({ key, label, status: node.stage_statuses[key] || 'missing' }))
  return (
    <div className="flex min-w-[520px] items-center gap-2" aria-label={`stage rail for ${node.title}`}>
      {stages.map(({ key, label, status }, index) => {
        return (
          <div key={key} className="flex flex-1 items-center gap-2">
            <div className="flex min-w-0 flex-col items-center gap-1">
              <span className={['h-3 w-3 rounded-full border transition', stageDotClass(status)].join(' ')} title={`${label}: ${status}`} />
              <span className="truncate text-[9px] uppercase tracking-[0.12em] text-[color:var(--ops-text-caption)]">{label}</span>
            </div>
            {index < stages.length - 1 ? <span className="h-px flex-1 bg-white/10" /> : null}
          </div>
        )
      })}
    </div>
  )
}

function WorkbenchDetailModal({
  node,
  onClose,
}: Readonly<{
  node: MissionWorkbenchNode
  onClose: () => void
}>) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/78 px-4 py-8 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={`Mission item detail ${node.title}`}>
      <section className="max-h-[86vh] w-full max-w-4xl overflow-auto rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] shadow-[0_32px_110px_rgba(0,0,0,0.55)]">
        <header className="flex items-start justify-between gap-4 border-b border-[color:var(--ops-stroke-soft)] px-6 py-5">
          <div>
            <div className="machine-label text-[color:var(--ops-text-caption)]">{node.type}</div>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{node.title}</h2>
          </div>
          <button type="button" className="rounded-xl border border-white/12 px-4 py-2 text-sm text-[color:var(--ops-text-body)]" onClick={onClose}>关闭</button>
        </header>
        <div className="space-y-5 p-6">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
              <div className="machine-label text-[color:var(--ops-text-caption)]">Status</div>
              <div className={['mt-2 inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em]', statusBadgeClass(node.status)].join(' ')}>{node.status}</div>
            </div>
            <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
              <div className="machine-label text-[color:var(--ops-text-caption)]">Object ID</div>
              <div className="mt-2 font-mono text-sm text-[color:var(--ops-text-body)]">{node.id}</div>
            </div>
            <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
              <div className="machine-label text-[color:var(--ops-text-caption)]">Lane / Goal</div>
              <div className="mt-2 text-sm text-[color:var(--ops-text-body)]">{node.lane || '-'} · {node.goal_key || '-'}</div>
            </div>
            <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
              <div className="machine-label text-[color:var(--ops-text-caption)]">Updated</div>
              <div className="mt-2 text-sm text-[color:var(--ops-text-body)]">{node.updated_at || '-'}</div>
            </div>
          </div>
          <div className="overflow-x-auto rounded-2xl border border-white/8 bg-white/[0.03] p-4">
            <StageRail node={node} />
          </div>
          <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
            <div className="machine-label text-[color:var(--ops-text-caption)]">Next Action</div>
            <p className="mt-2 text-sm leading-6 text-[color:var(--ops-text-body)]">{node.next_action || 'Open the linked surface for the next action.'}</p>
            {node.evidence_label ? <p className="mt-3 font-mono text-xs text-[color:var(--ops-text-caption)]">{node.evidence_label}</p> : null}
            {node.external_post_id ? (
              <div className="mt-3 rounded-2xl border border-emerald-300/20 bg-emerald-300/[0.06] p-3 text-sm text-emerald-100">
                <div className="font-semibold">X Post ID: {node.external_post_id}</div>
                <div className="mt-1 text-xs text-emerald-100/75">Published at: {node.published_at || '-'}</div>
                {node.external_url ? (
                  <a className="mt-2 inline-flex font-semibold underline" href={node.external_url} target="_blank" rel="noreferrer">
                    Open on X
                  </a>
                ) : null}
              </div>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {node.deep_link ? <Link className="rounded-xl border border-cyan-300/30 bg-cyan-300/15 px-4 py-2 text-sm font-semibold text-cyan-100" to={node.deep_link}>打开关联页面</Link> : null}
            {node.detail_api ? <span className="rounded-xl border border-white/10 px-4 py-2 font-mono text-xs text-[color:var(--ops-text-muted)]">{node.detail_api}</span> : null}
          </div>
        </div>
      </section>
    </div>
  )
}

export function MissionWorkbenchPanel({ workbench }: Readonly<{ workbench: MissionWorkbench | null }>) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [detailNode, setDetailNode] = useState<MissionWorkbenchNode | null>(null)
  const root = workbench?.root || null
  useEffect(() => {
    setExpanded(collectDefaultExpanded(root))
  }, [root])
  const rows = useMemo(() => flattenTree(root, expanded), [root, expanded])
  const toggle = (id: string) => {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  if (!root) {
    return (
      <section className="rounded-[28px] border border-dashed border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-8 text-sm text-[color:var(--ops-text-muted)]" data-testid="mission-workbench-tab">
        当前没有 active company goal。请先在 Planning 中创建或恢复目标。
      </section>
    )
  }

  return (
    <main className="space-y-4" data-testid="mission-workbench-tab">
      <section className="rounded-[28px] border border-cyan-300/20 bg-[radial-gradient(circle_at_15%_18%,rgba(34,211,238,0.12),transparent_35%),rgba(255,255,255,0.035)] p-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="machine-label text-cyan-200/70">Mission Workbench</div>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">目标 → 战线 → 任务 → 证据</h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
              这是操作态树状视图：用层级表达归属，用流程轨道表达每类任务自己的生命周期。Growth Lead 这里只显示增长摘要；具体草稿、回帖、转发候选在 Publishing 处理。
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="rounded-full border border-white/10 px-3 py-1 text-[color:var(--ops-text-muted)]">{workbench?.summary.active_goal_count || 0} active goals</span>
            <span className="rounded-full border border-white/10 px-3 py-1 text-[color:var(--ops-text-muted)]">{workbench?.summary.work_item_count || rows.length} nodes</span>
            {workbench?.unassigned.count ? <Link className="rounded-full border border-rose-300/30 bg-rose-400/[0.10] px-3 py-1 text-rose-100" to="/planning?tab=unassigned">Unassigned {workbench.unassigned.count}</Link> : null}
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
        <div className="grid grid-cols-[minmax(360px,1.25fr)_120px_minmax(560px,1.5fr)_110px] gap-4 border-b border-[color:var(--ops-stroke-soft)] bg-white/[0.035] px-5 py-3 text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">
          <div>Hierarchy</div>
          <div>Status</div>
          <div>Flow status</div>
          <div className="text-right">Action</div>
        </div>
        <div className="divide-y divide-white/8 overflow-x-auto">
          {rows.map((node) => {
            const hasChildren = node.children.length > 0
            return (
              <div key={node.id} className="grid min-w-[1160px] grid-cols-[minmax(360px,1.25fr)_120px_minmax(560px,1.5fr)_110px] items-center gap-4 px-5 py-3 transition hover:bg-cyan-300/[0.035]" data-testid={`mission-workbench-row-${node.id}`}>
                <div className="flex min-w-0 items-center gap-2" style={{ paddingLeft: `${node.level * 20}px` }}>
                  <button
                    type="button"
                    className="h-7 w-7 rounded-lg border border-white/10 text-xs text-[color:var(--ops-text-muted)] disabled:opacity-30"
                    disabled={!hasChildren}
                    onClick={() => toggle(node.id)}
                    aria-label={expanded.has(node.id) ? `Collapse ${node.title}` : `Expand ${node.title}`}
                  >
                    {hasChildren ? (expanded.has(node.id) ? '−' : '+') : '·'}
                  </button>
                  <div className="min-w-0">
                    <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)]">{node.type.replace(/_/g, ' ')}</div>
                    {node.deep_link ? (
                      <Link className="mt-1 block truncate text-sm font-semibold text-[color:var(--ops-text-title)] hover:text-cyan-100" to={node.deep_link}>{node.title}</Link>
                    ) : (
                      <div className="mt-1 truncate text-sm font-semibold text-[color:var(--ops-text-title)]">{node.title}</div>
                    )}
                    <div className="mt-1 truncate text-xs text-[color:var(--ops-text-muted)]">{node.next_action}</div>
                  </div>
                </div>
                <div>
                  <span className={['rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em]', statusBadgeClass(node.status)].join(' ')}>
                    {node.status}
                  </span>
                </div>
                <StageRail node={node} />
                <div className="text-right">
                  {node.type === 'requirement_candidate' && node.deep_link ? (
                    <Link className="rounded-xl border border-white/12 px-3 py-2 text-xs text-[color:var(--ops-text-body)] hover:bg-white/[0.06]" to={node.deep_link}>详情</Link>
                  ) : (
                    <button type="button" className="rounded-xl border border-white/12 px-3 py-2 text-xs text-[color:var(--ops-text-body)] hover:bg-white/[0.06]" onClick={() => setDetailNode(node)}>详情</button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </section>
      {detailNode ? <WorkbenchDetailModal node={detailNode} onClose={() => setDetailNode(null)} /> : null}
    </main>
  )
}
