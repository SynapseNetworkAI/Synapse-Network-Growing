import type { SocialContentAsset, SocialDistributionBoard as Board, SocialDistributionBoardCard as BoardCard } from '../apiSocialDistribution'
import { StateBadge, statusTone } from './SocialDistributionWidgets'

export function DistributionBoard({
  board,
  formatDateTime,
  onOpen,
}: {
  board: Board
  formatDateTime: (value: string | null | undefined) => string
  onOpen: (card: BoardCard) => void
}) {
  return (
    <section className="overflow-x-auto pb-3">
      <div className="grid min-w-[1120px] grid-cols-5 gap-3">
        {board.columns.map((column) => (
          <div key={column.key} className="min-h-[520px] rounded-[24px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)]" data-testid={`distribution-board-column-${column.key}`}>
            <div className="sticky top-0 z-10 rounded-t-[24px] border-b border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-4 py-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-semibold text-[color:var(--ops-text-title)]">{column.title}</h3>
                <span className="rounded-full bg-[color:var(--ops-panel-strong)] px-2 py-1 text-xs text-[color:var(--ops-text-muted)]">{column.count}</span>
              </div>
              <p className="mt-1 line-clamp-2 text-xs text-[color:var(--ops-text-caption)]">{column.description}</p>
            </div>
            <div className="space-y-3 p-3">
              {column.cards.length ? column.cards.map((card) => (
                <DistributionBoardCard key={card.id} card={card} formatDateTime={formatDateTime} onOpen={() => onOpen(card)} />
              )) : (
                <div className="rounded-2xl border border-dashed border-[color:var(--ops-stroke-soft)] p-4 text-xs text-[color:var(--ops-text-caption)]">No cards in this column.</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function DistributionBoardCard({ card, formatDateTime, onOpen }: { card: BoardCard; formatDateTime: (value: string | null | undefined) => string; onOpen: () => void }) {
  const taskCounts = Object.entries(card.status_counts ?? {}).map(([status, count]) => `${count} ${status}`).join(' / ')
  const failed = card.failed_count > 0
  const metrics = cardMetrics(card)
  return (
    <button
      type="button"
      className="w-full rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4 text-left transition hover:border-cyan-300/40 hover:bg-cyan-300/[0.035] focus:outline-none focus:ring-2 focus:ring-cyan-300/40"
      onClick={onOpen}
      data-testid={`distribution-board-card-${card.asset.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">ASSET-{card.asset.id} · {card.task_kind_label} · {card.asset.source_type}</div>
          <div className="mt-2 line-clamp-3 text-sm font-semibold text-[color:var(--ops-text-title)]">{card.asset.title}</div>
        </div>
        <StateBadge tone={failed ? 'blocked' : statusTone(card.asset.status)}>{card.asset.status}</StateBadge>
      </div>
      <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-[color:var(--ops-text-muted)]">{card.next_action}</p>
      <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
        {metrics.map((metric) => (
          <div key={metric.label} className="rounded-xl bg-[color:var(--ops-panel-strong)] px-2 py-2"><b>{metric.value}</b><span className="block text-[10px] text-[color:var(--ops-text-caption)]">{metric.label}</span></div>
        ))}
      </div>
      <div className="mt-3 font-mono text-[10px] leading-5 text-[color:var(--ops-text-caption)]">{taskCounts || 'no platform tasks'} · updated {formatDateTime(card.updated_at)}</div>
    </button>
  )
}

function cardMetrics(card: BoardCard) {
  if (card.task_kind_code !== 'x_reply_block') {
    return [
      { label: 'platforms', value: card.platform_count },
      { label: 'docs', value: card.document_count },
      { label: 'live', value: card.live_count },
    ]
  }
  const replyBlock = objectValue(card.asset.agent_metadata.reply_block)
  return [
    { label: 'source posts', value: arrayLength(replyBlock.source_candidate_ids) || numberValue(replyBlock.processed_source_count) },
    { label: 'candidates', value: arrayLength(replyBlock.reply_ids) },
    { label: 'live', value: card.live_count },
  ]
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function arrayLength(value: unknown): number {
  return Array.isArray(value) ? value.length : 0
}

function numberValue(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  return 0
}

export function AssetSummary({ asset, taskCount }: { asset: SocialContentAsset; taskCount: number }) {
  const counts = Object.entries(asset.status_counts ?? {}).map(([status, count]) => `${count} ${status}`).join(' / ')
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2"><b className="text-[color:var(--ops-text-title)]">{asset.title}</b><StateBadge tone={statusTone(asset.status)}>{asset.status}</StateBadge></div>
      <div className="mt-2 line-clamp-2 text-sm text-[color:var(--ops-text-muted)]">{asset.summary || asset.body || 'No summary yet.'}</div>
      <div className="mt-3 font-mono text-xs text-[color:var(--ops-text-caption)]">{asset.asset_type} · {asset.source_type} · {taskCount} tasks{counts ? ` · ${counts}` : ''}</div>
    </div>
  )
}
