import type { SocialDistributionBoard } from '../apiSocialDistribution'

export type TaskKindFilter = 'all' | 'content_distribution' | 'x_reply_block'

export function filterBoardByKind(board: SocialDistributionBoard, filter: TaskKindFilter): SocialDistributionBoard {
  if (filter === 'all') return board
  const columns = board.columns.map((column) => {
    const cards = column.cards.filter((card) => card.task_kind_code === filter)
    return { ...column, cards, count: cards.length }
  })
  return {
    ...board,
    columns,
    summary: {
      ...board.summary,
      total_assets: columns.reduce((sum, column) => sum + column.cards.length, 0),
    },
  }
}

export function TaskKindFilterControl({
  value,
  onChange,
}: {
  value: TaskKindFilter
  onChange: (value: TaskKindFilter) => void
}) {
  return (
    <div className="mb-4 flex flex-wrap gap-2">
      {FILTER_OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          className={`rounded-xl border px-3 py-2 text-sm ${value === option.value ? 'border-cyan-300/60 bg-cyan-300/10 text-cyan-100' : 'border-[color:var(--ops-stroke-strong)] text-[color:var(--ops-text-muted)]'}`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

const FILTER_OPTIONS: Array<{ value: TaskKindFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'content_distribution', label: '内容发布' },
  { value: 'x_reply_block', label: 'X 回复' },
]
