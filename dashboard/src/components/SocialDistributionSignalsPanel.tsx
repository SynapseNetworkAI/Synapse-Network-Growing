import { useEffect, useState } from 'react'
import { api, type SocialAccountSnapshotResult, type SocialWeeklyReviewResult } from '../api'
import { MetricCard, StateBadge } from './SocialDistributionWidgets'
import { SectionFrame, useToast } from './workbench'

export function DistributionSignalsMetricsPanel({ formatDateTime }: { formatDateTime: (value: string | null | undefined) => string }) {
  const toast = useToast()
  const [trends, setTrends] = useState<Array<{ id: number; topic: string; summary: string; source_url: string | null; author_handle: string | null; relevance_score: number; collected_at: string | null }>>([])
  const [summary, setSummary] = useState<{ observed_post_count: number; total_impressions: number; total_likes: number; total_replies: number; total_reposts: number; total_link_clicks: number; total_profile_visits: number; total_bookmarks: number; total_negative_feedback: number; total_subscription_conversions: number; last_observed_at: string | null; diagnostic?: string | null } | null>(null)
  const [snapshots, setSnapshots] = useState<SocialAccountSnapshotResult | null>(null)
  const [weeklyReviews, setWeeklyReviews] = useState<SocialWeeklyReviewResult | null>(null)
  const [metricForm, setMetricForm] = useState({
    external_post_id: '',
    impressions: '0',
    profile_visits: '0',
    replies: '0',
    bookmarks: '0',
    follows: '0',
    negative_feedback_count: '0',
    subscription_conversions: '0',
    format_kind: 'x_long_post',
    post_intent: 'technical_explainer',
    topic_tags: '',
    has_url: false,
    summary: '',
  })

  async function load() {
    try {
      const [trendRows, metricSummary, snapshotRows, reviewRows] = await Promise.all([
        api.getSocialTrends(),
        api.getSocialPostMetricSummary(),
        api.getSocialAccountSnapshots({ limit: 7 }),
        api.getSocialWeeklyReviews({ limit: 4 }),
      ])
      setTrends(trendRows.slice(0, 20))
      setSummary(metricSummary)
      setSnapshots(snapshotRows)
      setWeeklyReviews(reviewRows)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载 Signals & Metrics 失败')
    }
  }
  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function createManualMetric() {
    try {
      await api.createManualSocialPostMetric({
        external_post_id: metricForm.external_post_id.trim() || null,
        impressions: Number(metricForm.impressions || 0),
        profile_visits: Number(metricForm.profile_visits || 0),
        replies: Number(metricForm.replies || 0),
        bookmarks: Number(metricForm.bookmarks || 0),
        follows: Number(metricForm.follows || 0),
        negative_feedback_count: Number(metricForm.negative_feedback_count || 0),
        subscription_conversions: Number(metricForm.subscription_conversions || 0),
        format_kind: metricForm.format_kind,
        post_intent: metricForm.post_intent,
        topic_tags: metricForm.topic_tags.split(',').map((item) => item.trim()).filter(Boolean),
        has_url: metricForm.has_url,
        summary: metricForm.summary || 'Manual X metrics entry.',
      })
      setMetricForm({ ...metricForm, external_post_id: '', impressions: '0', profile_visits: '0', replies: '0', bookmarks: '0', follows: '0', negative_feedback_count: '0', subscription_conversions: '0', topic_tags: '', summary: '' })
      await load()
      toast.success('X 指标已记录')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '记录 X 指标失败')
    }
  }

  return (
    <SectionFrame eyebrow="Signals & Metrics" title="Signals & Metrics" description="这里只读本地 DB：趋势、watchlist 信号、已发布效果摘要，不在页面刷新时触发 X read。">
      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Observed posts" value={summary?.observed_post_count ?? 0} />
        <MetricCard label="Impressions" value={summary?.total_impressions ?? 0} />
        <MetricCard label="Profile visits" value={summary?.total_profile_visits ?? 0} />
        <MetricCard label="Bookmarks" value={summary?.total_bookmarks ?? 0} />
        <MetricCard label="Negative feedback" value={summary?.total_negative_feedback ?? 0} />
        <MetricCard label="Conversions" value={summary?.total_subscription_conversions ?? 0} />
        <MetricCard label="Engagement" value={(summary?.total_likes ?? 0) + (summary?.total_replies ?? 0) + (summary?.total_reposts ?? 0) + (summary?.total_bookmarks ?? 0)} />
      </div>
      <div className="mt-5 grid gap-4 xl:grid-cols-3">
        <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
          <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Post Performance</div>
          <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">
            X observer 只读官方 API；无 URL 内容的 link clicks 固定为 0，不当作失败。
          </div>
          <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">Last observed: {formatDateTime(summary?.last_observed_at)}</div>
        </div>
        <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
          <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Conversion Attribution</div>
          <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">
            Followers delta 使用账号快照弱归因；订阅/外链点击只来自 UTM 或人工记录，不强行归因给无链接回复。
          </div>
          {(snapshots?.items ?? []).slice(0, 2).map((snapshot) => (
            <div key={snapshot.id} className="mt-3 rounded-xl bg-white/[0.03] p-3 text-xs text-[color:var(--ops-text-muted)]">
              @{snapshot.account_handle} · followers {snapshot.followers} · delta {snapshot.followers_delta >= 0 ? '+' : ''}{snapshot.followers_delta} · {formatDateTime(snapshot.observed_at)}
            </div>
          ))}
        </div>
        <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
          <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Weekly Review</div>
          <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">
            周复盘只生成下一周建议，不自动改策略、不自动发布。
          </div>
          {(weeklyReviews?.items ?? []).slice(0, 1).map((review) => (
            <div key={review.id} className="mt-3 rounded-xl bg-white/[0.03] p-3 text-xs text-[color:var(--ops-text-muted)]">
              {review.summary ?? 'No summary'} · {formatDateTime(review.created_at)}
            </div>
          ))}
        </div>
      </div>
      <div className="mt-5 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-semibold text-[color:var(--ops-text-title)]">手动记录 X 曝光指标</div>
            <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">发布后从 X 页面抄 views / profile visits / replies / bookmarks / follows；这里不触发 X read。</div>
          </div>
          <button type="button" className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100" onClick={() => void createManualMetric()}>记录指标</button>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <input className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm" value={metricForm.external_post_id} onChange={(event) => setMetricForm({ ...metricForm, external_post_id: event.target.value })} placeholder="external post id" />
          <input className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm" value={metricForm.impressions} onChange={(event) => setMetricForm({ ...metricForm, impressions: event.target.value })} placeholder="views" />
          <input className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm" value={metricForm.profile_visits} onChange={(event) => setMetricForm({ ...metricForm, profile_visits: event.target.value })} placeholder="profile visits" />
          <input className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm" value={metricForm.bookmarks} onChange={(event) => setMetricForm({ ...metricForm, bookmarks: event.target.value })} placeholder="bookmarks" />
          <input className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm" value={metricForm.replies} onChange={(event) => setMetricForm({ ...metricForm, replies: event.target.value })} placeholder="replies" />
          <input className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm" value={metricForm.follows} onChange={(event) => setMetricForm({ ...metricForm, follows: event.target.value })} placeholder="follows" />
          <input className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm" value={metricForm.negative_feedback_count} onChange={(event) => setMetricForm({ ...metricForm, negative_feedback_count: event.target.value })} placeholder="negative feedback" />
          <input className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm" value={metricForm.subscription_conversions} onChange={(event) => setMetricForm({ ...metricForm, subscription_conversions: event.target.value })} placeholder="conversions" />
          <select className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm" value={metricForm.format_kind} onChange={(event) => setMetricForm({ ...metricForm, format_kind: event.target.value })}>
            <option value="x_long_post">x_long_post</option>
            <option value="single_x_post">single_x_post</option>
            <option value="x_reply">x_reply</option>
            <option value="x_quote">x_quote</option>
          </select>
          <select className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm" value={metricForm.post_intent} onChange={(event) => setMetricForm({ ...metricForm, post_intent: event.target.value })}>
            <option value="technical_explainer">technical_explainer</option>
            <option value="engagement_reply">engagement_reply</option>
            <option value="build_in_public">build_in_public</option>
            <option value="brand_positioning">brand_positioning</option>
            <option value="weekly_log">weekly_log</option>
          </select>
          <input className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm" value={metricForm.topic_tags} onChange={(event) => setMetricForm({ ...metricForm, topic_tags: event.target.value })} placeholder="topic_tags comma separated" />
          <label className="flex items-center gap-2 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm text-[color:var(--ops-text-muted)]">
            <input type="checkbox" checked={metricForm.has_url} onChange={(event) => setMetricForm({ ...metricForm, has_url: event.target.checked })} />
            has URL
          </label>
          <input className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 text-sm" value={metricForm.summary} onChange={(event) => setMetricForm({ ...metricForm, summary: event.target.value })} placeholder="note" />
        </div>
      </div>
      {summary?.diagnostic ? <div className="mt-4 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4 text-sm text-[color:var(--ops-text-muted)]">{summary.diagnostic}</div> : null}
      <div className="mt-5 space-y-3">
        {trends.map((trend) => (
          <div key={trend.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-[color:var(--ops-text-title)]">{trend.topic}</div>
                <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{trend.summary}</div>
              </div>
              <StateBadge tone={trend.source_url ? 'ready' : 'muted'}>{trend.source_url ? 'X source' : 'local seed'}</StateBadge>
            </div>
            <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">{trend.author_handle ?? '@unknown'} · score {Math.round(trend.relevance_score * 100)} · {formatDateTime(trend.collected_at)}</div>
          </div>
        ))}
      </div>
    </SectionFrame>
  )
}
