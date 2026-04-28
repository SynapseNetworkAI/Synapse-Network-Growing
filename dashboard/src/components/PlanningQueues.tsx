import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { MissionBoard, MissionBoardItem } from '../api'
import { MissionLaneItem } from './MissionBoardPanel'

export function MarkdownTabs({
  value,
  onChange,
  minHeightClass = 'min-h-[56vh]',
}: Readonly<{
  value: string
  onChange: (value: string) => void
  minHeightClass?: string
}>) {
  const [tab, setTab] = useState<'write' | 'preview'>('write')
  return (
    <section>
      <div className="flex items-center justify-between gap-3">
        <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Intent & PRD Markdown</div>
        <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-1">
          {(['write', 'preview'] as const).map((key) => (
            <button
              key={key}
              className={['rounded-lg px-3 py-1.5 text-xs font-medium capitalize transition', tab === key ? 'bg-cyan-300/[0.14] text-cyan-100' : 'text-[color:var(--ops-text-muted)]'].join(' ')}
              type="button"
              onClick={() => setTab(key)}
            >
              {key}
            </button>
          ))}
        </div>
      </div>
      {tab === 'write' ? (
        <textarea
          className={['mt-3 w-full rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-950 p-4 font-mono text-sm leading-6 text-slate-100 outline-none', minHeightClass].join(' ')}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Write the full PRD, context, constraints, and acceptance notes in Markdown..."
          spellCheck={false}
        />
      ) : (
        <div className={['mt-3 overflow-auto rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5 text-sm leading-7 text-[color:var(--ops-text-body)]', minHeightClass].join(' ')}>
          {value.trim() ? (
            <ReactMarkdown>{value}</ReactMarkdown>
          ) : (
            <div className="text-[color:var(--ops-text-muted)]">Markdown preview will appear here.</div>
          )}
        </div>
      )}
    </section>
  )
}

export function EngineeringQueue({ board }: Readonly<{ board: MissionBoard | null }>) {
  const items = board?.lanes.software_engineer || []
  return (
    <main className="space-y-4" data-testid="engineering-queue-tab">
      <section className="rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
        <div className="machine-label text-[color:var(--ops-text-caption)]">Software Engineer</div>
        <h2 className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">工程队列</h2>
        <p className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">只展示当前 active goal 下的工程候选、需求、Workflow 和 Release Task。代码类执行优先排队，避免撞车。</p>
      </section>
      {items.length ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => <MissionLaneItem key={item.id} item={item} />)}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-8 text-sm text-[color:var(--ops-text-muted)]">
          当前 active goal 下没有工程队列事项。
        </div>
      )}
    </main>
  )
}

export function UnassignedQueue({ items }: Readonly<{ items: MissionBoardItem[] }>) {
  return (
    <main className="space-y-4" data-testid="unassigned-queue-tab">
      <section className="rounded-[28px] border border-rose-300/25 bg-rose-400/[0.08] p-5">
        <div className="machine-label text-rose-100/70">Unassigned / Orphaned</div>
        <h2 className="mt-2 text-2xl font-semibold text-rose-50">未归属队列</h2>
        <p className="mt-2 text-sm leading-6 text-rose-100/80">这些是 active 但缺失 goal lineage 的数据。它们不能静默躲进 Debug，需要修复 goal_key、归档或取消。</p>
      </section>
      {items.length ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => <MissionLaneItem key={item.id} item={item} />)}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-8 text-sm text-[color:var(--ops-text-muted)]">
          没有未归属 active 数据，lineage clean。
        </div>
      )}
    </main>
  )
}
