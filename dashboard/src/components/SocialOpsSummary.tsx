import type { SocialCampaignGoal, SocialPostMetric } from '../api'
import type { SocialOpsOverview, SocialPostMetricSummary } from '../types/socialOps'
import { EmptyPane, StateBadge } from './workbench'

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
  metrics,
  summary,
  formatDateTime,
}: {
  metrics: SocialPostMetric[]
  summary: SocialPostMetricSummary | null
  formatDateTime: (value: string | null | undefined) => string
}) {
  const stats = [
    ['Impressions', summary?.total_impressions ?? 0],
    ['Likes', summary?.total_likes ?? 0],
    ['Replies', summary?.total_replies ?? 0],
    ['Reposts', summary?.total_reposts ?? 0],
    ['Link Clicks', summary?.total_link_clicks ?? 0],
  ]
  return (
    <>
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
      {metrics.length === 0 ? <EmptyPane>暂无发布效果记录。可以在 /schedules 手动 Run x_social_post_observer_sweep，或等待每小时 observer sweep；权限不足时这里会显示 diagnostic，而不会伪造数据。</EmptyPane> : null}
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
      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {metrics.map((metric) => (
          <div key={metric.id} className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Post {metric.external_post_id ?? metric.post_id ?? '-'}</div>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div><span className="text-[color:var(--ops-text-caption)]">Impressions</span><div className="font-semibold">{metric.impressions}</div></div>
              <div><span className="text-[color:var(--ops-text-caption)]">Likes</span><div className="font-semibold">{metric.likes}</div></div>
              <div><span className="text-[color:var(--ops-text-caption)]">Replies</span><div className="font-semibold">{metric.replies}</div></div>
              <div><span className="text-[color:var(--ops-text-caption)]">Clicks</span><div className="font-semibold">{metric.link_clicks}</div></div>
            </div>
            {metric.summary ? <p className="mt-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">{metric.summary}</p> : null}
          </div>
        ))}
      </div>
    </>
  )
}
