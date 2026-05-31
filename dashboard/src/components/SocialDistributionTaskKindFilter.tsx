import type { SocialDistributionBoard } from '../apiSocialDistribution'

export type TaskKindFilter = 'all' | 'content_distribution' | 'multi_platform_campaign' | 'x_article_pack' | 'x_media_post' | 'x_reply_block' | 'legacy_unclassified'

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
  board,
  value,
  onChange,
}: {
  board: SocialDistributionBoard
  value: TaskKindFilter
  onChange: (value: TaskKindFilter) => void
}) {
  const counts = taskKindCounts(board)
  return (
    <div className="mb-4 space-y-2">
      <div className="flex flex-wrap gap-2" aria-label="任务类型过滤">
        {FILTER_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            title={option.description}
            className={`rounded-xl border px-3 py-2 text-sm ${value === option.value ? 'border-cyan-300/60 bg-cyan-300/10 text-cyan-100' : 'border-[color:var(--ops-stroke-strong)] text-[color:var(--ops-text-muted)]'}`}
            onClick={() => onChange(option.value)}
          >
            <span>{option.label}</span>
            <span className="ml-2 rounded-full bg-white/10 px-2 py-0.5 font-mono text-[11px] text-[color:var(--ops-text-caption)]">{counts[option.value] ?? 0}</span>
          </button>
        ))}
      </div>
      <p className="text-xs text-[color:var(--ops-text-caption)]">
        任务类型是互斥过滤；每张卡只属于一个类型。看板列表示生命周期状态，不是分类。
      </p>
    </div>
  )
}

const FILTER_OPTIONS: Array<{ value: TaskKindFilter; label: string; description: string }> = [
  { value: 'all', label: '全部', description: '显示所有任务类型。' },
  { value: 'content_distribution', label: '通用内容发布', description: '旧版或通用内容分发任务，不代表全部发布任务。' },
  { value: 'multi_platform_campaign', label: '多平台', description: '跨平台分发任务。' },
  { value: 'x_article_pack', label: 'X Article', description: 'X Article 手动长文发布包。' },
  { value: 'x_media_post', label: 'X 图文', description: 'X 官方 API 图文帖。' },
  { value: 'x_reply_block', label: 'X 回复', description: 'X 回复候选任务。' },
  { value: 'legacy_unclassified', label: '历史/未分类', description: '无法安全归类的历史任务，需要人工整理。' },
]

function taskKindCounts(board: SocialDistributionBoard): Record<TaskKindFilter, number> {
  const counts = Object.fromEntries(FILTER_OPTIONS.map((option) => [option.value, 0])) as Record<TaskKindFilter, number>
  for (const column of board.columns) {
    for (const card of column.cards) {
      counts.all += 1
      const key = card.task_kind_code as TaskKindFilter
      if (key in counts) counts[key] += 1
    }
  }
  return counts
}
