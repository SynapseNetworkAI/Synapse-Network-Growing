import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { api, type SocialTrendItem } from '../api'
import { EmptyPane, OverlayModal, SectionFrame, StateBadge, useToast } from '../components/workbench'

const PAGE_SIZE = 20

type TrendFilters = {
  q: string
  dateFrom: string
  dateTo: string
  sourceKind: 'all' | 'x_post' | 'local_seed' | 'other'
  authorHandle: string
}

function formatDateInput(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function defaultFilters(): TrendFilters {
  const today = new Date()
  const weekStart = new Date()
  weekStart.setDate(today.getDate() - 6)
  return {
    q: '',
    dateFrom: formatDateInput(weekStart),
    dateTo: formatDateInput(today),
    sourceKind: 'all',
    authorHandle: '',
  }
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function sourceKindOf(trend: SocialTrendItem) {
  if (trend.source_kind) return trend.source_kind
  if (trend.source_platform === 'x' && trend.source_url) return 'x_post'
  if (!trend.source_url) return 'local_seed'
  return 'other'
}

function sourceKindLabel(kind: string) {
  const labels: Record<string, string> = {
    x_post: 'X 原帖',
    local_seed: '本地趋势种子',
    other: '其它来源',
    all: '全部来源',
  }
  return labels[kind] ?? kind
}

function sourceKindTone(kind: string): 'default' | 'ready' | 'running' | 'blocked' | 'validating' | 'delivered' | 'muted' {
  if (kind === 'x_post') return 'ready'
  if (kind === 'local_seed') return 'muted'
  return 'validating'
}

export default function PublishingTrendResultsPage() {
  const toast = useToast()
  const [filters, setFilters] = useState<TrendFilters>(() => defaultFilters())
  const [appliedFilters, setAppliedFilters] = useState<TrendFilters>(() => defaultFilters())
  const [items, setItems] = useState<SocialTrendItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState<SocialTrendItem | null>(null)
  const [detailLoadingId, setDetailLoadingId] = useState<number | null>(null)

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const page = Math.floor(offset / PAGE_SIZE) + 1
  const authorOptions = useMemo(
    () => Array.from(new Set(items.map((item) => item.author_handle).filter(Boolean) as string[])).sort(),
    [items],
  )

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await api.querySocialTrends({
        q: appliedFilters.q.trim() || undefined,
        date_from: appliedFilters.dateFrom || undefined,
        date_to: appliedFilters.dateTo || undefined,
        source_kind: appliedFilters.sourceKind,
        author_handle: appliedFilters.authorHandle.trim() || undefined,
        limit: PAGE_SIZE,
        offset,
      })
      setItems(result.items)
      setTotal(result.total)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '趋势结果加载失败')
    } finally {
      setLoading(false)
    }
  }, [appliedFilters, offset, toast])

  useEffect(() => {
    void load()
  }, [load])

  function submitSearch(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    setOffset(0)
    setAppliedFilters(filters)
  }

  async function openDetail(trend: SocialTrendItem) {
    setDetailLoadingId(trend.id)
    try {
      setDetail(await api.getSocialTrend(trend.id))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '趋势详情加载失败')
    } finally {
      setDetailLoadingId(null)
    }
  }

  return (
    <div className="space-y-5">
      <SectionFrame
        eyebrow="X Trend Radar"
        title="X 趋势雷达结果"
        description="检索 x_social_trend_radar_sweep 保留的趋势素材。这里不触发新的 X 抓取，也不会自动转发、回复或发布。"
        actions={
          <a
            className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm font-semibold text-[color:var(--ops-text-body)] transition hover:border-cyan-300/35 hover:text-cyan-100"
            href="/publishing"
          >
            返回内容发布
          </a>
        }
      >
        <form className="grid gap-3 lg:grid-cols-[1fr_1fr_1.1fr_1fr_auto]" onSubmit={submitSearch}>
          <label className="space-y-2 text-xs text-[color:var(--ops-text-caption)]">
            <span>开始日期</span>
            <input
              aria-label="开始日期"
              type="date"
              className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3 text-sm text-[color:var(--ops-text-body)] outline-none focus:border-cyan-300/45"
              value={filters.dateFrom}
              onChange={(event) => setFilters((current) => ({ ...current, dateFrom: event.target.value }))}
            />
          </label>
          <label className="space-y-2 text-xs text-[color:var(--ops-text-caption)]">
            <span>结束日期</span>
            <input
              aria-label="结束日期"
              type="date"
              className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3 text-sm text-[color:var(--ops-text-body)] outline-none focus:border-cyan-300/45"
              value={filters.dateTo}
              onChange={(event) => setFilters((current) => ({ ...current, dateTo: event.target.value }))}
            />
          </label>
          <label className="space-y-2 text-xs text-[color:var(--ops-text-caption)]">
            <span>关键字</span>
            <input
              aria-label="关键字搜索"
              className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3 text-sm text-[color:var(--ops-text-body)] outline-none placeholder:text-[color:var(--ops-text-caption)] focus:border-cyan-300/45"
              placeholder="搜索 topic / summary / author / source URL"
              value={filters.q}
              onChange={(event) => setFilters((current) => ({ ...current, q: event.target.value }))}
            />
          </label>
          <label className="space-y-2 text-xs text-[color:var(--ops-text-caption)]">
            <span>作者</span>
            <input
              aria-label="作者筛选"
              className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3 text-sm text-[color:var(--ops-text-body)] outline-none placeholder:text-[color:var(--ops-text-caption)] focus:border-cyan-300/45"
              list="trend-author-options"
              placeholder="@OpenAI"
              value={filters.authorHandle}
              onChange={(event) => setFilters((current) => ({ ...current, authorHandle: event.target.value }))}
            />
            <datalist id="trend-author-options">
              {authorOptions.map((handle) => (
                <option key={handle} value={`@${handle}`} />
              ))}
            </datalist>
          </label>
          <div className="flex items-end gap-2">
            <label className="min-w-[160px] flex-1 space-y-2 text-xs text-[color:var(--ops-text-caption)]">
              <span>来源类型</span>
              <select
                aria-label="来源类型"
                className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3 text-sm text-[color:var(--ops-text-body)] outline-none focus:border-cyan-300/45"
                value={filters.sourceKind}
                onChange={(event) => setFilters((current) => ({ ...current, sourceKind: event.target.value as TrendFilters['sourceKind'] }))}
              >
                <option value="all">全部</option>
                <option value="x_post">X 原帖</option>
                <option value="local_seed">本地趋势种子</option>
                <option value="other">其它来源</option>
              </select>
            </label>
            <button
              type="submit"
              className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-3 text-sm font-semibold text-white transition hover:brightness-110 disabled:opacity-50"
              disabled={loading}
            >
              {loading ? '检索中...' : '搜索'}
            </button>
          </div>
        </form>
      </SectionFrame>

      <SectionFrame
        eyebrow="Trend Items"
        title="趋势列表"
        description="真实 X 原帖必须带 source URL；本地种子只作为内容灵感，不能直接进入引用/转发发布。"
      >
        <div className="overflow-hidden rounded-[24px] border border-[color:var(--ops-stroke-soft)]">
          {items.length === 0 ? <EmptyPane>{loading ? '正在加载趋势结果...' : '没有符合条件的趋势结果。'}</EmptyPane> : null}
          {items.length > 0 ? (
            <>
              <table className="w-full min-w-[1040px] border-collapse text-left text-sm">
                <thead className="bg-[color:var(--ops-panel-subtle)] text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                  <tr>
                    <th className="px-5 py-4 font-medium">ID</th>
                    <th className="px-5 py-4 font-medium">主题</th>
                    <th className="px-5 py-4 font-medium">作者</th>
                    <th className="px-5 py-4 font-medium">来源类型</th>
                    <th className="px-5 py-4 font-medium">分数</th>
                    <th className="px-5 py-4 font-medium">状态</th>
                    <th className="px-5 py-4 font-medium">采集时间</th>
                    <th className="px-5 py-4 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[color:var(--ops-stroke-soft)]">
                  {items.map((trend) => {
                    const kind = sourceKindOf(trend)
                    return (
                      <tr key={trend.id} className="bg-[color:var(--ops-workspace-bg)] align-top">
                        <td className="whitespace-nowrap px-5 py-4 font-mono text-xs text-[color:var(--ops-text-caption)]">#{trend.id}</td>
                        <td className="max-w-[360px] px-5 py-4">
                          <div className="font-semibold text-[color:var(--ops-text-title)]">{trend.topic}</div>
                          <div className="mt-2 line-clamp-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">{trend.summary}</div>
                        </td>
                        <td className="px-5 py-4 font-semibold text-[color:var(--ops-text-body)]">@{trend.author_handle ?? 'unknown'}</td>
                        <td className="px-5 py-4">
                          <StateBadge tone={sourceKindTone(kind)}>{sourceKindLabel(kind)}</StateBadge>
                        </td>
                        <td className="px-5 py-4">
                          <StateBadge tone="validating">score {Math.round(trend.relevance_score * 100)}</StateBadge>
                        </td>
                        <td className="px-5 py-4 text-[color:var(--ops-text-muted)]">{trend.status}</td>
                        <td className="px-5 py-4 text-xs text-[color:var(--ops-text-muted)]">{formatDateTime(trend.collected_at)}</td>
                        <td className="px-5 py-4">
                          <div className="flex flex-wrap justify-end gap-2">
                            {trend.source_url ? (
                              <a className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" href={trend.source_url} target="_blank" rel="noreferrer">打开来源</a>
                            ) : null}
                            <button
                              type="button"
                              className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-40"
                              disabled={detailLoadingId === trend.id}
                              onClick={() => void openDetail(trend)}
                            >
                              {detailLoadingId === trend.id ? '加载中...' : '详情'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4 text-sm text-[color:var(--ops-text-muted)]">
                <span>第 {page} / {totalPages} 页 · 共 {total} 条趋势</span>
                <div className="flex gap-2">
                  <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={offset <= 0 || loading} onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}>上一页</button>
                  <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={offset + PAGE_SIZE >= total || loading} onClick={() => setOffset((current) => current + PAGE_SIZE)}>下一页</button>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </SectionFrame>

      <OverlayModal
        open={Boolean(detail)}
        eyebrow="Trend Detail"
        title={detail ? `趋势详情 #${detail.id}` : '趋势详情'}
        description="完整趋势素材、来源边界和采集信息。详情只读，不会触发 X 互动。"
        onClose={() => setDetail(null)}
        actions={
          detail?.source_url ? (
            <a className="rounded-2xl border border-cyan-300/35 px-4 py-2 text-sm font-semibold text-cyan-100" href={detail.source_url} target="_blank" rel="noreferrer">打开 X 原帖</a>
          ) : null
        }
      >
        {detail ? (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Author</div>
                <div className="mt-2 font-semibold text-[color:var(--ops-text-title)]">@{detail.author_handle ?? 'unknown'}</div>
              </div>
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Source</div>
                <div className="mt-2"><StateBadge tone={sourceKindTone(sourceKindOf(detail))}>{sourceKindLabel(sourceKindOf(detail))}</StateBadge></div>
              </div>
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Score</div>
                <div className="mt-2 font-semibold text-[color:var(--ops-text-title)]">{Math.round(detail.relevance_score * 100)}</div>
              </div>
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Status</div>
                <div className="mt-2 font-semibold text-[color:var(--ops-text-title)]">{detail.status}</div>
              </div>
            </div>

            <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4">
              <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Topic</div>
              <div className="mt-2 text-lg font-semibold text-[color:var(--ops-text-title)]">{detail.topic}</div>
              <div className="mt-4 whitespace-pre-wrap text-sm leading-7 text-[color:var(--ops-text-body)]">{detail.summary}</div>
            </div>

            {detail.source_url ? (
              <div className="rounded-3xl border border-cyan-300/20 bg-cyan-300/[0.07] p-4">
                <div className="text-[10px] uppercase tracking-[0.18em] text-cyan-100/70">Source URL</div>
                <a className="mt-2 block break-all text-sm font-semibold text-cyan-100" href={detail.source_url} target="_blank" rel="noreferrer">{detail.source_url}</a>
              </div>
            ) : (
              <div className="rounded-3xl border border-amber-300/25 bg-amber-300/[0.08] p-4 text-sm leading-6 text-amber-100">
                仅作内容灵感，不能引用转发。缺少 X 原帖 source_url 的趋势不会进入可发布的转发 / 引用动作。
              </div>
            )}

            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Collected At</div>
                <div className="mt-2 text-sm text-[color:var(--ops-text-body)]">{formatDateTime(detail.collected_at)}</div>
              </div>
              <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
                <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Updated At</div>
                <div className="mt-2 text-sm text-[color:var(--ops-text-body)]">{formatDateTime(detail.updated_at)}</div>
              </div>
            </div>
          </div>
        ) : null}
      </OverlayModal>
    </div>
  )
}
