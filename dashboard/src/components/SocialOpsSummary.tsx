import type {
  SocialCampaignGoal,
  SocialPostMetricDailyResult,
  SocialPostMetricDetail,
  SocialPostMetricQueryResult,
} from '../api'
import type { SocialOpsOverview, SocialPostMetricSummary } from '../types/socialOps'
import { EmptyPane, OverlayModal, StateBadge } from './workbench'

export function SocialOpsSummaryCards({
  overview,
  dailyActive,
  dailyTarget,
  campaignGoal,
}: {
  overview: SocialOpsOverview | null
  dailyActive: number
  dailyTarget: number
  campaignGoal: SocialCampaignGoal | undefined
}) {
  const dailyPercent = Math.min(100, Math.round((dailyActive / Math.max(1, dailyTarget)) * 100))
  return (
    <>
      <div className="grid gap-3 md:grid-cols-4">
        <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4">
          <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Active Goals</div>
          <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{overview?.active_goal_count ?? '-'}</div>
        </div>
        <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4">
          <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Daily Draft Stock</div>
          <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{dailyActive}/{dailyTarget}</div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
            <div className="h-full rounded-full bg-cyan-300" style={{ width: `${dailyPercent}%` }} />
          </div>
          <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">今日待发布草稿库存</div>
        </div>
        <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4">
          <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Signals</div>
          <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{(overview?.trend_count ?? 0) + (overview?.reply_needs_review_count ?? 0) + (overview?.repost_candidate_count ?? 0)}</div>
        </div>
        <div className="rounded-3xl border border-amber-300/25 bg-amber-300/10 p-4">
          <div className="text-[10px] uppercase tracking-[0.18em] text-amber-100/80">Human Gate</div>
          <div className="mt-2 text-sm leading-6 text-amber-100">发布、回复、引用转发、删除均需人类确认。</div>
        </div>
      </div>
      {campaignGoal ? (
        <div className="rounded-3xl border border-cyan-300/20 bg-cyan-300/[0.08] p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-cyan-100/70">Current Campaign Goal</div>
              <div className="mt-2 text-lg font-semibold text-[color:var(--ops-text-title)]">{campaignGoal.title}</div>
              <div className="mt-1 max-w-4xl text-sm leading-6 text-[color:var(--ops-text-muted)]">{campaignGoal.objective}</div>
            </div>
            <StateBadge tone="ready">{campaignGoal.cadence}</StateBadge>
          </div>
        </div>
      ) : null}
    </>
  )
}

export function DailyDraftInventoryBanner({ active, target }: { active: number; target: number }) {
  return (
    <div className="mb-4 rounded-3xl border border-cyan-300/20 bg-cyan-300/[0.08] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-cyan-100/75">Daily Planner Inventory</div>
          <div className="mt-2 text-lg font-semibold text-[color:var(--ops-text-title)]">今日待发布草稿 {active}/{target}</div>
          <p className="mt-1 text-sm leading-6 text-[color:var(--ops-text-muted)]">
            x_social_daily_content_planner 每小时检查一次，只补足 generating / needs_review / approved 草稿库存；已发布、失败、拒绝不计入库存。
          </p>
        </div>
        <StateBadge tone={active >= target ? 'ready' : 'running'}>
          {active >= target ? '库存已满足' : '等待补足'}
        </StateBadge>
      </div>
    </div>
  )
}

export function SocialMetricsPanel({
  daily,
  metricRows,
  selectedMetric,
  summary,
  dateFrom,
  dateTo,
  page,
  formatDateTime,
  onDateFromChange,
  onDateToChange,
  onSearch,
  onPageChange,
  onOpenMetric,
  onCloseMetric,
}: {
  daily: SocialPostMetricDailyResult | null
  metricRows: SocialPostMetricQueryResult | null
  selectedMetric: SocialPostMetricDetail | null
  summary: SocialPostMetricSummary | null
  dateFrom: string
  dateTo: string
  page: number
  formatDateTime: (value: string | null | undefined) => string
  onDateFromChange: (value: string) => void
  onDateToChange: (value: string) => void
  onSearch: () => void
  onPageChange: (page: number) => void
  onOpenMetric: (id: number) => void
  onCloseMetric: () => void
}) {
  const stats = [
    ['Impressions', summary?.total_impressions ?? 0],
    ['Likes', summary?.total_likes ?? 0],
    ['Replies', summary?.total_replies ?? 0],
    ['Reposts', summary?.total_reposts ?? 0],
    ['Link Clicks', summary?.total_link_clicks ?? 0],
  ]
  const rows = metricRows?.items ?? []
  const dailyRows = daily?.items ?? []
  const total = metricRows?.total ?? 0
  const limit = metricRows?.limit ?? 20
  const totalPages = Math.max(1, Math.ceil(total / Math.max(1, limit)))
  return (
    <>
      <div className="mb-4 rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Date From</div>
            <input
              type="date"
              className="mt-2 rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm"
              value={dateFrom}
              onChange={(event) => onDateFromChange(event.target.value)}
            />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Date To</div>
            <input
              type="date"
              className="mt-2 rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm"
              value={dateTo}
              onChange={(event) => onDateToChange(event.target.value)}
            />
          </div>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={onSearch}>
            查询本地指标
          </button>
          <div className="text-xs leading-5 text-[color:var(--ops-text-caption)]">
            这里只读本地 social_post_metrics；不会触发 X read。
          </div>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {stats.map(([label, value]) => (
          <div key={label} className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-4">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div>
            <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{value}</div>
          </div>
        ))}
      </div>
      <div className="mt-4 rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4 text-sm leading-6 text-[color:var(--ops-text-muted)]">
        <div className="font-semibold text-[color:var(--ops-text-title)]">Observer Summary</div>
        <div className="mt-2">
          已观察 {summary?.observed_post_count ?? 0} 条帖子，平均互动 {(summary?.average_engagement ?? 0).toFixed(1)}，
          最近同步 {formatDateTime(summary?.last_observed_at ?? null)}。
        </div>
        {summary?.diagnostic ? <div className="mt-2 text-amber-100">{summary.diagnostic}</div> : null}
      </div>
      {rows.length === 0 && dailyRows.length === 0 ? <EmptyPane>暂无发布效果记录。可以在 /schedules 手动 Run x_social_post_observer_sweep，或等待每小时 observer sweep；权限不足时这里会显示 diagnostic，而不会伪造数据。</EmptyPane> : null}
      {summary?.top_posts?.length ? (
        <div className="mt-4 rounded-[24px] border border-[color:var(--ops-stroke-soft)]">
          <div className="border-b border-[color:var(--ops-stroke-soft)] px-5 py-4 text-sm font-semibold text-[color:var(--ops-text-title)]">Top Posts</div>
          <div className="divide-y divide-[color:var(--ops-stroke-soft)]">
            {summary.top_posts.map((post) => (
              <div key={`${post.external_post_id ?? post.post_id}`} className="grid gap-3 px-5 py-4 text-sm md:grid-cols-[1.5fr_repeat(4,0.6fr)]">
                <div>
                  <div className="font-semibold text-[color:var(--ops-text-title)]">{post.title || `Post ${post.external_post_id ?? post.post_id ?? '-'}`}</div>
                  <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{formatDateTime(post.observed_at)}</div>
                </div>
                <div><span className="text-[color:var(--ops-text-caption)]">Impr.</span><div className="font-semibold">{post.impressions}</div></div>
                <div><span className="text-[color:var(--ops-text-caption)]">Likes</span><div className="font-semibold">{post.likes}</div></div>
                <div><span className="text-[color:var(--ops-text-caption)]">Replies</span><div className="font-semibold">{post.replies}</div></div>
                <div><span className="text-[color:var(--ops-text-caption)]">Clicks</span><div className="font-semibold">{post.link_clicks}</div></div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      <div className="mt-4 overflow-hidden rounded-[24px] border border-[color:var(--ops-stroke-soft)]">
        <div className="border-b border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4 text-sm font-semibold text-[color:var(--ops-text-title)]">按天统计</div>
        <table className="min-w-full border-collapse text-sm">
          <thead className="bg-[color:var(--ops-panel-subtle)] text-left text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
            <tr>
              <th className="px-5 py-3 font-medium">日期</th>
              <th className="px-4 py-3 font-medium">帖子</th>
              <th className="px-4 py-3 font-medium">Impressions</th>
              <th className="px-4 py-3 font-medium">互动</th>
              <th className="px-4 py-3 font-medium">Top Post</th>
              <th className="px-4 py-3 font-medium">最近同步</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[color:var(--ops-stroke-soft)]">
            {dailyRows.map((row) => (
              <tr key={row.local_date}>
                <td className="px-5 py-4 font-semibold text-[color:var(--ops-text-title)]">{row.local_date}</td>
                <td className="px-4 py-4 text-[color:var(--ops-text-muted)]">{row.observed_post_count}</td>
                <td className="px-4 py-4 text-[color:var(--ops-text-muted)]">{row.total_impressions}</td>
                <td className="px-4 py-4 text-[color:var(--ops-text-muted)]">{row.total_likes + row.total_replies + row.total_reposts + row.total_link_clicks}</td>
                <td className="px-4 py-4 text-[color:var(--ops-text-muted)]">{row.top_post?.title || row.top_post?.external_post_id || '-'}</td>
                <td className="px-4 py-4 text-[color:var(--ops-text-muted)]">{formatDateTime(row.last_observed_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 overflow-hidden rounded-[24px] border border-[color:var(--ops-stroke-soft)]">
        <div className="border-b border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4 text-sm font-semibold text-[color:var(--ops-text-title)]">明细列表</div>
        <table className="min-w-full border-collapse text-sm">
          <thead className="bg-[color:var(--ops-panel-subtle)] text-left text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
            <tr>
              <th className="px-5 py-3 font-medium">ID / Post</th>
              <th className="px-4 py-3 font-medium">标题</th>
              <th className="px-4 py-3 font-medium">Impressions</th>
              <th className="px-4 py-3 font-medium">互动</th>
              <th className="px-4 py-3 font-medium">观察时间</th>
              <th className="px-5 py-3 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[color:var(--ops-stroke-soft)]">
            {rows.map((metric) => (
              <tr key={metric.id}>
                <td className="px-5 py-4 text-[color:var(--ops-text-muted)]">#{metric.id}<div className="mt-1 text-xs">{metric.external_post_id ?? metric.post_id ?? '-'}</div></td>
                <td className="px-4 py-4">
                  <div className="font-semibold text-[color:var(--ops-text-title)]">{metric.post_title || `Post ${metric.external_post_id ?? metric.post_id ?? '-'}`}</div>
                  <div className="mt-1 line-clamp-2 max-w-xl text-xs leading-5 text-[color:var(--ops-text-caption)]">{metric.post_body_excerpt || metric.summary || '-'}</div>
                </td>
                <td className="px-4 py-4 text-[color:var(--ops-text-muted)]">{metric.impressions}</td>
                <td className="px-4 py-4 text-[color:var(--ops-text-muted)]">{metric.likes + metric.replies + metric.reposts + metric.link_clicks}</td>
                <td className="px-4 py-4 text-[color:var(--ops-text-muted)]">{formatDateTime(metric.observed_at)}</td>
                <td className="px-5 py-4 text-right">
                  <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2" onClick={() => onOpenMetric(metric.id)}>
                    详情
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4 text-sm text-[color:var(--ops-text-muted)]">
          <span>第 {page} / {totalPages} 页 · 共 {total} 条指标</span>
          <div className="flex gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={page <= 1} onClick={() => onPageChange(Math.max(1, page - 1))}>上一页</button>
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={page >= totalPages} onClick={() => onPageChange(Math.min(totalPages, page + 1))}>下一页</button>
          </div>
        </div>
      </div>
      <OverlayModal open={Boolean(selectedMetric)} title={`发布效果 #${selectedMetric?.id ?? ''}`} eyebrow="Metric Detail" onClose={onCloseMetric}>
        {selectedMetric ? (
          <div className="space-y-4">
            <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
              <div className="font-semibold text-[color:var(--ops-text-title)]">{selectedMetric.post_title || `Post ${selectedMetric.external_post_id ?? selectedMetric.post_id ?? '-'}`}</div>
              <p className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{selectedMetric.post_body_excerpt || selectedMetric.summary || '-'}</p>
              <div className="mt-3 grid gap-3 text-sm md:grid-cols-2">
                <div><span className="text-[color:var(--ops-text-caption)]">External Post</span><div>{selectedMetric.external_post_id ?? '-'}</div></div>
                <div><span className="text-[color:var(--ops-text-caption)]">Observed</span><div>{formatDateTime(selectedMetric.observed_at)}</div></div>
                <div><span className="text-[color:var(--ops-text-caption)]">Published</span><div>{formatDateTime(selectedMetric.published_at)}</div></div>
                <div><span className="text-[color:var(--ops-text-caption)]">Status</span><div>{selectedMetric.post_status ?? '-'}</div></div>
              </div>
              {selectedMetric.x_url ? <a className="mt-4 inline-flex rounded-xl border border-cyan-300/40 px-4 py-2 text-sm text-cyan-100" href={selectedMetric.x_url} target="_blank" rel="noreferrer">打开 X 原帖</a> : null}
            </div>
            <div className="grid gap-3 md:grid-cols-5">
              {[
                ['Impressions', selectedMetric.impressions],
                ['Likes', selectedMetric.likes],
                ['Replies', selectedMetric.replies],
                ['Reposts', selectedMetric.reposts],
                ['Clicks', selectedMetric.link_clicks],
              ].map(([label, value]) => (
                <div key={label} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white/[0.03] p-3">
                  <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">{label}</div>
                  <div className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{value}</div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </OverlayModal>
    </>
  )
}
